"""Insert {{Artikel}} and {{End}} markers into a concatenated band wiki file.

Reads  data/splitting/{BandXX}/{BandXX}.wiki  and  {BandXX}.csv,
estimates article boundaries using page markers and article-start markers,
inserts {{Artikel ...}} at each detected start and {{End}} at each detected
end, and writes  data/splitting/{BandXX}/{BandXX}_split.wiki.

Review (and adjust) the resulting _split.wiki file before running the
splitter, which will cut it into individual article files.

Usage:
    python -m src.articles.marker_inserter [--band Band01] [--dry-run] [--verbose]
"""

import argparse
import csv
import re

from .boundaries import find_paragraph_before
from .formatter import build_artikel_template
from .helpers import REPO_ROOT

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"

_MARKERS = ("'''Patrozinium:", "'''Zum Bauwerk:", "'''Auftraggeber:")


# ---------------------------------------------------------------------------
# Helpers (copied / adapted from splitter.py)
# ---------------------------------------------------------------------------


def _page_region(lines: list[str], target_page: int) -> tuple[int, int] | None:
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == target_page:
            for j in range(i + 1, len(lines)):
                if re.search(r"<!--\s*citation-page-bottom:", lines[j]):
                    return (i, j)
            return (i, len(lines) - 1)

    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == target_page:
            for j in range(i - 1, -1, -1):
                if re.search(r"<!--\s*citation-page-bottom:", lines[j]):
                    for k in range(j + 1, i + 1):
                        if re.search(r"<!--\s*citation-page-top:", lines[k]):
                            return (k, i)
                    return (i, i)
                if re.search(r"<!--\s*citation-page-top:", lines[j]):
                    return (j, i)
            return (i, i)
    return None


def _find_marker_in_range(lines: list[str], start: int, end: int) -> int | None:
    for marker in _MARKERS:
        for i in range(start, end + 1):
            if lines[i].strip().startswith(marker):
                return i
    return None


def _find_page_top(lines: list[str], page: int) -> int | None:
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == page:
            return i
    return None


def _find_page_bottom(lines: list[str], page: int) -> int | None:
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == page:
            return i
    return None


def _find_split_template(lines: list[str], start: int, end: int) -> int | None:
    for i in range(start, end + 1):
        if lines[i].strip() == "{{Split}}":
            return i
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def insert_markers(
    band_prefix: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Estimate article boundaries and insert {{Artikel}}/{{End}} markers.

    Returns True if the split file was written (or would be in dry-run mode).
    """
    wiki_path = SPLITTING_DIR / band_prefix / f"{band_prefix}.wiki"
    csv_path = SPLITTING_DIR / band_prefix / f"{band_prefix}.csv"

    if not wiki_path.is_file() or not csv_path.is_file():
        if verbose:
            print(f"  SKIP {band_prefix} — missing splitting files")
        return False

    full_text = wiki_path.read_text(encoding="utf-8")
    lines = full_text.splitlines()

    with open(csv_path, encoding="utf-8") as f:
        articles = list(csv.DictReader(f))

    for row in articles:
        try:
            row["_seite_von"] = int(row["Seite_von"])
            row["_seite_bis"] = int(row["Seite_bis"])
        except (ValueError, KeyError):
            row["_seite_von"] = None
            row["_seite_bis"] = None

    articles.sort(
        key=lambda r: r["_seite_von"] if r["_seite_von"] is not None else 99999
    )

    # ── Find start line for each article (same logic as splitter.py) ─────────
    start_lines: list[int | None] = []

    for idx, row in enumerate(articles):
        sv = row["_seite_von"]
        if sv is None:
            start_lines.append(None)
            continue

        sv = int(sv)
        prev_sb_raw = articles[idx - 1]["_seite_bis"] if idx > 0 else None
        prev_sb = int(prev_sb_raw) if prev_sb_raw is not None else None
        pages_clean = prev_sb is None or prev_sb < sv

        start: int | None = None

        region = _page_region(lines, sv)
        if region is not None:
            split_tpl = _find_split_template(lines, region[0], region[1])
            if split_tpl is not None:
                start = split_tpl

        if start is None and pages_clean:
            start = _find_page_top(lines, sv)

        if start is None:
            if region is None:
                region = _page_region(lines, sv)
            if region is not None:
                marker_line = _find_marker_in_range(lines, region[0], region[1])
                if marker_line is not None:
                    start = find_paragraph_before(lines, marker_line)

        # Fallback: overlapping pages but no marker found — use page-top anyway.
        if start is None:
            start = _find_page_top(lines, sv)
            if start is None:
                start = _find_page_bottom(lines, sv)
            if start is not None:
                link = f"file://{wiki_path}:{start + 1}"
                print(
                    f"  WARN: inexact split point for {row.get('Bauwerk', '?')!r}"
                    f" (page {sv}, overlapping pages) — review: {link}"
                )
            else:
                print(
                    f"  ERROR: page {sv} not found in file for"
                    f" {row.get('Bauwerk', '?')!r} — skipping"
                )
        start_lines.append(start)

    # Pair (start_line, row), drop articles without a start line.
    split_points: list[tuple[int, dict]] = [
        (sl, articles[i]) for i, sl in enumerate(start_lines) if sl is not None
    ]
    split_points.sort(key=lambda x: x[0])

    if not split_points:
        if verbose:
            print(f"  SKIP {band_prefix} — no split points found")
        return False

    # ── Build ordered neighbour info ─────────────────────────────────────────
    for sp_idx, (_, row) in enumerate(split_points):
        row["_davor"] = split_points[sp_idx - 1][1]["Bauwerk"] if sp_idx > 0 else None
        row["_danach"] = (
            split_points[sp_idx + 1][1]["Bauwerk"]
            if sp_idx + 1 < len(split_points)
            else None
        )

    # ── Build the output lines with inserted markers ──────────────────────────
    # We process the lines in order, inserting {{Artikel}} at each start line
    # and {{End}} just before the next article's start (or at EOF).
    output_lines: list[str] = []
    pending_insertions: list[
        tuple[int, str]
    ] = []  # (line_index, text_to_insert_before)

    for sp_idx, (start_line, row) in enumerate(split_points):
        # Determine end line: line just before the next article's start, or EOF.
        if sp_idx + 1 < len(split_points):
            end_line = split_points[sp_idx + 1][0]
        else:
            end_line = len(lines)

        autor_str = row.get("Autor", "")
        autoren = [a.strip() for a in autor_str.split("/") if a.strip()]

        template = build_artikel_template(
            bauwerk=row["Bauwerk"],
            literaturangabe=row.get("Literaturangabe", ""),
            ort=row.get("Ort", ""),
            autoren=autoren,
            eigenschaft=row.get("Eigenschaft", ""),
            band=row["Band"],
            seite_von=row.get("_seite_von"),
            seite_bis=row.get("_seite_bis"),
            davor=row.get("_davor"),
            danach=row.get("_danach"),
        )

        pending_insertions.append((start_line, template + "\n"))
        pending_insertions.append((end_line, "{{End}}\n"))

    # Merge insertions: build a map from line_index → list of blocks to insert before it.
    insertions_map: dict[int, list[str]] = {}
    for line_idx, block in pending_insertions:
        insertions_map.setdefault(line_idx, []).append(block)

    for i, line in enumerate(lines):
        if i in insertions_map:
            for block in insertions_map[i]:
                output_lines.append(block)
        output_lines.append(line)

    # Handle insertions at EOF (line_idx == len(lines))
    if len(lines) in insertions_map:
        for block in insertions_map[len(lines)]:
            output_lines.append(block)

    out_text = "\n".join(output_lines) + "\n"
    out_path = SPLITTING_DIR / band_prefix / f"{band_prefix}_split.wiki"

    if dry_run:
        print(
            f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
            f"  ({len(out_text)} chars, {len(split_points)} articles)"
        )
    else:
        out_path.write_text(out_text, encoding="utf-8")
        if verbose:
            print(
                f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                f"  ({len(out_text)} chars, {len(split_points)} articles)"
            )
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without writing."
    )
    parser.add_argument(
        "--band",
        type=str,
        default=None,
        help="Process only this Band prefix (e.g. Band01).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed progress."
    )
    args = parser.parse_args(argv)

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(
            d.name
            for d in SPLITTING_DIR.iterdir()
            if d.is_dir() and (d / f"{d.name}.wiki").is_file()
        )

    for band_prefix in band_prefixes:
        print(f"Inserting markers: {band_prefix} …")
        insert_markers(band_prefix, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
