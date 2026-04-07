#!/usr/bin/env python3
"""Check formatted articles for missing Ort names and suspiciously small sizes.

Reads the articles CSV and the corresponding formatted .wiki files, then
reports any article whose text does not mention its Ort value, as well as
articles with fewer than 1000 characters of content. Also prints word count
and image count (MediaWiki [[File:...]] transclusions) for each article.

Usage:
    python -m src.articles.check_ort [--problems-only]
"""

import argparse
import csv
import re

from .helpers import (
    META_CSV,
    OUTPUT_DIR,
    REPO_ROOT,
    csv_band_to_dir_prefix,
    row_sort_key,
    sanitize_filename,
)

MIN_ARTICLE_SIZE = 1000
MAX_ARTICLE_SIZE = 50_000
FILE_RE = re.compile(r"\[\[File:[^\]]+\]\]", re.IGNORECASE)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--problems-only", "-p",
        action="store_true",
        help="Only print articles with missing Ort or out-of-range size.",
    )
    args = parser.parse_args()

    with open(META_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows.sort(key=row_sort_key)

    checked = 0
    missing_ort = 0
    small_articles = 0
    large_articles = 0
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

        words = len(text.split())
        images = len(FILE_RE.findall(text))
        size = len(text)

        ort_missing = bool(ort and ort not in text)
        too_small = size < MIN_ARTICLE_SIZE
        too_large = size > MAX_ARTICLE_SIZE
        has_problem = ort_missing or too_small or too_large

        if not args.problems_only or has_problem:
            print(f"  {bauwerk} — {words} words, {images} image(s)")

        if ort_missing:
            print(f"    MISSING ORT: '{ort}' not found in {filepath.relative_to(REPO_ROOT)}")
            missing_ort += 1

        if too_small:
            print(f"    SMALL ({size} chars): {filepath.relative_to(REPO_ROOT)}")
            small_articles += 1

        if too_large:
            print(f"    LARGE ({size} chars): {filepath.relative_to(REPO_ROOT)}")
            large_articles += 1

    print(f"\nChecked {checked} articles, {missing_ort} missing Ort, "
          f"{small_articles} small (<{MIN_ARTICLE_SIZE} chars), "
          f"{large_articles} large (>{MAX_ARTICLE_SIZE} chars), "
          f"{no_file} files not found")


if __name__ == "__main__":
    main()
