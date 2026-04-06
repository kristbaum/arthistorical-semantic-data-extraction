#!/usr/bin/env python3
"""Check formatted articles for missing Ort names and suspiciously small sizes.

Reads the articles CSV and the corresponding formatted .wiki files, then
reports any article whose text does not mention its Ort value, as well as
articles with fewer than 1000 characters of content.

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

MIN_ARTICLE_SIZE = 1000


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
    small_articles = 0
    no_file = 0

    for row in rows:
        ort = row.get("Ort", "").strip()
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

        if ort and ort not in text:
            print(f"  MISSING ORT: {bauwerk} — '{ort}' not found in {filepath.relative_to(REPO_ROOT)}")
            missing_ort += 1
        elif args.verbose and ort:
            print(f"  OK: {bauwerk} — contains '{ort}'")

        if len(text) < MIN_ARTICLE_SIZE:
            print(f"  SMALL ({len(text)} chars): {bauwerk} — {filepath.relative_to(REPO_ROOT)}")
            small_articles += 1

    print(f"\nChecked {checked} articles, {missing_ort} missing Ort, "
          f"{small_articles} small (<{MIN_ARTICLE_SIZE} chars), {no_file} files not found")


if __name__ == "__main__":
    main()
