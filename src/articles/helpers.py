"""Shared helpers: path conventions, CSV mapping, filename sanitisation."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"
META_CSV = REPO_ROOT / "data" / "meta" / "Liste_Bände.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "formatted"


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
    """Extract the book page number from a citation-page-top/bottom comment."""
    pattern = rf"<!--\s*citation-page-{which}:\s*\S+\s+p(\d+)\s*-->"
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def extract_citation_band(text: str) -> str | None:
    """Extract the Band identifier from a citation-page-top comment (e.g. 'Band02')."""
    m = re.search(r"<!--\s*citation-page-top:\s*(\S+)\s+p\d+\s*-->", text)
    return m.group(1) if m else None


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename, preserving umlauts."""
    name = name.replace("/", "-")
    name = name.replace("\\", "-")
    name = name.replace(":", " -")
    name = re.sub(r'[<>"|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def row_sort_key(r: dict) -> tuple[int, int, int]:
    """Sort key for CSV rows: (band_num, band_part, seite_von)."""
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
