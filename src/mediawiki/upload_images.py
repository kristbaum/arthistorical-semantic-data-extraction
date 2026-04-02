#!/usr/bin/env python3
"""Upload processed images from every chunk to a MediaWiki instance.

Each image is uploaded with a description containing the {{BildQuelle}} template,
whose parameters are extracted from the filename and the corresponding wiki page:

  {{BildQuelle|Band=Band12-2|Chunk=chunk002|Chunkseite=p018|Originalseiten=384-385}}

Image filenames follow the pattern:
  {Band}_{Chunk}_{Page}_{Img}_p.jpg   →   uploaded as {Band}_{Chunk}_{Page}_{Img}.jpg

The Originalseiten are read from citation-page-top / citation-page-bottom comments
in the corresponding wiki/p*.wiki file.

Setup
-----
Before running, configure pywikibot credentials. Create ``user-config.py`` in the
working directory (or in ~/.pywikibot/) with at least:

    family = 'deckenmalerei'         # or your custom family name
    mylang = 'de'
    usernames['deckenmalerei']['de'] = 'YourBotUser'

And a ``user-password.py`` (kept out of version control):

    ('YourBotUser', BotPassword('YourBotUser', 'your-bot-password'))

Or set the PYWIKIBOT_USERNAME / PYWIKIBOT_PASSWORD environment variables.

Usage
-----
    python -m src.mediawiki.upload_images [--dry-run] [--band BAND] [--verbose]
    python -m src.mediawiki.upload_images --wiki-url https://badwcbd-lab.srv.mwn.de/api.php

Configuration
-------------
Change WIKI_URL below to point at your MediaWiki API endpoint.
"""

import argparse
import re
import sys
from pathlib import Path
import pywikibot


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXTRACTED_DIR = REPO_ROOT / "data" / "extracted"

# ── Default wiki URL — override with --wiki-url ──────────────────────────────
DEFAULT_WIKI_URL = "https://badwcbd-lab.srv.mwn.de/api.php"

# Allowed upload extensions (MediaWiki default whitelist)
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "svg", "pdf"}


# ── Metadata extraction ───────────────────────────────────────────────────────


def parse_image_filename(filename: str) -> dict | None:
    """Parse a processed-image filename into its components.

    Accepts:  Band12-2_chunk002_p018_img001_p.jpg
    Returns:  {band, chunk, page, img, wiki_name}
              wiki_name = filename without the '_p' suffix.
    Returns None if the filename does not match the expected pattern.
    """
    stem = Path(filename).stem  # e.g. Band12-2_chunk002_p018_img001_p
    m = re.match(
        r"(Band\d+(?:-\d+)?)_(chunk\d+)_(p\d+)_(img\d+)(?:_p)?$",
        stem,
    )
    if not m:
        return None
    band, chunk, page, img = m.groups()
    ext = Path(filename).suffix.lstrip(".")
    return {
        "band": band,
        "chunk": chunk,
        "page": page,
        "img": img,
        "wiki_name": f"{band}_{chunk}_{page}_{img}.{ext}",
        "chunk_dir_name": f"{band}_{chunk}",
    }


def get_original_pages(chunk_dir_name: str, page: str) -> str:
    """Read citation-page-top and -bottom from the wiki/ sibling and return a page range.

    Returns e.g. '384-385', '266', or '' if the wiki file is missing.
    """
    wiki_file = EXTRACTED_DIR / chunk_dir_name / "wiki" / f"{page}.wiki"
    if not wiki_file.is_file():
        return ""

    text = wiki_file.read_text(encoding="utf-8")

    top_m = re.search(r"<!--\s*citation-page-top:\s*\S+\s+p(\d+)\s*-->", text)
    bot_m = re.search(r"<!--\s*citation-page-bottom:\s*\S+\s+p(\d+)\s*-->", text)

    top = top_m.group(1) if top_m else None
    bot = bot_m.group(1) if bot_m else None

    if top and bot and top != bot:
        return f"{top}-{bot}"
    return top or bot or ""


def build_description(band: str, chunk: str, page: str, original_pages: str) -> str:
    """Return the MediaWiki wikitext description for the image."""
    band_num = band.removeprefix("Band")
    chunk_num = chunk.removeprefix("chunk")
    page_num = page.removeprefix("p")
    lines = [
        "{{BildQuelle",
        f"|Band={band_num}",
        f"|Chunk={chunk_num}",
        f"|Chunkseite={page_num}",
        f"|Originalseiten={original_pages}",
        "}}",
    ]
    return "\n".join(lines)


# ── Iterator over all images ──────────────────────────────────────────────────


def iter_images(band_filter: str | None = None):
    """Yield (image_path, meta, description) tuples for every processed image.

    ``band_filter`` limits output to a single band prefix (e.g. 'Band01').
    """
    for chunk_dir in sorted(EXTRACTED_DIR.iterdir()):
        if not chunk_dir.is_dir() or not chunk_dir.name.startswith("Band"):
            continue
        if band_filter and not chunk_dir.name.startswith(band_filter):
            continue

        proc_dir = chunk_dir / "processed_images"
        if not proc_dir.is_dir():
            continue

        for img_path in sorted(proc_dir.glob("*")):
            ext = img_path.suffix.lstrip(".").lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue

            meta = parse_image_filename(img_path.name)
            if meta is None:
                continue

            original_pages = get_original_pages(meta["chunk_dir_name"], meta["page"])
            description = build_description(
                meta["band"], meta["chunk"], meta["page"], original_pages
            )

            yield img_path, meta, description


# ── Upload ────────────────────────────────────────────────────────────────────


def upload_all(
    *,
    wiki_url: str,
    dry_run: bool,
    band_filter: str | None,
    verbose: bool,
    one: bool = False,
) -> None:
    """Upload all images; if dry_run, only print what would be done."""
    if not dry_run:
        site = pywikibot.Site(url=wiki_url)
        site.login()

    uploaded = 0
    skipped = 0

    for img_path, meta, description in iter_images(band_filter):
        wiki_name = meta["wiki_name"]

        if dry_run:
            print(f"  WOULD UPLOAD: {wiki_name}")
            if verbose:
                print(f"    source : {img_path.relative_to(REPO_ROOT)}")
                print(f"    desc   :\n{description}\n")
            uploaded += 1
            if one:
                break
            continue

        filepage = pywikibot.FilePage(site, f"File:{wiki_name}")

        if filepage.exists():
            if verbose:
                print(f"  SKIP (exists): {wiki_name}")
            skipped += 1
            continue

        try:
            site.upload(
                filepage,
                source_filename=str(img_path),
                comment=f"Upload {wiki_name}",
                text=description,
                ignore_warnings=False,
            )
            print(f"  UPLOADED: {wiki_name}")
            uploaded += 1
        except Exception as exc:
            print(f"  ERROR: {wiki_name} — {exc}", file=sys.stderr)
            skipped += 1

        if one:
            break

    print(
        f"\nDone: {uploaded} {'would upload' if dry_run else 'uploaded'}, {skipped} skipped"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--wiki-url", default=DEFAULT_WIKI_URL, help="MediaWiki API endpoint URL."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without uploading."
    )
    parser.add_argument(
        "--band", default=None, help="Limit to one band prefix (e.g. 'Band01')."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print description for each file."
    )
    parser.add_argument(
        "--one",
        action="store_true",
        help="Upload only the first file in queue (for testing).",
    )
    args = parser.parse_args(argv)

    print(f"Target wiki: {args.wiki_url}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'UPLOAD'}")
    if args.band:
        print(f"Band filter: {args.band}")
    print()

    upload_all(
        wiki_url=args.wiki_url,
        dry_run=args.dry_run,
        band_filter=args.band,
        verbose=args.verbose,
        one=args.one,
    )


if __name__ == "__main__":
    main()
