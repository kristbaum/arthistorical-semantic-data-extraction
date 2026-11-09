#!/usr/bin/env python3
"""Interactively upload Lua modules, templates and articles to the Deckenmalerei-Lab.

Logs in with a normal user account via ``action=clientlogin`` (no bot
password); username and password are asked for in the terminal.

What gets uploaded (in this order, so dependencies exist first):

  templates/Modul-Abk-Daten.lua   -> Modul:Abk/Daten
  templates/Modul-Abk.lua         -> Modul:Abk
  templates/<Name>-styles.css     -> Vorlage:<Name>/styles.css  (TemplateStyles)
  templates/<Name>.template       -> Vorlage:<Name>
  <articles-dir>/*.wiki           -> page title from |Lemma=

Module filenames map ``Modul-A-B.lua`` -> ``Modul:A/B``. Modules live in the
Module namespace (``Modul:``, ns 828), templates in the Template namespace
(``Vorlage:``, ns 10).

Every page is compared with the live version first; unchanged pages are
skipped. The plan is shown and must be confirmed before anything is written.

Usage
-----
    uv run python -m src.mediawiki.upload_pages
    uv run python -m src.mediawiki.upload_pages --articles data/cleaned-with-skill-v2/Band01
    uv run python -m src.mediawiki.upload_pages --no-templates --no-modules
"""

import argparse
import difflib
import getpass
import re
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
DEFAULT_ARTICLES = REPO_ROOT / "data" / "cleaned-with-skill-v2" / "Band01"
DEFAULT_API = "https://deckenmalerei-lab.badw.de/api.php"

_LEMMA_RE = re.compile(r"^\s*\|Lemma=(.*)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Collect local pages
# ---------------------------------------------------------------------------


def module_title(path: Path) -> str:
    # Modul-Abk-Daten.lua -> Modul:Abk/Daten
    parts = path.stem.split("-")
    assert parts[0] == "Modul", path
    return "Modul:" + "/".join(parts[1:])


def collect(args) -> list[tuple[str, str, Path]]:
    pages: list[tuple[str, str, Path]] = []
    if args.modules:
        mods = sorted(TEMPLATES_DIR.glob("Modul-*.lua"))
        # data modules (deeper subpages) first, so the main module can load them
        mods.sort(key=lambda p: -p.stem.count("-"))
        for p in mods:
            pages.append((module_title(p), p.read_text(encoding="utf-8"), p))
    if args.templates:
        for p in sorted(TEMPLATES_DIR.glob("*.css")):
            # Entität-styles.css -> Vorlage:Entität/styles.css
            title = "Vorlage:" + p.stem.replace("-", "/", 1) + ".css"
            pages.append((title, p.read_text(encoding="utf-8"), p))
        for p in sorted(TEMPLATES_DIR.glob("*.template")):
            pages.append((f"Vorlage:{p.stem}", p.read_text(encoding="utf-8"), p))
    if args.articles:
        for p in sorted(Path(args.articles).glob("*.wiki")):
            text = p.read_text(encoding="utf-8")
            m = _LEMMA_RE.search(text)
            if not m or not m.group(1).strip():
                print(f"  ! no |Lemma= in {p.name}, skipped", file=sys.stderr)
                continue
            pages.append((m.group(1).strip(), text, p))
    return pages


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class Wiki:
    def __init__(self, api: str):
        self.api = api
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "cbdd-upload-pages/1.0 (interactive)"

    def get(self, **params):
        params.update(format="json", formatversion="2")
        r = self.s.get(self.api, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def post(self, **data):
        data.update(format="json", formatversion="2")
        r = self.s.post(self.api, data=data, timeout=120)
        r.raise_for_status()
        return r.json()

    def login(self, user: str, password: str) -> str:
        token = self.get(action="query", meta="tokens", type="login")["query"][
            "tokens"]["logintoken"]
        res = self.post(
            action="clientlogin", username=user, password=password,
            loginreturnurl="https://example.org/", logintoken=token,
        )["clientlogin"]
        while res["status"] == "UI":  # e.g. 2FA
            print(res.get("message", "Additional input required."))
            extra = {}
            for req in res.get("requests", []):
                for field, spec in req.get("fields", {}).items():
                    prompt = f"  {spec.get('label', field)}: "
                    extra[field] = (getpass.getpass(prompt)
                                    if spec.get("sensitive") else input(prompt))
            res = self.post(action="clientlogin", logincontinue="1",
                            logintoken=token, **extra)["clientlogin"]
        if res["status"] != "PASS":
            raise SystemExit(f"Login failed: {res.get('message', res)}")
        return res["username"]

    def current(self, titles: list[str]) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for i in range(0, len(titles), 50):
            q = self.get(action="query", prop="revisions", rvprop="content",
                         rvslots="main", titles="|".join(titles[i:i + 50]))
            norm = {n["from"]: n["to"] for n in q["query"].get("normalized", [])}
            by_title = {}
            for pg in q["query"]["pages"]:
                if pg.get("missing"):
                    by_title[pg["title"]] = None
                else:
                    by_title[pg["title"]] = pg["revisions"][0]["slots"]["main"]["content"]
            for t in titles[i:i + 50]:
                out[t] = by_title.get(norm.get(t, t))
        return out

    def edit(self, title: str, text: str, summary: str) -> dict:
        token = self.get(action="query", meta="tokens")["query"]["tokens"]["csrftoken"]
        extra = {"contentmodel": "sanitized-css"} if title.endswith(".css") else {}
        res = self.post(action="edit", title=title, text=text, summary=summary,
                        token=token, **extra)
        if "error" in res:
            raise RuntimeError(res["error"].get("info", res["error"]))
        return res["edit"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--articles", default=str(DEFAULT_ARTICLES),
                    help="Folder with article .wiki files ('' to skip).")
    ap.add_argument("--no-modules", dest="modules", action="store_false")
    ap.add_argument("--no-templates", dest="templates", action="store_false")
    ap.add_argument("--summary", default="Upload from arthistorical-semantic-data-extraction")
    args = ap.parse_args(argv)

    pages = collect(args)
    if not pages:
        raise SystemExit("Nothing to upload.")

    wiki = Wiki(args.api)
    print(f"Wiki: {args.api}")
    user = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    name = wiki.login(user, password)
    del password
    print(f"Logged in as {name}.\n")

    live = wiki.current([t for t, _, _ in pages])
    todo = []
    for title, text, path in pages:
        old = live.get(title)
        if old is None:
            state = "NEW"
        elif old.rstrip() == text.rstrip():
            state = "same"
        else:
            state = "CHANGED"
        print(f"  [{state:7}] {title}   <- {path.relative_to(REPO_ROOT)}")
        if state != "same":
            todo.append((title, text, old))

    if not todo:
        print("\nEverything is up to date.")
        return

    print(f"\n{len(todo)} page(s) to write.")
    mode = ask("Write all [a], confirm each page [e], or quit [q]? ")
    if mode not in ("a", "e"):
        print("Aborted, nothing written.")
        return

    done = failed = 0
    for title, text, old in todo:
        if mode == "e":
            while True:
                c = ask(f"\n{title}: write [y], skip [n], show diff [d], quit [q]? ")
                if c == "d":
                    diff = difflib.unified_diff(
                        (old or "").splitlines(), text.splitlines(),
                        "live", "local", lineterm="", n=1)
                    print("\n".join(diff) or "(new page)")
                    continue
                break
            if c == "q":
                break
            if c != "y":
                continue
        verb = "Create" if old is None else "Update"
        try:
            res = wiki.edit(title, text, f"{verb}: {args.summary}")
            print(f"  {res.get('result')}: {title} (rev {res.get('newrevid', '-')})")
            done += 1
        except Exception as exc:
            print(f"  ERROR: {title} — {exc}", file=sys.stderr)
            failed += 1

    print(f"\nWritten: {done}, errors: {failed}.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
