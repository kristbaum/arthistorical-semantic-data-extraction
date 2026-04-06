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


def _find_marker_in_range(
    lines: list[str], start: int, end: int
) -> int | None:
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
    split_points: list[tuple[int, dict]] = []  # (line_index, row)
    missing: list[dict] = []

    for row in articles:
        sv = row["_seite_von"]
        if sv is None:
            missing.append(row)
            continue

        region = _page_region(lines, sv)
        if region is None:
            if verbose:
                print(
                    f"  WARN: page {sv} not found for "
                    f"{row.get('Bauwerk', '?')}"
                )
            missing.append(row)
            continue

        r_start, r_end = region
        marker_line = _find_marker_in_range(lines, r_start, r_end)

        if marker_line is not None:
            para_start = find_paragraph_before(lines, marker_line)
            split_points.append((para_start, row))
        else:
            # No marker on this page — use the region start as fallback
            if verbose:
                print(
                    f"  WARN: no marker on page {sv} for "
                    f"{row.get('Bauwerk', '?')} — using page start"
                )
            split_points.append((r_start, row))

    # Sort by line number
    split_points.sort(key=lambda x: x[0])

    # ── Resolve duplicates ───────────────────────────────────────────────────
    # When multiple articles land on the same line (same page, same first
    # marker), search forward from the marker for the *next* marker that
    # is not already claimed.  Primary lines are protected so retries
    # cannot steal another article's first-choice position.
    primary_lines: set[int] = {sp for sp, _ in split_points}
    deduped: list[tuple[int, dict]] = []
    used_lines: set[int] = set()

    for sp_line, row in split_points:
        if sp_line not in used_lines:
            used_lines.add(sp_line)
            deduped.append((sp_line, row))
            continue
        # Search forward for the next unclaimed marker
        resolved = False
        pos = sp_line + 1
        for _ in range(20):
            if pos >= len(lines):
                break
            for marker in _MARKERS:
                found = None
                for k in range(pos, min(pos + 2000, len(lines))):
                    if lines[k].strip().startswith(marker):
                        found = k
                        break
                if found is not None:
                    para = find_paragraph_before(lines, found)
                    if para not in used_lines and para not in primary_lines:
                        used_lines.add(para)
                        deduped.append((para, row))
                        resolved = True
                        break
            if resolved:
                break
            pos = (found or pos) + 1
        if not resolved:
            if verbose:
                print(
                    f"  WARN: duplicate split at line {sp_line} for "
                    f"{row.get('Bauwerk', '?')}"
                )
            missing.append(row)

    split_points = sorted(deduped, key=lambda x: x[0])

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
                print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                      f"  ({len(before_text)} chars)")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(before_text + "\n", encoding="utf-8")
                if verbose:
                    print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                          f"  ({len(before_text)} chars)")
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
        )

        lemma_filename = sanitize_filename(bauwerk) + ".wiki"
        out_path = out_dir / lemma_filename

        if dry_run:
            print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                  f"  ({len(article_text)} chars)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(article_text, encoding="utf-8")
            if verbose:
                print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                      f"  ({len(article_text)} chars)")
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
                        print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}"
                              f"  ({len(after_text)} chars)")
                    else:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(after_text + "\n", encoding="utf-8")
                        if verbose:
                            print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}"
                                  f"  ({len(after_text)} chars)")
                    ba_written += 1

    return written, ba_written, missing
