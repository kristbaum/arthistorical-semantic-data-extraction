#!/usr/bin/env python3
"""Match captions from Transkribus PAGE XML to extracted images.

For each extracted image, this script:
1. Parses the PAGE XML files to extract text regions with coordinates
2. Identifies likely caption lines (short, starts with a section code)
3. Scales XML coordinates to the extracted page image resolution
4. Matches captions to image regions based on spatial proximity
5. Creates a .md file per image with the caption text
"""

import argparse
import logging
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

PAGE_NS = {
    "p2013": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15",
    "p2019": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15",
}

# Pattern for recognising caption/heading lines:
# Lines starting with a section code like "D", "C3", "E1", "F1-2", "EU1", "W1-2", etc.
# followed by an ALL-CAPS lemma/heading
CAPTION_PATTERN = re.compile(
    r"^(?:[A-Z]+\d*(?:-\d+)?(?:,\s*)?)+\s+[A-ZÄÖÜ\s\-,.:;()]+(?:\s|$)"
)
# Simpler pattern: line starts with a section code
SECTION_CODE_PATTERN = re.compile(
    r"^(?:E[IVX]*|[A-Z])\d*(?:-\d+)?\s"
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


@dataclass
class ImageRect:
    """An extracted image with its bounding box on the full page image."""
    path: Path
    x: int
    y: int
    width: int
    height: int
    page_num: int
    band: str
    chunk: str


def detect_namespace(root: ET.Element) -> str | None:
    """Detect the PAGE XML namespace from the root element."""
    tag = root.tag
    if "{" in tag:
        return tag.split("}")[0] + "}"
    return None


def parse_coords_points(points_str: str) -> tuple[int, int, int, int]:
    """Parse a 'points' attribute into (x, y, w, h) bounding box."""
    pairs = []
    for pair in points_str.strip().split():
        parts = pair.split(",")
        if len(parts) == 2:
            pairs.append((int(parts[0]), int(parts[1])))
    if not pairs:
        return 0, 0, 0, 0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return x_min, y_min, x_max - x_min, y_max - y_min


def parse_page_xml(xml_path: Path) -> tuple[list[TextLine], int, int, str]:
    """Parse a PAGE XML file and return text lines with coordinates.

    Returns: (text_lines, page_width, page_height, image_filename)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = detect_namespace(root)
    if not ns:
        log.warning("Cannot detect namespace in %s", xml_path)
        return [], 0, 0, ""

    def find(elem, tag):
        return elem.find(f"{ns}{tag}")

    def findall(elem, tag):
        return elem.findall(f"{ns}{tag}")

    def findall_recursive(elem, tag):
        return elem.findall(f".//{ns}{tag}")

    page = find(root, "Page")
    if page is None:
        return [], 0, 0, ""

    page_w = int(page.get("imageWidth", 0))
    page_h = int(page.get("imageHeight", 0))
    img_fn = page.get("imageFilename", "")

    # Build reading order map
    reading_order = {}
    ro = find(page, "ReadingOrder")
    if ro is not None:
        for og in findall_recursive(ro, "RegionRefIndexed"):
            idx = int(og.get("index", 0))
            ref = og.get("regionRef", "")
            reading_order[ref] = idx

    # Collect all text regions sorted by reading order
    regions = findall(page, "TextRegion")
    regions.sort(key=lambda r: reading_order.get(r.get("id", ""), 999))

    lines = []
    for region in regions:
        region_id = region.get("id", "")
        for tl in findall(region, "TextLine"):
            line_id = tl.get("id", "")
            coords_elem = find(tl, "Coords")
            text_equiv = find(tl, "TextEquiv")
            unicode_elem = find(text_equiv, "Unicode") if text_equiv is not None else None

            text = ""
            if unicode_elem is not None and unicode_elem.text:
                text = unicode_elem.text.strip()

            if not text:
                continue

            if coords_elem is not None:
                points = coords_elem.get("points", "")
                x, y, w, h = parse_coords_points(points)
            else:
                x, y, w, h = 0, 0, 0, 0

            lines.append(TextLine(
                text=text, x=x, y=y, width=w, height=h,
                region_id=region_id, line_id=line_id
            ))

    return lines, page_w, page_h, img_fn


def is_caption_line(line: TextLine) -> bool:
    """Heuristic: is this text line likely an image caption or heading?"""
    text = line.text.strip()
    if not text:
        return False

    # Section code + all-caps text
    if CAPTION_PATTERN.match(text):
        return True

    # Lines that are entirely uppercase and short (likely headings for images)
    if len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True

    return False


def identify_captions(lines: list[TextLine]) -> list[dict]:
    """Identify caption blocks from text lines.

    A caption may span multiple lines – the first line matches the pattern,
    and subsequent lines in the same region that are short continue it.
    """
    captions = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_caption_line(line):
            caption_text = line.text
            caption_x = line.x
            caption_y = line.y
            caption_w = line.width
            caption_h = line.height

            # Peek ahead for continuation lines in same region
            j = i + 1
            while j < len(lines) and lines[j].region_id == line.region_id:
                next_line = lines[j]
                # If the next line is another caption or very long body text, stop
                if is_caption_line(next_line):
                    break
                # Include short continuation lines
                if len(next_line.text) < 70:
                    caption_text += " " + next_line.text
                    caption_h = (next_line.y + next_line.height) - caption_y
                    caption_w = max(caption_w, next_line.width)
                    j += 1
                else:
                    break

            captions.append({
                "text": caption_text,
                "x": caption_x,
                "y": caption_y,
                "width": caption_w,
                "height": caption_h,
                "line_id": line.line_id,
            })
            i = j
        else:
            i += 1

    return captions


def parse_image_filename(img_path: Path) -> dict | None:
    """Parse extracted image filename like Band03-1_chunk001_p018_img001.png."""
    m = re.match(
        r"(Band[\d\-]+)_(chunk\d+)_p(\d+)_img(\d+)\.png",
        img_path.name,
    )
    if not m:
        return None
    return {
        "band": m.group(1),
        "chunk": m.group(2),
        "page": int(m.group(3)),
        "img_num": int(m.group(4)),
        "path": img_path,
    }


def load_image_rects(images_dir: Path) -> dict[int, list[dict]]:
    """Load extracted image info grouped by page number.

    Uses the image file dimensions to infer the bounding box.
    For proper spatial matching, we'd need the coordinates saved during extraction.
    Currently we match by vertical position on the page.
    """
    import cv2

    by_page: dict[int, list[dict]] = {}
    for img_path in sorted(images_dir.glob("*_img*.png")):
        info = parse_image_filename(img_path)
        if not info:
            continue
        # Read image to get dimensions
        img = cv2.imread(str(img_path))
        if img is not None:
            info["height"] = img.shape[0]
            info["width"] = img.shape[1]
        else:
            info["height"] = 0
            info["width"] = 0

        page_num = info["page"]
        by_page.setdefault(page_num, []).append(info)

    return by_page


def match_captions_to_images(
    captions: list[dict],
    page_images: list[dict],
    xml_w: int,
    xml_h: int,
    page_img_w: int,
    page_img_h: int,
) -> list[tuple[dict, dict]]:
    """Match caption regions to extracted images using spatial proximity.

    Scale XML coordinates to the page image resolution and find
    the closest caption below or above each image.
    """
    if not captions or not page_images:
        return []

    # Scale factors from XML coordinate space to actual page image space
    scale_x = page_img_w / xml_w if xml_w > 0 else 1.0
    scale_y = page_img_h / xml_h if xml_h > 0 else 1.0

    matches = []
    used_captions = set()

    for img_info in page_images:
        best_caption = None
        best_distance = float("inf")

        for ci, caption in enumerate(captions):
            if ci in used_captions:
                continue

            # Scale caption coordinates to page image space
            cap_y_scaled = caption["y"] * scale_y
            cap_h_scaled = caption["height"] * scale_y

            # For now we don't have exact image coordinates from extraction,
            # so we match based on caption order and image order
            # This is a simplified approach; for better results,
            # save coordinates during extraction (see extract_images.py)

            # Use vertical position as primary matching criterion
            # Captions are typically directly above or below the image
            img_center_y = img_info.get("center_y", 0)
            cap_center_y = cap_y_scaled + cap_h_scaled / 2

            dist = abs(cap_center_y - img_center_y)
            if dist < best_distance:
                best_distance = dist
                best_caption = (ci, caption)

        if best_caption is not None:
            ci, caption = best_caption
            used_captions.add(ci)
            matches.append((img_info, caption))

    return matches


def match_by_order(
    captions: list[dict],
    page_images: list[dict],
    xml_w: int,
    xml_h: int,
) -> list[tuple[dict, dict]]:
    """Simple matching: match captions to images by vertical order on the page.

    Scale caption y-coordinates and image positions, sort both by y, and pair them.
    """
    if not captions or not page_images:
        return []

    # Sort captions by vertical position
    sorted_caps = sorted(captions, key=lambda c: c["y"])
    # Sort images by their index number (which corresponds to spatial order)
    sorted_imgs = sorted(page_images, key=lambda i: i["img_num"])

    matches = []
    for img_info, caption in zip(sorted_imgs, sorted_caps):
        matches.append((img_info, caption))

    return matches


def write_caption_md(img_path: Path, caption_text: str, band: str, page_num: int):
    """Write a markdown file alongside the image with the caption."""
    md_path = img_path.with_suffix(".md")
    # Clean up caption text
    caption_clean = caption_text.replace("¬", "").strip()

    content = f"<!-- Volume: {band}, Page: {page_num} -->\n\n"
    content += f"![{caption_clean}]({img_path.name})\n\n"
    content += f"{caption_clean}\n"

    md_path.write_text(content, encoding="utf-8")
    log.info("  Caption: %s → %s", md_path.name, caption_clean[:60])


def process_folder(folder: Path, extracted_dir: Path):
    """Process one Band/chunk folder: match captions to extracted images."""
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder.name)
    if not m:
        log.warning("Skipping %s – doesn't match pattern", folder.name)
        return

    band = m.group(1)
    chunk = m.group(2)

    images_dir = extracted_dir / folder.name / "images"
    if not images_dir.exists():
        log.info("No extracted images for %s, skipping", folder.name)
        return

    # Find XML files
    xml_files = sorted(folder.glob("*.xml"))
    if not xml_files:
        log.warning("No XML files in %s", folder)
        return

    # Load extracted images grouped by page
    try:
        import cv2  # noqa: F811
        image_by_page = load_image_rects(images_dir)
    except ImportError:
        log.error("OpenCV not installed. Run: pip install opencv-python")
        sys.exit(1)

    if not image_by_page:
        log.info("No extracted images found in %s", images_dir)
        return

    log.info("Processing captions for %s (%d pages with images)", folder.name, len(image_by_page))
    total_matched = 0

    for xml_path in xml_files:
        # Extract page number from filename like 0018_p018.xml
        page_m = re.match(r"\d+_p(\d+)\.xml", xml_path.name)
        if not page_m:
            continue
        page_num = int(page_m.group(1))

        if page_num not in image_by_page:
            continue

        lines, xml_w, xml_h, _ = parse_page_xml(xml_path)
        if not lines:
            continue

        captions = identify_captions(lines)
        page_images = image_by_page[page_num]

        if not captions:
            log.debug("  Page %d: no captions found", page_num)
            continue

        # Match captions to images by order
        matches = match_by_order(captions, page_images, xml_w, xml_h)

        for img_info, caption in matches:
            write_caption_md(
                img_info["path"],
                caption["text"],
                band,
                page_num,
            )
            total_matched += 1

        # Write remaining unmatched captions to a separate file for review
        matched_cap_ids = {id(c) for _, c in matches}
        unmatched = [c for c in captions if id(c) not in matched_cap_ids]
        if unmatched:
            unmatched_path = images_dir / f"{band}_{chunk}_p{page_num:03d}_unmatched_captions.txt"
            with open(unmatched_path, "w", encoding="utf-8") as f:
                for cap in unmatched:
                    f.write(f"[y={cap['y']}] {cap['text']}\n")

    log.info("  Matched %d caption(s) for %s", total_matched, folder.name)


def main():
    parser = argparse.ArgumentParser(description="Match XML captions to extracted images")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Root data directory containing Band*_chunk* folders with XMLs",
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=Path("data/extracted"),
        help="Directory with extracted images (from extract_images.py)",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Process only this specific folder",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    data_dir = args.data_dir

    if args.folder:
        folders = [data_dir / args.folder]
    else:
        folders = sorted(
            p for p in data_dir.iterdir() if p.is_dir() and re.match(r"Band[\d\-]+_chunk\d+", p.name)
        )

    if not folders:
        log.error("No matching folders found in %s", data_dir)
        sys.exit(1)

    for folder in folders:
        process_folder(folder, args.extracted_dir)

    log.info("Done.")


if __name__ == "__main__":
    main()
