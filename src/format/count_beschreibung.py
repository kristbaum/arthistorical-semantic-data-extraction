#!/usr/bin/env python3
"""Count and fix occurrences of 'Beschreibung und Ikonographie' in .wiki files.

Pass 1: Exact string matches.
Pass 2: Fuzzy near-matches (0 < edit distance <= MAX_EDITS).
Pass 3: Fix all matches — correct spelling and ensure == heading == format.
        Default mode is dry-run (prints proposed changes).
        Pass --apply to write changes to disk.
"""

import argparse
from pathlib import Path

from Levenshtein import distance as levenshtein

TARGET = "Beschreibung und Ikonographie"
TARGET_ALT = "Beschreibung und Ikonologie"
HEADING = f"== {TARGET} =="
HEADING_ALT = f"== {TARGET_ALT} =="
MAX_EDITS = 5


def best_target(substr: str) -> tuple[str, str, int]:
    """Return (chosen_target, chosen_heading, dist) for whichever canonical
    target is closer to substr.

    Uses prefix-aware disambiguation: compare substr against the same-length
    leading portion of each target. This correctly resolves truncated OCR like
    'Beschreibung und Ikonog' to Ikonographie (prefix dist=0) rather than
    Ikonologie (prefix dist=1), even though full Levenshtein would prefer the
    shorter target.
    """
    slen = len(substr)
    d1_full = levenshtein(substr, TARGET)
    d2_full = levenshtein(substr, TARGET_ALT)
    # Compare against same-length prefix of each target for truncation cases
    d1_prefix = levenshtein(substr, TARGET[:slen])
    d2_prefix = levenshtein(substr, TARGET_ALT[:slen])
    if d1_prefix <= d2_prefix:
        return TARGET, HEADING, d1_full
    return TARGET_ALT, HEADING_ALT, d2_full


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--apply",
    action="store_true",
    help="Write fixes to disk (default: dry-run, only print changes).",
)
args = parser.parse_args()
DRY_RUN = not args.apply


def is_correct_heading(line: str) -> bool:
    s = line.strip()
    return s == HEADING or s == HEADING_ALT


def is_heading(line: str) -> bool:
    s = line.strip()
    return s.startswith("==") and s.endswith("==")


def count_exact(text: str, target: str) -> int:
    return text.count(target)


def find_all_matches(
    text: str, max_edits: int
) -> list[tuple[int, str, bool, int, str]]:
    """Return list of (lineno, matched_substr, in_heading, dist, chosen_heading).

    chosen_heading is the canonical heading (HEADING or HEADING_ALT) closest
    to the matched substring. Skips lines already correct.
    """
    tlen = len(TARGET)  # both targets have similar length
    min_wlen = tlen - max_edits
    max_wlen = tlen + max_edits
    matches = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if is_correct_heading(line):
            continue
        heading = is_heading(line)
        stripped = line.strip().strip("=").strip()
        if not stripped:
            continue
        slen = len(stripped)

        # Whole-line check
        if min_wlen <= slen <= max_wlen:
            _, chosen_hdg, dist = best_target(stripped)
            if dist <= max_edits:
                matches.append((lineno, stripped, heading, dist, chosen_hdg))
                continue

        # Sliding-window for phrases in longer lines
        if slen > max_wlen and slen <= 5 * tlen:
            for wlen in range(min_wlen, min(max_wlen + 1, slen + 1)):
                found = False
                for i in range(slen - wlen + 1):
                    substr = stripped[i : i + wlen]
                    _, chosen_hdg, dist = best_target(substr)
                    if dist <= max_edits:
                        matches.append((lineno, substr, heading, dist, chosen_hdg))
                        found = True
                        break
                if found:
                    break
    return matches


def apply_fixes(text: str, fixes: dict[int, str]) -> str:
    """fixes maps 1-based line numbers to their replacement heading string."""
    lines = text.splitlines()
    result = [
        fixes[i + 1] if (i + 1) in fixes else line for i, line in enumerate(lines)
    ]
    return "\n".join(result) + ("\n" if text.endswith("\n") else "")


repo_root = Path(__file__).parent
wiki_files = sorted(repo_root.rglob("*.wiki"))
mode_label = "DRY RUN" if DRY_RUN else "APPLY"
print(f"Scanning {len(wiki_files)} .wiki files for '{TARGET}'  [{mode_label}]\n")

# ── Pass 1: exact ────────────────────────────────────────────────────────────
print("=" * 60)
print("Pass 1: Exact matches")
print("=" * 60)

exact_total = 0
exact_file_count = 0
for path in wiki_files:
    text = path.read_text(encoding="utf-8")
    n = text.count(TARGET) + text.count(TARGET_ALT)
    if n:
        rel = path.relative_to(repo_root)
        print(f"  {rel}: {n}")
        exact_total += n
        exact_file_count += 1

print(f"\nTotal exact: {exact_total} occurrences in {exact_file_count} files\n")

# ── Pass 2: fuzzy near-matches ───────────────────────────────────────────────
print("=" * 60)
print(f"Pass 2: Fuzzy near-matches only (0 < edit distance <= {MAX_EDITS})")
print("=" * 60)

near_in_heading = 0
near_in_text = 0

for path in wiki_files:
    text = path.read_text(encoding="utf-8")
    matches = find_all_matches(text, MAX_EDITS)
    near = [
        (ln, substr, hdg, dist, chosen)
        for ln, substr, hdg, dist, chosen in matches
        if dist > 0
    ]
    if near:
        rel = path.relative_to(repo_root)
        print(f"  {rel}: {len(near)}")
        for lineno, substr, in_heading, dist, chosen in near:
            ctx = "heading" if in_heading else "text"
            print(f"    line {lineno}: [dist={dist}, {ctx}] '{substr}' → '{chosen}'")
            if in_heading:
                near_in_heading += 1
            else:
                near_in_text += 1

near_total = near_in_heading + near_in_text
print(f"\n  Near-matches (dist>0): {near_total}")
print(f"    in == heading == : {near_in_heading}")
print(f"    in plain text    : {near_in_text}\n")

# ── Pass 3: fix ──────────────────────────────────────────────────────────────
print("=" * 60)
print(f"Pass 3: Fix all matches  →  '{HEADING}'")
print(f"        ({'DRY RUN — no files written' if DRY_RUN else 'WRITING FILES'})")
print("=" * 60)

files_changed = 0
lines_changed = 0

for path in wiki_files:
    text = path.read_text(encoding="utf-8")
    matches = find_all_matches(text, MAX_EDITS)
    if not matches:
        continue

    rel = path.relative_to(repo_root)
    fixes = {ln: chosen_hdg for ln, _, _, _, chosen_hdg in matches}
    raw_lines = text.splitlines()

    print(f"\n  {rel}:")
    for lineno, substr, in_heading, dist, chosen_hdg in matches:
        old = raw_lines[lineno - 1].rstrip()
        tag = "exact" if dist == 0 else f"dist={dist}"
        print(f"    line {lineno} [{tag}]: '{old}'")
        print(f"           → '{chosen_hdg}'")

    if not DRY_RUN:
        new_text = apply_fixes(text, fixes)
        path.write_text(new_text, encoding="utf-8")

    files_changed += 1
    lines_changed += len(fixes)

print(f"\nFiles {'would be' if DRY_RUN else ''} changed: {files_changed}")
print(f"Lines {'would be' if DRY_RUN else ''} changed: {lines_changed}")
if DRY_RUN:
    print("\nRun with --apply to write changes to disk.")
