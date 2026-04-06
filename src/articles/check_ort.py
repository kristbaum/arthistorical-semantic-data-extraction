#!/usr/bin/env python3
"""Check if each formatted article contains its Ort name from the CSV.

Reads the articles CSV and the corresponding formatted .wiki files, then
reports any article whose text does not mention its Ort value.

Usage:
    python -m src.articles.check_ort [--band 'Band 1'] [--verbose]
"""

import argparse
import csv

from .helpers import (
    META_CSV,
    OUTPUT_DIR,
    REPO_ROOT,
    csv_band_to_dir_prefix,
    row_sort_key,
    sanitize_filename,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--band", type=str, default=None, help="Check only this Band (e.g. 'Band 1').")
    parser.add_argument("--verbose", "-v", action="store_true", help="Also print matches.")
    args = parser.parse_args(argv)

    with open(META_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.band:
        rows = [r for r in rows if r["Band"] == args.band]
    rows.sort(key=row_sort_key)

    checked = 0
    missing_ort = 0
    no_file = 0

    for row in rows:
        ort = row.get("Ort", "").strip()
        if not ort:
            continue

        band_prefix = csv_band_to_dir_prefix(row["Band"])
        if not band_prefix:
            continue

        bauwerk = row["Bauwerk"]
        filename = sanitize_filename(bauwerk) + ".wiki"
        filepath = OUTPUT_DIR / band_prefix / filename

        if not filepath.is_file():
            no_file += 1
            continue

        text = filepath.read_text(encoding="utf-8")
        checked += 1

        if ort in text:
            if args.verbose:
                print(f"  OK: {bauwerk} — contains '{ort}'")
        else:
            print(f"  MISSING ORT: {bauwerk} — '{ort}' not found in {filepath.relative_to(REPO_ROOT)}")
            missing_ort += 1

    print(f"\nChecked {checked} articles, {missing_ort} missing Ort, {no_file} files not found")


if __name__ == "__main__":
    main()
