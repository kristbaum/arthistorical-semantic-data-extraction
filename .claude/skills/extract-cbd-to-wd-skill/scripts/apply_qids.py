#!/usr/bin/env python3
"""Write the QIDs of reconciled and created items back into the articles.

The cleaning step gives every {{Entität}} in an article a unique `id=`
(8 characters a-z0-9). In the claims file, each item that stands for such a
template notes it as `"ref": "<id>"`. Once the items exist — reconciled
(`"qid"` in the claims file) or created (placeholder resolved in
placeholders.tsv by `placeholders.py lookup --apply`) — this script sets
`qid=` on the matching template:

    {{Entität|Johann Adam Schöpf|rolle=Maler|id=wpeyhvwk}}
 -> {{Entität|Johann Adam Schöpf|rolle=Maler|qid=Q1234567|id=wpeyhvwk}}

Subcommands
-----------
  write --out data/wikidata/Band01 --articles data/cleaned-with-skill-v2/Band01 [--lemma L] [--apply]
      Resolve every ref to a QID and set it in the article. Dry run unless
      --apply. Reports refs still waiting for their item (placeholder without
      QID), refs not found in the article, and CONFLICTs (template already has
      a different qid — never overwritten).
  link  --out data/wikidata/Band01 --articles data/cleaned-with-skill-v2/Band01 [--apply]
      For claims files written before refs existed: suggest a ref for each
      item without one, by matching it to the article's {{Entität}}
      templates — main item -> rolle=Bauwerk; `field` -> the Deckenbild with
      that identifier; persons -> by surname (from `named_as` / label);
      rooms and paintings without field -> by label/titel. Ambiguous or
      unmatched items are listed, never guessed. --apply writes the refs into
      the claims files.

Afterwards re-upload the articles (src/mediawiki/upload_pages.py).
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

ENTITY_RE = re.compile(
    r"\{\{Entität\|(?:1=)?((?:[^{}]|\{\{[^{}]*\}\})*?)((?:\|(?:rolle|titel|bild|qid|id)=[^|{}]*)*)\}\}")
PARAM_RE = re.compile(r"\|(rolle|titel|bild|qid|id)=([^|{}]*)")
ABK_RE = re.compile(r"\{\{Abk\|([^|}]*)(?:\|([^|}]*))?[^}]*\}\}")
QID_RE = re.compile(r"^Q\d+$")
# room words of the articles -> the label used for room items
ROOM_SYNONYMS = {"lhs": "langhaus", "ar": "altarraum", "chor": "altarraum", "saal": "langhaus",
                 "gemeinderaum": "langhaus", "msch": "mittelschiff", "ssch": "seitenschiff",
                 "qsch": "querschiff", "qhs": "querhaus"}
PERSON_ROLES = {"Auftraggeber", "Maler", "Stuckateur", "Baumeister", "Stecher", "Kistler", "Vergolder", "Person"}


def slugify(s: str) -> str:  # same as build.py
    s = s.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(s: str) -> str:
    s = re.sub(r"</?sub>", "", ABK_RE.sub(lambda m: m.group(2) or m.group(1), s))
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^\w]+", " ", s).strip()


def entities(wiki: str) -> list[dict]:
    out = []
    for m in ENTITY_RE.finditer(wiki):
        e = {"text": m.group(1), **dict(PARAM_RE.findall(m.group(2)))}
        out.append(e)
    return out


def placeholder(lemma: str, key: str, kind: str) -> str:  # same as build.py expand()
    return f"{{NEW:{'painting' if kind in ('ceiling', 'wall') else kind}:{slugify(lemma)}-{slugify(key)}}}"


def load_created(out: Path) -> dict[str, str]:
    path = out / "placeholders.tsv"
    if not path.exists():
        return {}
    return {r["placeholder"]: (r.get("qid") or "").strip()
            for r in csv.DictReader(path.open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)}


def dump_claims(spec: dict) -> str:
    """The claims-file layout: one line per item and per claim."""
    one = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    parts = []
    for k, v in spec.items():
        if isinstance(v, dict) and v:
            body = ",\n".join(f"    {one(ik)}: {one(iv)}" for ik, iv in v.items())
            parts.append(f"  {one(k)}: {{\n{body}\n  }}")
        elif isinstance(v, list) and v:
            body = ",\n".join(f"    {one(x)}" for x in v)
            parts.append(f"  {one(k)}: [\n{body}\n  ]")
        else:
            parts.append(f"  {one(k)}: {one(v)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def claims_files(out: Path):
    for p in sorted((out / "claims").glob("*.json")):
        yield p, json.loads(p.read_text(encoding="utf-8"))


# ----------------------------------------------------------------- write
def cmd_write(a) -> int:
    created = load_created(a.out)
    stats = {"set": 0, "already": 0, "waiting": 0, "missing": 0, "conflict": 0}
    for _p, spec in claims_files(a.out):
        lemma = spec["lemma"]
        if a.lemma and lemma != a.lemma:
            continue
        art = a.articles / f"{lemma}.wiki"
        if not art.exists():
            print(f"  NOARTICLE {lemma}")
            continue
        wiki = art.read_text(encoding="utf-8")
        target: dict[str, str] = {}
        for key, it in spec["items"].items():
            ref = it.get("ref")
            if not ref:
                continue
            qid = it.get("qid") or created.get(placeholder(lemma, key, it.get("new", "")), "")
            if QID_RE.match(qid or ""):
                target[ref] = qid
            else:
                stats["waiting"] += 1
                print(f"  WAITING  {lemma} / {key} ({ref}): item not created yet")

        found = set()

        def setq(m: re.Match) -> str:
            params = dict(PARAM_RE.findall(m.group(2)))
            ref = params.get("id")
            if ref not in target:
                return m.group(0)
            found.add(ref)
            have = params.get("qid", "").strip()
            if have == target[ref]:
                stats["already"] += 1
                return m.group(0)
            if have:
                stats["conflict"] += 1
                print(f"  CONFLICT {lemma} ({ref}): article has {have}, claims say {target[ref]} — not changed")
                return m.group(0)
            stats["set"] += 1
            print(f"  SET      {lemma} ({ref}): {m.group(1)[:40]} -> {target[ref]}")
            return m.group(0).replace(f"|id={ref}", f"|qid={target[ref]}|id={ref}", 1)

        new = ENTITY_RE.sub(setq, wiki)
        for ref in sorted(set(target) - found):
            stats["missing"] += 1
            print(f"  MISSING  {lemma} ({ref}): no {{{{Entität}}}} with this id in the article")
        if a.apply and new != wiki:
            art.write_text(new, encoding="utf-8")
    print(("Written: " if a.apply else "Dry run: ") + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 1 if stats["conflict"] else 0


# ------------------------------------------------------------------ link
def item_names(spec: dict, key: str, it: dict) -> list[str]:
    names = [it.get("label", "")]
    for c in spec.get("claims", []):
        if c.get("v") == key and c.get("named_as"):
            names.append(c["named_as"])
    names.append(key)
    return [n for n in names if n]


def match(spec: dict, key: str, it: dict, ents: list[dict]) -> list[dict]:
    if it.get("main"):
        return [e for e in ents if e.get("rolle") == "Bauwerk"]
    if it.get("field"):
        return [e for e in ents if e.get("rolle") == "Deckenbild"
                and norm(e["text"]).replace(" ", "") == it["field"].lower()]
    kind = it.get("new")
    if kind in ("ceiling", "wall") or it.get("painting"):
        lab = norm(it.get("label", ""))
        by_label = [e for e in ents if e.get("rolle") == "Deckenbild" and lab
                    and lab in (norm(e.get("titel", "")), norm(e["text"]))]
        # existing painting items carry no field: a key like "b" or "eb1" names the identifier
        by_key = [e for e in ents if e.get("rolle") == "Deckenbild"
                  and norm(e["text"]).replace(" ", "") == key.lower()]
        return by_label or by_key
    if kind == "room":
        lab = norm(it.get("label", ""))

        def room(e):
            w = norm(e["text"])
            w = ROOM_SYNONYMS.get(w, w)
            return w == lab or w.endswith(lab)  # »Doppelempore« -> Empore

        return [e for e in ents if e.get("rolle") == "Raum" and lab and room(e)]
    if kind in ("building",):
        return []
    # person (existing items carry no kind): surname of a known name in the marked text
    surnames = {norm(n).split()[-1] for n in item_names(spec, key, it) if norm(n)}
    # prefix: the printed form may be inflected (»Johann Baptist Anwanders«)
    return [e for e in ents if e.get("rolle") in PERSON_ROLES
            and any(w.startswith(s) for s in surnames for w in norm(e["text"]).split()
                    if len(s) > 2 and len(w) - len(s) <= 2)]


def cmd_link(a) -> int:
    n_new = n_open = 0
    for path, spec in claims_files(a.out):
        if a.lemma and spec["lemma"] != a.lemma:
            continue
        art = a.articles / f"{spec['lemma']}.wiki"
        if not art.exists():
            print(f"  NOARTICLE {spec['lemma']}")
            continue
        ents = entities(art.read_text(encoding="utf-8"))
        used = {it["ref"] for it in spec["items"].values() if it.get("ref")}
        changed = False
        for key, it in spec["items"].items():
            if it.get("ref"):
                continue
            cands = [e for e in match(spec, key, it, ents) if e.get("id") and e["id"] not in used]
            if len(cands) == 1:
                it["ref"] = cands[0]["id"]
                used.add(it["ref"])
                changed = True
                n_new += 1
                print(f"  LINK  {spec['lemma'][:40]} / {key} -> {it['ref']} ({cands[0]['text'][:30]}, {cands[0].get('rolle')})")
            else:
                n_open += 1
                what = "ambiguous: " + ", ".join(f"{e['id']} {e['text'][:20]}" for e in cands) if cands else "no match"
                print(f"  OPEN  {spec['lemma'][:40]} / {key}: {what}")
        if a.apply and changed:
            path.write_text(dump_claims(spec), encoding="utf-8")
    print(f"{'Written' if a.apply else 'Dry run'}: {n_new} refs linked, {n_open} items open")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("write", "link"):
        s = sub.add_parser(name)
        s.add_argument("--out", required=True, type=Path, help="data/wikidata/{Band}")
        s.add_argument("--articles", required=True, type=Path, help="folder with the cleaned {Lemma}.wiki files")
        s.add_argument("--apply", action="store_true")
        s.add_argument("--lemma", help="only this article (exact lemma)")
    a = ap.parse_args()
    return cmd_write(a) if a.cmd == "write" else cmd_link(a)


if __name__ == "__main__":
    sys.exit(main())
