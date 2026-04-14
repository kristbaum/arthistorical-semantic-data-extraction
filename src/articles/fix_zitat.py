"""Fix damaged {{ZITAT|NNN}} placeholders in pass1 and *_split.wiki files.

The LLM pass1 processing sometimes outputs malformed placeholder brackets,
e.g.  {ZITAT|000},  {ZITAT|000}},  {{ZITAT|000}  instead of {{ZITAT|000}}.

This script:
  1. Scans every pass1/pXXX.wiki file for damaged ZITAT patterns.
  2. Looks up the original »…« quote text in the matching wiki/pXXX.wiki
     (the pre-LLM Surya source file).
  3. Fixes the pass1 file in-place (with --apply).
  4. Applies the same repairs (in document order) to the matching
     BandXX_split.wiki so it immediately reflects the corrections.

Default mode is a dry-run; pass --apply to write the changes to disk.

Usage:
    python -m src.articles.fix_zitat [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from .helpers import EXTRACTED_DIR, REPO_ROOT, band_chunk_key, page_sort_key

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"

# Matches any brace cluster around ZITAT|NNN (one or more braces on either side).
_ZITAT_ANY_RE = re.compile(r"\{+ZITAT\|(\d+)\}+")
_ZITAT_VALID_RE = re.compile(r"^\{\{ZITAT\|\d+\}\}$")


def _is_valid(text: str) -> bool:
    return bool(_ZITAT_VALID_RE.match(text))


def _original_quotes(orig_text: str) -> list[str]:
    """Return all »…« spans from the original (pre-LLM) wiki text, in order."""
    return re.findall(r"»[^»«]*«", orig_text, re.DOTALL)


def _find_repairs(
    text: str, quotes: list[str]
) -> list[tuple[int, int, str, str]]:
    """Return (start, end, damaged_form, correct_quote) for each damaged ZITAT."""
    repairs = []
    for m in _ZITAT_ANY_RE.finditer(text):
        damaged = m.group(0)
        if _is_valid(damaged):
            continue
        idx = int(m.group(1))
        if idx >= len(quotes):
            continue  # Can't resolve: ZITAT index out of range for this page
        repairs.append((m.start(), m.end(), damaged, quotes[idx]))
    return repairs


def _apply_repairs_to_text(
    text: str, repairs: list[tuple[int, int, str, str]]
) -> str:
    """Splice (start, end, damaged, correct) repairs into text."""
    if not repairs:
        return text
    parts: list[str] = []
    prev = 0
    for start, end, _damaged, correct in repairs:
        parts.append(text[prev:start])
        parts.append(correct)
        prev = end
    parts.append(text[prev:])
    return "".join(parts)


def _apply_repairs_to_split(
    split_text: str,
    ordered_repairs: list[tuple[str, str]],
) -> str:
    """Apply (damaged, correct) repairs to split_text in document order.

    Processes each repair by searching forward from the last match position,
    so the same damaged form appearing from two different source pages is
    handled correctly: first occurrence gets the first fix, second gets the
    second, and so on.
    """
    if not ordered_repairs:
        return split_text
    parts: list[str] = []
    pos = 0
    for damaged, correct in ordered_repairs:
        idx = split_text.find(damaged, pos)
        if idx == -1:
            continue  # Already resolved or not present
        parts.append(split_text[pos:idx])
        parts.append(correct)
        pos = idx + len(damaged)
    parts.append(split_text[pos:])
    return "".join(parts)


def fix_band(
    band_prefix: str,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> int:
    """Fix damaged ZITAT placeholders for one band. Returns total repair count."""

    split_path = SPLITTING_DIR / band_prefix / f"{band_prefix}_split.wiki"

    # Ordered list of (damaged_form, correct_quote) across all pass1 files,
    # in the order they appear when pass1 files are concatenated (= document order
    # in split.wiki, since split.wiki is assembled from the same files).
    ordered_repairs: list[tuple[str, str]] = []
    total = 0

    for chunk_dir in sorted(EXTRACTED_DIR.iterdir(), key=band_chunk_key):
        if not chunk_dir.name.startswith(band_prefix + "_chunk"):
            continue
        pass1_dir = chunk_dir / "pass1"
        wiki_dir = chunk_dir / "wiki"
        if not pass1_dir.is_dir() or not wiki_dir.is_dir():
            continue

        for pass1_file in sorted(pass1_dir.glob("p*.wiki"), key=page_sort_key):
            orig_file = wiki_dir / pass1_file.name
            if not orig_file.exists():
                if verbose:
                    print(
                        f"  [WARN] No original for "
                        f"{chunk_dir.name}/{pass1_file.name} — skipping"
                    )
                continue

            pass1_text = pass1_file.read_text(encoding="utf-8")

            # Fast skip: any damaged pattern at all?
            damaged_iter = [
                m for m in _ZITAT_ANY_RE.finditer(pass1_text)
                if not _is_valid(m.group(0))
            ]
            if not damaged_iter:
                continue

            orig_text = orig_file.read_text(encoding="utf-8")
            quotes = _original_quotes(orig_text)
            repairs = _find_repairs(pass1_text, quotes)

            if not repairs:
                # All damaged patterns had out-of-range indices
                for m in damaged_iter:
                    print(
                        f"  [UNRESOLVABLE] {chunk_dir.name}/{pass1_file.name}: "
                        f"{m.group(0)!r} (index out of range, "
                        f"{len(quotes)} quote(s) in original)"
                    )
                continue

            verb = "FIX" if apply else "WOULD FIX"
            for _s, _e, damaged, correct in repairs:
                preview = correct[:60] + ("…" if len(correct) > 60 else "")
                print(
                    f"  [{verb}] {chunk_dir.name}/{pass1_file.name}: "
                    f"{damaged!r} → {preview!r}"
                )
                ordered_repairs.append((damaged, correct))

            total += len(repairs)

            if apply:
                fixed_text = _apply_repairs_to_text(pass1_text, repairs)
                pass1_file.write_text(fixed_text, encoding="utf-8")

    # ── Patch split.wiki ──────────────────────────────────────────────────────
    if not split_path.is_file():
        if ordered_repairs and verbose:
            print(f"  [WARN] {band_prefix}_split.wiki not found — split.wiki not patched")
        return total

    if ordered_repairs:
        split_text = split_path.read_text(encoding="utf-8")
        new_split_text = _apply_repairs_to_split(split_text, ordered_repairs)

        if new_split_text != split_text:
            verb = "Wrote" if apply else "WOULD update"
            print(
                f"  [{verb}] {split_path.relative_to(REPO_ROOT)} "
                f"({len(ordered_repairs)} repair(s))"
            )
            if apply:
                split_path.write_text(new_split_text, encoding="utf-8")
        elif verbose:
            diff = sum(1 for d, _ in ordered_repairs if d in split_text)
            print(
                f"  [OK] {split_path.name}: "
                f"{diff} damaged pattern(s) still present but no changes written (dry-run)"
                if not apply else
                f"  [OK] {split_path.name}: no changes needed"
            )
    elif verbose:
        print(f"  OK {band_prefix}: no damaged ZITAT placeholders found")

    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--band",
        metavar="BAND",
        help="Process only this band, e.g. Band01 or Band03-1",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write fixes to disk (default: dry-run, only report)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(
            p.name for p in SPLITTING_DIR.iterdir() if p.is_dir()
        )

    total = 0
    for bp in band_prefixes:
        n = fix_band(bp, apply=args.apply, verbose=args.verbose)
        total += n

    mode = "Applied" if args.apply else "Found"
    print(f"\n{mode} {total} repair(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
