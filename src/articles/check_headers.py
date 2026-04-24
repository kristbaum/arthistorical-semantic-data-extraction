"""Report all non-canonical == headings == found in formatted articles.

Canonical headings (kept as-is):
    == Befund ==
    == Beschreibung und Ikonologie ==
    == Quellen und Literatur ==

All other == heading == lines are reported (any number of = signs).
With --apply, the heading markup (= signs) is stripped, leaving plain text.

Usage:
    python -m src.articles.check_headers [--band Band01] [--apply]
"""

import argparse
import re
from collections import defaultdict

from .helpers import OUTPUT_DIR
from .normalize_structure import _get_lemma, _is_list_article

_HEADING_RE = re.compile(r"^(==+)\s*(.+?)\s*(==+)\s*$")

_CANONICAL = {
    "Befund",
    "Beschreibung und Ikonologie",
    "Beschreibung und Ikonographie",
    "Quellen und Literatur",
    "Rekonstruierende Beschreibung und Ikonographie",
    "Zur Ikonologie"
}


# OSC 8 hyperlink: clickable in most modern terminals (including VS Code)
def _link(path, text: str) -> str:
    uri = path.as_uri()
    return f"\033]8;;{uri}\033\\{text}\033]8;;\033\\"


def collect_band(band_prefix: str):
    """Return list of (path, line_index, heading_text, full_line, lines, text) tuples."""
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

        for i, line in enumerate(lines):
            m = _HEADING_RE.match(line.strip())
            if not m:
                continue
            heading_text = m.group(2).strip()
            if heading_text in _CANONICAL:
                continue
            results.append((path, i, heading_text, line, lines, text))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", metavar="BAND")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Strip == markers from non-canonical headings (convert to plain text)",
    )
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    all_results = []
    for bp in band_prefixes:
        all_results.extend(collect_band(bp))

    for path, i, heading_text, line, _lines, _text in all_results:
        print(f"  {_link(path, str(path))}:{i + 1}  {line.strip()}")

    print(f"\n{len(all_results)} non-canonical heading(s) found.")

    if not args.apply:
        return

    # Group by file (keyed by path + id(lines) so each file's list object is unique)
    to_fix: dict = defaultdict(list)
    for path, i, heading_text, line, lines, text in all_results:
        to_fix[(path, id(lines))].append((i, lines, text, path))

    for (path, _), entries in to_fix.items():
        lines = entries[0][1]
        text = entries[0][2]
        changed = 0
        for i, _lines, _text, _path in entries:
            m = _HEADING_RE.match(lines[i].strip())
            if m:
                # Preserve any leading whitespace, replace with plain heading text
                leading = len(lines[i]) - len(lines[i].lstrip())
                lines[i] = lines[i][:leading] + m.group(2).strip()
                changed += 1
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
        path.write_text(new_text, encoding="utf-8")
        print(f"  → stripped {changed} heading(s) in {path.name}")


if __name__ == "__main__":
    main()
