"""Shared helpers: path conventions, CSV mapping, filename sanitisation."""

import re
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"
META_CSV = REPO_ROOT / "data" / "meta" / "Liste_Bände.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "formatted"


# ---------------------------------------------------------------------------
# Iterating over formatted articles
# ---------------------------------------------------------------------------
#
# The formatted folder holds one .wiki file per article, grouped by band:
#     data/formatted/{Band}/{Lemma}.wiki
# These helpers give every script the same, ordered view of that tree so the
# band-selection + glob boilerplate lives in one place.


def formatted_band_prefixes(
    band: str | None = None, *, base: Path = OUTPUT_DIR
) -> list[str]:
    """Band directory names under the formatted folder, sorted.

    With ``band`` set, returns just that band (as a single-element list if it
    exists, otherwise empty).
    """
    if band:
        return [band] if (base / band).is_dir() else []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def iter_formatted_articles(
    band: str | None = None, *, base: Path = OUTPUT_DIR
) -> Iterator[Path]:
    """Yield every article .wiki file in the formatted folder.

    Files are ordered by band, then by filename. Restrict to a single band by
    passing its prefix (e.g. ``"Band01"``). ``base`` overrides the formatted
    root (used by run_pass2's ``--input-dir``).
    """
    for prefix in formatted_band_prefixes(band, base=base):
        yield from sorted((base / prefix).glob("*.wiki"))


# ---------------------------------------------------------------------------
# Article file parsing
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")


def parse_article_file(text: str) -> tuple[str, dict[str, str], str]:
    """Split an article file into (template_block, fields, body).

    template_block: the raw text from {{Artikel to }} inclusive (with newlines).
    fields:         dict of field_name → value.
    body:           everything after the closing }}.
    """
    lines = text.splitlines(keepends=True)
    in_tpl = False
    tpl_lines: list[str] = []
    fields: dict[str, str] = {}
    body_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("{{Artikel"):
            in_tpl = True
            tpl_lines.append(line)
        elif s == "}}" and in_tpl:
            tpl_lines.append(line)
            body_start = i + 1
            break
        elif in_tpl:
            tpl_lines.append(line)
            m = _FIELD_RE.match(line)
            if m:
                fields[m.group(1)] = m.group(2).strip()

    template_block = "".join(tpl_lines)
    body = "".join(lines[body_start:])
    return template_block, fields, body


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
