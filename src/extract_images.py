#!/usr/bin/env python3
"""Detect and extract rectangular images from rendered PDF pages.

Works together with pdf_to_images.py: call render_folder() to get page images,
then this script runs detection and saves results.

Naming convention for saved files: {band}_{chunk}_p{page}_img{n}.png
"""

import logging
import re
from pathlib import Path

import cv2
import numpy as np

from pdf_to_images import DATA_DIR, OUTPUT_DIR, parse_folder_name, render_folder

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Minimum image area as fraction of page area to avoid detecting tiny artifacts
MIN_AREA_FRACTION: float = 0.01
# Maximum image area – skip regions that are basically the whole page
MAX_AREA_FRACTION: float = 0.80
# Minimum aspect ratio (width/height or height/width) to filter slivers
MIN_ASPECT_RATIO: float = 0.15
# Extra pixels added around each detected bounding box when saving
SAVE_MARGIN: int = 5

# ──────────────────────────────────────────────────────────────────────────────


def detect_images(page_img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Detect rectangular image regions on a scanned page.

    Returns list of (x, y, w, h) bounding boxes.
    """
    h, w = page_img.shape[:2]
    page_area = h * w
    min_area = page_area * MIN_AREA_FRACTION
    max_area = page_area * MAX_AREA_FRACTION

    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

    # Apply bilateral filter to reduce noise while keeping edges
    filtered = cv2.bilateralFilter(gray, 9, 75, 75)

    # Detect edges
    edges = cv2.Canny(filtered, 30, 100)

    # Dilate to close gaps in edge contours
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.dilate(edges, kernel, iterations=2)
    edges = cv2.erode(edges, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects: list[tuple[int, int, int, int]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        x, y, bw, bh = cv2.boundingRect(approx)
        bbox_area = bw * bh
        if bbox_area < min_area or bbox_area > max_area:
            continue

        aspect = min(bw, bh) / max(bw, bh) if max(bw, bh) > 0 else 0
        if aspect < MIN_ASPECT_RATIO:
            continue

        roi = gray[y : y + bh, x : x + bw]
        if roi.size == 0:
            continue

        # Text regions have high edge density; images have moderate density
        roi_edges = cv2.Canny(roi, 50, 150)
        edge_density = np.count_nonzero(roi_edges) / roi.size
        if edge_density > 0.20:
            continue

        # Require sufficient tonal variation (skip blank/uniform patches)
        if np.std(roi) < 15:
            continue

        rects.append((x, y, bw, bh))

    return _remove_overlapping(rects)


def _remove_overlapping(
    rects: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Keep larger rectangles, discard smaller ones that overlap >50% with them."""
    if not rects:
        return rects

    rects = sorted(rects, key=lambda r: r[2] * r[3], reverse=True)
    keep: list[tuple[int, int, int, int]] = []

    for rect in rects:
        x1, y1, w1, h1 = rect
        suppress = False
        for kx, ky, kw, kh in keep:
            ix = max(x1, kx)
            iy = max(y1, ky)
            ix2 = min(x1 + w1, kx + kw)
            iy2 = min(y1 + h1, ky + kh)
            if ix < ix2 and iy < iy2:
                inter_area = (ix2 - ix) * (iy2 - iy)
                smaller_area = min(w1 * h1, kw * kh)
                if inter_area > 0.5 * smaller_area:
                    suppress = True
                    break
        if not suppress:
            keep.append(rect)

    return keep


def extract_and_save(
    page_img: np.ndarray,
    rects: list[tuple[int, int, int, int]],
    output_dir: Path,
    base_name: str,
    margin: int = SAVE_MARGIN,
) -> list[tuple[Path, tuple[int, int, int, int]]]:
    """Crop detected regions from *page_img* and write them to *output_dir*."""
    h, w = page_img.shape[:2]
    saved = []
    for idx, (x, y, bw, bh) in enumerate(rects, 1):
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


def process_folder(folder: Path, output_base: Path = OUTPUT_DIR) -> None:
    """Render and extract images from all PDF pages in *folder*."""
    band, chunk = parse_folder_name(folder.name)
    if not band:
        log.warning("Skipping %s — doesn't match Band*_chunk* pattern", folder.name)
        return

    output_dir = output_base / folder.name / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = render_folder(folder, output_base)
    if not pages:
        return

    total = 0
    for page_num, page_img, base_name in pages:
        rects = detect_images(page_img)
        if rects:
            log.info("  Page %d: %d image(s) detected", page_num, len(rects))
            saved = extract_and_save(page_img, rects, output_dir, base_name)
            total += len(saved)
        else:
            log.debug("  Page %d: no images detected", page_num)

    log.info("  Total: %d images extracted from %s", total, folder.name)


def main() -> None:
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
        process_folder(folder, OUTPUT_DIR)

    log.info("Done.")


if __name__ == "__main__":
    main()
