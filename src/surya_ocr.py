"""Line segmentation and OCR using Surya recognition."""

import logging

import numpy as np
from PIL import Image

from surya_config import TEXT_LABELS, Region
from surya_models import get_recognition_predictor

log = logging.getLogger(__name__)


def segment_lines(crop: Image.Image, min_line_height: int = 8) -> list[tuple[int, int]]:
    """Find text line boundaries in a crop using horizontal projection profile.

    Returns a list of (y_start, y_end) pairs relative to the crop.
    """
    arr = np.array(crop.convert("L"))
    # Binarise: dark text → 1, light background → 0
    binary = (arr < 180).astype(np.uint8)
    h_proj = binary.sum(axis=1)

    in_text = False
    lines: list[tuple[int, int]] = []
    line_start = 0
    for y, val in enumerate(h_proj):
        if not in_text and val > 5:
            in_text = True
            line_start = y
        elif in_text and val <= 5:
            in_text = False
            if y - line_start > min_line_height:
                lines.append((line_start, y))

    if in_text and arr.shape[0] - line_start > min_line_height:
        lines.append((line_start, arr.shape[0]))

    # If no lines found but the crop has content, use the whole crop
    if not lines and binary.sum() > 100:
        lines = [(0, arr.shape[0])]

    return lines


def ocr_text_regions(
    page_pil: Image.Image,
    regions: list[Region],
    max_crops_per_batch: int = 8,
) -> None:
    """Run OCR on text regions. Updates Region.lines and Region.text.

    Processes crops in batches of *max_crops_per_batch* to stay within VRAM.
    """
    rec = get_recognition_predictor()

    # Collect text region crops and their line bboxes
    crops: list[Image.Image] = []
    line_bboxes_per_crop: list[list[list[int]]] = []
    crop_to_region: list[int] = []

    for i, region in enumerate(regions):
        if region.label not in TEXT_LABELS:
            continue
        x1, y1, x2, y2 = region.bbox
        rw, rh = x2 - x1, y2 - y1
        if rw < 20 or rh < 10:
            continue

        crop = page_pil.crop((x1, y1, x2, y2))
        line_bounds = segment_lines(crop)
        if not line_bounds:
            continue

        line_bboxes = [[0, ly1, crop.size[0], ly2] for ly1, ly2 in line_bounds]
        crops.append(crop)
        line_bboxes_per_crop.append(line_bboxes)
        crop_to_region.append(i)

    if not crops:
        return

    # Process in batches to avoid OOM on pages with many text regions
    for batch_start in range(0, len(crops), max_crops_per_batch):
        batch_end = min(batch_start + max_crops_per_batch, len(crops))
        batch_crops = crops[batch_start:batch_end]
        batch_bboxes = line_bboxes_per_crop[batch_start:batch_end]
        batch_indices = crop_to_region[batch_start:batch_end]

        results = rec(
            batch_crops,
            bboxes=batch_bboxes,
            recognition_batch_size=64,
            math_mode=False,
        )

        for result, region_idx in zip(results, batch_indices):
            region = regions[region_idx]
            region.lines = [tl.text for tl in result.text_lines]
            region.text = "\n".join(region.lines)
