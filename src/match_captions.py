#!/usr/bin/env python3
"""Match captions from Transkribus PAGE XML to extracted images.

For each extracted image this script:
1. Parses the PAGE XML files to extract text regions with coordinates
2. Identifies likely caption lines (short, starts with a section code)
3. Scales XML coordinates to the extracted page image resolution
4. Matches captions to image regions by vertical order
5. Creates a .md file alongside each image with the caption text
"""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import cv2

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Root data directory containing Band*_chunk* folders with XML files
DATA_DIR = Path("data")

# Directory that holds extracted images (produced by extract_images.py)
EXTRACTED_DIR = Path("data/extracted")

# ──────────────────────────────────────────────────────────────────────────────

CAPTION_PATTERN = re.compile(
    r"^(?:[A-Z]+\d*(?:-\d+)?(?:,\s*)?)+\s+[A-ZÄÖÜ\s\-,.:;()]+(?:\s|$)"
)


@dataclass
class TextLine:
    text: str
    x: int
    y: int
    width: int
    height: int
    region_id: str
    line_id: str


# ── XML parsing ───────────────────────────────────────────────────────────────


def _detect_namespace(root: ET.Element) -> str | None:
    tag = root.tag
    return (tag.split("}")[0] + "}") if "{" in tag else None


def _parse_coords(points_str: str) -> tuple[int, int, int, int]:
    pairs = []
    for pair in points_str.strip().split():
        parts = pair.split(",")
        if len(parts) == 2:
            pairs.append((int(parts[0]), int(parts[1])))
    if not pairs:
        return 0, 0, 0, 0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def parse_page_xml(xml_path: Path) -> tuple[list[TextLine], int, int]:
    """Parse a PAGE XML file; return (text_lines, page_width, page_height)."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = _detect_namespace(root)
    if not ns:
        return [], 0, 0

    def find(elem, tag):
        return elem.find(f"{ns}{tag}")

    def findall(elem, tag):
        return elem.findall(f"{ns}{tag}")

    page = find(root, "Page")
    if page is None:
        return [], 0, 0

    page_w = int(page.get("imageWidth", 0))
    page_h = int(page.get("imageHeight", 0))

    reading_order: dict[str, int] = {}
    ro = find(page, "ReadingOrder")
    if ro is not None:
        for ref in root.findall(f".//{ns}RegionRefIndexed"):
            reading_order[ref.get("regionRef", "")] = int(ref.get("index", 0))

    regions = findall(page, "TextRegion")
    regions.sort(key=lambda r: reading_order.get(r.get("id", ""), 999))

    lines: list[TextLine] = []
    for region in regions:
        region_id = region.get("id", "")
        for tl in findall(region, "TextLine"):
            te = find(tl, "TextEquiv")
            ue = find(te, "Unicode") if te is not None else None
            text = (ue.text or "").strip() if ue is not None else ""
            if not text:
                continue
            coords_elem = find(tl, "Coords")
            x, y, w, h = (
                _parse_coords(coords_elem.get("points", ""))
                if coords_elem is not None
                else (0, 0, 0, 0)
            )
            lines.append(
                TextLine(
                    text=text,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    region_id=region_id,
                    line_id=tl.get("id", ""),
                )
            )
    return lines, page_w, page_h


# ── Caption identification ────────────────────────────────────────────────────


def is_caption_line(line: TextLine) -> bool:
    text = line.text.strip()
    if not text:
        return False
    if CAPTION_PATTERN.match(text):
        return True
    if len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True
    return False


def identify_captions(lines: list[TextLine]) -> list[dict]:
    """Group consecutive matching lines into caption blocks."""
    captions: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_caption_line(line):
            text = line.text
            cx, cy, cw, ch = line.x, line.y, line.width, line.height
            j = i + 1
            while j < len(lines) and lines[j].region_id == line.region_id:
                nxt = lines[j]
                if is_caption_line(nxt):
                    break
                if len(nxt.text) < 70:
                    text += " " + nxt.text
                    ch = (nxt.y + nxt.height) - cy
                    cw = max(cw, nxt.width)
                    j += 1
                else:
                    break
            captions.append(
                {
                    "text": text,
                    "x": cx,
                    "y": cy,
                    "width": cw,
                    "height": ch,
                    "line_id": line.line_id,
                }
            )
            i = j
        else:
            i += 1
    return captions


# ── Image loading ─────────────────────────────────────────────────────────────


def _parse_image_filename(img_path: Path) -> dict | None:
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)_p(\d+)_img(\d+)\.png", img_path.name)
    if not m:
        return None
    return {
        "band": m.group(1),
        "chunk": m.group(2),
        "page": int(m.group(3)),
        "img_num": int(m.group(4)),
        "path": img_path,
    }


def load_image_info(images_dir: Path) -> dict[int, list[dict]]:
    """Load extracted image metadata grouped by page number."""
    by_page: dict[int, list[dict]] = {}
    for img_path in sorted(images_dir.glob("*_img*.png")):
        info = _parse_image_filename(img_path)
        if not info:
            continue
        img = cv2.imread(str(img_path))
        info["height"] = img.shape[0] if img is not None else 0
        info["width"] = img.shape[1] if img is not None else 0
        by_page.setdefault(info["page"], []).append(info)
    return by_page


# ── Matching ──────────────────────────────────────────────────────────────────


def match_by_order(
    captions: list[dict], page_images: list[dict]
) -> list[tuple[dict, dict]]:
    """Pair captions to images by vertical order (top-to-bottom on the page)."""
    sorted_caps = sorted(captions, key=lambda c: c["y"])
    sorted_imgs = sorted(page_images, key=lambda i: i["img_num"])
    return list(zip(sorted_imgs, sorted_caps))


def write_caption_md(
    img_path: Path, caption_text: str, band: str, page_num: int
) -> None:
    caption_clean = caption_text.replace("¬", "").strip()
    md_path = img_path.with_suffix(".md")
    content = (
        f"<!-- Volume: {band}, Page: {page_num} -->\n\n"
        f"![{caption_clean}]({img_path.name})\n\n"
        f"{caption_clean}\n"
    )
    md_path.write_text(content, encoding="utf-8")
    log.info("  Caption: %s → %s", md_path.name, caption_clean[:60])


# ── Per-folder processing ─────────────────────────────────────────────────────


def process_folder(folder: Path, extracted_dir: Path = EXTRACTED_DIR) -> None:
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder.name)
    if not m:
        log.warning("Skipping %s — doesn't match Band*_chunk* pattern", folder.name)
        return

    band, chunk = m.group(1), m.group(2)
    images_dir = extracted_dir / folder.name / "images"
    if not images_dir.exists():
        log.info("No extracted images for %s, skipping", folder.name)
        return

    xml_files = sorted(folder.glob("*.xml"))
    if not xml_files:
        log.warning("No XML files in %s", folder)
        return

    image_by_page = load_image_info(images_dir)
    if not image_by_page:
        log.info("No extracted images found in %s", images_dir)
        return

    log.info(
        "Matching captions for %s (%d pages with images)",
        folder.name,
        len(image_by_page),
    )
    total_matched = 0

    for xml_path in xml_files:
        page_m = re.match(r"\d+_p(\d+)\.xml", xml_path.name)
        if not page_m:
            continue
        page_num = int(page_m.group(1))
        if page_num not in image_by_page:
            continue

        lines, _, _ = parse_page_xml(xml_path)
        if not lines:
            continue

        captions = identify_captions(lines)
        if not captions:
            log.debug("  Page %d: no captions found", page_num)
            continue

        page_images = image_by_page[page_num]
        matches = match_by_order(captions, page_images)

        for img_info, caption in matches:
            write_caption_md(img_info["path"], caption["text"], band, page_num)
            total_matched += 1

        matched_ids = {id(c) for _, c in matches}
        unmatched = [c for c in captions if id(c) not in matched_ids]
        if unmatched:
            unmatched_path = (
                images_dir / f"{band}_{chunk}_p{page_num:03d}_unmatched_captions.txt"
            )
            with unmatched_path.open("w", encoding="utf-8") as f:
                for cap in unmatched:
                    f.write(f"[y={cap['y']}] {cap['text']}\n")

    log.info("  Matched %d caption(s) for %s", total_matched, folder.name)


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
        process_folder(folder, EXTRACTED_DIR)

    log.info("Done.")


if __name__ == "__main__":
    main()
