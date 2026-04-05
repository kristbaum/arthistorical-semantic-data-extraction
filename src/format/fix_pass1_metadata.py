#!/usr/bin/env python3
"""Fix missing citation metadata in pass1 wiki files by copying from wiki/ siblings.

For each pass1/*.wiki file that lacks citation-page-top or citation-page-bottom
comments, this script reads the corresponding wiki/*.wiki file and copies the
missing metadata across, writing the result back to the pass1 file.

Usage:
    python -m src.format.fix_pass1_metadata [--dry-run] [--verbose]
"""

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"


def clean_footer(text: str) -> tuple[str, int]:
    """Remove horizontal rule and OCR junk (e.g. page numbers) before citation-page-bottom.

    Returns (cleaned_text, removed_char_count).
    """
    lines = text.split("\n")

    # Find citation-page-bottom line
    bottom_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if "citation-page-bottom:" in lines[i]:
            bottom_idx = i
            break

    if bottom_idx is None:
        return text, 0

    # Walk backwards from just before bottom, looking for ----
    hr_idx = None
    for i in range(bottom_idx - 1, max(-1, bottom_idx - 15), -1):
        if i >= 0 and lines[i].strip().startswith("----"):
            hr_idx = i
            break

    if hr_idx is None:
        return text, 0

    # Also trim trailing blank lines above the ----
    trim_start = hr_idx
    while trim_start > 0 and lines[trim_start - 1].strip() == "":
        trim_start -= 1

    new_lines = lines[:trim_start] + lines[bottom_idx:]
    result = "\n".join(new_lines)
    removed = len(text) - len(result)

    return result, removed


def fix_file(pass1_file: Path, *, dry_run: bool = False) -> tuple[bool, int]:
    """Fix missing citation metadata and clean footer junk in a single pass1 file.

    Returns (metadata_modified, footer_chars_removed).
    """
    pass1_text = pass1_file.read_text(encoding="utf-8")
    meta_modified = False

    has_top = "citation-page-top:" in pass1_text
    has_bottom = "citation-page-bottom:" in pass1_text

    if not (has_top and has_bottom):
        wiki_file = pass1_file.parent.parent / "wiki" / pass1_file.name
        if wiki_file.is_file():
            wiki_text = wiki_file.read_text(encoding="utf-8")

            if not has_top:
                meta_lines: list[str] = []
                for line in wiki_text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("<!--") and (
                        "citation-page" in stripped or "dropbox:" in stripped
                    ):
                        meta_lines.append(line)
                    elif meta_lines and stripped == "":
                        continue
                    elif meta_lines:
                        break
                if meta_lines:
                    pass1_text = "\n".join(meta_lines) + "\n\n" + pass1_text
                    meta_modified = True

            if not has_bottom:
                m = re.search(r"(<!--\s*citation-page-bottom:.*?-->)", wiki_text)
                if m:
                    pass1_text = pass1_text.rstrip() + "\n" + m.group(1) + "\n"
                    meta_modified = True

    # Clean footer junk (---- and OCR noise before citation-page-bottom).
    # Small removals (≤18 chars) are applied automatically; larger ones are
    # surfaced as suggestions in the caller.
    cleaned_text, footer_removed = clean_footer(pass1_text)
    if footer_removed <= 18 and footer_removed > 0:
        pass1_text = cleaned_text

    if (meta_modified or (0 < footer_removed <= 18)) and not dry_run:
        pass1_file.write_text(pass1_text, encoding="utf-8")

    return meta_modified, footer_removed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report changes without writing."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print each fixed file."
    )
    args = parser.parse_args(argv)

    fixed = 0
    checked = 0
    footers_cleaned = 0
    possible_footer_fixes: list[tuple[Path, int]] = []

    missing_wiki = 0

    # Group chunk dirs by band prefix to identify last chunk per band
    chunk_dirs = sorted(
        d
        for d in EXTRACTED_DIR.iterdir()
        if d.is_dir() and "_chunk" in d.name and (d / "pass1").is_dir()
    )
    last_chunk_per_band: set[Path] = set()
    prev_band = None
    prev_dir = None
    for d in chunk_dirs:
        band = d.name.split("_chunk")[0]
        if prev_band is not None and band != prev_band:
            last_chunk_per_band.add(prev_dir)
        prev_band = band
        prev_dir = d
    if prev_dir is not None:
        last_chunk_per_band.add(prev_dir)

    for chunk_dir in chunk_dirs:
        pass1_dir = chunk_dir / "pass1"

        # Check for missing wiki files p001..p025 (skip last chunk per band)
        if chunk_dir not in last_chunk_per_band:
            wiki_dir = chunk_dir / "wiki"
            for page_num in range(1, 26):
                expected = wiki_dir / f"p{page_num:03d}.wiki"
                if not expected.is_file():
                    print(f"  MISSING WIKI: {expected.relative_to(REPO_ROOT)}")
                    missing_wiki += 1

        for wiki_file in sorted(pass1_dir.glob("p*.wiki")):
            checked += 1
            meta_mod, footer_chars = fix_file(wiki_file, dry_run=args.dry_run)
            if meta_mod:
                fixed += 1
                if args.verbose:
                    prefix = "WOULD FIX" if args.dry_run else "FIXED"
                    print(f"  {prefix}: {wiki_file.relative_to(REPO_ROOT)}")
            if 0 < footer_chars <= 18:
                footers_cleaned += 1
                prefix = "WOULD CLEAN" if args.dry_run else "CLEANED"
                print(
                    f"  {prefix} FOOTER: {wiki_file.relative_to(REPO_ROOT)} ({footer_chars} chars)"
                )
            elif footer_chars > 18:
                possible_footer_fixes.append((wiki_file, footer_chars))

    print(f"\nChecked {checked} pass1 files")
    print(f"  Metadata {'would fix' if args.dry_run else 'fixed'}: {fixed}")
    print(
        f"  Footers {'would clean' if args.dry_run else 'cleaned'}: {footers_cleaned}"
    )
    if missing_wiki:
        print(f"  Missing wiki files: {missing_wiki}")
    if possible_footer_fixes:
        print(
            f"\nPossible footer fixes (>18 chars removed, not applied — {len(possible_footer_fixes)} files):"
        )
        for path, chars in possible_footer_fixes:
            print(f"  {path.relative_to(REPO_ROOT)} ({chars} chars)")


if __name__ == "__main__":
    main()
