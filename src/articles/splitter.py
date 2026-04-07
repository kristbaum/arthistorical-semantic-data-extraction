"""Split a concatenated band wiki file into individual article files.

Loads {BandXX}.wiki and {BandXX}.csv from data/splitting/{BandXX}/,
identifies article start points using the CSV start pages and boundary
markers ('''Patrozinium:''' / '''Zum Bauwerk:''' / '''Auftraggeber:'''),
then writes each article to data/formatted/{BandXX}/.

Text before the first article → before_articles.wiki
Text after the last article  → after_articles.wiki
Everything in between is assigned to articles by cutting at boundaries.

Usage (via assemble.py):
    python -m src.articles [--dry-run] [--band 'Band 1'] [--verbose]
"""

import csv
import re

from .boundaries import find_paragraph_before
from .formatter import format_article
from .helpers import (
    OUTPUT_DIR,
    REPO_ROOT,
    sanitize_filename,
)

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"

# Markers that signal the start of an article, in priority order.
_MARKERS = ("'''Patrozinium:", "'''Zum Bauwerk:", "'''Auftraggeber:")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _page_region(lines: list[str], target_page: int) -> tuple[int, int] | None:
    """Return the (start, end) line range for *target_page*.

    Looks for citation-page-top first; if found, the region runs from that
    line down to the next citation-page-bottom.  If only a citation-page-bottom
    is found, the region runs from the preceding citation-page-top up to that
    bottom line.  Returns None if the page cannot be located at all.
    """
    # Try citation-page-top first
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == target_page:
            # Scan forward for the matching bottom
            for j in range(i + 1, len(lines)):
                if re.search(r"<!--\s*citation-page-bottom:", lines[j]):
                    return (i, j)
            return (i, len(lines) - 1)

    # Fallback: citation-page-bottom → walk back to paired top
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == target_page:
            for j in range(i - 1, -1, -1):
                if re.search(r"<!--\s*citation-page-bottom:", lines[j]):
                    # Hit an earlier spread; top must be between j and i
                    for k in range(j + 1, i + 1):
                        if re.search(r"<!--\s*citation-page-top:", lines[k]):
                            return (k, i)
                    return (i, i)  # no top found
                if re.search(r"<!--\s*citation-page-top:", lines[j]):
                    return (j, i)
            return (i, i)

    return None


def _find_marker_in_range(lines: list[str], start: int, end: int) -> int | None:
    """Find the first article-start marker between *start* and *end* (inclusive).

    Searches for '''Patrozinium:''', '''Zum Bauwerk:''', and '''Auftraggeber:'''
    in priority order — returns the first hit of the highest-priority marker.
    """
    for marker in _MARKERS:
        for i in range(start, end + 1):
            if lines[i].strip().startswith(marker):
                return i
    return None


def _clean(text: str) -> str:
    """Strip leading/trailing blank lines."""
    ls = text.split("\n")
    while ls and ls[0].strip() == "":
        ls.pop(0)
    while ls and ls[-1].strip() == "":
        ls.pop()
    return "\n".join(ls)


def _find_page_top(lines: list[str], page: int) -> int | None:
    """Return the line index of citation-page-top for *page*, or None."""
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == page:
            return i
    return None


def _find_page_bottom(lines: list[str], page: int) -> int | None:
    """Return the line index of citation-page-bottom for *page*, or None."""
    for i, line in enumerate(lines):
        m = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", line)
        if m and int(m.group(1)) == page:
            return i
    return None


# ---------------------------------------------------------------------------
# Main splitting logic
# ---------------------------------------------------------------------------


def split_band(
    band_prefix: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int, list[dict]]:
    """Split a concatenated band file into articles.

    Returns (written_count, before_after_count, missing_rows).
    """
    wiki_path = SPLITTING_DIR / band_prefix / f"{band_prefix}.wiki"
    csv_path = SPLITTING_DIR / band_prefix / f"{band_prefix}.csv"

    if not wiki_path.is_file() or not csv_path.is_file():
        if verbose:
            print(f"  SKIP {band_prefix} — missing splitting files")
        return 0, 0, []

    full_text = wiki_path.read_text(encoding="utf-8")
    lines = full_text.splitlines()

    # Read CSV
    with open(csv_path, encoding="utf-8") as f:
        articles = list(csv.DictReader(f))

    for row in articles:
        try:
            row["_seite_von"] = int(row["Seite_von"])
            row["_seite_bis"] = int(row["Seite_bis"])
        except (ValueError, KeyError):
            row["_seite_von"] = None
            row["_seite_bis"] = None

    # Sort by start page
    articles.sort(
        key=lambda r: r["_seite_von"] if r["_seite_von"] is not None else 99999
    )

    # ── Phase 1: find each article's start line ──────────────────────────────
    # Strategy (in order of preference):
    #   1. No page overlap with predecessor → use citation-page-top directly.
    #   2. Pages overlap (or page-top not found) → search for a split marker
    #      (Patrozinium / Zum Bauwerk / Auftraggeber) on the start-page region.
    #   Only emit an ERROR when all attempts for an article fail.

    # Parallel lists: start_lines[i] corresponds to articles[i].
    start_lines: list[int | None] = []
    missing: list[dict] = []

    for idx, row in enumerate(articles):
        sv = row["_seite_von"]
        if sv is None:
            start_lines.append(None)
            missing.append(row)
            continue

        sv = int(sv)  # guaranteed int by the parse block above
        prev_sb_raw = articles[idx - 1]["_seite_bis"] if idx > 0 else None
        prev_sb = int(prev_sb_raw) if prev_sb_raw is not None else None
        pages_clean = prev_sb is None or prev_sb < sv

        start: int | None = None

        # Try 1: clean page boundary → use page-top directly.
        if pages_clean:
            start = _find_page_top(lines, sv)

        # Try 2: overlapping pages (or page-top not found) → marker search.
        if start is None:
            region = _page_region(lines, sv)
            if region is not None:
                marker_line = _find_marker_in_range(lines, region[0], region[1])
                if marker_line is not None:
                    start = find_paragraph_before(lines, marker_line)

        if start is None:
            print(
                f"  ERROR: cannot find split point for "
                f"{row.get('Bauwerk', '?')!r} (page {sv})"
            )
            start_lines.append(None)
            missing.append(row)
        else:
            start_lines.append(start)

    # Build split_points list from parallel arrays, sorted by line number.
    split_points: list[tuple[int, dict]] = [
        (sl, articles[i]) for i, sl in enumerate(start_lines) if sl is not None
    ]
    split_points.sort(key=lambda x: x[0])

    # ── Phase 2: cut the text ────────────────────────────────────────────────
    out_dir = OUTPUT_DIR / band_prefix
    written = 0
    ba_written = 0

    # Before text: everything before first split point
    if split_points:
        first_line = split_points[0][0]
        before_text = _clean("\n".join(lines[:first_line]))
        if before_text:
            out_path = out_dir / "before_articles.wiki"
            if dry_run:
                print(
                    f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                    f"  ({len(before_text)} chars)"
                )
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(before_text + "\n", encoding="utf-8")
                if verbose:
                    print(
                        f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                        f"  ({len(before_text)} chars)"
                    )
            ba_written += 1

    # Each article: from its split point to the next split point
    for idx, (sp_line, row) in enumerate(split_points):
        if idx + 1 < len(split_points):
            end_line = split_points[idx + 1][0]
        else:
            end_line = len(lines)

        content = _clean("\n".join(lines[sp_line:end_line]))
        if not content:
            missing.append(row)
            continue

        bauwerk = row["Bauwerk"]
        ort = row.get("Ort", "")
        eigenschaft = row.get("Eigenschaft", "")
        literaturangabe = row.get("Literaturangabe", "")
        autor_str = row.get("Autor", "")
        autoren = [a.strip() for a in autor_str.split("/") if a.strip()]

        # Neighbours in the sorted split_points list (already resolved).
        sp_idx = next(i for i, (_, r) in enumerate(split_points) if r is row)
        prev_bauwerk = split_points[sp_idx - 1][1]["Bauwerk"] if sp_idx > 0 else None
        next_bauwerk = (
            split_points[sp_idx + 1][1]["Bauwerk"]
            if sp_idx + 1 < len(split_points)
            else None
        )

        article_text = format_article(
            bauwerk,
            content,
            literaturangabe,
            ort,
            autoren,
            eigenschaft,
            row["Band"],
            seite_von=row.get("_seite_von"),
            seite_bis=row.get("_seite_bis"),
            davor=prev_bauwerk,
            danach=next_bauwerk,
        )

        lemma_filename = sanitize_filename(bauwerk) + ".wiki"
        out_path = out_dir / lemma_filename

        if dry_run:
            print(
                f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                f"  ({len(article_text)} chars)"
            )
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(article_text, encoding="utf-8")
            if verbose:
                print(
                    f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                    f"  ({len(article_text)} chars)"
                )
        written += 1

    # After text: content after the last article's _seite_bis page
    if split_points:
        last_row = split_points[-1][1]
        last_sb = last_row.get("_seite_bis")
        if last_sb is not None:
            after_start = None
            for i in range(len(lines) - 1, -1, -1):
                m = re.search(
                    r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->",
                    lines[i],
                )
                if m and int(m.group(1)) == last_sb:
                    after_start = i + 1
                    break
            if after_start is not None and after_start < len(lines):
                after_text = _clean("\n".join(lines[after_start:]))
                if after_text:
                    out_path = out_dir / "after_articles.wiki"
                    if dry_run:
                        print(
                            f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                            f"  ({len(after_text)} chars)"
                        )
                    else:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(after_text + "\n", encoding="utf-8")
                        if verbose:
                            print(
                                f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                                f"  ({len(after_text)} chars)"
                            )
                    ba_written += 1

    return written, ba_written, missing
