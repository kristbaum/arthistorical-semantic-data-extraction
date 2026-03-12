#!/usr/bin/env python3
"""Unified pipeline: layout detection → image extraction → OCR → Markdown.

Uses Surya for layout analysis and text recognition, with horizontal
projection profiling for line segmentation within text regions.

For each Band/chunk folder this script:
1. Renders PDF pages to images (or uses pre-rendered pages)
2. Runs Surya layout detection to classify regions (Text, Picture, Caption, …)
3. Extracts Picture/Figure regions as image files
4. Performs line-level OCR on text regions (projection profile + Surya recognition)
5. Matches captions to their nearest images
6. Assembles one Markdown file per page, with image links replacing captions
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

DATA_DIR = Path("data")
OUTPUT_DIR = Path("data/extracted")

# Extra pixels around each detected image bounding box when saving
SAVE_MARGIN: int = 5

# Minimum dimension (px) for an image region to be saved (filters false positives)
MIN_IMAGE_DIM: int = 150

# Layout labels considered as image content
IMAGE_LABELS: set[str] = {"Picture", "Figure"}

# Layout labels considered as text that should be OCR'd
TEXT_LABELS: set[str] = {
    "Text",
    "Caption",
    "Section-header",
    "SectionHeader",
    "PageHeader",
    "Page-header",
    "Page-footer",
    "PageFooter",
    "Footnote",
    "List-item",
}

# Caption detection regex from the existing codebase
CAPTION_PATTERN = re.compile(
    r"^(?:[A-Z]+\d*(?:-\d+)?(?:,\s*)?)+\s+[A-ZÄÖÜ][A-ZÄÖÜ\s\-,.:;()]+(?:\s|$)"
)

# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class Region:
    """A layout region detected on a page."""

    label: str
    position: int  # reading order
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    text: str = ""  # filled after OCR
    image_path: Path | None = None  # filled after image extraction
    lines: list[str] = field(default_factory=list)


# ── Model management (only one model in VRAM at a time for 6 GB GPUs) ────────

_layout_predictor = None
_recognition_predictor = None


def _free_gpu():
    """Free CUDA memory between model loads."""
    import gc
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _get_layout_predictor():
    global _layout_predictor, _recognition_predictor
    if _layout_predictor is None:
        # Unload recognition model first to free VRAM
        if _recognition_predictor is not None:
            log.info("Unloading recognition model …")
            del _recognition_predictor
            _recognition_predictor = None
            _free_gpu()

        from surya.foundation import FoundationPredictor
        from surya.layout import LayoutPredictor
        from surya.settings import settings

        log.info("Loading Surya layout model …")
        _layout_predictor = LayoutPredictor(
            FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)
        )
    return _layout_predictor


def _get_recognition_predictor():
    global _layout_predictor, _recognition_predictor
    if _recognition_predictor is None:
        # Unload layout model first to free VRAM
        if _layout_predictor is not None:
            log.info("Unloading layout model …")
            del _layout_predictor
            _layout_predictor = None
            _free_gpu()

        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        log.info("Loading Surya recognition model …")
        _recognition_predictor = RecognitionPredictor(FoundationPredictor())
    return _recognition_predictor


# ── Helpers ───────────────────────────────────────────────────────────────────


def parse_folder_name(folder_name: str) -> tuple[str | None, str | None]:
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder_name)
    return (m.group(1), m.group(2)) if m else (None, None)


def polygon_to_bbox(polygon: list[list[float]]) -> tuple[int, int, int, int]:
    """Convert a Surya polygon (list of [x,y] points) to (x1, y1, x2, y2)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


# ── Line segmentation ────────────────────────────────────────────────────────


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


# ── Layout detection ──────────────────────────────────────────────────────────


def detect_layout(page_pil: Image.Image) -> list[Region]:
    """Run Surya layout detection and return Region objects sorted by position."""
    predictor = _get_layout_predictor()
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


# ── Image extraction ──────────────────────────────────────────────────────────


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
            log.debug("  Skipping small image region %dx%d at pos %d", rw, rh, region.position)
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


# ── OCR ───────────────────────────────────────────────────────────────────────


def ocr_text_regions(
    page_pil: Image.Image,
    regions: list[Region],
    max_crops_per_batch: int = 8,
) -> None:
    """Run OCR on text regions. Updates Region.lines and Region.text.

    Processes crops in batches of *max_crops_per_batch* to stay within VRAM.
    """
    rec = _get_recognition_predictor()

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


# ── Caption matching ──────────────────────────────────────────────────────────


def _is_caption_text(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if CAPTION_PATTERN.match(text):
        return True
    if len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True
    return False


def match_captions_to_images(regions: list[Region], images_dir: Path) -> None:
    """Match Caption regions to their nearest Picture/Figure region.

    Writes a .md file alongside each image with the caption text.
    """
    image_regions = [r for r in regions if r.image_path is not None]
    caption_regions = [r for r in regions if r.label == "Caption" and r.text.strip()]

    for cap in caption_regions:
        cap_cy = (cap.bbox[1] + cap.bbox[3]) / 2

        best_img = None
        best_dist = float("inf")
        for img_r in image_regions:
            img_cy = (img_r.bbox[1] + img_r.bbox[3]) / 2
            dist = abs(cap_cy - img_cy)
            if dist < best_dist:
                best_dist = dist
                best_img = img_r

        if best_img and best_img.image_path:
            caption_clean = cap.text.replace("\n", " ").strip()
            md_path = best_img.image_path.with_suffix(".md")
            content = (
                f"![{caption_clean}]({best_img.image_path.name})\n\n"
                f"{caption_clean}\n"
            )
            md_path.write_text(content, encoding="utf-8")
            log.info("  Caption → %s: %s", md_path.name, caption_clean[:60])


# ── Line joining (hyphenation) ────────────────────────────────────────────────


def join_lines(lines: list[str]) -> str:
    """Join OCR lines, handling soft hyphens (¬) and word-break hyphens."""
    if not lines:
        return ""

    parts: list[str] = []
    for i, line in enumerate(lines):
        text = line.rstrip()
        if not text:
            continue

        if text.endswith("¬") or text.endswith("\u00ac"):
            # Soft hyphen: join directly (remove hyphen marker)
            text = text.rstrip("¬\u00ac")
        elif text.endswith("-") and i + 1 < len(lines):
            nxt = lines[i + 1].lstrip()
            if nxt and nxt[0].islower():
                # Word-break hyphen before lowercase: join without hyphen
                text = text[:-1]
            else:
                text += " "
        else:
            text += " "

        parts.append(text)

    return "".join(parts).strip()


# ── Markdown assembly ─────────────────────────────────────────────────────────


def _region_to_markdown(region: Region, images_rel_dir: str) -> str | None:
    """Convert a single region to its Markdown representation."""
    if region.label in IMAGE_LABELS:
        if region.image_path is None:
            return None
        # Check if there's a caption .md file
        cap_md = region.image_path.with_suffix(".md")
        if cap_md.exists():
            caption = cap_md.read_text(encoding="utf-8").strip().split("\n")[-1]
        else:
            caption = region.image_path.stem
        rel = f"{images_rel_dir}/{region.image_path.name}"
        return f"\n![{caption}]({rel})\n"

    if region.label == "Caption":
        # Captions that matched an image are already embedded via the image link;
        # skip them here to avoid duplication.
        if any(
            region.image_path is not None
            for _ in [None]  # dummy; we check caption .md existence below
        ):
            pass
        # If the caption was written to a .md, it's linked via the image.
        # Still include it as bold text for accessibility.
        text = join_lines(region.lines)
        if text:
            return f"\n**{text}**\n"
        return None

    if region.label in ("Section-header", "SectionHeader"):
        text = join_lines(region.lines)
        if text:
            return f"\n## {text}\n"
        return None

    if region.label in ("PageHeader", "Page-header"):
        # Page headers are typically repeating — include as small comment
        text = join_lines(region.lines)
        if text:
            return f"<!-- header: {text} -->"
        return None

    if region.label in ("PageFooter", "Page-footer", "Footnote"):
        text = join_lines(region.lines)
        if text:
            return f"\n---\n{text}\n"
        return None

    # Default: Text, List-item, etc.
    text = join_lines(region.lines)
    if text:
        return text
    return None


def assemble_markdown(
    regions: list[Region],
    page_num: int,
    images_rel_dir: str = "images",
) -> str:
    """Assemble Markdown for one page from its layout regions."""
    parts: list[str] = []
    for region in regions:
        md = _region_to_markdown(region, images_rel_dir)
        if md:
            parts.append(md)

    if not parts:
        return ""

    return f"<!-- Page {page_num} -->\n\n" + "\n\n".join(parts) + "\n"


# ── Page-level processing ────────────────────────────────────────────────────


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
    markdown_dir = output_folder / "markdown"

    for d in (pages_dir, images_dir, markdown_dir):
        d.mkdir(parents=True, exist_ok=True)

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
        raw_pages = pdf_to_images(pdf_path)
        pages = []
        for idx, page_img in enumerate(raw_pages):
            page_num = idx + 1
            base_name = f"{band}_{chunk}_p{page_num:03d}"
            save_page_image(page_img, pages_dir, base_name)
            pf = pages_dir / f"{base_name}_full.jpg"
            pages.append((page_num, pf))

    # ── Pass 1: Layout detection + image extraction (layout model loaded) ────
    log.info("Pass 1: Layout detection on %d pages …", len(pages))
    page_regions: dict[int, list[Region]] = {}
    for page_num, page_path in pages:
        base_name = f"{band}_{chunk}_p{page_num:03d}"
        page_pil = Image.open(page_path).convert("RGB")

        regions = detect_layout(page_pil)
        log.info(
            "  Page %d: %d regions (%s)",
            page_num,
            len(regions),
            ", ".join(r.label for r in regions[:6]),
        )
        extract_images(page_pil, regions, images_dir, base_name)
        page_regions[page_num] = regions

    # ── Pass 2: OCR + markdown (recognition model loaded, layout freed) ──────
    log.info("Pass 2: OCR on %d pages …", len(pages))
    total_images = 0
    total_text_regions = 0
    for page_num, page_path in pages:
        regions = page_regions[page_num]
        page_pil = Image.open(page_path).convert("RGB")

        ocr_text_regions(page_pil, regions)
        match_captions_to_images(regions, images_dir)

        md = assemble_markdown(regions, page_num)
        if md.strip():
            md_path = markdown_dir / f"p{page_num:03d}.md"
            md_path.write_text(md, encoding="utf-8")
            log.info("  Page %d → %s", page_num, md_path.name)

        total_images += sum(1 for r in regions if r.image_path is not None)
        total_text_regions += sum(1 for r in regions if r.text)

    log.info(
        "Done: %s — %d pages, %d images, %d text regions",
        folder.name,
        len(pages),
        total_images,
        total_text_regions,
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
