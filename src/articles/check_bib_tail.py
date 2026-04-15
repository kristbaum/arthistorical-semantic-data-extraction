"""Report non-list articles that have a == heading == after == Quellen und Literatur ==.

After normalize_structure --apply, all bibliography headings are canonical, so
no fuzzy matching is needed.

Usage:
    python -m src.articles.check_bib_tail [--band Band01]
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


def check_band(band_prefix: str) -> int:
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        return 0

    hits = 0
    for path in sorted(band_dir.glob("*.wiki")):
        lines = path.read_text(encoding="utf-8").splitlines()
        lemma = _get_lemma(lines)
        if _is_list_article(lemma):
            continue

        # Find the canonical bib heading
        bib_idx = next(
            (i for i, l in enumerate(lines) if l.strip() == _BIB_HEADING), None
        )
        if bib_idx is None:
            continue

        # Check for any == heading == after it
        for i, line in enumerate(lines[bib_idx + 1 :], start=bib_idx + 1):
            if _HEADING_RE.match(line.strip()):
                print(f"  {_link(path, str(path))}:{i + 1}  {line.strip()}")
                hits += 1

    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", metavar="BAND")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    total = 0
    for bp in band_prefixes:
        total += check_band(bp)

    print(f"\n{total} heading(s) found after == Quellen und Literatur ==.")


if __name__ == "__main__":
    main()
