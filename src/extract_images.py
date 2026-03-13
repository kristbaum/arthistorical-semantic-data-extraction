#!/usr/bin/env python3
"""Detect and extract rectangular images from rendered PDF pages.

Uses Surya's layout detection model to classify page regions as
Picture, Figure, Text, Caption, etc.  Only regions labelled Picture
or Figure are extracted.

Works together with pdf_to_images.py: call render_folder() to get page images,
then this script runs detection and saves results.

Naming convention for saved files: {band}_{chunk}_p{page}_img{n}.jpg
"""

import logging
import os
import re
from pathlib import Path

import cv2
from PIL import Image

from pdf_to_images import DATA_DIR, OUTPUT_DIR, parse_folder_name

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Extra pixels added around each detected bounding box when saving
SAVE_MARGIN: int = 5

# Layout labels that correspond to image content
IMAGE_LABELS: set[str] = {"Picture", "Figure"}

# ──────────────────────────────────────────────────────────────────────────────

# Lazy-loaded predictor (heavy model; only instantiated once)
_layout_predictor = None


def _get_layout_predictor():
    """Lazily initialise the Surya LayoutPredictor (singleton)."""
    global _layout_predictor  # noqa: PLW0603
    if _layout_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings

        log.info("Loading Surya layout model …")
        _layout_predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )
    return _layout_predictor


def detect_images_surya(
    page_pil: Image.Image,
) -> list[tuple[int, int, int, int]]:
    """Run Surya layout detection and return (x, y, w, h) boxes for images."""
    predictor = _get_layout_predictor()
    results = predictor([page_pil])

    rects: list[tuple[int, int, int, int]] = []
    for bbox_info in results[0].bboxes:
        if bbox_info.label not in IMAGE_LABELS:
            continue
        x1, y1, x2, y2 = bbox_info.bbox
        w = int(x2 - x1)
        h = int(y2 - y1)
        rects.append((int(x1), int(y1), w, h))

    return rects


def extract_and_save(
    page_img,
    rects: list[tuple[int, int, int, int]],
    output_dir: Path,
    base_name: str,
    margin: int = SAVE_MARGIN,
) -> list[tuple[Path, tuple[int, int, int, int]]]:
    """Crop detected regions from *page_img* and write them to *output_dir*.

    *page_img* can be a numpy (BGR) array or a PIL Image.
    """
    if isinstance(page_img, Image.Image):
        w, h = page_img.size
    else:
        h, w = page_img.shape[:2]

    saved = []
    for idx, (x, y, bw, bh) in enumerate(rects, 1):
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(w, x + bw + margin)
        y1 = min(h, y + bh + margin)

        if isinstance(page_img, Image.Image):
            roi = page_img.crop((x0, y0, x1, y1))
            fname = f"{base_name}_img{idx:03d}.jpg"
            out_path = output_dir / fname
            roi.save(str(out_path), quality=90)
        else:
            roi = page_img[y0:y1, x0:x1]
            fname = f"{base_name}_img{idx:03d}.jpg"
            out_path = output_dir / fname
            cv2.imwrite(str(out_path), roi, [cv2.IMWRITE_JPEG_QUALITY, 90])

        saved.append((out_path, (x0, y0, x1 - x0, y1 - y0)))
        log.info("  Saved %s (%dx%d)", fname, x1 - x0, y1 - y0)

    return saved


def process_folder(folder: Path, output_base: Path = OUTPUT_DIR) -> None:
    """Extract images from pre-rendered pages in output_base/folder.name/pages/."""
    band, chunk = parse_folder_name(folder.name)
    output_dir = output_base / folder.name / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_base / folder.name / "pages"

    page_files = sorted(pages_dir.glob("*.jpg"))
    total = 0
    for page_path in page_files:
        match = re.search(r"_p(\d+)", page_path.stem)
        if not match:
            log.warning(
                "  Skipping %s: filename does not match expected pattern",
                page_path.name,
            )
            continue
        page_num = int(match.group(1))
        base_name = f"{band}_{chunk}_p{page_num:03d}"

        page_pil = Image.open(page_path).convert("RGB")

        rects = detect_images_surya(page_pil)
        if rects:
            log.info("  Page %d: %d image(s) detected", page_num, len(rects))
            saved = extract_and_save(page_pil, rects, output_dir, base_name)
            total += len(saved)
        else:
            log.debug("  Page %d: no images detected", page_num)

    log.info("  Total: %d images extracted from %s", total, folder.name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Sensible VRAM defaults for a 6 GB GPU (GTX 1660)
    os.environ.setdefault("LAYOUT_BATCH_SIZE", "8")

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
