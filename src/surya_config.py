"""Shared configuration, constants, and data structures for the Surya pipeline."""

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

DATA_DIR = Path("data")
OUTPUT_DIR = Path("data/extracted")

# ── Image extraction ──────────────────────────────────────────────────────────

# Extra pixels around each detected image bounding box when saving
SAVE_MARGIN: int = 5

# Minimum dimension (px) for an image region to be saved (filters false positives)
MIN_IMAGE_DIM: int = 150

# ── Layout labels ─────────────────────────────────────────────────────────────

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

# ── Caption detection ─────────────────────────────────────────────────────────

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
    caption: str = ""  # filled after caption matching
    caption_matched: bool = False  # True when this caption is embedded in a [[File:]] tag
    lines: list[str] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def parse_folder_name(folder_name: str) -> tuple[str | None, str | None]:
    """Return (band, chunk) from a folder name like Band03-1_chunk001."""
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder_name)
    return (m.group(1), m.group(2)) if m else (None, None)


def polygon_to_bbox(polygon: list[list[float]]) -> tuple[int, int, int, int]:
    """Convert a Surya polygon (list of [x,y] points) to (x1, y1, x2, y2)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
