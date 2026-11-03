#!/usr/bin/env python3
"""Placeholders for items that do not exist on Wikidata yet.

Batches written by the extract-cbd-to-wd skill refer to items still to be
created as  {NEW:<kind>:<slug>}  (kind = person | building | room | painting |
other; slug = lowercase a-z0-9 and hyphens), e.g. {NEW:room:adelshausen-ar}.
placeholders.tsv (TAB-separated, header row) lists each one:

    placeholder  kind  label_de  description_de  qid

Subcommands
-----------
  check  [--map placeholders.tsv] BATCH...
      Validate batches with the as-quickstatments validator after swapping each
      placeholder for a dummy QID; also report placeholders used in a batch but
      missing from the map, map rows never used, and CREATE blocks without a
      placeholder comment.
  lookup --map placeholders.tsv [--apply]
      For rows without a qid, search Wikidata for an item whose German label
      AND description equal label_de / description_de (that pair is unique on
      Wikidata). Prints what it found; --apply writes the qids into the map.
  fill   --map placeholders.tsv BATCH [-o OUT] [--pending PENDING]
      Replace placeholders with their qids. Lines whose placeholders are all
      resolved go to OUT (default: BATCH with .filled.qs); lines still holding
      an unresolved placeholder go to PENDING (default: .pending.qs).
"""

from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

PH_RE = re.compile(r"\{NEW:(person|building|room|painting|other):([a-z0-9][a-z0-9-]*)\}")
ANY_NEW = re.compile(r"\{NEW:[^}]*\}")
API = "https://www.wikidata.org/w/api.php"
UA = "cbdd-extract-placeholders/1.0 (Wikidata batch helper)"
FIELDS = ["placeholder", "kind", "label_de", "description_de", "qid"]


def load_map(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    for r in rows:
        for f in FIELDS:
            r[f] = (r.get(f) or "").strip()
    return rows


def save_map(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def find_validator(explicit: str | None):
    cands = [explicit] if explicit else []
    here = Path(__file__).resolve()
    cands += glob.glob(str(here.parents[2] / "*quickstat*" / "scripts" / "validate_qs.py"))
    cands += glob.glob(str(Path.home() / ".claude" / "skills" / "**" / "*quickstat*" / "scripts" / "validate_qs.py"), recursive=True)
    for c in cands:
        if c and Path(c).exists():
            spec = importlib.util.spec_from_file_location("validate_qs", c)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, c
    return None, None


def cmd_check(a) -> int:
    rows = {r["placeholder"]: r for r in load_map(Path(a.map))} if a.map else {}
    mod, vpath = find_validator(a.validator)
    if not mod:
        print("as-quickstatments validate_qs.py not found; pass --validator PATH", file=sys.stderr)
    errors, used = 0, set()
    dummy: dict[str, str] = {}
    for b in a.batches:
        lines = Path(b).read_text(encoding="utf-8").splitlines(keepends=True)
        out = []
        create_open = None
        for n, line in enumerate(lines, 1):
            for bad in ANY_NEW.findall(line):
                if not PH_RE.fullmatch(bad):
                    print(f"{b}:{n}: ERROR: malformed placeholder {bad}")
                    errors += 1
            for m in PH_RE.finditer(line):
                ph = m.group(0)
                used.add(ph)
                if a.map and ph not in rows:
                    print(f"{b}:{n}: ERROR: {ph} not in {a.map}")
                    errors += 1
                dummy.setdefault(ph, f"Q{900000000 + len(dummy)}")
            fields = line.rstrip("\n").split("\t")
            if fields[0].strip() == "CREATE":
                if create_open is not None:
                    print(f"{b}:{create_open}: warning: CREATE block has no {{NEW:…}} comment on a LAST line")
                create_open = n
            elif fields[0] == "LAST" and "/*" in line and PH_RE.search(line.split("/*", 1)[1]):
                create_open = None
            elif fields[0] == "LAST" and PH_RE.search(line.split("/*", 1)[0]):
                print(f"{b}:{n}: ERROR: placeholder used as a value inside a CREATE block; move that statement to statements.qs")
                errors += 1
            out.append(PH_RE.sub(lambda m: dummy[m.group(0)], line))
        if create_open is not None:
            print(f"{b}:{create_open}: warning: CREATE block has no {{NEW:…}} comment on a LAST line")
        if mod:
            buf = io.StringIO()
            with redirect_stdout(buf):
                e = mod.validate(out, b)
            errors += e
            shown = 0
            for msg in buf.getvalue().splitlines():
                if re.match(rf"{re.escape(b)}: \d+ error\(s\), \d+ warning\(s\)$", msg):
                    continue
                m = re.match(rf"{re.escape(b)}:(\d+): warning: (.*)", msg)
                if m:
                    src_line = out[int(m.group(1)) - 1]
                    # repeated CREATE / LAST lines across CREATE blocks are expected;
                    # described by source (P1343) is itself the source
                    if m.group(2).startswith("duplicate of line") and src_line.split("\t")[0].strip() in ("CREATE", "LAST"):
                        continue
                    if m.group(2).startswith("P1343 has no reference"):
                        continue
                    shown += 1
                print(msg)
            print(f"{b}: {e} error(s), {shown} warning(s)")
    if a.map:
        for ph in rows:
            if ph not in used:
                print(f"{a.map}: warning: {ph} defined but not used in the given batches")
        dup = {}
        for r in rows.values():
            dup.setdefault((r["label_de"], r["description_de"]), []).append(r["placeholder"])
        for k, v in dup.items():
            if len(v) > 1:
                print(f"{a.map}: ERROR: label+description {k} shared by {v} (must be unique on Wikidata)")
                errors += 1
    if mod:
        print(f"(validator: {vpath})")
    return 1 if errors else 0


def api(params: dict) -> dict:
    params = {**params, "format": "json"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cmd_lookup(a) -> int:
    path = Path(a.map)
    rows = load_map(path)
    changed = 0
    for r in rows:
        if r["qid"] or not r["label_de"]:
            continue
        res = api({"action": "wbsearchentities", "search": r["label_de"], "language": "de",
                   "strictlanguage": 1, "type": "item", "limit": 50})
        ids = [s["id"] for s in res.get("search", []) if s.get("label") == r["label_de"]]
        hits = []
        for i in range(0, len(ids), 50):
            ents = api({"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]),
                        "props": "labels|descriptions", "languages": "de"}).get("entities", {})
            for q, e in ents.items():
                if e.get("descriptions", {}).get("de", {}).get("value") == r["description_de"]:
                    hits.append(q)
        if len(hits) == 1:
            print(f"{r['placeholder']}\t{hits[0]}")
            r["qid"] = hits[0]
            changed += 1
        else:
            print(f"{r['placeholder']}\t{'NOT FOUND' if not hits else 'AMBIGUOUS ' + ','.join(hits)}")
        time.sleep(0.2)
    if a.apply and changed:
        save_map(path, rows)
        print(f"wrote {changed} qid(s) to {path}")
    elif changed:
        print(f"{changed} qid(s) found; rerun with --apply to write them")
    return 0


def cmd_fill(a) -> int:
    rows = {r["placeholder"]: r["qid"] for r in load_map(Path(a.map))}
    src = Path(a.batch)
    out = Path(a.output) if a.output else src.with_suffix(".filled.qs")
    pend = Path(a.pending) if a.pending else src.with_suffix(".pending.qs")
    done, pending = [], []
    for line in src.read_text(encoding="utf-8").splitlines(keepends=True):
        missing = [m.group(0) for m in PH_RE.finditer(line) if not re.fullmatch(r"Q\d+", rows.get(m.group(0), ""))]
        if missing:
            pending.append(line)
        else:
            done.append(PH_RE.sub(lambda m: rows[m.group(0)], line))
    out.write_text("".join(done), encoding="utf-8")
    print(f"{out}: {sum(1 for l in done if l.strip())} line(s)")
    if pending:
        pend.write_text("".join(pending), encoding="utf-8")
        print(f"{pend}: {len(pending)} line(s) still waiting for a qid")
    elif pend.exists():
        pend.unlink()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--map")
    c.add_argument("--validator")
    c.add_argument("batches", nargs="+")
    lk = sub.add_parser("lookup")
    lk.add_argument("--map", required=True)
    lk.add_argument("--apply", action="store_true")
    f = sub.add_parser("fill")
    f.add_argument("--map", required=True)
    f.add_argument("batch")
    f.add_argument("-o", "--output")
    f.add_argument("--pending")
    a = ap.parse_args()
    sys.exit({"check": cmd_check, "lookup": cmd_lookup, "fill": cmd_fill}[a.cmd](a))


if __name__ == "__main__":
    main()
