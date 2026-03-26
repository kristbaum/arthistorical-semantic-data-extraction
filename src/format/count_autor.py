#!/usr/bin/env python3
"""Count and fix occurrences of 'Autor und Entstehungszeit:' in .wiki files.

Expected format: **Autor und Entstehungszeit:** <text on same line>
  - Wrapped in ** ... **
  - At the start of a line (block)
  - Text follows on the same line (not standalone)

Detects:
  - Already correct  : **Autor und Entstehungszeit:** text...
  - Wrong markup     : <b>...</b>, == heading == with content, no markup
  - Standalone       : alone on a line (== heading == or bare) — reported but not fixed

Pass --apply to write fixes to disk (default: dry-run).
"""

import argparse
import re
from pathlib import Path
from Levenshtein import distance as levenshtein

TARGET = "Autor und Entstehungszeit"
TARGET_COLON = TARGET + ":"
FIXED = f"**{TARGET_COLON}**"
MAX_EDITS = 2

# Patterns for classification
RE_CORRECT = re.compile(r"^\*\*" + re.escape(TARGET_COLON) + r"\*\*\s+\S")
RE_BOLD_HTML = re.compile(r"^<b>" + re.escape(TARGET_COLON) + r"</b>\s*", re.IGNORECASE)
RE_HEADING = re.compile(r"^==\s*(.*?)\s*==$")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--dry-run", action="store_true", help="Print proposed edits without writing."
)
parser.add_argument(
    "--apply", action="store_true", help="Write fixes to disk."
)
args = parser.parse_args()
DRY_RUN = args.dry_run
APPLY = args.apply


def fuzzy_contains_target(stripped: str, max_edits: int) -> tuple[bool, int]:
    """Check if stripped line starts with (a fuzzy match of) TARGET.

    Returns (matched, dist). Checks the leading len(TARGET)±max_edits chars.
    """
    tlen = len(TARGET)
    for wlen in range(tlen - max_edits, tlen + max_edits + 1):
        if wlen < 1 or wlen > len(stripped):
            continue
        dist = levenshtein(stripped[:wlen], TARGET)
        if dist <= max_edits:
            return True, dist
    return False, 999


def classify(line: str) -> tuple[str, int] | None:
    """Return (category, dist) or None if not a match.

    Categories:
      'correct'    — already **Autor und Entstehungszeit:** text
      'html_bold'  — <b>Autor und Entstehungszeit:</b> text
      'heading_content' — == Autor und Entstehungszeit: content ==
      'heading_alone'   — == Autor und Entstehungszeit == (standalone)
      'bare'       — no markup, target at start of line with text following
      'bare_alone' — no markup, target is the whole line
    """
    stripped = line.strip()

    # Already correct
    if RE_CORRECT.match(stripped):
        return "correct", 0

    # HTML bold inline: <b>Autor und Entstehungszeit:</b> text
    m = RE_BOLD_HTML.match(stripped)
    if m:
        rest = stripped[m.end() :]
        dist = levenshtein(stripped[3 : 3 + len(TARGET_COLON)], TARGET_COLON)
        if dist <= MAX_EDITS:
            return ("html_bold_inline" if rest else "html_bold_alone"), dist

    # == heading ==
    m = RE_HEADING.match(stripped)
    if m:
        inner = m.group(1)
        # Strip any inner <b> tags
        inner_clean = re.sub(r"</?b>", "", inner, flags=re.IGNORECASE).strip()
        # Does inner start with TARGET (with optional colon)?
        candidate = inner_clean[: len(TARGET) + 2]  # +2 for ": "
        dist = levenshtein(candidate[: len(TARGET)], TARGET)
        if dist <= MAX_EDITS:
            # Is there content after the target label?
            after_target = inner_clean[len(TARGET) :].lstrip(": ").strip()
            return ("heading_content" if after_target else "heading_alone"), dist

    # Bare line — check first word-group against TARGET
    # Strip leading punctuation/markup
    bare = re.sub(r"^[^A-Za-zÄÖÜäöüß]+", "", stripped)
    matched, dist = fuzzy_contains_target(bare, MAX_EDITS)
    if matched:
        rest = bare[len(TARGET) :].lstrip(": ").strip()
        return ("bare" if rest else "bare_alone"), dist

    return None


def build_fix(line: str, category: str) -> str | None:
    """Return the fixed line, or None if unfixable (standalone headings)."""
    stripped = line.strip()

    if category in ("heading_alone", "bare_alone"):
        return None  # can't inline without following text

    if category == "correct":
        return None  # nothing to do

    if category == "html_bold_inline":
        m = RE_BOLD_HTML.match(stripped)
        rest = stripped[m.end() :]
        return f"{FIXED} {rest}"

    if category == "heading_content":
        m = RE_HEADING.match(stripped)
        inner = re.sub(r"</?b>", "", m.group(1), flags=re.IGNORECASE).strip()
        rest = inner[len(TARGET) :].lstrip(": ").strip()
        return f"{FIXED} {rest}"

    if category == "bare":
        bare = re.sub(r"^[^A-Za-zÄÖÜäöüß]+", "", stripped)
        rest = bare[len(TARGET) :].lstrip(": ").strip()
        return f"{FIXED} {rest}"

    return None


repo_root = Path(__file__).parent
wiki_files = sorted(repo_root.rglob("*.wiki"))
mode_label = "APPLY" if APPLY else ("DRY RUN" if DRY_RUN else "COUNT ONLY")
print(f"Scanning {len(wiki_files)} .wiki files for '{TARGET}'  [{mode_label}]\n")

# ── Scan ─────────────────────────────────────────────────────────────────────
stats: dict[str, int] = {}
all_findings: list[tuple[Path, int, str, str, int]] = []  # path,lineno,raw,cat,dist

for path in wiki_files:
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        result = classify(line)
        if result is None:
            continue
        cat, dist = result
        all_findings.append((path, lineno, line.rstrip(), cat, dist))
        stats[cat] = stats.get(cat, 0) + 1

# ── Report ────────────────────────────────────────────────────────────────────
print("=" * 60)
print("Summary by category")
print("=" * 60)
for cat, count in sorted(stats.items()):
    print(f"  {cat:25s}: {count}")
total = sum(stats.values())
print(f"\n  Total: {total}\n")

fixable_cats = {"html_bold_inline", "heading_content", "bare"}
skip_cats = {"heading_alone", "bare_alone"}

fixable = [
    (p, ln, raw, cat, d) for p, ln, raw, cat, d in all_findings if cat in fixable_cats
]
skippable = [
    (p, ln, raw, cat, d) for p, ln, raw, cat, d in all_findings if cat in skip_cats
]
correct = [
    (p, ln, raw, cat, d) for p, ln, raw, cat, d in all_findings if cat == "correct"
]

print("=" * 60)
print(f"Already correct: {len(correct)}")
print("=" * 60)

print(f"\nSkipped (standalone — can't inline): {len(skippable)}")
if DRY_RUN or APPLY:
    for path, lineno, raw, cat, dist in skippable:
        rel = path.relative_to(repo_root)
        tag = f"dist={dist}" if dist else "exact"
        print(f"  {rel}:{lineno} [{cat},{tag}] '{raw}'")

print(f"\nFixable: {len(fixable)}")
print("=" * 60)
if DRY_RUN or APPLY:
    for path, lineno, raw, cat, dist in fixable:
        rel = path.relative_to(repo_root)
        fix = build_fix(raw, cat)
        tag = f"dist={dist}" if dist else "exact"
        print(f"  {rel}:{lineno} [{cat},{tag}]")
        print(f"    was: '{raw}'")
        print(f"    fix: '{fix}'")

# ── Apply ─────────────────────────────────────────────────────────────────────
if fixable and (DRY_RUN or APPLY):
    print(f"\n{'=' * 60}")
    print(f"Fix  ({'DRY RUN — no files written' if DRY_RUN else 'WRITING FILES'})")
    print("=" * 60)

    files_changed = 0
    lines_changed = 0

    fixable_by_file: dict[Path, list] = {}
    for path, lineno, raw, cat, dist in fixable:
        fixable_by_file.setdefault(path, []).append((lineno, raw, cat, dist))

    for path, entries in sorted(fixable_by_file.items()):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        changed = False
        for lineno, raw, cat, dist in entries:
            fix = build_fix(raw, cat)
            if fix is not None:
                lines[lineno - 1] = fix
                lines_changed += 1
                changed = True
        if changed and APPLY:
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            path.write_text(new_text, encoding="utf-8")
            files_changed += 1

    print(
        f"\nFiles {'would be' if DRY_RUN else ''} changed: {files_changed if APPLY else len(fixable_by_file)}"
    )
    print(f"Lines {'would be' if DRY_RUN else ''} changed: {lines_changed}")
    if DRY_RUN:
        print("\nRun with --apply to write changes to disk.")
elif fixable:
    print("\nRun with --dry-run to preview changes, or --apply to write them.")
