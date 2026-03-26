#!/usr/bin/env python3
"""Locate 'Autor und Entstehungszeit' preceding every exact '== Befund ==' heading.

For each exact '== Befund ==' match, searches *upward* (decreasing line numbers)
for a line that starts with 'Autor und Entstehungszeit' (Levenshtein distance
≤ MAX_EDITS against the leading characters of the stripped line).

Search order when no match is found in the same file:
  1. Previous pages in the same chunk   (descending page numbers)
  2. Previous chunks in the same Band   (descending chunk numbers)
  3. Previous Bands                     (descending)

Reports the word count of text between the two markers.

Pass --apply to rewrite matching Autor lines to:
    '''Autor und Entstehungszeit:''' <original rest-of-line content>
"""

import argparse
import re
from pathlib import Path

from Levenshtein import distance as levenshtein

BEFUND_HEADING = "== Befund =="
AUTOR_TARGET = "Autor und Entstehungszeit"
MAX_EDITS = 4
FIXED_PREFIX = f"'''{AUTOR_TARGET}:'''"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--apply",
    action="store_true",
    help="Write fixes to disk.",
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Print proposed edits without writing (implies no --apply).",
)
parser.add_argument(
    "--min-words",
    type=int,
    default=0,
    metavar="N",
    help="Only show matches where the word count between markers is >= N.",
)
args = parser.parse_args()
DRY_RUN = not args.apply
SHOW_FIXES = args.dry_run


# ── Helpers ───────────────────────────────────────────────────────────────────


def fuzzy_matches_autor(line: str) -> tuple[bool, int]:
    """Return (matched, best_dist) if the start of the stripped line fuzzy-matches AUTOR_TARGET.

    Checks all window lengths in [tlen-MAX_EDITS, tlen+MAX_EDITS] and returns
    the minimum distance found, so exact matches always report dist=0.
    """
    stripped = line.strip()
    tlen = len(AUTOR_TARGET)
    best = 999
    for wlen in range(max(1, tlen - MAX_EDITS), tlen + MAX_EDITS + 1):
        if wlen > len(stripped):
            break
        dist = levenshtein(stripped[:wlen], AUTOR_TARGET)
        if dist < best:
            best = dist
    if best <= MAX_EDITS:
        return True, best
    return False, best


def count_words(text: str) -> int:
    return len(text.split())


def _band_chunk_key(chunk_dir: Path) -> tuple[int, int, int]:
    """Sort key for directory names like Band01_chunk002 or Band03-1_chunk001."""
    m = re.match(r"Band(\d+)(?:-(\d+))?_chunk(\d+)", chunk_dir.name)
    if m:
        return int(m.group(1)), int(m.group(2) or 0), int(m.group(3))
    return 999, 999, 999


def _page_number(path: Path) -> int:
    m = re.match(r"p(\d+)\.wiki$", path.name)
    return int(m.group(1)) if m else -1


def build_ordered_wiki_files(repo_root: Path) -> list[Path]:
    """Return all wiki files sorted by (Band, Band-sub, chunk, page)."""
    extracted = repo_root / "data" / "extracted"
    if not extracted.is_dir():
        return sorted(repo_root.rglob("*.wiki"))

    result: list[Path] = []
    for chunk_dir in sorted(extracted.iterdir(), key=_band_chunk_key):
        wiki_dir = chunk_dir / "wiki"
        if not wiki_dir.is_dir():
            continue
        for page in sorted(wiki_dir.glob("p*.wiki"), key=_page_number):
            result.append(page)
    return result


# ── Core search ───────────────────────────────────────────────────────────────


def search_upward(
    befund_file: Path,
    befund_lineno: int,  # 1-based
    all_files: list[Path],
    file_index: dict[Path, int],
) -> tuple[Path | None, int | None, str | None, int | None]:
    """Search upward from befund_lineno for an Autor line.

    Returns (path, lineno, raw_line, dist) or (None, None, None, None).
    """
    befund_idx = file_index[befund_file]

    # 1. Same file — lines strictly above the Befund heading
    lines = befund_file.read_text(encoding="utf-8").splitlines()
    for i in range(befund_lineno - 2, -1, -1):
        matched, dist = fuzzy_matches_autor(lines[i])
        if matched:
            return befund_file, i + 1, lines[i], dist

    # 2. Preceding files in reverse order
    for prev_file in reversed(all_files[:befund_idx]):
        prev_lines = prev_file.read_text(encoding="utf-8").splitlines()
        for i in range(len(prev_lines) - 1, -1, -1):
            matched, dist = fuzzy_matches_autor(prev_lines[i])
            if matched:
                return prev_file, i + 1, prev_lines[i], dist

    return None, None, None, None


def count_words_between(
    autor_file: Path,
    autor_lineno: int,  # 1-based
    befund_file: Path,
    befund_lineno: int,  # 1-based
    all_files: list[Path],
    file_index: dict[Path, int],
) -> int:
    """Count words in the content strictly between the two matched lines."""
    if autor_file == befund_file:
        lines = autor_file.read_text(encoding="utf-8").splitlines()
        between = lines[autor_lineno : befund_lineno - 1]
        return count_words("\n".join(between))

    autor_idx = file_index[autor_file]
    befund_idx = file_index[befund_file]
    total = 0

    # Tail of the Autor file (lines after the Autor line)
    autor_lines = autor_file.read_text(encoding="utf-8").splitlines()
    total += count_words("\n".join(autor_lines[autor_lineno:]))

    # Full intermediate files
    for mid_file in all_files[autor_idx + 1 : befund_idx]:
        total += count_words(mid_file.read_text(encoding="utf-8"))

    # Head of the Befund file (lines before the Befund heading)
    befund_lines = befund_file.read_text(encoding="utf-8").splitlines()
    total += count_words("\n".join(befund_lines[: befund_lineno - 1]))

    return total


# ── Fix formatter ─────────────────────────────────────────────────────────────


def build_fix(raw_line: str) -> str:
    """Reformat an Autor line → '''Autor und Entstehungszeit:''' <rest>."""
    stripped = raw_line.strip()

    # Unwrap == heading == markers
    m = re.match(r"^==\s*(.*?)\s*==$", stripped)
    if m:
        stripped = m.group(1).strip()

    # Remove HTML bold tags
    stripped = re.sub(r"</?b>", "", stripped, flags=re.IGNORECASE).strip()

    # Remove MediaWiki bold markers at both ends
    stripped = re.sub(r"^\\*|\*\*$", "", stripped).strip()

    # Extract rest after the ~25-char target label plus optional colon/space
    tlen = len(AUTOR_TARGET)
    rest = stripped[tlen:].lstrip(": ").strip()

    return f"{FIXED_PREFIX} {rest}" if rest else FIXED_PREFIX


# ── Main ──────────────────────────────────────────────────────────────────────


repo_root = Path(__file__).parent
all_files = build_ordered_wiki_files(repo_root)
file_index: dict[Path, int] = {f: i for i, f in enumerate(all_files)}

mode_label = "DRY RUN" if args.dry_run else ("APPLY" if args.apply else "COUNT ONLY")
print(f"Indexed {len(all_files)} .wiki files  [{mode_label}]\n")

# Collect all exact == Befund == matches
befund_matches: list[tuple[Path, int]] = []
for path in all_files:
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if line.strip() == BEFUND_HEADING:
            befund_matches.append((path, lineno))

print(f"Found {len(befund_matches)} exact '{BEFUND_HEADING}' matches\n")
print("=" * 72)

fixes_needed: list[tuple[Path, int, str, str]] = []  # (path, lineno, raw, fix)

# Collect all results first, print after all loops
Result = dict  # (befund_rel, befund_lineno, autor_rel, autor_lineno, autor_raw, tag, span, words, fixed, not_found)
results: list[Result] = []

for befund_file, befund_lineno in befund_matches:
    rel_befund = befund_file.relative_to(repo_root)

    autor_file, autor_lineno, autor_raw, autor_dist = search_upward(
        befund_file, befund_lineno, all_files, file_index
    )

    if autor_file is None:
        results.append({"befund_rel": rel_befund, "befund_lineno": befund_lineno, "not_found": True})
        continue

    rel_autor = autor_file.relative_to(repo_root)
    tag = "exact" if autor_dist == 0 else f"dist={autor_dist}"
    same_file = autor_file == befund_file

    words = count_words_between(
        autor_file, autor_lineno, befund_file, befund_lineno, all_files, file_index
    )
    span = (
        f"{befund_lineno - autor_lineno - 1} lines"
        if same_file
        else f"across {file_index[befund_file] - file_index[autor_file]} file(s)"
    )

    fixed = build_fix(autor_raw)
    needs_fix = autor_raw.strip() != fixed.strip()
    if needs_fix:
        fixes_needed.append((autor_file, autor_lineno, autor_raw, fixed))

    results.append({
        "befund_rel": rel_befund,
        "befund_lineno": befund_lineno,
        "not_found": False,
        "autor_rel": rel_autor,
        "autor_lineno": autor_lineno,
        "autor_raw": autor_raw,
        "tag": tag,
        "span": span,
        "words": words,
        "fixed": fixed,
        "needs_fix": needs_fix,
    })

for r in results:
    if not r["not_found"] and r["words"] < args.min_words:
        continue
    print(f"\nBefund : {r['befund_rel']}:{r['befund_lineno']}")
    if r["not_found"]:
        print("  Autor  : NOT FOUND (exhausted all preceding files)")
        continue
    print(f"  Autor  : {r['autor_rel']}:{r['autor_lineno']} [{r['tag']}]  '{r['autor_raw'].strip()}'")
    print(f"  Words between ({r['span']}): {r['words']}")
    if r["needs_fix"]:
        if SHOW_FIXES:
            print(f"  Fix    : '{r['fixed']}'")
    else:
        print("  Format : already correct")

# ── Apply / report fixes ──────────────────────────────────────────────────────

print(f"\n{'=' * 72}")
if not fixes_needed:
    print("No fixes needed.")
else:
    print(
        f"Fixes needed: {len(fixes_needed)} line(s)  "
        f"({'DRY RUN — no files written' if DRY_RUN else 'WRITING FILES'})"
    )
    print("=" * 72)

    by_file: dict[Path, list[tuple[int, str, str]]] = {}
    for path, lineno, raw, fix in fixes_needed:
        by_file.setdefault(path, []).append((lineno, raw, fix))

    for path, entries in sorted(by_file.items()):
        if SHOW_FIXES:
            rel = path.relative_to(repo_root)
            print(f"\n  {rel}:")
            for lineno, raw, fix in entries:
                print(f"    line {lineno}:  '{raw.strip()}'")
                print(f"           →  '{fix}'")
        if not DRY_RUN:
            text = path.read_text(encoding="utf-8")
            lines_out = text.splitlines()
            for lineno, _raw, fix in entries:
                lines_out[lineno - 1] = fix
            path.write_text(
                "\n".join(lines_out) + ("\n" if text.endswith("\n") else ""),
                encoding="utf-8",
            )

    print(f"\nFiles {'would be' if DRY_RUN else ''} changed: {len(by_file)}")
    print(f"Lines {'would be' if DRY_RUN else ''} changed: {len(fixes_needed)}")
    if DRY_RUN:
        print("\nRun with --dry-run to preview changes, or --apply to write them.")
