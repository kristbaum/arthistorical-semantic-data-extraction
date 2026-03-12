#!/usr/bin/env python3
"""Extract rectangular images from PDF pages of scanned art-historical volumes.

For each Band/chunk folder containing a PDF, this script:
1. Converts each PDF page to a high-resolution image
2. Uses edge detection to find rectangular image regions
3. Extracts them as individual files named: {band}_{chunk}_p{page}_img{n}.png
"""

import argparse
import logging
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from pdf2image import convert_from_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Minimum image area as fraction of page area to avoid detecting tiny artifacts
MIN_AREA_FRACTION = 0.01
# Maximum image area – skip regions that are basically the whole page
MAX_AREA_FRACTION = 0.80
# Minimum aspect ratio (width/height or height/width) to filter slivers
MIN_ASPECT_RATIO = 0.15
# DPI for PDF→image conversion (higher = better quality but slower)
RENDER_DPI = 300


def parse_folder_name(folder_name: str):
    """Extract band and chunk identifiers from folder name like Band03-1_chunk001."""
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder_name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def find_pdf(folder: Path) -> Path | None:
    """Find the single PDF file in a chunk folder."""
    pdfs = list(folder.glob("*.pdf"))
    if len(pdfs) == 1:
        return pdfs[0]
    if len(pdfs) > 1:
        log.warning("Multiple PDFs in %s, using first: %s", folder, pdfs[0].name)
        return pdfs[0]
    return None


def pdf_to_images(pdf_path: Path, dpi: int = RENDER_DPI) -> list[np.ndarray]:
    """Convert all pages of a PDF to numpy arrays (BGR)."""

    pil_images = convert_from_path(str(pdf_path), dpi=dpi, fmt="png")
    result = []
    for pil_img in pil_images:
        arr = np.array(pil_img)
        # Convert RGB to BGR for OpenCV
        if arr.ndim == 3 and arr.shape[2] == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        result.append(arr)
    return result


def detect_images(
    page_img: np.ndarray, page_num: int
) -> list[tuple[int, int, int, int]]:
    """Detect rectangular image regions on a scanned page.

    Returns list of (x, y, w, h) bounding boxes.
    """
    h, w = page_img.shape[:2]
    page_area = h * w
    min_area = page_area * MIN_AREA_FRACTION
    max_area = page_area * MAX_AREA_FRACTION

    # Convert to grayscale
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

    # Apply bilateral filter to reduce noise while keeping edges
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)

    # Detect edges
    edges = cv2.Canny(filtered, 30, 100)

    # Dilate to close gaps in edge contours
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.erode(edges, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        # Approximate the contour to a polygon
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # Accept quadrilaterals (4 vertices) or use bounding rect
        x, y, bw, bh = cv2.boundingRect(approx)
        bbox_area = bw * bh
        if bbox_area < min_area or bbox_area > max_area:
            continue

        # Filter out very thin slivers (likely text lines or borders)
        aspect = min(bw, bh) / max(bw, bh) if max(bw, bh) > 0 else 0
        if aspect < MIN_ASPECT_RATIO:
            continue

        # Check if the region actually has image-like content (not just text)
        # Images tend to have higher variance and more continuous tonal areas
        roi = gray[y : y + bh, x : x + bw]
        if roi.size == 0:
            continue

        # Use edge density: text regions have high edge density, images have moderate
        roi_edges = cv2.Canny(roi, 50, 150)
        edge_density = np.count_nonzero(roi_edges) / roi.size
        # Images typically 0.02-0.15, text blocks > 0.15
        if edge_density > 0.20:
            continue

        # Check for sufficient tonal variation (images vs blank/uniform areas)
        std_dev = np.std(roi)
        if std_dev < 15:
            continue

        rects.append((x, y, bw, bh))

    # Remove overlapping rectangles – keep larger ones
    rects = remove_overlapping(rects)

    return rects


def remove_overlapping(
    rects: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Remove smaller rectangles that overlap significantly with larger ones."""
    if not rects:
        return rects

    # Sort by area descending
    rects = sorted(rects, key=lambda r: r[2] * r[3], reverse=True)
    keep = []

    for rect in rects:
        x1, y1, w1, h1 = rect
        overlapping = False
        for kx, ky, kw, kh in keep:
            # Compute intersection
            ix = max(x1, kx)
            iy = max(y1, ky)
            ix2 = min(x1 + w1, kx + kw)
            iy2 = min(y1 + h1, ky + kh)
            if ix < ix2 and iy < iy2:
                inter_area = (ix2 - ix) * (iy2 - iy)
                smaller_area = min(w1 * h1, kw * kh)
                if inter_area > 0.5 * smaller_area:
                    overlapping = True
                    break
        if not overlapping:
            keep.append(rect)

    return keep


def extract_and_save(
    page_img: np.ndarray,
    rects: list[tuple[int, int, int, int]],
    output_dir: Path,
    base_name: str,
    margin: int = 5,
):
    """Extract detected image regions and save them."""
    h, w = page_img.shape[:2]
    saved = []
    for idx, (x, y, bw, bh) in enumerate(rects, 1):
        # Add small margin, clamp to page bounds
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(w, x + bw + margin)
        y1 = min(h, y + bh + margin)

        roi = page_img[y0:y1, x0:x1]
        fname = f"{base_name}_img{idx:03d}.png"
        out_path = output_dir / fname
        cv2.imwrite(str(out_path), roi)
        saved.append((out_path, (x0, y0, x1 - x0, y1 - y0)))
        log.info("  Saved %s (%dx%d)", fname, x1 - x0, y1 - y0)
    return saved


def save_page_image(page_img: np.ndarray, output_dir: Path, base_name: str) -> Path:
    """Save the full page image for later use in caption matching."""
    page_path = output_dir / f"{base_name}_full.png"
    cv2.imwrite(str(page_path), page_img)
    return page_path


def process_folder(folder: Path, output_base: Path, save_full_pages: bool = True):
    """Process one Band/chunk folder."""
    band, chunk = parse_folder_name(folder.name)
    if not band:
        log.warning(
            "Skipping %s – doesn't match BandXX-X_chunkXXX pattern", folder.name
        )
        return

    pdf_path = find_pdf(folder)
    if not pdf_path:
        log.warning("No PDF found in %s", folder)
        return

    output_dir = output_base / folder.name / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    pages_dir = None
    if save_full_pages:
        pages_dir = output_base / folder.name / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

    log.info("Processing %s (%s)", folder.name, pdf_path.name)
    pages = pdf_to_images(pdf_path)
    log.info("  Converted %d pages at %d DPI", len(pages), RENDER_DPI)

    total_images = 0
    for page_idx, page_img in enumerate(pages):
        page_num = page_idx + 1
        base_name = f"{band}_{chunk}_p{page_num:03d}"

        if save_full_pages and pages_dir is not None:
            save_page_image(page_img, pages_dir, base_name)

        rects = detect_images(page_img, page_num)
        if rects:
            log.info("  Page %d: found %d image(s)", page_num, len(rects))
            saved = extract_and_save(page_img, rects, output_dir, base_name)
            total_images += len(saved)
        else:
            log.debug("  Page %d: no images detected", page_num)

    log.info("  Total: %d images extracted from %s", total_images, folder.name)


def main():
    global RENDER_DPI, MIN_AREA_FRACTION
    parser = argparse.ArgumentParser(
        description="Extract images from scanned PDF pages"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Root data directory containing Band*_chunk* folders",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/extracted"),
        help="Output directory for extracted images",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Process only this specific folder (e.g., Band03-1_chunk001)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=RENDER_DPI,
        help=f"DPI for PDF rendering (default: {RENDER_DPI})",
    )
    parser.add_argument(
        "--no-full-pages",
        action="store_true",
        help="Don't save full page images (needed for caption matching)",
    )
    parser.add_argument(
        "--min-area",
        type=float,
        default=MIN_AREA_FRACTION,
        help=f"Min image area as fraction of page (default: {MIN_AREA_FRACTION})",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    RENDER_DPI = args.dpi
    MIN_AREA_FRACTION = args.min_area

    data_dir = args.data_dir

    if args.folder:
        folders = [data_dir / args.folder]
    else:
        folders = sorted(
            p
            for p in data_dir.iterdir()
            if p.is_dir() and re.match(r"Band[\d\-]+_chunk\d+", p.name)
        )

    if not folders:
        log.error("No matching folders found in %s", data_dir)
        sys.exit(1)

    log.info("Found %d folder(s) to process", len(folders))
    for folder in folders:
        process_folder(folder, args.output_dir, save_full_pages=not args.no_full_pages)

    log.info("Done.")


if __name__ == "__main__":
    main()
