#!/usr/bin/env python3
"""Preprocess extracted images: trim white margins independently per side.

Images are already digitally cropped from scanned pages by the layout pipeline
(surya_layout.py). They contain artwork/photos on white paper with small, often
unequal margins — some sides may touch the content edge while others have several
pixels of white margin.

Strategy:
  - For each side, count consecutive rows/columns whose per-row/col pixel
    minimum is above WHITE_MIN_THRESHOLD. These are genuine white margin
    rows/cols with no content at all. Trim them, keeping CONTENT_PADDING pixels.
  - Using the per-row minimum (not mean) cleanly separates white paper (min ~200+)
    from content rows (min drops immediately to 0–50).
  - Deskew is intentionally omitted: these images contain artwork with many
    diagonal lines, making angle detection unreliable and harmful.

For each Band/chunk folder under data/extracted/:
  - Reads images from <chunk>/images/
  - Trims white margins independently on all four sides
  - Saves results to <chunk>/processed_images/ with suffix _p (same extension)
"""

import logging
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path("data/extracted")

# A row or column is considered a white margin if its darkest pixel is at or
# above this value. White paper: ~200+. Content: min immediately drops to <80.
WHITE_MIN_THRESHOLD = 150

# Pixels of margin to preserve on each trimmed side (keeps a sliver of context).
CONTENT_PADDING = 3


def _white_strip_width(mins: np.ndarray) -> int:
    """Count consecutive values >= WHITE_MIN_THRESHOLD from the start of *mins*.

    *mins* is a 1-D array of per-row or per-column minimum pixel values,
    ordered from the image edge inward.
    """
    below = mins < WHITE_MIN_THRESHOLD
    if not below.any():
        return len(mins)  # entire axis is white
    return int(np.argmax(below))  # index of first non-white entry


def trim_white_margins(
    img: np.ndarray, gray: np.ndarray
) -> tuple[np.ndarray, tuple[int, int, int, int]] | np.ndarray:
    """Trim white margins independently from each of the four sides."""
    h, w = gray.shape
    row_mins = gray.min(axis=1)  # shape (h,) — darkest pixel in each row
    col_mins = gray.min(axis=0)  # shape (w,) — darkest pixel in each column

    top = _white_strip_width(row_mins)
    bottom = _white_strip_width(row_mins[::-1])
    left = _white_strip_width(col_mins)
    right = _white_strip_width(col_mins[::-1])

    # Pull back by CONTENT_PADDING so we don't clip anti-aliased edges
    y1 = max(0, top - CONTENT_PADDING)
    y2 = min(h, h - bottom + CONTENT_PADDING)
    x1 = max(0, left - CONTENT_PADDING)
    x2 = min(w, w - right + CONTENT_PADDING)

    if y2 <= y1 or x2 <= x1:
        log.warning("Trim would eliminate entire image, returning original.")
        return img

    trimmed = (
        top - CONTENT_PADDING,
        bottom - CONTENT_PADDING,
        left - CONTENT_PADDING,
        right - CONTENT_PADDING,
    )  # (top_trimmed, bottom_trimmed, left_trimmed, right_trimmed)
    return img[y1:y2, x1:x2], trimmed


def process_image(src: Path, dst: Path) -> None:
    """Trim white margins of a single image and save result to *dst*."""
    img = cv2.imread(str(src))
    if img is None:
        log.warning("Could not read %s, skipping.", src)
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    result = trim_white_margins(img, gray)

    if isinstance(result, tuple):
        cropped, (top_, bottom_, left_, right_) = result
        sides = f"T={top_} B={bottom_} L={left_} R={right_}"
    else:
        cropped = result
        sides = "unchanged"

    cv2.imwrite(str(dst), cropped)
    log.info(
        "  %s  %dx%d → %dx%d  trimmed(%s)",
        src.name,
        img.shape[1],
        img.shape[0],
        cropped.shape[1],
        cropped.shape[0],
        sides,
    )


def process_chunk(chunk_dir: Path) -> None:
    """Process all images in <chunk_dir>/images/ → <chunk_dir>/processed_images/."""
    images_dir = chunk_dir / "images"
    if not images_dir.exists():
        log.debug("No images/ folder in %s, skipping.", chunk_dir.name)
        return

    image_files = sorted(
        f
        for f in images_dir.iterdir()
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    )
    if not image_files:
        log.info("No images found in %s", images_dir)
        return

    out_dir = chunk_dir / "processed_images"
    out_dir.mkdir(exist_ok=True)

    log.info("Processing %d images in %s", len(image_files), chunk_dir.name)
    for src in image_files:
        stem = src.stem + "_p"
        dst = out_dir / (stem + src.suffix)
        process_image(src, dst)


def main() -> None:
    chunk_dirs = sorted(d for d in DATA_DIR.iterdir() if d.is_dir())

    if not chunk_dirs:
        log.error("No chunk folders found under %s", DATA_DIR)
        return

    # ── Test mode: process only the first folder ──────────────────────────────
    # process_chunk(chunk_dirs[0])

    # ── Full run: uncomment to process all folders ────────────────────────────
    for chunk_dir in chunk_dirs:
        process_chunk(chunk_dir)


if __name__ == "__main__":
    main()
