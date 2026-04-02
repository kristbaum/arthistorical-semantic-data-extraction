"""Build a page-number index over all pass1 wiki files."""

import re
from pathlib import Path

from .helpers import (
    EXTRACTED_DIR,
    band_chunk_key,
    extract_citation_page,
    page_sort_key,
)


def _has_pass1(band_prefix: str) -> bool:
    """Return True if at least one chunk of this band has a pass1/ folder."""
    for chunk_dir in EXTRACTED_DIR.iterdir():
        if chunk_dir.name.startswith(band_prefix + "_chunk"):
            if (chunk_dir / "pass1").is_dir():
                return True
    return False


def build_page_index() -> dict[str, dict[int, list[tuple[Path, str]]]]:
    """Build an index: band_prefix -> {book_page_number -> [(file_path, text), ...]}.

    Only indexes bands that have pass1/ folders.
    """
    index: dict[str, dict[int, list[tuple[Path, str]]]] = {}

    for chunk_dir in sorted(EXTRACTED_DIR.iterdir(), key=band_chunk_key):
        pass1_dir = chunk_dir / "pass1"
        if not pass1_dir.is_dir():
            continue

        band_prefix_m = re.match(r"(Band\d+(?:-\d+)?)", chunk_dir.name)
        if not band_prefix_m:
            continue
        bp = band_prefix_m.group(1)

        if bp not in index:
            index[bp] = {}

        for wiki_file in sorted(pass1_dir.glob("p*.wiki"), key=page_sort_key):
            text = wiki_file.read_text(encoding="utf-8")

            page_top = extract_citation_page(text, "top")
            page_bottom = extract_citation_page(text, "bottom")

            if page_top is not None:
                index[bp].setdefault(page_top, [])
                if not any(e[0] == wiki_file for e in index[bp][page_top]):
                    index[bp][page_top].append((wiki_file, text))

            if page_bottom is not None and page_bottom != page_top:
                index[bp].setdefault(page_bottom, [])
                if not any(e[0] == wiki_file for e in index[bp][page_bottom]):
                    index[bp][page_bottom].append((wiki_file, text))

    return index


def build_ordered_files(band_prefix: str) -> list[tuple[Path, str]]:
    """Return all pass1 wiki files for a band, ordered by chunk then page."""
    result: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    for chunk_dir in sorted(EXTRACTED_DIR.iterdir(), key=band_chunk_key):
        if not chunk_dir.name.startswith(band_prefix + "_chunk"):
            continue
        pass1_dir = chunk_dir / "pass1"
        if not pass1_dir.is_dir():
            continue
        for wiki_file in sorted(pass1_dir.glob("p*.wiki"), key=page_sort_key):
            if wiki_file not in seen:
                seen.add(wiki_file)
                text = wiki_file.read_text(encoding="utf-8")
                result.append((wiki_file, text))
    return result
