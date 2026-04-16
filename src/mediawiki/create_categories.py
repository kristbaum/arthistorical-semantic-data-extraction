#!/usr/bin/env python3
"""Collect {{Artikel}} template statistics and create MediaWiki categories.

Iterates all formatted articles, tallies values for:
    Band, Meta, Typ, Ort, AutorIn1–AutorIn6

Then (with --apply) creates one Category: page per unique non-empty value on
the configured MediaWiki instance.  Existing category pages are left untouched.

Category naming
---------------
  Band N            →  Category:Band N
  Meta=<value>      →  Category:Meta:<value>
  Typ=<value>       →  Category:Typ:<value>
  Ort=<value>       →  Category:Ort:<value>
  AutorIn[1-6]=<v>  →  Category:AutorIn:<value>

Usage
-----
    # Show frequency tables only (no wiki access)
    python -m src.mediawiki.create_categories

    # Filter to one band
    python -m src.mediawiki.create_categories --band Band05

    # Preview which category pages would be created
    python -m src.mediawiki.create_categories --dry-run

    # Actually create pages on the wiki
    python -m src.mediawiki.create_categories --apply
"""

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pywikibot

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FORMATTED_DIR = REPO_ROOT / "data" / "formatted"

_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")

# Fields to collect as single-valued categories
_SINGLE_FIELDS = ("Band", "Meta", "Typ", "Ort")

# AutorIn fields 1-6
_AUTOR_FIELDS = tuple(f"AutorIn{i}" for i in range(1, 7))

# Category prefix per field
_PREFIX: dict[str, str] = {
    "Band": "Band ",
    "Meta": "Meta:",
    "Typ": "Typ:",
    "Ort": "Ort:",
    "AutorIn": "AutorIn:",
}


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------


def _read_fields(text: str) -> dict[str, str]:
    """Extract |field=value pairs from the {{Artikel}} template block."""
    fields: dict[str, str] = {}
    in_tpl = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("{{Artikel"):
            in_tpl = True
        elif s == "}}" and in_tpl:
            break
        elif in_tpl:
            m = _FIELD_RE.match(line)
            if m:
                fields[m.group(1)] = m.group(2).strip()
    return fields


# ---------------------------------------------------------------------------
# Article iteration
# ---------------------------------------------------------------------------


def iter_articles(band_filter: str | None = None):
    """Yield (path, fields) for every formatted article."""
    dirs = sorted(FORMATTED_DIR.iterdir()) if FORMATTED_DIR.exists() else []
    for band_dir in dirs:
        if not band_dir.is_dir():
            continue
        if band_filter and band_dir.name != band_filter:
            continue
        for wiki_file in sorted(band_dir.glob("*.wiki")):
            text = wiki_file.read_text(encoding="utf-8")
            fields = _read_fields(text)
            if fields.get("Lemma"):
                yield wiki_file, fields


# ---------------------------------------------------------------------------
# Category name helpers
# ---------------------------------------------------------------------------


def category_name(field_group: str, value: str) -> str:
    """Return the MediaWiki category page title (without 'Category:' prefix)."""
    prefix = _PREFIX.get(field_group, f"{field_group}:")
    return f"{prefix}{value}"


# ---------------------------------------------------------------------------
# Statistics collection
# ---------------------------------------------------------------------------


def collect_stats(band_filter: str | None = None) -> dict[str, Counter]:
    """Return a Counter per logical field group."""
    counters: dict[str, Counter] = {g: Counter() for g in list(_SINGLE_FIELDS) + ["AutorIn"]}

    for _path, fields in iter_articles(band_filter):
        for field in _SINGLE_FIELDS:
            val = fields.get(field, "").strip()
            if val:
                counters[field][val] += 1

        for af in _AUTOR_FIELDS:
            val = fields.get(af, "").strip()
            if val:
                counters["AutorIn"][val] += 1

    return counters


def print_stats(counters: dict[str, Counter]) -> None:
    """Print a frequency table per field."""
    total_articles = sum(counters["Band"].values())
    print(f"Total articles (non-empty Lemma): {total_articles}\n")

    for group, counter in counters.items():
        if not counter:
            continue
        print(f"{'=' * 50}")
        print(f"  {group}  ({len(counter)} unique values, {sum(counter.values())} occurrences)")
        print(f"{'=' * 50}")
        for val, count in counter.most_common():
            cat = category_name(group, val)
            print(f"  {count:4d}  {cat}")
        print()


# ---------------------------------------------------------------------------
# Category creation
# ---------------------------------------------------------------------------

_CATEGORY_DESCRIPTION: dict[str, str] = {
    "Band": "Artikel aus {value} des Corpus der barocken Deckenmalerei in Deutschland.",
    "Meta": 'Metaartikel vom Typ "{value}".',
    "Typ": 'Artikel vom Gebäudetyp "{value}".',
    "Ort": "Artikel zum Ort {value}.",
    "AutorIn": "Artikel von {value}.",
}


def _category_text(field_group: str, value: str) -> str:
    tmpl = _CATEGORY_DESCRIPTION.get(field_group, "Kategorie {value}.")
    return tmpl.format(value=value)


def create_categories(
    counters: dict[str, Counter],
    *,
    dry_run: bool = True,
    verbose: bool = False,
) -> None:
    """Create one Category: page per unique value that does not yet exist."""
    site = pywikibot.Site()
    site.login()

    created = 0
    skipped = 0
    errors = 0

    for group, counter in counters.items():
        for value in counter:
            cat_title = f"Category:{category_name(group, value)}"
            if dry_run:
                print(f"  Would create: {cat_title}")
                created += 1
                continue

            try:
                page = pywikibot.Page(site, cat_title)
                if page.exists():
                    if verbose:
                        print(f"  Exists (skip): {cat_title}")
                    skipped += 1
                    continue
                page.text = _category_text(group, value)
                page.save(summary=f"[bot] Kategorie erstellt: {category_name(group, value)}")
                print(f"  Created: {cat_title}")
                created += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {cat_title}: {exc}", file=sys.stderr)
                errors += 1

    action = "Would create" if dry_run else "Created"
    print(f"\n{action}: {created}  |  Skipped (exists): {skipped}  |  Errors: {errors}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--band", metavar="BAND", help="Restrict to a single band folder (e.g. Band05)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created, do not write to wiki")
    parser.add_argument("--apply", action="store_true", help="Actually create category pages on the wiki")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print skipped (already existing) pages")
    args = parser.parse_args()

    counters = collect_stats(args.band)
    print_stats(counters)

    if args.apply or args.dry_run:
        print("Category creation", "(dry-run)" if args.dry_run else "(live)", "\n")
        create_categories(
            counters,
            dry_run=not args.apply,
            verbose=args.verbose,
        )
    else:
        print("Pass --dry-run to preview category pages or --apply to create them on the wiki.")


if __name__ == "__main__":
    main()
