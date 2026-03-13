#!/usr/bin/env python3
"""Convert PDF pages to single-page JPG files at 300 DPI."""

import logging
import re
from pathlib import Path

from pdf2image import convert_from_path

log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
OUTPUT_DIR = Path("data/extracted")
DPI = 300


def render_pdf(pdf_path: Path) -> None:
    chunk_name = pdf_path.stem
    pages_dir = OUTPUT_DIR / chunk_name / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    pages = convert_from_path(str(pdf_path), dpi=DPI, fmt="jpeg", thread_count=8)
    for idx, page in enumerate(pages):
        out_path = pages_dir / f"{chunk_name}_p{idx + 1:03d}.jpg"
        page.save(str(out_path), "JPEG", quality=90)
    log.info("%s: %d pages saved", pdf_path.name, len(pages))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pdfs = sorted(
        p
        for p in RAW_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".pdf"
        and re.match(r"(Band[\d\-]+|Index)_chunk\d+", p.stem)
    )
    if not pdfs:
        log.error("No matching PDFs found in %s", RAW_DIR)
        return

    for pdf_path in pdfs:
        render_pdf(pdf_path)

    log.info("Done.")


if __name__ == "__main__":
    main()
