"""Check Liste_Bände for non-consecutive page numbers per band.

Reports gaps, overlaps, and articles sharing the same start page.
Can also reorder the CSV so articles are sorted by page number within each band.

Usage:  python -m src.articles.check_pages [--band 'Band 1'] [--sort]
"""

import argparse
import csv

from .helpers import META_CSV, row_sort_key


def check_pages(*, band_filter: str | None = None) -> None:
    with open(META_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    rows.sort(key=row_sort_key)

    # Group by band
    bands: dict[str, list[dict]] = {}
    for row in rows:
        b = row["Band"]
        if band_filter and b != band_filter:
            continue
        bands.setdefault(b, []).append(row)

    total_issues = 0

    for band, articles in bands.items():
        issues: list[str] = []

        for i, art in enumerate(articles):
            try:
                von = int(art["Seite_von"])
                bis = int(art["Seite_bis"])
            except (ValueError, KeyError):
                issues.append(
                    f"  MISSING/INVALID pages: {art['Bauwerk']!r} "
                    f"(Seite_von={art.get('Seite_von')!r}, Seite_bis={art.get('Seite_bis')!r})"
                )
                continue

            if bis < von:
                issues.append(
                    f"  INVERTED range: {art['Bauwerk']!r} ({von}–{bis})"
                )

            if i == 0:
                continue

            prev = articles[i - 1]
            try:
                prev_bis = int(prev["Seite_bis"])
            except (ValueError, KeyError):
                continue

            expected = prev_bis + 1
            if von == int(prev["Seite_von"]):
                issues.append(
                    f"  SAME Seite_von={von}: {prev['Bauwerk']!r} & {art['Bauwerk']!r}"
                )
            elif von < prev_bis:
                issues.append(
                    f"  OVERLAP: {prev['Bauwerk']!r} ends p{prev_bis}, "
                    f"{art['Bauwerk']!r} starts p{von} (overlap of {prev_bis - von + 1} pages)"
                )
            elif von == prev_bis:
                # Shared boundary page — common and usually fine
                pass
            elif von > expected:
                issues.append(
                    f"  GAP: {prev['Bauwerk']!r} ends p{prev_bis}, "
                    f"{art['Bauwerk']!r} starts p{von} (gap of {von - expected} pages)"
                )

        if issues:
            print(f"\n{band} ({len(articles)} articles):")
            for issue in issues:
                print(issue)
            total_issues += len(issues)

    if total_issues == 0:
        print("No page-number issues found.")
    else:
        print(f"\nTotal issues: {total_issues}")


def sort_csv(*, band_filter: str | None = None) -> None:
    """Reorder Liste_Bände.csv so articles are sorted by page number within each band."""
    with open(META_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    rows.sort(key=row_sort_key)

    with open(META_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Sorted {len(rows)} rows in {META_CSV.name} by (Band, Seite_von).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", help="Filter to a single band, e.g. 'Band 1'")
    parser.add_argument("--sort", action="store_true", help="Sort the CSV by page number within each band")
    args = parser.parse_args()
    if args.sort:
        sort_csv(band_filter=args.band)
    check_pages(band_filter=args.band)


if __name__ == "__main__":
    main()
