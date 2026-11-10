#!/usr/bin/env python3
"""Apply Como game decisions to the claims that follow them.

build.py puts one representative of each identical claim (same passage,
property and value for several fields of one article) into a game; the
others are listed in followers.tsv. Como writes the representative itself.
This script reads the game results export ("Download CSV" on the game page,
or GET /api/games/<slug>/download/, unzipped) and writes the same decision
for every follower to followers.qs, with the qualifier the players chose.

Usage:
  apply_results.py --out data/wikidata/Band01 export-wer-hat-das-gemalt.csv [more exports …]

Prompts that are not done, disputed, answered "No" or "none of these" are
skipped and counted.

Exports of the reconciliation game "Wer ist gemeint?" (var_claim = a {REC:…}
placeholder) set the chosen candidate's QID in reconcile.tsv; "Kein passender
Eintrag" or "none of these" sets "none" (create the item, then put its QID
there). A qid already in reconcile.tsv is never overwritten. Rerun build.py
afterwards: the pending statements on that entity are routed normally.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# option number -> qualifier pairs, mirroring the trigger_option templates in build.py
CHOICE_QUALIFIERS = {
    "maler": {"1": [], "2": [("P5102", "Q230768")], "3": [("P1480", "Q18122778")], "4": [("P1480", "Q56644435")]},
    "datierung": {"1": [], "2": [("P1480", "Q5727902")], "3": [("P1480", "Q18122778")]},
}


def apply_reconciliation(out: Path, decisions: dict[str, dict]) -> None:
    path = out / "reconcile.tsv"
    if not path.exists() or not any(k.startswith("{REC:") for k in decisions):
        return
    with path.open(encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        cols, rows = rd.fieldnames, list(rd)
    stats = Counter()
    for r in rows:
        d = decisions.get(r["placeholder"])
        if not d:
            continue
        if r["qid"].strip():
            stats["already set"] += 1
            continue
        if d.get("done") != "True" or d.get("note"):
            stats["open or disputed"] += 1
            continue
        cands = [c for c in r["candidates"].split(",") if c][:4]
        choice = (d.get("selected_choice") or "").strip()
        n = int(choice) if choice.isdigit() else 0
        r["qid"] = cands[n - 1] if 1 <= n <= len(cands) else "none"
        stats["matched" if r["qid"] != "none" else "none"] += 1
        print(f"  {r['lemma']} / {r['label']}: {r['qid']}")
    with path.open("w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(r[c] for c in cols) + "\n")
    print(f"reconcile.tsv: {dict(stats)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("exports", nargs="+", type=Path)
    a = ap.parse_args()

    decisions: dict[str, dict] = {}
    for path in a.exports:
        for row in csv.DictReader(path.open(encoding="utf-8")):
            if row.get("var_claim"):
                decisions[row["var_claim"]] = row
    apply_reconciliation(a.out, decisions)
    if not (a.out / "followers.tsv").exists():
        return 0
    lines, stats = [], Counter()
    for f in csv.DictReader((a.out / "followers.tsv").open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
        d = decisions.get(f["rep_id"])
        if not d:
            stats["no result yet"] += 1
            continue
        if d.get("done") != "True" or d.get("note"):
            stats["open or disputed"] += 1
            continue
        if f["game"] in CHOICE_QUALIFIERS:
            choice = d.get("selected_choice") or ""
            if choice not in CHOICE_QUALIFIERS[f["game"]]:
                stats["rejected"] += 1
                continue
            quals = CHOICE_QUALIFIERS[f["game"]][choice]
        else:
            if d.get("yns") != "True":
                stats["rejected"] += 1
                continue
            quals = []
        parts = [f["entity"], f["property"], f["value"]]
        for p, v in quals:
            parts += [p, v]
        if f["named_as"]:
            parts += ["P1932", f'"{f["named_as"]}"']
        parts += ["S248", f["volume"], "S304", f'"{f["pages"]}"']
        lines.append("\t".join(parts) + f"\t/* follows {f['rep_id']} */")
        stats["written"] += 1
    (a.out / "followers.qs").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"followers.qs: {dict(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
