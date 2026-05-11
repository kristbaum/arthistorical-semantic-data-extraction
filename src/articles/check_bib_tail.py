"""Report non-list articles that have a == heading == after == Quellen und Literatur ==.

Shows the number of characters of content after each detected heading.
With --apply, moves each heading (and its content) to the start of the following
article (after the {{Artikel ...}} template block), using the |danach= field to
identify the following article.

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


def _get_danach(lines: list[str]) -> str:
    """Extract the |danach= value from the Artikel template."""
    for line in lines:
        m = re.match(r"^\s*\|danach=(.*)$", line)
        if m:
            return m.group(1).strip()
    return ""


def _find_template_end(lines: list[str]) -> int:
    """Return the index of the }} line that closes the Artikel template, or -1."""
    for i, line in enumerate(lines):
        if line.strip() == "}}":
            return i
    return -1


def collect_band(band_prefix: str):
    """Return list of (char_count, path, hi, heading_text, lines, text) tuples."""
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
        help="Move heading sections to the start of the following article (via |danach=)",
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

    for char_count, path, hi, heading_text, lines, text in all_results:
        danach = _get_danach(lines)
        following_path = path.parent / f"{danach}.wiki" if danach else None
        following_exists = following_path is not None and following_path.exists()
        print(
            f"  {_link(path, str(path))}:{hi + 1}  {heading_text}  [{char_count} chars after]"
            + (f"  → {danach}" if danach else "  → [no danach]")
            + ("" if following_exists else "  [missing!]")
        )

    if args.apply:
        # Process each source file once; move everything from the first detected
        # heading after the bibliography to the start of the |danach= article.
        seen_sources: set = set()
        ordered = sorted(all_results, key=lambda r: (str(r[1].parent), str(r[1]), r[2]))

        for _cc, path, _hi, _ht, _lines, _text in ordered:
            if path in seen_sources:
                continue
            seen_sources.add(path)

            # Re-read for freshness
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()

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

            first_hi = heading_indices[0]

            # Block to move: from the first heading to EOF
            content_to_move = lines[first_hi:]
            while content_to_move and not content_to_move[-1].strip():
                content_to_move.pop()

            # Resolve following article via |danach=
            danach = _get_danach(lines)
            if not danach:
                print(f"  [skip] {path.name}: no |danach= field found")
                continue

            following_path = path.parent / f"{danach}.wiki"
            if not following_path.exists():
                print(
                    f"  [skip] {path.name}: following article not found: {danach}.wiki"
                )
                continue

            # Rewrite source: drop from first_hi onwards, trim trailing blank lines
            new_source_lines = lines[:first_hi]
            while new_source_lines and not new_source_lines[-1].strip():
                new_source_lines.pop()
            new_source_text = "\n".join(new_source_lines) + (
                "\n" if text.endswith("\n") else ""
            )
            path.write_text(new_source_text, encoding="utf-8")

            # Insert content into following article after its }} template closer
            following_text = following_path.read_text(encoding="utf-8")
            following_lines = following_text.splitlines()
            template_end = _find_template_end(following_lines)
            if template_end == -1:
                print(
                    f"  [skip] {following_path.name}: no }} closing the Artikel template"
                )
                continue

            insert_block = [""] + content_to_move + [""]
            new_following_lines = (
                following_lines[: template_end + 1]
                + insert_block
                + following_lines[template_end + 1 :]
            )
            new_following_text = "\n".join(new_following_lines) + (
                "\n" if following_text.endswith("\n") else ""
            )
            following_path.write_text(new_following_text, encoding="utf-8")

            print(
                f"  → moved {len(content_to_move)} line(s) from {path.name}"
                f" to {following_path.name}"
            )

    print(f"\n{len(all_results)} heading(s) found after == Quellen und Literatur ==.")


if __name__ == "__main__":
    main()
