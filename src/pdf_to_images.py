#!/usr/bin/env python3
"""Convert PDF pages to high-resolution images.

Converts every page of the PDF found in a Band/chunk folder to a numpy array
(BGR) and optionally saves them as full-page PNG files for later use.
"""

import logging
import re
from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# DPI for PDF → image conversion (higher = better quality but slower)
RENDER_DPI: int = 300

# Root data directory containing Band*_chunk* sub-folders
DATA_DIR = Path("data")

# Output base directory for rendered pages
OUTPUT_DIR = Path("data/extracted")

# Whether to save the full-page PNG next to the extracted images
SAVE_FULL_PAGES: bool = True

# ──────────────────────────────────────────────────────────────────────────────


def parse_folder_name(folder_name: str) -> tuple[str | None, str | None]:
    """Return (band, chunk) from a folder name like Band03-1_chunk001."""
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder_name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def find_pdf(folder: Path) -> Path | None:
    """Return the single PDF file in a chunk folder, or None."""
    pdfs = list(folder.glob("*.pdf"))
    if not pdfs:
        return None
    if len(pdfs) > 1:
        log.warning("Multiple PDFs in %s — using first: %s", folder, pdfs[0].name)
    return pdfs[0]


def pdf_to_images(pdf_path: Path, dpi: int = RENDER_DPI) -> list[np.ndarray]:
    """Convert all PDF pages to BGR numpy arrays."""
    pil_images = convert_from_path(str(pdf_path), dpi=dpi, fmt="png")
    result = []
    for pil_img in pil_images:
        arr = np.array(pil_img)
        if arr.ndim == 3 and arr.shape[2] == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        result.append(arr)
    return result


def save_page_image(page_img: np.ndarray, output_dir: Path, base_name: str) -> Path:
    """Save a full-page image and return the path."""
    path = output_dir / f"{base_name}_full.png"
    cv2.imwrite(str(path), page_img)
    return path


def render_folder(
    folder: Path, output_base: Path = OUTPUT_DIR
) -> list[tuple[int, np.ndarray, str]]:
    """Render all pages of the PDF in *folder*.

    Returns a list of (page_num, page_image, base_name) tuples.
    Saves full-page PNGs to output_base/folder.name/pages/ when SAVE_FULL_PAGES is True.
    """
    band, chunk = parse_folder_name(folder.name)
    if not band:
        log.warning("Skipping %s — doesn't match Band*_chunk* pattern", folder.name)
        return []

    pdf_path = find_pdf(folder)
    if not pdf_path:
        log.warning("No PDF found in %s", folder)
        return []

    pages_dir = None
    if SAVE_FULL_PAGES:
        pages_dir = output_base / folder.name / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

    log.info("Rendering %s at %d DPI …", pdf_path.name, RENDER_DPI)
    raw_pages = pdf_to_images(pdf_path)
    log.info("  %d pages rendered", len(raw_pages))

    result = []
    for idx, page_img in enumerate(raw_pages):
        page_num = idx + 1
        base_name = f"{band}_{chunk}_p{page_num:03d}"
        if pages_dir is not None:
            save_page_image(page_img, pages_dir, base_name)
        result.append((page_num, page_img, base_name))

    return result


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    folders = sorted(
        p
        for p in DATA_DIR.iterdir()
        if p.is_dir() and re.match(r"Band[\d\-]+_chunk\d+", p.name)
    )
    if not folders:
        log.error("No Band*_chunk* folders found in %s", DATA_DIR)
        return

    for folder in folders:
        render_folder(folder, OUTPUT_DIR)

    log.info("Done.")


if __name__ == "__main__":
    main()
