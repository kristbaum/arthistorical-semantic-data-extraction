#!/usr/bin/env python3
"""Assemble complete MediaWiki articles from pass1 page files using CSV metadata.

Two-phase pipeline:
  1. COLLECT — concatenate each band's pass1 pages into data/splitting/{BandXX}/
     and write a per-band CSV there.
  2. SPLIT  — read each concatenated band file, find article boundaries, and
     write individual article files to data/formatted/{BandXX}/.

Articles that cannot be matched are saved to data/formatted/missing_articles.csv.
"""

import argparse
import csv
from collections import defaultdict

from .collector import collect_band
from .splitter import split_band
from .helpers import (
    META_CSV,
    OUTPUT_DIR,
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

    # ── Phase 1: COLLECT — concatenate bands into data/splitting/ ────────────
    print("\n── Phase 1: Collecting bands ──")
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
    print(f"  Collected {collected} bands")

    # ── Phase 2: SPLIT — cut articles from concatenated files ────────────────
    print("\n── Phase 2: Splitting articles ──")
    total_written = 0
    total_ba = 0
    all_missing: list[dict] = list(invalid_rows)

    for band_prefix in sorted(bands):
        if args.verbose:
            print(f"\n  Splitting {band_prefix} …")
        w, ba, miss = split_band(
            band_prefix,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        total_written += w
        total_ba += ba
        all_missing.extend(miss)

    # ── Write missing articles CSV ───────────────────────────────────────────
    if all_missing:
        missing_path = OUTPUT_DIR / "missing_articles.csv"
        clean_missing = [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in all_missing
        ]
        if args.dry_run:
            print(
                f"\nWOULD WRITE missing_articles.csv with {len(clean_missing)} entries"
            )
        else:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(missing_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=clean_missing[0].keys())
                writer.writeheader()
                writer.writerows(clean_missing)
            print(f"\nWrote missing_articles.csv with {len(clean_missing)} entries")

    print(
        f"\nDone: {total_written} articles, {total_ba} before/after files, {len(all_missing)} missing/skipped"
    )


if __name__ == "__main__":
    main()
