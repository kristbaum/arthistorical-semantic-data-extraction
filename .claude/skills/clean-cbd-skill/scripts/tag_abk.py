#!/usr/bin/env python3
"""Wrap abbreviations from the CBD glossary in {{Abk|…}} (rule 3.12).

Keys and context rules come from templates/Modul-Abk-Daten.lua (the static
copy of Modul:Abk/Daten, taken from [[Zur Benutzung]]). Every occurrence in
the main text is tagged.

Never tagged: »quotations« / ›…‹, the == Quellen und Literatur == /
== Literatur == section, == headings ==, [[links]], {{templates}} (so text
already inside {{Abk|…}} is left alone), <gallery>, '''bold titles and
labels''', <sub>/<sup>, comments; keys with kontext "manuell" (S, W, O, x).
Context rules: "vor_zahl" keys only before a number, "nach_zahl" only after
one, "kapitel" (Bible books) only before chapter,verse or a chapter closed by
) or ; — so »Rom 410 durch« and »Am 3.3.1687« stay plain but »Rom 12,5« and
»(Ps 50)« are tagged.

Idempotent. Prints one SUSPECT line per tag of an ambiguous key (Bible books
that are also German words or names, compass and region codes)
for the model to confirm or unwrap.

Usage:
    python .claude/skills/clean-cbd-skill/scripts/tag_abk.py FILE.wiki [...] [--apply]
"""

import re
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA = REPO_ROOT / "templates" / "Modul-Abk-Daten.lua"

_ENTRY_RE = re.compile(
    r'^\t\t\["((?:[^"\\]|\\.)*)"\] = \{ voll = .*?typ = "(\w+)"(?:, kontext = "(\w+)")? \},$', re.M)

# spans that are never tagged
_PROTECTED_RE = re.compile(
    r"^==+\s*(?:Quellen|Literatur)[^\n]*\n.*?(?=^==[^=]|\Z)"  # bibliography section
    r"|\{\{.*?\}\}"                # templates, incl. existing {{Abk|…}}
    r"|\[\[.*?\]\]"                # links and files
    r"|<gallery\b.*?</gallery>"
    r"|<!--.*?-->"
    r"|<sub>.*?</sub>|<sup>.*?</sup>"
    r"|»[^«]*«|›[^‹]*‹"            # quotations
    r"|'''.*?'''"                  # bold entry titles and labels
    r"|^=+.*?=+[ \t]*$",           # headings
    re.S | re.M,
)
_LETTER = "A-Za-zÄÖÜäöüß"

# ambiguous in running German: report every tag of these for review
_SUSPECT = {
    "Am", "Is", "Os", "Dan", "Bar", "Mal", "Rom", "Gen", "Ion", "Tit", "Act",
    "Ex", "Num", "Iob", "Ruth", "Tob", "Nah", "Mich", "Hab", "Lam", "Io",
    "AR", "AT", "NT", "NO", "SO", "NW", "SW", "OB", "NB", "MFr", "Schw",
}


@lru_cache(maxsize=1)
def load_keys() -> tuple[re.Pattern, dict[str, str]]:
    text = DATA.read_text(encoding="utf-8")
    abk_part = text.split("\tbildfeld = {")[0]
    kontext: dict[str, str] = {}
    for key, _typ, ctx in _ENTRY_RE.findall(abk_part):
        key = key.replace('\\"', '"')
        if ctx != "manuell":
            kontext[key] = ctx or ""
    alts = "|".join(re.escape(k) for k in sorted(kontext, key=len, reverse=True))
    return re.compile(rf"(?<![{_LETTER}\d.])(?:{alts})"), kontext


def _context_ok(key: str, ctx: str, text: str, start: int, end: int) -> bool:
    after, before = text[end:end + 16], text[max(0, start - 8):start]
    if key[-1] != "." and re.match(rf"[{_LETTER}\d]", after):
        return False  # "AR" in "ARt"
    if ctx == "vor_zahl":
        return bool(re.match(r"\s?\d", after))
    if ctx == "nach_zahl":
        return bool(re.search(r"\d\s?$", before))
    if ctx == "kapitel":
        return bool(re.match(r"\s\d{1,3}(?:,\s?\d|\s?[);\]])", after))
    return True


def tag_body(body: str) -> tuple[str, list[str]]:
    """Return (tagged body, SUSPECT lines)."""
    pattern, kontext = load_keys()
    protected = [m.span() for m in _PROTECTED_RE.finditer(body)]
    out, suspects, pos = [], [], 0
    for m in pattern.finditer(body):
        key = m.group(0)
        s, e = m.span()
        if any(a <= s < b for a, b in protected):
            continue
        if not _context_ok(key, kontext[key], body, s, e):
            continue
        out.append(body[pos:s])
        out.append(f"{{{{Abk|{key}}}}}")
        pos = e
        if key in _SUSPECT:
            ctx = (body[max(0, s - 35):s] + "⟦" + key + "⟧" + body[e:e + 25]).replace("\n", " ")
            suspects.append(f"SUSPECT {key}: …{ctx}…")
    out.append(body[pos:])
    return "".join(out), suspects


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--apply"]
    if not args:
        sys.exit(__doc__)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from articles.helpers import parse_article_file

    for arg in args:
        path = Path(arg)
        text = path.read_text(encoding="utf-8")
        tpl, _f, body = parse_article_file(text)
        new_body, suspects = tag_body(body)
        n = new_body.count("{{Abk|") - body.count("{{Abk|")
        print(f"[{n} tagged, {len(suspects)} suspect] {path}")
        for line in suspects:
            print("  " + line)
        if "--apply" in sys.argv and n:
            path.write_text(tpl.rstrip("\n") + "\n\n" + new_body.strip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
