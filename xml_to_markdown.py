#!/usr/bin/env python3
"""Convert Transkribus PAGE XML files to Markdown.

For each Band/chunk folder, this script:
1. Parses XML files in page order
2. Follows the reading order specified in the XML
3. Joins hyphenated words (soft hyphens ¬ and line-break hyphens)
4. Removes repeating page headers (e.g. chapter titles at top of pages)
5. Replaces image captions with Markdown image links
6. Adds page numbers as invisible HTML comments
7. Produces one .md file per page
"""

import argparse
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Pattern for caption lines starting with section codes
CAPTION_PATTERN = re.compile(
    r"^(?:[A-Z]+\d*(?:-\d+)?(?:,\s*)?)+\s+[A-ZÄÖÜ][A-ZÄÖÜ\s\-,.:;()]+(?:\s|$)"
)

# Pattern for section codes at start of line
SECTION_CODE_RE = re.compile(
    r"^((?:[A-Z]{1,3}\d*(?:-\d+)?(?:,\s*)?)+)\s+((?:[A-ZÄÖÜ][A-ZÄÖÜ\s\-,.:;()]*[A-ZÄÖÜ.)]))\s*(.*)"
)


def detect_namespace(root: ET.Element) -> str | None:
    tag = root.tag
    if "{" in tag:
        return tag.split("}")[0] + "}"
    return None


def parse_coords_points(points_str: str) -> tuple[int, int, int, int]:
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


def parse_page_xml(xml_path: Path) -> tuple[list[dict], int, int]:
    """Parse a PAGE XML file into ordered text blocks.

    Returns: (blocks, page_width, page_height)
    Each block is a dict with keys: lines (list of str), region_id, y_pos
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = detect_namespace(root)
    if not ns:
        return [], 0, 0

    def find(elem, tag):
        return elem.find(f"{ns}{tag}")

    def findall(elem, tag):
        return elem.findall(f"{ns}{tag}")

    def findall_recursive(elem, tag):
        return elem.findall(f".//{ns}{tag}")

    page = find(root, "Page")
    if page is None:
        return [], 0, 0

    page_w = int(page.get("imageWidth", 0))
    page_h = int(page.get("imageHeight", 0))

    # Build reading order
    reading_order = {}
    ro = find(page, "ReadingOrder")
    if ro is not None:
        for ref in findall_recursive(ro, "RegionRefIndexed"):
            idx = int(ref.get("index", 0))
            region_ref = ref.get("regionRef", "")
            reading_order[region_ref] = idx

    regions = findall(page, "TextRegion")
    regions.sort(key=lambda r: reading_order.get(r.get("id", ""), 999))

    blocks = []
    for region in regions:
        region_id = region.get("id", "")
        region_coords = find(region, "Coords")
        region_y = 0
        if region_coords is not None:
            _, region_y, _, _ = parse_coords_points(region_coords.get("points", ""))

        text_lines = findall(region, "TextLine")

        # Sort text lines by their reading order attribute if available
        def line_sort_key(tl):
            custom = tl.get("custom", "")
            m = re.search(r"readingOrder\s*\{index:(\d+)", custom)
            if m:
                return int(m.group(1))
            # Fallback: sort by y coordinate
            coords = find(tl, "Coords")
            if coords is not None:
                _, y, _, _ = parse_coords_points(coords.get("points", ""))
                return y
            return 0

        text_lines.sort(key=line_sort_key)

        lines = []
        for tl in text_lines:
            te = find(tl, "TextEquiv")
            ue = find(te, "Unicode") if te is not None else None
            text = ""
            if ue is not None and ue.text:
                text = ue.text

            coords_elem = find(tl, "Coords")
            y_pos = 0
            if coords_elem is not None:
                _, y_pos, _, _ = parse_coords_points(coords_elem.get("points", ""))

            lines.append({"text": text, "y": y_pos})

        if lines:
            blocks.append({
                "lines": lines,
                "region_id": region_id,
                "y_pos": region_y,
            })

    return blocks, page_w, page_h


def detect_page_header(all_pages_blocks: dict[int, list[dict]]) -> str | None:
    """Detect repeating page header text that appears on many pages.

    Returns the header text if found, or None.
    """
    first_lines = Counter()
    for page_num, blocks in all_pages_blocks.items():
        if blocks:
            # Check first line of first block
            first_block = blocks[0]
            if first_block["lines"]:
                text = first_block["lines"][0]["text"].strip()
                if text:
                    first_lines[text] += 1

    if not first_lines:
        return None

    # The most common first line across pages is likely the header
    most_common, count = first_lines.most_common(1)[0]
    total_pages = len(all_pages_blocks)
    # If it appears on more than 30% of pages, it's likely a header
    if count > max(2, total_pages * 0.3):
        log.info("Detected page header: '%s' (on %d/%d pages)", most_common, count, total_pages)
        return most_common

    return None


def is_caption_line(text: str) -> bool:
    """Check if a line looks like an image caption."""
    text = text.strip()
    if not text:
        return False
    if CAPTION_PATTERN.match(text):
        return True
    if len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True
    return False


def join_lines(lines: list[dict], remove_header: str | None = None) -> list[str]:
    """Join text lines, handling hyphenation and line breaks.

    - Soft hyphens (¬) at end of line: join with next line, removing the hyphen
    - Regular hyphens (-) at end of line before a lowercase letter: join
    - Other line breaks: replace with space (same paragraph) or double newline
    """
    if not lines:
        return []

    result_parts = []
    skip_next = False

    for i, line_info in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        text = line_info["text"]
        if not text.strip():
            continue

        # Remove page header
        if remove_header and text.strip() == remove_header:
            continue

        # Handle hyphenation at end of line
        if text.endswith("¬") or text.endswith("\u00AC"):
            # Soft hyphen: always join with next line
            text = text.rstrip("¬\u00AC")
            if i + 1 < len(lines):
                next_text = lines[i + 1]["text"]
                text = text + next_text
                skip_next = True
        elif text.endswith("-") and i + 1 < len(lines):
            next_text = lines[i + 1]["text"]
            # Join if next line starts with lowercase (word continuation)
            if next_text and next_text[0].islower():
                text = text[:-1] + next_text
                skip_next = True

        result_parts.append(text)

    return result_parts


def format_block_as_markdown(
    parts: list[str],
    band: str,
    chunk: str,
    page_num: int,
    images_dir: Path | None = None,
) -> str:
    """Format text parts into Markdown, converting captions to image links."""
    output_lines = []

    for text in parts:
        text = text.strip()
        if not text:
            continue

        # Check if this is a caption line – convert to image link
        m = SECTION_CODE_RE.match(text)
        if m and is_caption_line(text):
            code = m.group(1).strip()
            title = m.group(2).strip()
            rest = m.group(3).strip() if m.group(3) else ""

            # Build a potential image filename
            img_name = f"{band}_{chunk}_p{page_num:03d}"

            # Check if a matching image file exists
            img_found = False
            if images_dir and images_dir.exists():
                for img_file in images_dir.glob(f"{img_name}_img*.png"):
                    # Check if this image has a caption .md matching this text
                    cap_md = img_file.with_suffix(".md")
                    if cap_md.exists():
                        cap_text = cap_md.read_text(encoding="utf-8")
                        if code in cap_text or title[:20] in cap_text:
                            rel_path = img_file.relative_to(images_dir.parent.parent)
                            output_lines.append(f"\n**{code} {title}**\n")
                            output_lines.append(f"![{code} {title}]({rel_path})\n")
                            if rest:
                                output_lines.append(rest)
                            img_found = True
                            break

            if not img_found:
                # No image found, just format as a heading
                output_lines.append(f"\n**{code} {title}**")
                if rest:
                    output_lines.append(rest)
        else:
            output_lines.append(text)

    return " ".join(output_lines)


def blocks_to_markdown(
    blocks: list[dict],
    page_num: int,
    band: str,
    chunk: str,
    remove_header: str | None,
    images_dir: Path | None,
) -> str:
    """Convert page blocks to a single Markdown string."""
    md_parts = []

    for block in blocks:
        parts = join_lines(block["lines"], remove_header)
        if not parts:
            continue

        formatted = format_block_as_markdown(parts, band, chunk, page_num, images_dir)
        if formatted.strip():
            md_parts.append(formatted)

    if not md_parts:
        return ""

    # Combine all blocks with paragraph separators
    page_md = f"<!-- Page {page_num} -->\n\n"
    page_md += "\n\n".join(md_parts)
    page_md += "\n"

    return page_md


def process_folder(folder: Path, output_base: Path, extracted_dir: Path | None):
    """Process one Band/chunk folder: convert all XMLs to Markdown."""
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder.name)
    if not m:
        log.warning("Skipping %s – doesn't match pattern", folder.name)
        return

    band = m.group(1)
    chunk = m.group(2)

    xml_files = sorted(folder.glob("*.xml"))
    if not xml_files:
        log.warning("No XML files in %s", folder)
        return

    output_dir = output_base / folder.name / "markdown"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Images directory for linking
    images_dir = None
    if extracted_dir:
        candidate = extracted_dir / folder.name / "images"
        if candidate.exists():
            images_dir = candidate

    # First pass: parse all pages and detect header
    all_pages: dict[int, list[dict]] = {}
    for xml_path in xml_files:
        page_m = re.match(r"\d+_p(\d+)\.xml", xml_path.name)
        if not page_m:
            continue
        page_num = int(page_m.group(1))
        blocks, _, _ = parse_page_xml(xml_path)
        all_pages[page_num] = blocks

    # Detect repeating header
    remove_header = detect_page_header(all_pages)

    log.info("Converting %s: %d pages", folder.name, len(all_pages))

    # Second pass: convert to markdown
    for page_num in sorted(all_pages.keys()):
        blocks = all_pages[page_num]
        md_content = blocks_to_markdown(
            blocks, page_num, band, chunk, remove_header, images_dir
        )

        if md_content.strip():
            out_path = output_dir / f"p{page_num:03d}.md"
            out_path.write_text(md_content, encoding="utf-8")
            log.debug("  Wrote %s", out_path.name)

    log.info("  Done: %d markdown files written to %s", len(all_pages), output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Transkribus PAGE XML to Markdown"
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
        help="Output directory for markdown files",
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=None,
        help="Directory with extracted images (for image links). "
             "Defaults to --output-dir.",
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

    if args.extracted_dir is None:
        args.extracted_dir = args.output_dir

    data_dir = args.data_dir

    if args.folder:
        folders = [data_dir / args.folder]
    else:
        folders = sorted(
            p for p in data_dir.iterdir()
            if p.is_dir() and re.match(r"Band[\d\-]+_chunk\d+", p.name)
        )

    if not folders:
        log.error("No matching folders found in %s", data_dir)
        return

    for folder in folders:
        process_folder(folder, args.output_dir, args.extracted_dir)

    log.info("All done.")


if __name__ == "__main__":
    main()
