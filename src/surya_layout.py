"""Layout detection and image extraction using Surya."""

import logging
from pathlib import Path

from PIL import Image

from surya_config import (
    IMAGE_LABELS,
    MIN_IMAGE_DIM,
    SAVE_MARGIN,
    Region,
    polygon_to_bbox,
)
from surya_models import get_layout_predictor

log = logging.getLogger(__name__)


def detect_layout(page_pil: Image.Image) -> list[Region]:
    """Run Surya layout detection and return Region objects sorted by position."""
    predictor = get_layout_predictor()
    results = predictor([page_pil])

    regions: list[Region] = []
    for box in results[0].bboxes:
        bbox = polygon_to_bbox(box.polygon)
        regions.append(
            Region(
                label=box.label,
                position=box.position,
                bbox=bbox,
                confidence=box.confidence or 0.0,
            )
        )

    regions.sort(key=lambda r: r.position)
    return regions


def extract_images(
    page_pil: Image.Image,
    regions: list[Region],
    output_dir: Path,
    base_name: str,
) -> None:
    """Extract image regions and save as JPG files. Updates Region.image_path."""
    w, h = page_pil.size
    img_idx = 0
    for region in regions:
        if region.label not in IMAGE_LABELS:
            continue
        x1, y1, x2, y2 = region.bbox
        rw, rh = x2 - x1, y2 - y1
        if rw < MIN_IMAGE_DIM or rh < MIN_IMAGE_DIM:
            log.debug(
                "  Skipping small image region %dx%d at pos %d",
                rw,
                rh,
                region.position,
            )
            continue

        # Apply margin
        cx1 = max(0, x1 - SAVE_MARGIN)
        cy1 = max(0, y1 - SAVE_MARGIN)
        cx2 = min(w, x2 + SAVE_MARGIN)
        cy2 = min(h, y2 + SAVE_MARGIN)

        img_idx += 1
        fname = f"{base_name}_img{img_idx:03d}.jpg"
        out_path = output_dir / fname
        roi = page_pil.crop((cx1, cy1, cx2, cy2))
        roi.save(str(out_path), quality=90)
        region.image_path = out_path
        log.info("  Saved %s (%dx%d)", fname, cx2 - cx1, cy2 - cy1)
