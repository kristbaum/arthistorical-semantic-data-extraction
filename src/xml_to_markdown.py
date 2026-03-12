#!/usr/bin/env python3
"""Convert Transkribus PAGE XML files to Markdown.

For each Band/chunk folder this script:
1. Parses XML files in page order following the <ReadingOrder> element
2. Joins hyphenated words (soft hyphens ¬ and line-break hyphens -)
3. Detects and removes repeating page headers (e.g. chapter titles)
4. Replaces image captions with Markdown image links when images exist
5. Adds page numbers as invisible HTML comments
6. Produces one .md file per page
"""

import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Root data directory containing Band*_chunk* folders with XML files
DATA_DIR = Path("data")

# Output base directory; markdown files go to OUTPUT_DIR/folder.name/markdown/
OUTPUT_DIR = Path("data/extracted")

# Directory with extracted images (for building image links)
# Set to None to skip image linking
EXTRACTED_DIR: Path | None = Path("data/extracted")

# ──────────────────────────────────────────────────────────────────────────────

CAPTION_PATTERN = re.compile(
    r"^(?:[A-Z]+\d*(?:-\d+)?(?:,\s*)?)+\s+[A-ZÄÖÜ][A-ZÄÖÜ\s\-,.:;()]+(?:\s|$)"
)
SECTION_CODE_RE = re.compile(
    r"^((?:[A-Z]{1,3}\d*(?:-\d+)?(?:,\s*)?)+)\s+((?:[A-ZÄÖÜ][A-ZÄÖÜ\s\-,.:;()]*[A-ZÄÖÜ.)]))\s*(.*)"
)


# ── XML helpers ───────────────────────────────────────────────────────────────


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


def parse_page_xml(xml_path: Path) -> tuple[list[dict], int, int]:
    """Parse a PAGE XML file into ordered text blocks.

    Returns: (blocks, page_width, page_height)
    Each block: {"lines": [{"text": str, "y": int}], "region_id": str, "y_pos": int}
    """
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

    blocks: list[dict] = []
    for region in regions:
        region_id = region.get("id", "")
        region_coords = find(region, "Coords")
        _, region_y, _, _ = (
            _parse_coords(region_coords.get("points", ""))
            if region_coords is not None
            else (0, 0, 0, 0)
        )

        text_lines = findall(region, "TextLine")

        def _line_order(tl) -> int:
            m = re.search(r"readingOrder\s*\{index:(\d+)", tl.get("custom", ""))
            if m:
                return int(m.group(1))
            ce = find(tl, "Coords")
            if ce is not None:
                _, y, _, _ = _parse_coords(ce.get("points", ""))
                return y
            return 0

        text_lines.sort(key=_line_order)

        lines: list[dict] = []
        for tl in text_lines:
            te = find(tl, "TextEquiv")
            ue = find(te, "Unicode") if te is not None else None
            text = (ue.text or "") if ue is not None else ""
            ce = find(tl, "Coords")
            _, y_pos, _, _ = (
                _parse_coords(ce.get("points", "")) if ce is not None else (0, 0, 0, 0)
            )
            lines.append({"text": text, "y": y_pos})

        if lines:
            blocks.append({"lines": lines, "region_id": region_id, "y_pos": region_y})

    return blocks, page_w, page_h


# ── Header detection ──────────────────────────────────────────────────────────


def detect_page_header(all_pages: dict[int, list[dict]]) -> str | None:
    """Return the text of a repeating page header found on >30% of pages, or None."""
    first_lines: Counter = Counter()
    for blocks in all_pages.values():
        if blocks and blocks[0]["lines"]:
            text = blocks[0]["lines"][0]["text"].strip()
            if text:
                first_lines[text] += 1

    if not first_lines:
        return None

    most_common, count = first_lines.most_common(1)[0]
    total = len(all_pages)
    if count > max(2, total * 0.3):
        log.info(
            "Detected page header: '%s' (on %d/%d pages)", most_common, count, total
        )
        return most_common
    return None


# ── Line joining ──────────────────────────────────────────────────────────────


def join_lines(lines: list[dict], remove_header: str | None = None) -> list[str]:
    """Join line dicts into strings, handling hyphenation and header removal.

    - ¬ at end of line: soft hyphen — join directly with next line
    - - at end of line before lowercase: hard hyphen — join, remove hyphen
    """
    if not lines:
        return []

    parts: list[str] = []
    skip_next = False
    for i, info in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        text = info["text"]
        if not text.strip():
            continue
        if remove_header and text.strip() == remove_header:
            continue

        if text.endswith("¬") or text.endswith("\u00ac"):
            text = text.rstrip("¬\u00ac")
            if i + 1 < len(lines):
                text += lines[i + 1]["text"]
                skip_next = True
        elif text.endswith("-") and i + 1 < len(lines):
            nxt = lines[i + 1]["text"]
            if nxt and nxt[0].islower():
                text = text[:-1] + nxt
                skip_next = True

        parts.append(text)
    return parts


# ── Markdown formatting ───────────────────────────────────────────────────────


def _is_caption(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if CAPTION_PATTERN.match(text):
        return True
    if len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True
    return False


def format_block(
    parts: list[str],
    band: str,
    chunk: str,
    page_num: int,
    images_dir: Path | None,
) -> str:
    output: list[str] = []
    for text in parts:
        text = text.strip()
        if not text:
            continue

        m = SECTION_CODE_RE.match(text)
        if m and _is_caption(text):
            code = m.group(1).strip()
            title = m.group(2).strip()
            rest = m.group(3).strip() if m.group(3) else ""
            img_name = f"{band}_{chunk}_p{page_num:03d}"
            img_found = False

            if images_dir and images_dir.exists():
                for img_file in sorted(images_dir.glob(f"{img_name}_img*.png")):
                    cap_md = img_file.with_suffix(".md")
                    if cap_md.exists():
                        cap_text = cap_md.read_text(encoding="utf-8")
                        if code in cap_text or title[:20] in cap_text:
                            rel_path = img_file.relative_to(images_dir.parent.parent)
                            output.append(f"\n**{code} {title}**\n")
                            output.append(f"![{code} {title}]({rel_path})\n")
                            if rest:
                                output.append(rest)
                            img_found = True
                            break

            if not img_found:
                output.append(f"\n**{code} {title}**")
                if rest:
                    output.append(rest)
        else:
            output.append(text)

    return " ".join(output)


def blocks_to_markdown(
    blocks: list[dict],
    page_num: int,
    band: str,
    chunk: str,
    remove_header: str | None,
    images_dir: Path | None,
) -> str:
    md_parts: list[str] = []
    for block in blocks:
        parts = join_lines(block["lines"], remove_header)
        if not parts:
            continue
        formatted = format_block(parts, band, chunk, page_num, images_dir)
        if formatted.strip():
            md_parts.append(formatted)

    if not md_parts:
        return ""

    return f"<!-- Page {page_num} -->\n\n" + "\n\n".join(md_parts) + "\n"


# ── Per-folder processing ─────────────────────────────────────────────────────


def process_folder(
    folder: Path,
    output_base: Path = OUTPUT_DIR,
    extracted_dir: Path | None = EXTRACTED_DIR,
) -> None:
    m = re.match(r"(Band[\d\-]+)_(chunk\d+)", folder.name)
    if not m:
        log.warning("Skipping %s — doesn't match Band*_chunk* pattern", folder.name)
        return

    band, chunk = m.group(1), m.group(2)
    xml_files = sorted(folder.glob("*.xml"))
    if not xml_files:
        log.warning("No XML files in %s", folder)
        return

    output_dir = output_base / folder.name / "markdown"
    output_dir.mkdir(parents=True, exist_ok=True)

    images_dir: Path | None = None
    if extracted_dir:
        candidate = extracted_dir / folder.name / "images"
        if candidate.exists():
            images_dir = candidate

    # First pass: parse all pages, detect repeating header
    all_pages: dict[int, list[dict]] = {}
    for xml_path in xml_files:
        page_m = re.match(r"\d+_p(\d+)\.xml", xml_path.name)
        if not page_m:
            continue
        page_num = int(page_m.group(1))
        blocks, _, _ = parse_page_xml(xml_path)
        all_pages[page_num] = blocks

    remove_header = detect_page_header(all_pages)
    log.info("Converting %s: %d pages", folder.name, len(all_pages))

    # Second pass: write one .md per page
    for page_num in sorted(all_pages.keys()):
        content = blocks_to_markdown(
            all_pages[page_num], page_num, band, chunk, remove_header, images_dir
        )
        if content.strip():
            (output_dir / f"p{page_num:03d}.md").write_text(content, encoding="utf-8")

    log.info("  %d markdown files → %s", len(all_pages), output_dir)


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
        process_folder(folder, OUTPUT_DIR, EXTRACTED_DIR)

    log.info("All done.")


if __name__ == "__main__":
    main()
