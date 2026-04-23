"""Report non-list articles that have a == heading == after == Quellen und Literatur ==.

Shows the number of characters of content after each detected heading.
With --apply, removes headings that have no content after them (0 chars).

After normalize_structure --apply, all bibliography headings are canonical, so
no fuzzy matching is needed.

Usage:
    python -m src.articles.check_bib_tail [--band Band01] [--apply]
"""

import argparse
import re

from .helpers import OUTPUT_DIR
from .normalize_structure import _get_lemma, _is_list_article

_BIB_HEADING = "== Quellen und Literatur =="
_HEADING_RE = re.compile(r"^==+\s*.+\s*==+\s*$")

# OSC 8 hyperlink: clickable in most modern terminals (including VS Code)
def _link(path, text: str) -> str:
    uri = path.as_uri()
    return f"\033]8;;{uri}\033\\{text}\033]8;;\033\\"


def check_band(band_prefix: str, apply: bool = False) -> int:
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        return 0

    hits = 0
    for path in sorted(band_dir.glob("*.wiki")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        lemma = _get_lemma(lines)
        if _is_list_article(lemma):
            continue

        # Find the canonical bib heading
        bib_idx = next(
            (i for i, l in enumerate(lines) if l.strip() == _BIB_HEADING), None
        )
        if bib_idx is None:
            continue

        # Collect all heading indices after the bib heading
        heading_indices = [
            i
            for i, line in enumerate(lines[bib_idx + 1 :], start=bib_idx + 1)
            if _HEADING_RE.match(line.strip())
        ]

        if not heading_indices:
            continue

        to_remove = []
        for j, hi in enumerate(heading_indices):
            next_boundary = heading_indices[j + 1] if j + 1 < len(heading_indices) else len(lines)
            char_count = len("".join(lines[hi + 1 : next_boundary]).strip())
            print(
                f"  {_link(path, str(path))}:{hi + 1}  {lines[hi].strip()}"
                f"  [{char_count} chars after]"
            )
            hits += 1
            if apply and char_count == 0:
                to_remove.append(hi)

        if to_remove:
            for hi in reversed(to_remove):
                lines.pop(hi)
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            path.write_text(new_text, encoding="utf-8")
            print(f"    → removed {len(to_remove)} empty heading(s) from {path.name}")

    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", metavar="BAND")
    parser.add_argument("--apply", action="store_true", help="Remove headings with no content after them")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    total = 0
    for bp in band_prefixes:
        total += check_band(bp, apply=args.apply)

    print(f"\n{total} heading(s) found after == Quellen und Literatur ==.")


if __name__ == "__main__":
    main()
