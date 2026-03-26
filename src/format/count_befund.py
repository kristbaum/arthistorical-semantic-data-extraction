#!/usr/bin/env python3
"""Count and fix occurrences of 'Befund' as a standalone line in .wiki files.

Pass 1: Exact matches — lines where the stripped content is exactly 'Befund'
        (with or without == heading markers).
Pass 2: Fuzzy near-matches — lines within Levenshtein distance <= MAX_EDITS
        of 'Befund' (catches broken OCR like 'Befud', 'Befunnd', etc.).
Pass 3: Fix all matches → '== Befund =='
        Default: dry-run. Pass --apply to write changes to disk.
"""

import argparse
from pathlib import Path
from itertools import groupby
from operator import itemgetter
from Levenshtein import distance as levenshtein

TARGET = "Befund"
HEADING = f"== {TARGET} =="
MAX_EDITS = 3

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--apply",
    action="store_true",
    help="Write fixes to disk (default: dry-run, only print changes).",
)
args = parser.parse_args()
DRY_RUN = not args.apply


def is_heading(line: str) -> bool:
    s = line.strip()
    return s.startswith("==") and s.endswith("==")


def scan_files(
    wiki_files: list[Path], max_edits: int
) -> list[tuple[Path, int, str, bool, int]]:
    """Return list of (path, lineno, raw_line, in_heading, dist) for all matches.

    dist=0 → exact; dist>0 → fuzzy near-match.
    Only single-line occurrences are considered (stripped content ~ TARGET).
    """
    tlen = len(TARGET)
    results = []
    for path in wiki_files:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            heading = is_heading(line)
            stripped = line.strip().strip("=").strip()
            if not stripped:
                continue
            slen = len(stripped)
            # Only consider lines whose length is within max_edits of TARGET
            if abs(slen - tlen) > max_edits:
                continue
            dist = levenshtein(stripped, TARGET)
            if dist <= max_edits:
                results.append((path, lineno, line.rstrip(), heading, dist))
    return results


def apply_fixes(text: str, fix_linenos: set[int]) -> str:
    lines = text.splitlines()
    result = [
        HEADING if (i + 1) in fix_linenos else line for i, line in enumerate(lines)
    ]
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


repo_root = Path(__file__).parent
wiki_files = sorted(repo_root.rglob("*.wiki"))
mode_label = "DRY RUN" if DRY_RUN else "APPLY"
print(f"Scanning {len(wiki_files)} .wiki files for '{TARGET}'  [{mode_label}]\n")

all_matches = scan_files(wiki_files, MAX_EDITS)
exact = [(p, ln, raw, hdg, d) for p, ln, raw, hdg, d in all_matches if d == 0]
fuzzy = [(p, ln, raw, hdg, d) for p, ln, raw, hdg, d in all_matches if d > 0]

# ── Pass 1: exact ────────────────────────────────────────────────────────────
print("=" * 60)
print("Pass 1: Exact matches")
print("=" * 60)

exact_heading = 0
exact_text = 0
for path, lineno, raw, in_heading, _ in exact:
    rel = path.relative_to(repo_root)
    ctx = "heading" if in_heading else "text"
    print(f"  {rel}:{lineno} [{ctx}] '{raw}'")
    if in_heading:
        exact_heading += 1
    else:
        exact_text += 1

print(f"\nTotal exact: {len(exact)}")
print(f"  in == heading == : {exact_heading}")
print(f"  in plain text    : {exact_text}\n")

# ── Pass 2: fuzzy near-matches ───────────────────────────────────────────────
print("=" * 60)
print(f"Pass 2: Fuzzy near-matches (0 < edit distance <= {MAX_EDITS})")
print("=" * 60)

fuzzy_heading = 0
fuzzy_text = 0
for path, lineno, raw, in_heading, dist in fuzzy:
    rel = path.relative_to(repo_root)
    ctx = "heading" if in_heading else "text"
    print(f"  {rel}:{lineno} [dist={dist}, {ctx}] '{raw}'")
    if in_heading:
        fuzzy_heading += 1
    else:
        fuzzy_text += 1

print(f"\nTotal near-matches: {len(fuzzy)}")
print(f"  in == heading == : {fuzzy_heading}")
print(f"  in plain text    : {fuzzy_text}")

print(f"\nGrand total (exact + near): {len(all_matches)}")
print(f"  in == heading == : {exact_heading + fuzzy_heading}")
print(f"  in plain text    : {exact_text + fuzzy_text}")

# ── Pass 3: fix ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"Pass 3: Fix all matches  →  '{HEADING}'")
print(f"        ({'DRY RUN — no files written' if DRY_RUN else 'WRITING FILES'})")
print("=" * 60)

files_changed = 0
lines_changed = 0

# Group matches by file


for path, group in groupby(all_matches, key=itemgetter(0)):
    entries = list(group)
    # Only entries whose raw line is not already the correct heading
    to_fix = [(ln, raw, dist) for _, ln, raw, _, dist in entries
              if raw.strip() != HEADING]
    if not to_fix:
        continue

    fix_linenos = {ln for ln, _, _ in to_fix}
    rel = path.relative_to(repo_root)

    print(f"\n  {rel}:")
    for lineno, raw, dist in to_fix:
        tag = "exact" if dist == 0 else f"dist={dist}"
        print(f"    line {lineno} [{tag}]: '{raw}'")
        print(f"           → '{HEADING}'")

    if not DRY_RUN:
        text = path.read_text(encoding="utf-8")
        path.write_text(apply_fixes(text, fix_linenos), encoding="utf-8")

    files_changed += 1
    lines_changed += len(fix_linenos)

print(f"\nFiles {'would be' if DRY_RUN else ''} changed: {files_changed}")
print(f"Lines {'would be' if DRY_RUN else ''} changed: {lines_changed}")
if DRY_RUN:
    print("\nRun with --apply to write changes to disk.")
