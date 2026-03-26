#!/usr/bin/env python3
"""Wrap inline section labels with MediaWiki bold markers in .wiki files.

Targets (Levenshtein distance ≤ 2 against the leading label characters):
  Auftraggeber:   →  '''Auftraggeber:''' <rest>
  Zum Bauwerk:    →  '''Zum Bauwerk:''' <rest>
  Patrozinium:    →  '''Patrozinium:''' <rest>

Lines where the label is the entire content (standalone headings) are skipped.
Lines already correctly formatted are reported as-is.

Default: count-only mode. Use --dry-run to preview, --apply to write.
"""

import argparse
import re
from pathlib import Path

from Levenshtein import distance as levenshtein

MAX_EDITS = 2

TARGETS = [
    "Auftraggeber:",
    "Zum Bauwerk:",
    "Patrozinium:",
]

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--apply", action="store_true", help="Write fixes to disk.")
parser.add_argument(
    "--dry-run", action="store_true", help="Preview fixes without writing."
)
parser.add_argument(
    "--fuzzy-only",
    action="store_true",
    help="Only list matches with Levenshtein distance > 0 (imperfect OCR labels).",
)
args = parser.parse_args()
SHOW_FIXES = args.dry_run


# ── Helpers ───────────────────────────────────────────────────────────────────


def match_target(stripped: str) -> tuple[str | None, int]:
    """Return (canonical_target, dist) for the best-matching label, or (None, 999)."""
    best_target = None
    best_dist = 999
    for target in TARGETS:
        tlen = len(target)
        for wlen in range(max(1, tlen - MAX_EDITS), tlen + MAX_EDITS + 1):
            if wlen > len(stripped):
                break
            dist = levenshtein(stripped[:wlen], target)
            if dist < best_dist:
                best_dist = dist
                best_target = target
    if best_dist <= MAX_EDITS:
        return best_target, best_dist
    return None, best_dist


def build_fix(raw_line: str, target: str) -> str | None:
    """Return the fixed line, or None if the label is standalone (no content)."""
    stripped = raw_line.strip()

    # Unwrap == heading == markers
    m = re.match(r"^==\s*(.*?)\s*==$", stripped)
    if m:
        stripped = m.group(1).strip()

    # Remove HTML bold / MediaWiki bold markers
    stripped = re.sub(r"</?b>", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"^'''|'''$", "", stripped).strip()

    # Extract rest after the label (which may be slightly misspelled)
    tlen = len(target)
    # Find how many chars were consumed by the fuzzy label match
    best_wlen = tlen
    best_dist = 999
    for wlen in range(max(1, tlen - MAX_EDITS), tlen + MAX_EDITS + 1):
        if wlen > len(stripped):
            break
        dist = levenshtein(stripped[:wlen], target)
        if dist < best_dist:
            best_dist = dist
            best_wlen = wlen
    rest = stripped[best_wlen:].lstrip(": ").strip()

    if not rest:
        return f"'''{target}'''"  # standalone label — wrap with no trailing text

    return f"'''{target}''' {rest}"


# ── Main ──────────────────────────────────────────────────────────────────────


repo_root = Path(__file__).parent
wiki_files = sorted(repo_root.rglob("*.wiki"))

mode_label = "DRY RUN" if args.dry_run else ("APPLY" if args.apply else "COUNT ONLY")
print(f"Scanning {len(wiki_files)} .wiki files  [{mode_label}]\n")

# ── Scan ─────────────────────────────────────────────────────────────────────

stats: dict[str, int] = {"correct": 0, "fixable": 0}
findings: list[tuple[Path, int, str, str, str, int]] = []
# (path, lineno, raw_line, canonical_target, fix, dist)

for path in wiki_files:
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        # Strip heading / bold markers before matching to expose the label
        inner = re.sub(r"^==\s*|\s*==$", "", stripped).strip()
        inner = re.sub(r"</?b>|^'''|'''$", "", inner, flags=re.IGNORECASE).strip()

        target, _dist = match_target(inner)
        if target is None:
            continue

        fix = build_fix(line, target)
        correct_form = f"'''{target}'''"
        already_correct = stripped.startswith(correct_form)

        if fix is None:
            pass  # unreachable now
        elif already_correct:
            stats["correct"] += 1
        else:
            stats["fixable"] += 1
            findings.append((path, lineno, line.rstrip(), target, fix, _dist))

# ── Report ────────────────────────────────────────────────────────────────────

print("=" * 60)
print("Summary")
print("=" * 60)
for label, count in sorted(stats.items()):
    print(f"  {label:12s}: {count}")
print(f"\n  Total fixable: {stats['fixable']}\n")

if SHOW_FIXES or args.fuzzy_only:
    display = [f for f in findings if not args.fuzzy_only or f[5] > 0]
    print("=" * 60)
    title = "Fuzzy-only matches (dist > 0)" if args.fuzzy_only else "Proposed fixes"
    print(title)
    print("=" * 60)
    for path, lineno, raw, target, fix, dist in display:
        rel = path.relative_to(repo_root)
        tag = f"dist={dist}" if dist > 0 else "exact"
        print(f"\n  {rel}:{lineno} [{tag}]")
        print(f"    was: '{raw}'")
        print(f"    fix: '{fix}'")
    print(f"\nShowing {len(display)} of {len(findings)} fixable matches.")

# ── Apply ─────────────────────────────────────────────────────────────────────

if args.apply and findings:
    by_file: dict[Path, list[tuple[int, str]]] = {}
    for path, lineno, _raw, _target, fix, _dist in findings:
        by_file.setdefault(path, []).append((lineno, fix))

    files_changed = 0
    for path, entries in sorted(by_file.items()):
        text = path.read_text(encoding="utf-8")
        lines_out = text.splitlines()
        for lineno, fix in entries:
            lines_out[lineno - 1] = fix
        path.write_text(
            "\n".join(lines_out) + ("\n" if text.endswith("\n") else ""),
            encoding="utf-8",
        )
        files_changed += 1

    print(f"Files changed : {files_changed}")
    print(f"Lines changed : {len(findings)}")
elif not args.apply:
    if findings:
        print("Run with --dry-run to preview, or --apply to write changes.")
