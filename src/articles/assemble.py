#!/usr/bin/env python3
"""Assemble complete MediaWiki articles from pass1 page files using CSV metadata.

Iterates ALL pass1 pages in each band and assigns them to articles (via CSV page
ranges) or to before_articles.wiki / after_articles.wiki for content that falls
outside any article boundary.

Articles that cannot be matched are saved to data/formatted/missing_articles.csv.
"""

import argparse
import csv
from collections import defaultdict

from .collector import assemble_band, clean_content
from .formatter import format_article
from .helpers import (
    META_CSV,
    OUTPUT_DIR,
    REPO_ROOT,
    csv_band_to_dir_prefix,
    row_sort_key,
    sanitize_filename,
)
from .page_index import build_ordered_files


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files.")
    parser.add_argument("--band", type=str, default=None, help="Process only this Band (e.g. 'Band 1').")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed progress.")
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

    missing: list[dict] = list(invalid_rows)
    written = 0
    skipped = len(invalid_rows)
    before_after_written = 0

    # ── Process each band ────────────────────────────────────────────────────
    for band_prefix in sorted(bands):
        band_articles = bands[band_prefix]
        ordered_files = build_ordered_files(band_prefix)

        if not ordered_files:
            if args.verbose:
                print(f"  SKIP band {band_prefix} — no pass1 files")
            for row in band_articles:
                missing.append(row)
                skipped += 1
            continue

        if args.verbose:
            print(f"\n  Band {band_prefix}: {len(ordered_files)} pages, {len(band_articles)} articles")

        # Run band assembly
        before_parts, art_parts, after_parts = assemble_band(ordered_files, band_articles)

        # ── Write before_articles.wiki ───────────────────────────────
        if before_parts:
            before_text = clean_content("\n".join(before_parts))
            if before_text:
                out_path = OUTPUT_DIR / band_prefix / "before_articles.wiki"
                if args.dry_run:
                    print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(before_text)} chars)")
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(before_text + "\n", encoding="utf-8")
                    if args.verbose:
                        print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(before_text)} chars)")
                before_after_written += 1

        # ── Write each article ───────────────────────────────────────
        for i, row in enumerate(band_articles):
            if not art_parts[i]:
                if args.verbose:
                    print(f"  MISS: {row['Bauwerk']} — no content assigned for {band_prefix} p{row['_seite_von']}")
                missing.append(row)
                skipped += 1
                continue

            content = clean_content("\n".join(art_parts[i]))
            if not content:
                missing.append(row)
                skipped += 1
                continue

            bauwerk = row["Bauwerk"]
            ort = row.get("Ort", "")
            eigenschaft = row.get("Eigenschaft", "")
            literaturangabe = row.get("Literaturangabe", "")
            autor_str = row.get("Autor", "")
            autoren = [a.strip() for a in autor_str.split("/") if a.strip()]

            article_text = format_article(
                bauwerk, content, literaturangabe, ort, autoren, eigenschaft, row["Band"],
            )

            out_dir = OUTPUT_DIR / band_prefix
            lemma_filename = sanitize_filename(bauwerk) + ".wiki"
            out_path = out_dir / lemma_filename

            if args.dry_run:
                print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(article_text)} chars)")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(article_text, encoding="utf-8")
                if args.verbose:
                    print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(article_text)} chars)")

            written += 1

        # ── Write after_articles.wiki ────────────────────────────────
        if after_parts:
            after_text = clean_content("\n".join(after_parts))
            if after_text:
                out_path = OUTPUT_DIR / band_prefix / "after_articles.wiki"
                if args.dry_run:
                    print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({len(after_text)} chars)")
                else:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(after_text + "\n", encoding="utf-8")
                    if args.verbose:
                        print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({len(after_text)} chars)")
                before_after_written += 1

    # ── Write missing articles CSV ───────────────────────────────────────────
    if missing:
        missing_path = OUTPUT_DIR / "missing_articles.csv"
        # Remove internal keys before writing
        clean_missing = [{k: v for k, v in row.items() if not k.startswith("_")} for row in missing]
        if args.dry_run:
            print(f"\nWOULD WRITE missing_articles.csv with {len(clean_missing)} entries")
        else:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            with open(missing_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=clean_missing[0].keys())
                writer.writeheader()
                writer.writerows(clean_missing)
            print(f"\nWrote missing_articles.csv with {len(clean_missing)} entries")

    print(f"\nDone: {written} articles, {before_after_written} before/after files, {skipped} missing/skipped")


if __name__ == "__main__":
    main()
