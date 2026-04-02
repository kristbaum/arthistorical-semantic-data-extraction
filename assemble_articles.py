#!/usr/bin/env python3
"""Assemble complete MediaWiki articles from pass1 page files using the CSV metadata.

For each row in Liste_Bände.csv:
  1. Find the pass1/*.wiki file whose citation-page-top matches (Band, Seite_von)
  2. On that page, locate the article start by searching for '''Patrozinium:''' or
     '''Zum Bauwerk:''', then include the paragraph above that marker
  3. Collect content from Seite_von through Seite_bis pages
  4. Prepend metadata categories and Literaturangabe template
  5. Write to data/formatted/BandXX/<Bauwerk>.wiki

Articles that cannot be matched are saved to data/formatted/missing_articles.csv.
"""

import argparse
import csv
import re
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"
META_CSV = REPO_ROOT / "data" / "meta" / "Liste_Bände.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "formatted"

# ── CLI ───────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--dry-run", action="store_true", help="Print plan without writing files."
)
parser.add_argument(
    "--band", type=str, default=None, help="Process only this Band (e.g. 'Band 1')."
)
parser.add_argument(
    "--verbose", "-v", action="store_true", help="Print detailed progress."
)
args = parser.parse_args()

# ── Helpers ───────────────────────────────────────────────────────────────────


def csv_band_to_dir_prefix(band_csv: str) -> str:
    """Convert CSV band name to directory prefix.

    'Band 1'      -> 'Band01'
    'Band 3, I'   -> 'Band03-1'
    'Band 12, II' -> 'Band12-2'
    """
    m = re.match(r"Band\s+(\d+)(?:,\s*(I+))?", band_csv)
    if not m:
        return ""
    num = int(m.group(1))
    part = m.group(2)
    prefix = f"Band{num:02d}"
    if part:
        roman_map = {"I": 1, "II": 2, "III": 3}
        prefix += f"-{roman_map.get(part, 1)}"
    return prefix


def band_chunk_key(chunk_dir: Path) -> tuple[int, int, int]:
    """Sort key for directory names like Band01_chunk002 or Band03-1_chunk001."""
    m = re.match(r"Band(\d+)(?:-(\d+))?_chunk(\d+)", chunk_dir.name)
    if m:
        return int(m.group(1)), int(m.group(2) or 0), int(m.group(3))
    return (999, 999, 999)


def page_sort_key(path: Path) -> int:
    m = re.match(r"p(\d+)\.wiki$", path.name)
    return int(m.group(1)) if m else -1


def extract_citation_page(text: str, which: str = "top") -> int | None:
    """Extract the book page number from a citation-page-top/bottom comment.

    Returns the integer page number, or None if not found.
    """
    pattern = rf"<!--\s*citation-page-{which}:\s*\S+\s+p(\d+)\s*-->"
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def extract_citation_band(text: str) -> str | None:
    """Extract the Band identifier from a citation-page-top comment (e.g. 'Band02')."""
    m = re.search(r"<!--\s*citation-page-top:\s*(\S+)\s+p\d+\s*-->", text)
    return m.group(1) if m else None


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename, preserving umlauts."""
    # Replace characters not allowed in filenames
    name = name.replace("/", "-")
    name = name.replace("\\", "-")
    name = name.replace(":", " -")
    name = re.sub(r'[<>"|?*]', "", name)
    # Collapse multiple spaces/dashes
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ── Build page index ──────────────────────────────────────────────────────────


def build_page_index() -> dict[str, dict[int, list[tuple[Path, str]]]]:
    """Build an index: band_prefix -> {book_page_number -> [(file_path, full_text), ...]}.

    A single book page may appear BOTH as citation-page-top and citation-page-bottom
    of adjacent files.  We include all files that reference the page, in chunk order.
    Also builds an ordered list of all files per band.
    """
    index: dict[str, dict[int, list[tuple[Path, str]]]] = {}

    for chunk_dir in sorted(EXTRACTED_DIR.iterdir(), key=band_chunk_key):
        pass1_dir = chunk_dir / "pass1"
        wiki_dir = chunk_dir / "wiki"

        # Prefer pass1/, fall back to wiki/
        source_dir = pass1_dir if pass1_dir.is_dir() else wiki_dir
        if not source_dir.is_dir():
            continue

        band_prefix = re.match(r"(Band\d+(?:-\d+)?)", chunk_dir.name)
        if not band_prefix:
            continue
        bp = band_prefix.group(1)

        if bp not in index:
            index[bp] = {}

        for wiki_file in sorted(source_dir.glob("p*.wiki"), key=page_sort_key):
            text = wiki_file.read_text(encoding="utf-8")
            if source_dir == pass1_dir:
                text = _ensure_citation_metadata(wiki_file, text)

            page_top = extract_citation_page(text, "top")
            page_bottom = extract_citation_page(text, "bottom")

            if page_top is not None:
                index[bp].setdefault(page_top, [])
                entry = (wiki_file, text)
                if entry not in [(e[0], e[1]) for e in index[bp][page_top]]:
                    index[bp][page_top].append(entry)

            if page_bottom is not None and page_bottom != page_top:
                index[bp].setdefault(page_bottom, [])
                entry = (wiki_file, text)
                if entry not in [(e[0], e[1]) for e in index[bp][page_bottom]]:
                    index[bp][page_bottom].append(entry)

    return index


def _ensure_citation_metadata(pass1_file: Path, pass1_text: str) -> str:
    """If the pass1 file lacks citation-page-top or bottom, copy from the wiki/ sibling."""
    has_top = "citation-page-top:" in pass1_text
    has_bottom = "citation-page-bottom:" in pass1_text

    if has_top and has_bottom:
        return pass1_text

    wiki_file = pass1_file.parent.parent / "wiki" / pass1_file.name
    if not wiki_file.is_file():
        return pass1_text

    wiki_text = wiki_file.read_text(encoding="utf-8")

    if not has_top:
        # Extract all header metadata from wiki version
        meta_lines: list[str] = []
        for line in wiki_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("<!--") and (
                "citation-page" in stripped or "dropbox:" in stripped
            ):
                meta_lines.append(line)
            elif meta_lines and stripped == "":
                continue
            elif meta_lines:
                break
        if meta_lines:
            pass1_text = "\n".join(meta_lines) + "\n\n" + pass1_text

    if not has_bottom:
        # Extract citation-page-bottom from wiki version and append
        m = re.search(r"(<!--\s*citation-page-bottom:.*?-->)", wiki_text)
        if m:
            pass1_text = pass1_text.rstrip() + "\n" + m.group(1) + "\n"

    return pass1_text


def build_ordered_files(band_prefix: str) -> list[tuple[Path, str]]:
    """Return all pass1 wiki files for a band, ordered by chunk then page, with text cached.

    If a pass1 file lacks citation-page-top metadata, the comment is copied from
    the corresponding wiki/ file.  If a chunk has no pass1/ folder at all, the
    wiki/ folder is used instead.
    """
    result: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    for chunk_dir in sorted(EXTRACTED_DIR.iterdir(), key=band_chunk_key):
        if not chunk_dir.name.startswith(band_prefix + "_chunk"):
            continue

        pass1_dir = chunk_dir / "pass1"
        wiki_dir = chunk_dir / "wiki"

        # Prefer pass1/, fall back to wiki/
        source_dir = pass1_dir if pass1_dir.is_dir() else wiki_dir
        if not source_dir.is_dir():
            continue

        for wiki_file in sorted(source_dir.glob("p*.wiki"), key=page_sort_key):
            if wiki_file not in seen:
                seen.add(wiki_file)
                text = wiki_file.read_text(encoding="utf-8")
                if source_dir == pass1_dir:
                    text = _ensure_citation_metadata(wiki_file, text)
                result.append((wiki_file, text))
    return result


# ── Article boundary detection ────────────────────────────────────────────────


def find_article_start_line(lines: list[str]) -> int | None:
    """Find the line index of '''Patrozinium:''' or '''Zum Bauwerk:''' in a page.

    Returns the 0-based line index, or None if neither marker is found.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("'''Patrozinium:'''") or stripped.startswith(
            "'''Patrozinium:"
        ):
            return i
        if stripped.startswith("'''Zum Bauwerk:'''") or stripped.startswith(
            "'''Zum Bauwerk:"
        ):
            return i
    return None


def find_paragraph_before(lines: list[str], marker_line: int) -> int:
    """Find the start of the prose paragraph just above the marker line.

    Walks upward from marker_line-1, skipping blank lines, then collecting
    non-blank lines until a blank line or a comment/header/heading line.
    Returns the 0-based line index where the paragraph starts.
    """
    # Skip blank lines immediately above the marker
    i = marker_line - 1
    while i >= 0 and lines[i].strip() == "":
        i -= 1

    if i < 0:
        return marker_line  # No paragraph above

    # Now walk upward through the prose paragraph
    while i >= 0:
        stripped = lines[i].strip()
        if stripped == "":
            return i + 1
        # Stop at comments, headings, image tags
        if stripped.startswith("<!--") and (
            "citation-page" in stripped or "header:" in stripped
        ):
            return i + 1
        if re.match(r"^==\s+.*\s+==$", stripped):
            # This is a section heading — include it as it might be the article title
            return i
        if stripped.startswith("[[File:") or stripped.startswith("[[Datei:"):
            return i + 1
        i -= 1

    return 0


def find_next_article_start(lines: list[str], after_line: int) -> int | None:
    """Find the next '''Patrozinium:''' or '''Zum Bauwerk:''' after after_line.

    Returns the line index of the prose paragraph start before the next marker,
    or None if no next article is found.
    """
    for i in range(after_line, len(lines)):
        stripped = lines[i].strip()
        if (
            stripped.startswith("'''Patrozinium:'''")
            or stripped.startswith("'''Patrozinium:")
            or stripped.startswith("'''Zum Bauwerk:'''")
            or stripped.startswith("'''Zum Bauwerk:")
        ):
            # Found next article boundary — return the paragraph start before it
            return find_paragraph_before(lines, i)
    return None


# ── Collect article content ───────────────────────────────────────────────────


def _find_by_name(
    bauwerk: str,
    ordered_files: list[tuple[Path, str]],
) -> tuple[Path | None, str | None, int | None]:
    """Fallback: find the article start by searching for the building name.

    Extracts the location name (e.g. "Ammerfeld") and looks for a file containing
    both '''Patrozinium:''' and the location name near each other.

    Returns (path, text, marker_line_index) or (None, None, None).
    """
    location = bauwerk.split(",")[0].strip()
    if not location:
        return None, None, None

    loc_upper = location.upper()

    for fpath, ftext in ordered_files:
        upper_text = ftext.upper()
        ftext.splitlines()
        upper_lines = upper_text.splitlines()

        if loc_upper not in upper_text:
            continue

        # Find each Patrozinium marker and check if location is above it
        for i, uline in enumerate(upper_lines):
            if not (
                uline.strip().startswith("'''PATROZINIUM:")
                or uline.strip().startswith("'''ZUM BAUWERK:")
            ):
                continue
            # Check preceding ~30 lines for the location name
            search_start = max(0, i - 30)
            preceding = "\n".join(upper_lines[search_start:i])
            if loc_upper in preceding:
                return fpath, ftext, i

    # Second pass: header comments
    for fpath, ftext in ordered_files:
        upper_text = ftext.upper()
        ftext.splitlines()
        upper_lines = upper_text.splitlines()

        if f"HEADER: {loc_upper}" not in upper_text:
            continue

        for i, uline in enumerate(upper_lines):
            if uline.strip().startswith("'''PATROZINIUM:") or uline.strip().startswith(
                "'''ZUM BAUWERK:"
            ):
                # Check if a header comment with our location precedes this marker
                search_start = max(0, i - 30)
                preceding = "\n".join(upper_lines[search_start:i])
                if f"HEADER: {loc_upper}" in preceding:
                    return fpath, ftext, i

    return None, None, None


def collect_article_content(
    band_prefix: str,
    seite_von: int,
    seite_bis: int,
    page_index: dict[str, dict[int, list[tuple[Path, str]]]],
    ordered_files: list[tuple[Path, str]],
    next_article_seite_von: int | None,
    bauwerk: str = "",
) -> str | None:
    """Collect the content for one article spanning seite_von to seite_bis.

    Strategy:
    1. Find the file containing citation-page-top matching seite_von
    2. In that file, find '''Patrozinium:''' or '''Zum Bauwerk:''' and include
       the paragraph above it
    3. Continue collecting through all files up to seite_bis
    4. On the last page (seite_bis), if another article starts, stop before it
    5. If page-based lookup fails, search by building name (Bauwerk)

    Returns the collected text, or None if the start page can't be found.
    """
    bp_index = page_index.get(band_prefix, {})

    # Find the file that contains the starting page.
    start_file = None
    start_text = None

    # 1. Exact citation-page-top match
    for fpath, ftext in bp_index.get(seite_von, []):
        top = extract_citation_page(ftext, "top")
        if top == seite_von:
            start_file = fpath
            start_text = ftext
            break

    # 2. The page appears as citation-page-bottom → article starts mid-file
    if start_file is None:
        for fpath, ftext in bp_index.get(seite_von, []):
            bottom = extract_citation_page(ftext, "bottom")
            if bottom == seite_von:
                start_file = fpath
                start_text = ftext
                break

    # 3. Page is between some file's top and bottom (no explicit mention)
    if start_file is None:
        for page_files in bp_index.values():
            for fpath, ftext in page_files:
                top = extract_citation_page(ftext, "top")
                bottom = extract_citation_page(ftext, "bottom")
                if (
                    top is not None
                    and bottom is not None
                    and top <= seite_von <= bottom
                ):
                    start_file = fpath
                    start_text = ftext
                    break
            if start_file is not None:
                break

    # 4. Name-based fallback: search all files of this band for the Bauwerk name
    name_marker_line = None
    if start_file is None and bauwerk:
        start_file, start_text, name_marker_line = _find_by_name(bauwerk, ordered_files)

    if start_file is None or start_text is None:
        return None

    start_lines = start_text.splitlines()

    # Use the marker line from name-based search if available
    if name_marker_line is not None:
        marker_line = name_marker_line
    else:
        marker_line = find_article_start_line(start_lines)

    if marker_line is None:
        # No Patrozinium or Zum Bauwerk found on the start page — possibly
        # the article structure is different. Try to find content starting
        # after the header comment.
        # Look for a == HEADING == that might be the article title
        for i, line in enumerate(start_lines):
            stripped = line.strip()
            if (
                re.match(r"^==\s+[A-ZÄÖÜ]", stripped)
                and not stripped.startswith("== Befund")
                and not stripped.startswith("== Beschreibung")
            ):
                marker_line = i
                break

    if marker_line is None:
        return None

    # Find paragraph start above the marker
    if marker_line is not None:
        article_start = find_paragraph_before(start_lines, marker_line)
    else:
        article_start = 0

    # Build the file index position mapping
    file_to_idx = {fpath: idx for idx, (fpath, _) in enumerate(ordered_files)}

    if start_file not in file_to_idx:
        return None

    start_idx = file_to_idx[start_file]
    content_parts: list[str] = []

    # First file: from article_start to end (or next article on same page)
    first_file_lines = start_lines[article_start:]

    # Check if there's another article starting on the same page after our marker
    start_lines[marker_line + 1 :]
    next_on_same_page = find_next_article_start(start_lines, marker_line + 1)

    if next_on_same_page is not None and next_on_same_page > article_start:
        # There's another article on this same page — only take up to that point
        first_file_lines = start_lines[article_start:next_on_same_page]

    content_parts.append("\n".join(first_file_lines))

    # If article is only on one page and we already trimmed it, we're done
    if next_on_same_page is not None and seite_von == seite_bis:
        return _clean_content("\n".join(content_parts))

    # Continue through subsequent files
    for idx in range(start_idx + 1, len(ordered_files)):
        fpath, ftext = ordered_files[idx]
        page_top = extract_citation_page(ftext, "top")
        page_bottom = extract_citation_page(ftext, "bottom")

        # Determine if this file is still within our article's page range
        if page_top is not None and page_top > seite_bis:
            break
        if page_bottom is not None and page_bottom > seite_bis + 1:
            # This file extends beyond our range — check if we need part of it
            pass

        flines = ftext.splitlines()

        # Check if a new article starts on this page
        find_article_start_line(flines)

        if page_top is not None and page_top > seite_bis:
            break

        # If this is the last page or goes beyond, check for next article boundary
        if page_top is not None and page_top >= seite_bis:
            # On the boundary page — check for next article
            if next_article_seite_von is not None and page_top is not None:
                next_marker = find_next_article_start(flines, 0)
                if next_marker is not None:
                    content_parts.append("\n".join(flines[:next_marker]))
                else:
                    content_parts.append(ftext)
            else:
                content_parts.append(ftext)
            break
        elif page_bottom is not None and page_bottom > seite_bis:
            # File straddles the boundary
            next_marker = find_next_article_start(flines, 0)
            if next_marker is not None:
                content_parts.append("\n".join(flines[:next_marker]))
            else:
                content_parts.append(ftext)
            break
        else:
            content_parts.append(ftext)

    return _clean_content("\n".join(content_parts))


def _clean_content(text: str) -> str:
    """Strip leading/trailing whitespace from collected article content."""
    # Remove leading blank lines
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


# ── Format output ─────────────────────────────────────────────────────────────


def format_article(
    bauwerk: str,
    content: str,
    literaturangabe: str,
    ort: str,
    autoren: list[str],
    eigenschaft: str,
    band: str,
) -> str:
    """Format the final article with metadata categories and templates."""
    parts: list[str] = []

    # Categories
    categories: list[str] = []
    if ort:
        categories.append(f"[[Kategorie:{ort}]]")
    for autor in autoren:
        autor = autor.strip()
        if autor:
            categories.append(f"[[Kategorie:{autor}]]")
    if eigenschaft:
        categories.append(f"[[Kategorie:{eigenschaft}]]")
    if band:
        categories.append(f"[[Kategorie:{band}]]")

    # Literaturangabe template
    if literaturangabe:
        parts.append(f"{{{{Literaturangabe|text={literaturangabe}}}}}")
        parts.append("")

    # Main content
    parts.append(content)

    # Categories at the bottom
    if categories:
        parts.append("")
        parts.extend(categories)

    return "\n".join(parts) + "\n"


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    print(f"Reading CSV: {META_CSV}")
    rows: list[dict] = []
    with open(META_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if args.band and row["Band"] != args.band:
                continue
            rows.append(row)

    print(f"  {len(rows)} articles to process")

    # Sort rows by Band then Seite_von for sequential processing
    def row_sort_key(r):
        band = r["Band"]
        m = re.match(r"Band\s+(\d+)(?:,\s*(I+))?", band)
        band_num = int(m.group(1)) if m else 999
        part = m.group(2) if m else ""
        roman_map = {"I": 1, "II": 2, "III": 3, "": 0}
        band_part = roman_map.get(part, 0)
        try:
            seite = int(r["Seite_von"])
        except (ValueError, KeyError):
            seite = 9999
        return (band_num, band_part, seite)

    rows.sort(key=row_sort_key)

    print("Building page index...")
    page_index = build_page_index()
    total_pages = sum(len(pages) for pages in page_index.values())
    print(f"  Indexed {total_pages} page entries across {len(page_index)} bands")

    # Cache ordered files per band
    ordered_files_cache: dict[str, list[tuple[Path, str]]] = {}

    missing: list[dict] = []
    written = 0
    skipped = 0

    for i, row in enumerate(rows):
        band = row["Band"]
        bauwerk = row["Bauwerk"]
        ort = row.get("Ort", "")
        eigenschaft = row.get("Eigenschaft", "")
        literaturangabe = row.get("Literaturangabe", "")
        autor_str = row.get("Autor", "")
        autoren = [a.strip() for a in autor_str.split("/") if a.strip()]

        try:
            seite_von = int(row["Seite_von"])
            seite_bis = int(row["Seite_bis"])
        except (ValueError, KeyError):
            if args.verbose:
                print(f"  SKIP: {bauwerk} — invalid page numbers")
            missing.append(row)
            skipped += 1
            continue

        band_prefix = csv_band_to_dir_prefix(band)
        if not band_prefix:
            if args.verbose:
                print(f"  SKIP: {bauwerk} — cannot map band '{band}'")
            missing.append(row)
            skipped += 1
            continue

        # Get ordered files for this band
        if band_prefix not in ordered_files_cache:
            ordered_files_cache[band_prefix] = build_ordered_files(band_prefix)

        ordered_files = ordered_files_cache[band_prefix]

        # Determine next article's start page (for boundary detection)
        next_seite_von = None
        if i + 1 < len(rows):
            next_row = rows[i + 1]
            if csv_band_to_dir_prefix(next_row["Band"]) == band_prefix:
                try:
                    next_seite_von = int(next_row["Seite_von"])
                except (ValueError, KeyError):
                    pass

        # Collect content
        content = collect_article_content(
            band_prefix,
            seite_von,
            seite_bis,
            page_index,
            ordered_files,
            next_seite_von,
            bauwerk=bauwerk,
        )

        if content is None:
            if args.verbose:
                print(
                    f"  MISS: {bauwerk} — no matching content for {band_prefix} p{seite_von}"
                )
            missing.append(row)
            skipped += 1
            continue

        # Format the article
        article = format_article(
            bauwerk, content, literaturangabe, ort, autoren, eigenschaft, band
        )

        # Write output
        band_dir_name = band_prefix  # e.g. Band01, Band03-1
        out_dir = OUTPUT_DIR / band_dir_name
        lemma_filename = sanitize_filename(bauwerk) + ".wiki"
        out_path = out_dir / lemma_filename

        if args.dry_run:
            print(
                f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(article)} chars)"
            )
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(article, encoding="utf-8")
            if args.verbose:
                print(
                    f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(article)} chars)"
                )

        written += 1

    # Write missing articles CSV
    if missing:
        missing_path = OUTPUT_DIR / "missing_articles.csv"
        if args.dry_run:
            print(f"\nWOULD WRITE missing_articles.csv with {len(missing)} entries")
        else:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(missing_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=missing[0].keys())
                writer.writeheader()
                writer.writerows(missing)
            print(f"\nWrote missing_articles.csv with {len(missing)} entries")

    print(f"\nDone: {written} articles written, {skipped} missing/skipped")


if __name__ == "__main__":
    main()
