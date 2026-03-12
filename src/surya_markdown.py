"""Caption matching, line joining, and Markdown assembly."""

import logging
from pathlib import Path

from surya_config import CAPTION_PATTERN, IMAGE_LABELS, Region

log = logging.getLogger(__name__)


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
        # Still include caption as bold text for accessibility
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
