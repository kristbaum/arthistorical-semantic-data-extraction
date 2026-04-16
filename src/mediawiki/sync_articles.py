#!/usr/bin/env python3
"""Sync formatted articles from data/formatted/BandXX/ to a MediaWiki instance.

For each .wiki file the page title is taken from the |Lemma= field in the
{{Artikel}} template.  The full file content (template + body) is uploaded as
the page wikitext.

Behaviour:
  - If the page does not exist it is created.
  - If the page already exists and the content differs it is updated.
  - If the page already exists and the content is identical it is skipped.
  - Pages with a |Meta= value are included unless --skip-meta is passed.

Usage
-----
    # Dry-run across all bands
    python -m src.mediawiki.sync_articles --dry-run

    # Upload a single band
    python -m src.mediawiki.sync_articles --band Band05

    # Upload everything
    python -m src.mediawiki.sync_articles

    # Skip already-correct pages silently
    python -m src.mediawiki.sync_articles --band Band05 --verbose

Setup
-----
Configure pywikibot before running (see upload_images.py for details).
"""

import argparse
import re
import sys
from pathlib import Path

import pywikibot

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FORMATTED_DIR = REPO_ROOT / "data" / "formatted"

DEFAULT_WIKI_URL = "https://badwcbd-lab.srv.mwn.de/api.php"

_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")


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
# Iterator over articles
# ---------------------------------------------------------------------------


def iter_articles(band_filter: str | None = None, skip_meta: bool = False):
    """Yield (lemma, wikitext) for every formatted article.

    Skips files that have no |Lemma= value.
    If skip_meta is True, skips articles with a non-empty |Meta= field.
    """
    for band_dir in sorted(FORMATTED_DIR.iterdir()):
        if not band_dir.is_dir():
            continue
        if band_filter and band_dir.name != band_filter:
            continue

        for wiki_path in sorted(band_dir.glob("*.wiki")):
            text = wiki_path.read_text(encoding="utf-8")
            fields = _read_fields(text)
            lemma = fields.get("Lemma", "").strip()
            if not lemma:
                continue
            if skip_meta and fields.get("Meta", "").strip():
                continue
            yield lemma, text


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------


def sync_all(
    *,
    wiki_url: str,
    dry_run: bool,
    band_filter: str | None,
    skip_meta: bool,
    verbose: bool,
    summary: str,
) -> None:
    if not dry_run:
        site = pywikibot.Site(url=wiki_url)
        site.login()
    else:
        site = None

    created = updated = skipped = errors = 0

    for lemma, wikitext in iter_articles(band_filter, skip_meta=skip_meta):
        if dry_run:
            print(f"  WOULD SYNC: {lemma}")
            if verbose:
                print(f"    ({len(wikitext)} chars)")
            created += 1
            continue

        try:
            page = pywikibot.Page(site, lemma)
            existing = page.text if page.exists() else None

            if existing is None:
                page.text = wikitext
                page.save(summary=f"[bot] Create: {summary}")
                print(f"  CREATED: {lemma}")
                created += 1
            elif existing.strip() != wikitext.strip():
                page.text = wikitext
                page.save(summary=f"[bot] Update: {summary}")
                print(f"  UPDATED: {lemma}")
                updated += 1
            else:
                if verbose:
                    print(f"  SKIP (unchanged): {lemma}")
                skipped += 1

        except Exception as exc:
            print(f"  ERROR: {lemma} — {exc}", file=sys.stderr)
            errors += 1

    mode = "Would sync" if dry_run else "Synced"
    print(
        f"\n{mode}: {created} created, {updated} updated, "
        f"{skipped} unchanged, {errors} errors."
    )
    if errors:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--wiki-url",
        default=DEFAULT_WIKI_URL,
        help="MediaWiki API endpoint URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without writing to the wiki.",
    )
    parser.add_argument(
        "--band",
        default=None,
        metavar="BAND",
        help="Limit to one band directory name, e.g. Band05.",
    )
    parser.add_argument(
        "--skip-meta",
        action="store_true",
        help="Skip articles with a non-empty |Meta= field.",
    )
    parser.add_argument(
        "--summary",
        default="automated sync from formatted articles",
        help="Edit summary used for all page saves.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    print(f"Target wiki : {args.wiki_url}")
    print(f"Mode        : {'DRY RUN' if args.dry_run else 'SYNC'}")
    if args.band:
        print(f"Band filter : {args.band}")
    print()

    sync_all(
        wiki_url=args.wiki_url,
        dry_run=args.dry_run,
        band_filter=args.band,
        skip_meta=args.skip_meta,
        verbose=args.verbose,
        summary=args.summary,
    )


if __name__ == "__main__":
    main()
