#!/usr/bin/env python3
"""Concatenate pass1 pages per band and write band CSVs into data/splitting/.

This is step 1 of the three-step pipeline:
  1. COLLECT (this script) — concatenate each band's pass1 pages and write
     a per-band CSV into data/splitting/{BandXX}/.
  2. MARK   (marker_inserter.py) — estimate article boundaries, insert
     {{Artikel …}} / {{End}} markers, write {BandXX}_split.wiki for review.
  3. SPLIT  (splitter.py) — read the reviewed _split.wiki files and write
     individual article files to data/formatted/{BandXX}/.
"""

import argparse
import csv
from collections import defaultdict

from .collector import collect_band
from .helpers import (
    META_CSV,
    csv_band_to_dir_prefix,
    row_sort_key,
)


def main(argv: list[str] | None = None) -> None:
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
    args = parser.parse_args(argv)

    # ── Read & group CSV rows by band ────────────────────────────────────────
    print(f"Reading CSV: {META_CSV}")
    all_rows: list[dict] = []
    with open(META_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if args.band and row["Band"] != args.band:
                continue
            all_rows.append(row)

    all_rows.sort(key=row_sort_key)
    print(f"  {len(all_rows)} articles to process")

    # Group by band_prefix, keeping original order (already sorted)
    bands: dict[str, list[dict]] = defaultdict(list)
    invalid_rows: list[dict] = []
    for row in all_rows:
        band_prefix = csv_band_to_dir_prefix(row["Band"])
        if not band_prefix:
            invalid_rows.append(row)
            continue
        try:
            row["_seite_von"] = int(row["Seite_von"])
            row["_seite_bis"] = int(row["Seite_bis"])
        except (ValueError, KeyError):
            invalid_rows.append(row)
            continue
        bands[band_prefix].append(row)

    if invalid_rows:
        print(f"  {len(invalid_rows)} rows skipped (invalid band or page numbers)")

    # ── COLLECT — concatenate bands into data/splitting/ ─────────────────────
    print("\nCollecting bands …")
    collected = 0
    for band_prefix in sorted(bands):
        ok = collect_band(
            band_prefix,
            bands[band_prefix],
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        if ok:
            collected += 1

    print(f"\nDone: collected {collected} bands into data/splitting/.")
    print("Next: run marker_inserter.py to insert {{Artikel}}/{{End}} markers.")


if __name__ == "__main__":
    main()
