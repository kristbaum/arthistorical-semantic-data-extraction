#!/usr/bin/env python3
"""Write the QIDs of matched, reconciled and created items back into the articles.

The cleaning step gives every {{Entität}} in an article a unique `id=`
(8 characters a-z0-9). make_bundle.py lists which bundle entity each one
stands for in refs.tsv (next to bundle.json).
An entity's QID is known when it is a `match` in the bundle, or when the
claim-bundle pipeline stored it in the state file (`ids`: created by a
QuickStatements batch, matched in a reconciliation game, decided by hand).
This script then sets `qid=` on the template:

    {{Entität|Johann Adam Schöpf|rolle=Maler|id=wpeyhvwk}}
 -> {{Entität|Johann Adam Schöpf|rolle=Maler|qid=Q1234567|id=wpeyhvwk}}

Usage:
  apply_qids.py --bundle data/claim-bundles/Band01/bundle.json \
                --articles data/cleaned-with-skill-v2/Band01 [--apply]

Dry run unless --apply. Reports refs still waiting for their item, refs not
found in the article, and CONFLICTs (the template already has a different
qid; never overwritten). Afterwards re-upload the articles
(src/mediawiki/upload_pages.py).
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ENTITY_RE = re.compile(
    r"\{\{Entität\|(?:1=)?((?:[^{}]|\{\{[^{}]*\}\})*?)((?:\|(?:rolle|titel|bild|qid|id)=[^|{}]*)*)\}\}")
PARAM_RE = re.compile(r"\|(rolle|titel|bild|qid|id)=([^|{}]*)")
QID_RE = re.compile(r"^Q\d+$")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--state", type=Path, help="default: <bundle>.state.json")
    ap.add_argument("--articles", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    bundle = json.loads(a.bundle.read_text(encoding="utf-8"))
    state_path = a.state or a.bundle.with_suffix(".state.json")
    ids = json.loads(state_path.read_text(encoding="utf-8")).get("ids", {}) if state_path.exists() else {}
    # lemma -> ref -> (entity id, qid or None)
    targets: dict[str, dict[str, tuple[str, str | None]]] = defaultdict(dict)
    refs_path = a.bundle.parent / "refs.tsv"
    for r in csv.DictReader(refs_path.open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
        e = bundle["entities"].get(r["entity"], {})
        qid = e.get("qid") if e.get("status") == "match" else ids.get(r["entity"])
        targets[r["lemma"]][r["ref"]] = (r["entity"], qid if QID_RE.match(qid or "") else None)

    stats = {"set": 0, "already": 0, "waiting": 0, "missing": 0, "conflict": 0}
    for lemma, refs in sorted(targets.items()):
        path = a.articles / f"{lemma}.wiki"
        if not path.exists():
            print(f"  NOARTICLE {lemma}")
            continue
        wiki = path.read_text(encoding="utf-8")
        found = set()

        def setq(m: re.Match) -> str:
            params = dict(PARAM_RE.findall(m.group(2)))
            ref = params.get("id")
            if ref not in refs:
                return m.group(0)
            found.add(ref)
            eid, qid = refs[ref]
            if not qid:
                stats["waiting"] += 1
                print(f"  WAITING  {lemma} ({ref}) {eid}: no QID yet")
                return m.group(0)
            have = params.get("qid", "").strip()
            if have == qid:
                stats["already"] += 1
                return m.group(0)
            if have:
                stats["conflict"] += 1
                print(f"  CONFLICT {lemma} ({ref}): article has {have}, bundle/state say {qid}; not changed")
                return m.group(0)
            stats["set"] += 1
            print(f"  SET      {lemma} ({ref}): {m.group(1)[:40]} -> {qid}")
            return m.group(0).replace(f"|id={ref}", f"|qid={qid}|id={ref}", 1)

        new = ENTITY_RE.sub(setq, wiki)
        for ref in sorted(set(refs) - found):
            stats["missing"] += 1
            print(f"  MISSING  {lemma} ({ref}): no {{{{Entität}}}} with this id in the article")
        if a.apply and new != wiki:
            path.write_text(new, encoding="utf-8")
    print(("Written: " if a.apply else "Dry run: ") + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 1 if stats["conflict"] else 0


if __name__ == "__main__":
    sys.exit(main())
