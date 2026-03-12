#!/usr/bin/env python3
"""Unified pipeline: layout detection → image extraction → OCR → MediaWiki.

Uses Surya for layout analysis and text recognition, with horizontal
projection profiling for line segmentation within text regions.

For each Band/chunk folder this script:
1. Renders PDF pages to images (or uses pre-rendered pages)
2. Runs Surya layout detection to classify regions (Text, Picture, Caption, …)
3. Extracts Picture/Figure regions as image files
4. Performs line-level OCR on text regions (projection profile + Surya recognition)
5. Matches captions to their nearest images
6. Assembles one MediaWiki file per page, with image tags including captions
"""

import logging
import os
import re
import time
from pathlib import Path

from PIL import Image

from surya_config import DATA_DIR, OUTPUT_DIR, Region, parse_folder_name
from surya_layout import detect_layout, extract_images
from surya_markdown import assemble_mediawiki, match_captions_to_images
from surya_ocr import ocr_text_regions

log = logging.getLogger(__name__)


# ── Folder-level processing ───────────────────────────────────────────────────


def process_folder(folder: Path, output_base: Path = OUTPUT_DIR) -> None:
    """Run the full pipeline on a Band/chunk folder.

    Two-pass approach to avoid loading both models simultaneously on
    limited-VRAM GPUs:
      Pass 1 (layout model): detect regions, extract images
      Pass 2 (recognition model): OCR text regions, match captions, write markdown
    """
    band, chunk = parse_folder_name(folder.name)
    if not band:
        log.warning("Skipping %s — doesn't match Band*_chunk* pattern", folder.name)
        return

    output_folder = output_base / folder.name
    pages_dir = output_folder / "pages"
    images_dir = output_folder / "images"
    wiki_dir = output_folder / "wiki"

    for d in (pages_dir, images_dir, wiki_dir):
        d.mkdir(parents=True, exist_ok=True)

    folder_t0 = time.monotonic()

    # Check for pre-rendered pages, or render from PDF
    page_files = sorted(pages_dir.glob("*_full.jpg"))
    if page_files:
        log.info("Using %d pre-rendered pages from %s", len(page_files), pages_dir)
        pages = []
        for pf in page_files:
            m = re.search(r"_p(\d+)_full", pf.stem)
            if m:
                pages.append((int(m.group(1)), pf))
    else:
        from pdf_to_images import find_pdf, pdf_to_images, save_page_image

        pdf_path = find_pdf(folder)
        if not pdf_path:
            log.error("No PDF and no pre-rendered pages in %s", folder.name)
            return
        log.info("Rendering PDF %s …", pdf_path.name)
        render_t0 = time.monotonic()
        raw_pages = pdf_to_images(pdf_path)
        pages = []
        for idx, page_img in enumerate(raw_pages):
            page_num = idx + 1
            base_name = f"{band}_{chunk}_p{page_num:03d}"
            save_page_image(page_img, pages_dir, base_name)
            pf = pages_dir / f"{base_name}_full.jpg"
            pages.append((page_num, pf))
        log.info("PDF rendering: %.1fs", time.monotonic() - render_t0)

    # ── Pass 1: Layout detection + image extraction (layout model loaded) ────
    log.info("Pass 1: Layout detection on %d pages …", len(pages))
    pass1_t0 = time.monotonic()
    page_regions: dict[int, list[Region]] = {}
    for page_num, page_path in pages:
        page_t0 = time.monotonic()
        base_name = f"{band}_{chunk}_p{page_num:03d}"
        page_pil = Image.open(page_path).convert("RGB")

        regions = detect_layout(page_pil)
        log.info(
            "  Page %d: %d regions (%s) [%.1fs]",
            page_num,
            len(regions),
            ", ".join(r.label for r in regions[:6]),
            time.monotonic() - page_t0,
        )
        extract_images(page_pil, regions, images_dir, base_name)
        page_regions[page_num] = regions
    log.info("Pass 1 complete: %.1fs", time.monotonic() - pass1_t0)

    # ── Pass 2: OCR + markdown (recognition model loaded, layout freed) ──────
    log.info("Pass 2: OCR on %d pages …", len(pages))
    pass2_t0 = time.monotonic()
    total_images = 0
    total_text_regions = 0
    for page_num, page_path in pages:
        page_t0 = time.monotonic()
        regions = page_regions[page_num]
        page_pil = Image.open(page_path).convert("RGB")

        ocr_text_regions(page_pil, regions)
        match_captions_to_images(regions)

        wiki = assemble_mediawiki(regions, page_num, folder.name)
        if wiki.strip():
            wiki_path = wiki_dir / f"p{page_num:03d}.wiki"
            wiki_path.write_text(wiki, encoding="utf-8")
            log.info(
                "  Page %d → %s [%.1fs]",
                page_num,
                wiki_path.name,
                time.monotonic() - page_t0,
            )

        total_images += sum(1 for r in regions if r.image_path is not None)
        total_text_regions += sum(1 for r in regions if r.text)

    log.info("Pass 2 complete: %.1fs", time.monotonic() - pass2_t0)
    log.info(
        "Done: %s — %d pages, %d images, %d text regions, total %.1fs",
        folder.name,
        len(pages),
        total_images,
        total_text_regions,
        time.monotonic() - folder_t0,
    )


# ── CLI entry point ──────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # VRAM defaults for 6 GB GPU
    os.environ.setdefault("LAYOUT_BATCH_SIZE", "8")
    os.environ.setdefault("RECOGNITION_BATCH_SIZE", "64")

    folders = sorted(
        p
        for p in DATA_DIR.iterdir()
        if p.is_dir() and re.match(r"Band[\d\-]+_chunk\d+", p.name)
    )
    if not folders:
        log.error("No Band*_chunk* folders found in %s", DATA_DIR)
        return

    for folder in folders:
        process_folder(folder)

    log.info("All folders processed.")


if __name__ == "__main__":
    main()
