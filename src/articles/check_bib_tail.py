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


def collect_band(band_prefix: str):
    """Return list of (char_count, path, line_index, heading_text, lines, text) tuples."""
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        return []

    results = []
    for path in sorted(band_dir.glob("*.wiki")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        lemma = _get_lemma(lines)
        if _is_list_article(lemma):
            continue

        bib_idx = next(
            (i for i, l in enumerate(lines) if l.strip() == _BIB_HEADING), None
        )
        if bib_idx is None:
            continue

        heading_indices = [
            i
            for i, line in enumerate(lines[bib_idx + 1 :], start=bib_idx + 1)
            if _HEADING_RE.match(line.strip())
        ]

        if not heading_indices:
            continue

        for j, hi in enumerate(heading_indices):
            next_boundary = (
                heading_indices[j + 1] if j + 1 < len(heading_indices) else len(lines)
            )
            char_count = len("".join(lines[hi + 1 : next_boundary]).strip())
            results.append((char_count, path, hi, lines[hi].strip(), lines, text))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", metavar="BAND")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove headings with no content after them",
    )
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    all_results = []
    for bp in band_prefixes:
        all_results.extend(collect_band(bp))

    all_results.sort(key=lambda r: r[0])

    # Group removals by file
    from collections import defaultdict

    to_remove_by_file: dict = defaultdict(list)

    for char_count, path, hi, heading_text, lines, text in all_results:
        print(
            f"  {_link(path, str(path))}:{hi + 1}  {heading_text}  [{char_count} chars after]"
        )
        if args.apply and char_count == 0:
            to_remove_by_file[(path, id(lines))].append((hi, lines, text, path))

    if args.apply:
        for (path, _), entries in to_remove_by_file.items():
            lines, text = entries[0][1], entries[0][2]
            indices = [e[0] for e in entries]
            for hi in sorted(indices, reverse=True):
                lines.pop(hi)
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            path.write_text(new_text, encoding="utf-8")
            print(f"    → removed {len(indices)} empty heading(s) from {path.name}")

    print(f"\n{len(all_results)} heading(s) found after == Quellen und Literatur ==.")


if __name__ == "__main__":
    main()
