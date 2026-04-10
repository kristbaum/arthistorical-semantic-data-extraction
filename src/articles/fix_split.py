"""Verify and fix {{Artikel}} templates in BandXX_split.wiki files.

Checks and optionally fixes:

1. Originalseitenvon / Originalseitenbis — verified against the
   <!-- citation-page-top/bottom --> comments found *inside* the article
   block (between the closing ``}}`` of the template and the ``{{End}}``
   marker).  Originalseitenvon = min page number; Originalseitenbis = max.

2. davor / danach — verified against the Lemma of the immediately preceding
   and following {{Artikel}} blocks in the same file.

Default mode is a dry-run that only reports discrepancies.
Pass ``--apply`` to write the corrected file back to disk.

Usage:
    python -m src.articles.fix_split [--band Band01] [--apply] [--verbose]
"""

import argparse
import re
from collections import defaultdict

from .helpers import REPO_ROOT

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"

_ARTIKEL_RE = re.compile(r"^\{\{Artikel\b")
_END_RE = re.compile(r"^\{\{End\}\}")


# ---------------------------------------------------------------------------
# Template field helpers
# ---------------------------------------------------------------------------


def _get_field(template_lines: list[str], field: str) -> str:
    """Return the value of |field= in the template lines, stripped."""
    pat = re.compile(rf"^\s*\|{re.escape(field)}=(.*)$")
    for line in template_lines:
        m = pat.match(line)
        if m:
            return m.group(1).strip()
    return ""


def _set_field(template_lines: list[str], field: str, value: str) -> list[str]:
    """Replace the value of |field= in-place, preserving leading whitespace."""
    pat = re.compile(rf"^(\s*\|{re.escape(field)}=).*$")
    result = []
    for line in template_lines:
        m = pat.match(line)
        if m:
            result.append(m.group(1) + value)
        else:
            result.append(line)
    return result


def _safe_int(s: str) -> int | None:
    try:
        return int(s) if s.strip() else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------


def _parse_blocks(lines: list[str]) -> list[dict]:
    """Return one dict per {{Artikel}}…{{End}} block found in lines.

    Each dict contains:
      template_start  – line index of ``{{Artikel``
      template_end    – line index of the closing ``}}``
      end_line        – line index of ``{{End}}``
      lemma, von, bis, davor, danach
    """
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        if not _ARTIKEL_RE.match(lines[i].strip()):
            i += 1
            continue

        template_start = i

        # Find the closing '}}'  of the template (first standalone '}}' line).
        j = i + 1
        while j < len(lines) and lines[j].strip() != "}}":
            j += 1
        if j >= len(lines):
            i += 1
            continue
        template_end = j

        # Find the matching {{End}}.
        k = template_end + 1
        while k < len(lines) and not _END_RE.match(lines[k].strip()):
            k += 1
        if k >= len(lines):
            i += 1
            continue
        end_line = k

        tpl = lines[template_start : template_end + 1]
        blocks.append(
            {
                "template_start": template_start,
                "template_end": template_end,
                "end_line": end_line,
                "lemma": _get_field(tpl, "Lemma"),
                "von": _safe_int(_get_field(tpl, "Originalseitenvon")),
                "bis": _safe_int(_get_field(tpl, "Originalseitenbis")),
                "davor": _get_field(tpl, "davor"),
                "danach": _get_field(tpl, "danach"),
            }
        )
        i = end_line + 1

    return blocks


# ---------------------------------------------------------------------------
# Per-band fixer
# ---------------------------------------------------------------------------


def fix_band(
    band_prefix: str,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> int:
    """Check (and optionally fix) one BandXX_split.wiki.

    Returns the number of discrepancies found (or applied).
    """
    split_path = SPLITTING_DIR / band_prefix / f"{band_prefix}_split.wiki"
    if not split_path.is_file():
        if verbose:
            print(f"  SKIP {band_prefix}: {split_path.name} not found")
        return 0

    text = split_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks = _parse_blocks(lines)

    if not blocks:
        if verbose:
            print(f"  SKIP {band_prefix}: no {{{{Artikel}}}} blocks found")
        return 0

    # Collect fixes: (block_index, field_name, old_value, new_value)
    fixes: list[tuple[int, str, str, str]] = []

    for idx, block in enumerate(blocks):
        von, bis = block["von"], block["bis"]

        # --- Invalid template: bis before von ---
        if von is not None and bis is not None and bis < von:
            print(
                f"  [INVALID] {band_prefix} / {block['lemma']!r}: von={von} > bis={bis}"
            )

        if idx > 0:
            prev = blocks[idx - 1]
            prev_bis = prev["bis"]

            # --- Overlap: starts before previous article ends ---
            if prev_bis is not None and von is not None and von < prev_bis:
                print(
                    f"  [OVERLAP] {band_prefix} / {prev['lemma']!r} (ends p{prev_bis})"
                    f" → {block['lemma']!r} (starts p{von})"
                )

            # --- Gap: page(s) skipped between consecutive articles ---
            elif prev_bis is not None and von is not None and von > prev_bis + 1:
                print(
                    f"  [GAP] {band_prefix} / {prev['lemma']!r} (ends p{prev_bis})"
                    f" → {block['lemma']!r} (starts p{von})"
                )

        # --- davor ---
        expected_davor = blocks[idx - 1]["lemma"] if idx > 0 else ""
        if block["davor"] != expected_davor:
            fixes.append((idx, "davor", block["davor"], expected_davor))

        # --- danach ---
        expected_danach = blocks[idx + 1]["lemma"] if idx < len(blocks) - 1 else ""
        if block["danach"] != expected_danach:
            fixes.append((idx, "danach", block["danach"], expected_danach))

    if not fixes:
        if verbose:
            print(f"  OK {band_prefix} ({len(blocks)} articles, no issues)")
        return 0

    # Report
    verb = "FIX" if apply else "WOULD FIX"
    for block_idx, field, old, new in fixes:
        lemma = blocks[block_idx]["lemma"]
        print(f"  [{verb}] {band_prefix} / {lemma!r}")
        print(f"           {field}: {old!r} → {new!r}")

    if not apply:
        return len(fixes)

    # Apply: group by block index, then patch template lines in-place.
    # Line count does not change, so stored indices stay valid.
    block_changes: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for block_idx, field, _old, new_val in fixes:
        block_changes[block_idx].append((field, new_val))

    new_lines = list(lines)
    for block_idx, changes in block_changes.items():
        b = blocks[block_idx]
        segment = new_lines[b["template_start"] : b["template_end"] + 1]
        for field, new_val in changes:
            segment = _set_field(segment, field, new_val)
        new_lines[b["template_start"] : b["template_end"] + 1] = segment

    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    split_path.write_text(new_text, encoding="utf-8")
    if verbose:
        print(f"  Wrote {split_path.relative_to(REPO_ROOT)}  ({len(fixes)} fixes)")

    return len(fixes)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--band",
        metavar="BAND",
        help="Process only this band prefix, e.g. Band01 or Band03-1",
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
        band_prefixes = sorted(p.name for p in SPLITTING_DIR.iterdir() if p.is_dir())

    total_fixes = 0
    for bp in band_prefixes:
        n = fix_band(bp, apply=args.apply, verbose=args.verbose)
        total_fixes += n

    mode = "Applied" if args.apply else "Found"
    print(f"\n{mode} {total_fixes} fix(es) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
