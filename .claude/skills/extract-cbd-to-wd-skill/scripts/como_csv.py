#!/usr/bin/env python3
"""Build a Como game CSV from the extraction batches + their text contexts.

Every statement in create.qs / statements.qs that has a row in context.tsv
becomes one Como prompt: players see the item, the statement in words, and the
passage of the corpus it was taken from, and answer Yes/No ("does the passage
support the statement?"). The Yes-confirmed rows (custom_value1 = the exact QS
line) can then be filtered back into the batch.

context.tsv (TAB-separated, header row), one row per extracted statement:

    entity  property  value  lemma  pages  quote

  entity    QID or {NEW:…} placeholder exactly as in the batch
  property  P-id
  value     the value field exactly as in the QS line (Q1692498, "73C464",
            +1795-00-00T00:00:00Z/9, 1.00U11573, la:"…")
  lemma     article lemma;  pages  printed pages ("19-21")
  quote     the passage from the article text the statement rests on, verbatim
            (one or two sentences; markup removed)

Usage:
  como_csv.py --context context.tsv --map placeholders.tsv \
              -o como.csv create.qs statements.qs [--no-fetch]

Labels for Q/P ids come from the Wikidata API (German, fallback English);
--no-fetch prints the bare ids. Placeholders with a qid in placeholders.tsv
are replaced by it; unresolved ones are shown with their German label.
Reports QS statements without context (except structural properties, which
are not text claims) and context rows that match no statement.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PH_RE = re.compile(r"\{NEW:(?:person|building|room|painting|other):[a-z0-9][a-z0-9-]*\}")
COMMENT_RE = re.compile(r"\s*/\*(.*?)\*/\s*$")
ID_RE = re.compile(r"^[QP]\d+$")
API = "https://www.wikidata.org/w/api.php"
UA = "cbdd-extract-como/1.0 (Wikidata batch helper)"
# derived / bookkeeping statements: no text claim behind them, not played
STRUCTURAL = {"P1343", "P527", "P155", "P156", "P1639", "P31"}
COMO_FIELDS = [
    "custom_id", "custom_value1", "custom_value2",
    "text1", "text1_link", "text2", "text3",
]
GAME = {
    "language": "de",
    "prompt_type": "TTT",
    "prompt_labels_list": ["Objekt", "Aussage", "Textstelle"],
    "response_type": "YN",
    "confidence_type": "D",
    "question_template": "Wird die Aussage durch die Textstelle aus dem Corpus der barocken Deckenmalerei belegt?",
}


def parse_batches(paths: list[str]) -> list[dict]:
    """QS lines → {entity, property, value, quals, line}. LAST resolves to the
    placeholder named in the comment of its CREATE block's label line."""
    out = []
    for p in paths:
        current = None
        for raw in Path(p).read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            m = COMMENT_RE.search(raw)
            comment = m.group(1) if m else ""
            line = COMMENT_RE.sub("", raw)
            f = line.split("\t")
            if f[0].strip() == "CREATE":
                current = None
                continue
            ph = PH_RE.search(comment)
            if f[0] == "LAST" and ph:
                current = ph.group(0)
            entity = current if f[0] == "LAST" else f[0]
            if len(f) < 3 or not re.match(r"^P\d+$", f[1]):
                continue  # terms, sitelinks, special commands
            quals, i = [], 3
            if i < len(f) and re.match(r"^R[+0-]$", f[i]):
                i += 1
            while i + 1 < len(f) and re.match(r"^P\d+$", f[i]):
                quals.append((f[i], f[i + 1]))
                i += 2
            qs_line = line if f[0] != "LAST" else "\t".join([entity or "LAST", *f[1:]])
            out.append({"entity": entity, "property": f[1], "value": f[2], "quals": quals, "line": qs_line})
    return out


def fetch_labels(ids: set[str]) -> dict[str, tuple[str, str]]:
    res: dict[str, tuple[str, str]] = {}
    ids_l = sorted(ids)
    for i in range(0, len(ids_l), 50):
        q = {"action": "wbgetentities", "ids": "|".join(ids_l[i:i + 50]), "props": "labels|descriptions",
             "languages": "de|en", "format": "json"}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            ents = json.load(r).get("entities", {})
        for k, e in ents.items():
            lab = e.get("labels", {})
            des = e.get("descriptions", {})
            res[k] = ((lab.get("de") or lab.get("en") or {}).get("value", k),
                      (des.get("de") or des.get("en") or {}).get("value", ""))
        time.sleep(0.2)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", required=True)
    ap.add_argument("--map", help="placeholders.tsv")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("batches", nargs="+")
    a = ap.parse_args()

    phmap = {}
    if a.map and Path(a.map).exists():
        for r in csv.DictReader(Path(a.map).open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            phmap[r["placeholder"]] = r
    ctx = {}
    for r in csv.DictReader(Path(a.context).open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
        ctx[(r["entity"].strip(), r["property"].strip(), r["value"].strip())] = r
    stmts = parse_batches(a.batches)

    ids = set()
    for s in stmts:
        for tok in [s["entity"], s["property"], s["value"], *[x for q in s["quals"] for x in q]]:
            if tok and ID_RE.match(tok):
                ids.add(tok)
            m = re.search(r"U(\d+)$", tok or "")
            if m:
                ids.add("Q" + m.group(1))
    labels = {} if a.no_fetch else fetch_labels(ids)

    def resolve(tok: str) -> str:
        if PH_RE.fullmatch(tok or ""):
            q = (phmap.get(tok) or {}).get("qid", "").strip()
            return q if ID_RE.match(q) else tok
        return tok

    def lab(tok: str) -> str:
        tok = resolve(tok)
        if PH_RE.fullmatch(tok):
            return f"{(phmap.get(tok) or {}).get('label_de') or tok} (neu)"
        if ID_RE.match(tok):
            return labels.get(tok, (tok, ""))[0]
        return tok

    def val(v: str) -> str:
        v = resolve(v)
        if v == "somevalue":
            return "unbekannt"
        if v == "novalue":
            return "keiner"
        m = re.match(r"^\+(\d+)-(\d\d)-(\d\d)T00:00:00Z/(\d+)$", v)
        if m:
            y, mo, d, p = int(m[1]), m[2], m[3], int(m[4])
            return {7: f"{(y - 1) // 100 + 1}. Jh.", 8: f"{y // 10 * 10}er", 9: str(y),
                    10: f"{mo}/{y}", 11: f"{d}.{mo}.{y}"}.get(p, v)
        m = re.match(r"^([+-]?[\d.]+)(?:~[\d.]+)?(?:U(\d+))?$", v)
        if m:
            return f"{m[1].replace('.', ',')} {lab('Q' + m[2]) if m[2] else ''}".strip()
        m = re.match(r'^([a-z-]+):"(.*)"$', v)
        if m:
            return f"»{m[2]}« ({m[1]})"
        if v.startswith('"') and v.endswith('"'):
            return v[1:-1]
        return lab(v)

    rows, missing, used = [], [], set()
    for s in stmts:
        key = (s["entity"], s["property"], s["value"])
        c = ctx.get(key)
        if not c:
            if s["property"] not in STRUCTURAL:
                missing.append(s["line"])
            continue
        used.add(key)
        ent = resolve(s["entity"])
        if ID_RE.match(ent):
            t1 = labels.get(ent, (ent, ""))[0]
            desc = labels.get(ent, ("", ""))[1]
            link = f"https://www.wikidata.org/wiki/{ent}"
        else:
            r = phmap.get(ent) or {}
            t1, desc, link = f"{r.get('label_de') or ent} (neu)", r.get("description_de", ""), ""
        quals = "; ".join(f"{lab(p)}: {val(v)}" for p, v in s["quals"])
        t2 = f"{lab(s['property'])}: {val(s['value'])}" + (f" ({quals})" if quals else "")
        qs_line = PH_RE.sub(lambda m: resolve(m.group(0)), s["line"])
        if len(qs_line) > 500:
            print(f"warning: QS line > 500 chars, custom_value1 truncated: {qs_line[:80]}…", file=sys.stderr)
        rows.append({
            "custom_id": "|".join(resolve(x).strip('"') for x in key),
            "custom_value1": qs_line[:500],
            "custom_value2": f"{c['lemma']}, S. {c['pages']}",
            "text1": f"{t1} – {desc}" if desc else t1,
            "text1_link": link,
            "text2": t2,
            "text3": f"»{c['quote'].strip()}« ({c['lemma']}, S. {c['pages']})",
        })

    with open(a.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COMO_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{a.output}: {len(rows)} prompt(s)")
    dup = len(rows) - len({r["custom_id"] for r in rows})
    if dup:
        print(f"warning: {dup} duplicate custom_id(s)", file=sys.stderr)
    for line in missing:
        print(f"no context: {line}", file=sys.stderr)
    for key in ctx:
        if key not in used:
            print(f"context row matches no statement: {key}", file=sys.stderr)
    print("game config:", json.dumps(GAME, ensure_ascii=False))


if __name__ == "__main__":
    main()
