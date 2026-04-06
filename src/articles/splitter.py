"""Split a concatenated band wiki file into individual article files.

Loads {BandXX}.wiki and {BandXX}.csv from data/splitting/{BandXX}/,
identifies article start points using the CSV start pages and boundary
markers ('''Patrozinium:''' / '''Zum Bauwerk:'''), then writes each article
to data/formatted/{BandXX}/.

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_page_line(lines: list[str], target_page: int) -> int | None:
    """Find the start of the page region containing *target_page*.

    If target_page matches a citation-page-top, return that line directly.
    If it matches a citation-page-bottom, walk backwards to the **immediately**
    preceding citation-page-top (same page spread) so the boundary search
    covers the full spread but NOT an earlier spread.
    Returns the 0-based line index, or None.
    """
    # First: exact citation-page-top match
    for i, line in enumerate(lines):
        m_top = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", line)
        if m_top and int(m_top.group(1)) == target_page:
            return i

    # Fallback: citation-page-bottom match → walk back to its paired page-top
    for i, line in enumerate(lines):
        m_bot = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", line)
        if m_bot and int(m_bot.group(1)) == target_page:
            # Walk back, but stop if we hit another citation-page-bottom first
            # (that means we crossed into a different page spread)
            for j in range(i - 1, -1, -1):
                if re.search(r"<!--\s*citation-page-bottom:", lines[j]):
                    # Hit an earlier spread — find the page-top after that bottom
                    for k in range(j + 1, i + 1):
                        if re.search(r"<!--\s*citation-page-top:", lines[k]):
                            return k
                    return i  # no top found; use the bottom line
                if re.search(r"<!--\s*citation-page-top:", lines[j]):
                    return j
            return i  # no preceding top found

    return None


def _find_all_boundaries(lines: list[str], start: int, count: int) -> list[int]:
    """Find up to *count* article boundary lines starting from *start*.

    An article boundary is a '''Patrozinium:''' marker, or a '''Zum Bauwerk:'''
    marker that is NOT immediately preceded by a '''Patrozinium:''' (i.e. it
    starts an article on its own).

    Each boundary is the paragraph-start line (including the intro paragraph
    above the marker). Returns a list of 0-based line indices, sorted ascending.
    """
    boundaries: list[int] = []
    pos = start
    while len(boundaries) < count and pos < len(lines):
        # Search for the next Patrozinium, standalone Zum Bauwerk, or
        # standalone Auftraggeber (some articles lack Patrozinium/Zum Bauwerk
        # and use Auftraggeber as the first bold marker instead).
        found_at = None
        for k in range(pos, len(lines)):
            stripped = lines[k].strip()
            if stripped.startswith("'''Patrozinium:"):
                found_at = k
                break
            if stripped.startswith("'''Zum Bauwerk:"):
                # Only count as a new article if no Patrozinium directly above
                # (within 3 non-blank lines)
                has_patro_above = False
                for back in range(k - 1, max(pos - 1, k - 6), -1):
                    bs = lines[back].strip()
                    if bs.startswith("'''Patrozinium:"):
                        has_patro_above = True
                        break
                    if bs and not bs.startswith("'''"):
                        break
                if not has_patro_above:
                    found_at = k
                    break
            if stripped.startswith("'''Auftraggeber:"):
                # Tertiary fallback: only count if no Patrozinium or
                # Zum Bauwerk appears within 20 lines above.
                has_marker_above = False
                for back in range(k - 1, max(pos - 1, k - 20), -1):
                    bs = lines[back].strip()
                    if bs.startswith("'''Patrozinium:") or bs.startswith(
                        "'''Zum Bauwerk:"
                    ):
                        has_marker_above = True
                        break
                if not has_marker_above:
                    found_at = k
                    break
        if found_at is None:
            break
        para = find_paragraph_before(lines, found_at)
        boundaries.append(para)
        pos = found_at + 1  # continue searching after this marker
    return boundaries


def _find_chunk_info(lines: list[str], sp_line: int) -> tuple[int | None, int | None]:
    """Return (chunk_number, page_within_chunk) by searching backward for a dropbox link.

    Dropbox links look like: <!-- dropbox: .../BandXX_chunkNNN.pdf#page=P -->
    Searches up to 500 lines before sp_line.
    """
    for i in range(min(sp_line, len(lines) - 1), max(0, sp_line - 500), -1):
        m = re.search(r"chunk(\d+)\.pdf#page=(\d+)", lines[i])
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def _clean(text: str) -> str:
    """Strip leading/trailing blank lines."""
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def _normalize(s: str) -> str:
    """Lowercase and strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-zäöüß0-9 ]", "", s.lower()).strip()


def _find_heading_near(lines: list[str], page_line: int, bauwerk: str) -> int | None:
    """Find a == HEADING == or <!-- header: ... --> near *page_line* matching *bauwerk*.

    Searches forward up to 200 lines from page_line. Returns the line index
    of the heading, or None if no match.
    """
    # Build search tokens from the Bauwerk name:
    # "München, Schloss Harlaching" → try "Harlaching", "Schloss Harlaching"
    # Take the last significant part after comma
    bw_parts = [p.strip() for p in bauwerk.split(",")]
    search_terms: list[str] = []
    for part in bw_parts:
        normed = _normalize(part)
        if normed and len(normed) > 3:
            search_terms.append(normed)
    # Also use the full bauwerk name normalized
    search_terms.append(_normalize(bauwerk))

    end = min(page_line + 200, len(lines))
    for i in range(page_line, end):
        stripped = lines[i].strip()
        # Check == HEADING == lines
        heading_m = re.match(r"^==\s+(.+?)\s+==$", stripped)
        if heading_m:
            heading_text = _normalize(heading_m.group(1))
            for term in search_terms:
                if term in heading_text or heading_text in term:
                    return i
        # Check <!-- header: ... --> comments
        header_m = re.search(r"<!--\s*header:\s*(.+?)\s*-->", stripped)
        if header_m:
            header_text = _normalize(header_m.group(1))
            for term in search_terms:
                if term in header_text or header_text in term:
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

    # ── Phase 1: identify split line for each article ────────────────────────
    # For each article:
    #   1. Locate the citation-page line matching _seite_von
    #   2. Search forward from there for a heading or boundary marker that
    #      matches the article, using the Bauwerk name to disambiguate when
    #      multiple articles share the same page region.
    split_points: list[tuple[int, dict]] = []  # (line_index, row)
    missing: list[dict] = []

    for row in articles:
        sv = row["_seite_von"]
        if sv is None:
            missing.append(row)
            continue

        page_line = _find_page_line(lines, sv)
        if page_line is None:
            if verbose:
                print(
                    f"  WARN: page {sv} not found in {band_prefix} for {row.get('Bauwerk', '?')}"
                )
            missing.append(row)
            continue

        # Try to narrow down by finding the article's heading near the page
        bauwerk = row.get("Bauwerk", "")
        heading_line = _find_heading_near(lines, page_line, bauwerk)

        search_from = heading_line if heading_line is not None else page_line
        boundaries = _find_all_boundaries(lines, search_from, 1)

        if boundaries:
            split_points.append((boundaries[0], row))
        else:
            # No marker — use the heading or page line as start
            split_points.append((search_from, row))

    # Sort split points by line number
    split_points.sort(key=lambda x: x[0])

    # Resolve duplicates: when two articles land on the same line, search
    # forward for the next distinct boundary marker for the later one.
    # IMPORTANT: retries must not steal lines that are another article's
    # primary (first-choice) split point.
    primary_lines: set[int] = set()
    for sp_line, _ in split_points:
        primary_lines.add(sp_line)

    deduped: list[tuple[int, dict]] = []
    used_lines: set[int] = set()
    for sp_line, row in split_points:
        if sp_line not in used_lines:
            used_lines.add(sp_line)
            deduped.append((sp_line, row))
            continue
        # Find enough boundaries from the duplicate point to skip past claimed ones
        candidates = _find_all_boundaries(lines, sp_line, 10)
        resolved = False
        for alt in candidates:
            if alt not in used_lines and alt > sp_line and alt not in primary_lines:
                used_lines.add(alt)
                deduped.append((alt, row))
                resolved = True
                break
        if not resolved:
            if verbose:
                print(
                    f"  WARN: duplicate split at line {sp_line} for {row.get('Bauwerk', '?')}"
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
                print(
                    f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(before_text)} chars)"
                )
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(before_text + "\n", encoding="utf-8")
                if verbose:
                    print(
                        f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(before_text)} chars)"
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
            print(
                f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(article_text)} chars)"
            )
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(article_text, encoding="utf-8")
            if verbose:
                print(
                    f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(article_text)} chars)"
                )
        written += 1

    # After text: content after the last article's _seite_bis page
    if split_points:
        last_row = split_points[-1][1]
        last_sb = last_row.get("_seite_bis")
        if last_sb is not None:
            # Find the last citation-page-bottom matching _seite_bis
            after_start = None
            for i in range(len(lines) - 1, -1, -1):
                m = re.search(
                    r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", lines[i]
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
                            f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(after_text)} chars)"
                        )
                    else:
                        out_dir.mkdir(parents=True, exist_ok=True)
                        out_path.write_text(after_text + "\n", encoding="utf-8")
                        if verbose:
                            print(
                                f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(after_text)} chars)"
                            )
                    ba_written += 1

    return written, ba_written, missing
