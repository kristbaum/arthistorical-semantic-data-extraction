#!/usr/bin/env python3
"""Shift Band10 citation page numbers >= 14 by +2 in all wiki and pass1 files.

Pages 14 and 15 were missing from the Band10 scan, so every citation-page
number from 14 onwards is currently 2 less than the actual book page.

Only citation-page-top and citation-page-bottom comments are touched;
dropbox #page= references (PDF page numbers) are left unchanged.

Usage:
    python -m src.format.shift_band10_pages [--dry-run]
"""

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"

SHIFT_FROM = 14  # first book page number that needs correction
SHIFT_BY = 2
BAND_PREFIX = "Band10"

# Matches:  <!-- citation-page-top: Band10 p14 -->
#           <!-- citation-page-bottom: Band10 p127 -->
_CITATION_RE = re.compile(
    r"(<!--\s*citation-page-(?:top|bottom):\s*Band10\s+p)(\d+)(\s*-->)"
)


def _shift_line(line: str) -> str:
    """Return the line with any eligible citation page number shifted up."""
    def _replace(m: re.Match) -> str:
        page = int(m.group(2))
        if page >= SHIFT_FROM:
            page += SHIFT_BY
        return m.group(1) + str(page) + m.group(3)

    return _CITATION_RE.sub(_replace, line)


def shift_file(path: Path, *, dry_run: bool) -> int:
    """Shift citation page numbers in *path*. Returns number of changed lines."""
    text = path.read_text(encoding="utf-8")
    new_lines = [_shift_line(line) for line in text.splitlines(keepends=True)]
    new_text = "".join(new_lines)
    changed = sum(a != b for a, b in zip(text.splitlines(), new_text.splitlines()))
    if changed and not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    args = parser.parse_args()

    chunk_dirs = sorted(
        d for d in EXTRACTED_DIR.iterdir()
        if d.is_dir() and d.name.startswith(BAND_PREFIX + "_chunk")
    )

    total_files = 0
    total_lines = 0

    for chunk_dir in chunk_dirs:
        for subdir in ("wiki", "pass1"):
            sub = chunk_dir / subdir
            if not sub.is_dir():
                continue
            for wiki_file in sorted(sub.glob("p*.wiki")):
                changed = shift_file(wiki_file, dry_run=args.dry_run)
                if changed:
                    total_files += 1
                    total_lines += changed
                    prefix = "WOULD UPDATE" if args.dry_run else "UPDATED"
                    print(f"  {prefix}: {wiki_file.relative_to(REPO_ROOT)} ({changed} line(s))")

    action = "Would update" if args.dry_run else "Updated"
    print(f"\n{action} {total_lines} line(s) in {total_files} file(s) across Band10.")


if __name__ == "__main__":
    main()
