"""Convert Liste_Bände.xlsx to a single CSV.

Skips the first sheet (Bände_Verzeichnis), reads the remaining 16 sheets,
concatenates all rows, and adds a 'Band' column with the sheet name.

Usage:
    python excel_to_csv.py                          # default paths
    python excel_to_csv.py input.xlsx output.csv
"""

import csv
import re
import sys
from pathlib import Path

import openpyxl

_PAGE_RE = re.compile(r"S\.?\s*(\d+)(?:\s*[-–]\s*(\d+))?\.?\s*$")
_ZU_RE = re.compile(r"^Zu\s+(.+?)\s*:")

COLUMNS = [
    "Bauwerk",
    "Modul",
    "Eigenschaft",
    "Literaturangabe",
    "Autor",
    "Eingabe komplett",
    "Datenbankeintrag (Bild, Kurztext, Literaturverweis, basis Strukturdaten)",
    "Notiz",
]


def _find_bauwerk_col(row: tuple) -> int | None:
    """Return the index of the 'Bauwerk' cell in a header row, or None."""
    for i, cell in enumerate(row):
        if cell is not None and str(cell).strip() == "Bauwerk":
            return i
    return None


def _split_literaturangabe(lit: str) -> list[str]:
    """Split a Literaturangabe cell on newlines, stripping '&' separators."""
    parts = []
    for part in lit.split("\n"):
        part = part.strip().lstrip("&").strip()
        if part:
            parts.append(part)
    return parts or [lit]


def _bauwerk_for_part(original_bauwerk: str, lit_part: str) -> str:
    """Derive the Bauwerk for a split Literaturangabe line.

    Lines starting with 'Zu <Subpart>:' yield '<original>, <Subpart>'.
    All other lines keep the original Bauwerk unchanged.
    """
    m = _ZU_RE.match(lit_part)
    if m:
        return f"{original_bauwerk}, {m.group(1)}"
    return original_bauwerk


def _strip_lit_prefix(lit_part: str) -> str:
    """Remove everything up to and including the first ': ' in a citation string.

    'Zu Stiegenhaus: Siehe ...' -> 'Siehe ...'
    'Walleshausen, in: Bauer ...' -> 'Bauer ...'
    Returns the original string unchanged if no ': ' is found.
    """
    idx = lit_part.find(": ")
    if idx == -1:
        return lit_part
    return lit_part[idx + 2:]


def _ort_from_bauwerk(bauwerk: str) -> str:
    """Return the location name: text before the first ',' in Bauwerk."""
    idx = bauwerk.find(",")
    if idx == -1:
        return bauwerk
    return bauwerk[:idx]


def _parse_pages(literaturangabe: str | None) -> tuple[str, str]:
    """Extract start and end page numbers from a Literaturangabe string."""
    if not literaturangabe:
        return "", ""
    m = _PAGE_RE.search(str(literaturangabe))
    if not m:
        return "", ""
    start = m.group(1)
    end = m.group(2) if m.group(2) else start
    return start, end


# Index of "Eigenschaft" within COLUMNS (0-based)
_EIGENSCHAFT_IDX = COLUMNS.index("Eigenschaft")
# Index of "Literaturangabe" within COLUMNS (0-based)
_LITERATURANGABE_IDX = COLUMNS.index("Literaturangabe")


def excel_to_csv(xlsx_path: Path, csv_path: Path) -> None:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Band"] + COLUMNS + ["Seite_von", "Seite_bis", "Ort"])

        for sheet in wb.worksheets[1:]:  # skip first sheet
            band = sheet.title
            col_start: int | None = None  # index of "Bauwerk" column

            for row in sheet.iter_rows(values_only=True):
                # Detect header row by finding "Bauwerk"
                if col_start is None:
                    col_start = _find_bauwerk_col(row)
                    continue  # skip header row itself

                data = list(row[col_start : col_start + len(COLUMNS)])
                # Pad if the row is shorter than expected
                data += [None] * (len(COLUMNS) - len(data))

                # Skip completely empty rows
                if all(c is None for c in data):
                    continue

                # Skip rows with no Eigenschaft value
                if not data[_EIGENSCHAFT_IDX]:
                    continue

                original_bauwerk = data[0]
                lit_raw = data[_LITERATURANGABE_IDX]
                parts = _split_literaturangabe(str(lit_raw)) if lit_raw else [lit_raw]

                for part in parts:
                    row_data = list(data)  # copy
                    derived_bauwerk = _bauwerk_for_part(
                        str(original_bauwerk or ""), part or ""
                    )
                    row_data[0] = derived_bauwerk
                    stripped_lit = _strip_lit_prefix(part or "")
                    row_data[_LITERATURANGABE_IDX] = stripped_lit
                    seite_von, seite_bis = _parse_pages(stripped_lit)
                    ort = _ort_from_bauwerk(derived_bauwerk)
                    writer.writerow([band] + row_data + [seite_von, seite_bis, ort])

    print(f"Written: {csv_path}")


if __name__ == "__main__":
    args = sys.argv[1:]
    xlsx = Path(args[0]) if len(args) > 0 else Path("Liste_Bände.xlsx")
    csv_out = Path(args[1]) if len(args) > 1 else xlsx.with_suffix(".csv")
    excel_to_csv(xlsx, csv_out)
