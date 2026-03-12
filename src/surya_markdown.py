"""Caption matching, line joining, and MediaWiki markup assembly."""

import logging

from surya_config import IMAGE_LABELS, Region

log = logging.getLogger(__name__)


def match_captions_to_images(regions: list[Region]) -> None:
    """Match Caption regions to their nearest Picture/Figure region.

    Stores the caption text on the image Region's ``caption`` field.
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
            best_img.caption = caption_clean
            log.info("  Caption → %s: %s", best_img.image_path.name, caption_clean[:60])


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
            text = text.rstrip("¬\u00ac").rstrip()
        elif text.endswith("-") and i + 1 < len(lines):
            nxt = lines[i + 1].lstrip()
            if nxt and nxt[0].islower():
                # Word-break hyphen before lowercase: join without hyphen
                text = text[:-1].rstrip()
            else:
                text += " "
        else:
            text += " "

        parts.append(text)

    return "".join(parts).strip()


# ── MediaWiki assembly ────────────────────────────────────────────────────────


def _region_to_mediawiki(region: Region) -> str | None:
    """Convert a single region to its MediaWiki markup representation."""
    if region.label in IMAGE_LABELS:
        if region.image_path is None:
            return None
        caption = region.caption or region.image_path.stem
        return f"\n[[File:{region.image_path.name}|thumb|{caption}]]\n"

    if region.label == "Caption":
        # Captions matched to images are already embedded via [[File:...]]
        # Include unmatched captions as bold text
        text = join_lines(region.lines)
        if text:
            return f"\n'''{text}'''\n"
        return None

    if region.label in ("Section-header", "SectionHeader"):
        text = join_lines(region.lines)
        if text:
            return f"\n== {text} ==\n"
        return None

    if region.label in ("PageHeader", "Page-header"):
        # Page headers are typically repeating — include as comment
        text = join_lines(region.lines)
        if text:
            return f"<!-- header: {text} -->"
        return None

    if region.label in ("PageFooter", "Page-footer", "Footnote"):
        text = join_lines(region.lines)
        if text:
            return f"\n----\n{text}\n"
        return None

    # Default: Text, List-item, etc.
    text = join_lines(region.lines)
    if text:
        return text
    return None


def assemble_mediawiki(
    regions: list[Region], page_num: int, folder_name: str = ""
) -> str:
    """Assemble MediaWiki markup for one page from its layout regions."""
    parts: list[str] = []
    for region in regions:
        wiki = _region_to_mediawiki(region)
        if wiki:
            parts.append(wiki)

    if not parts:
        return ""

    header = f"<!-- {folder_name} Page {page_num} -->" if folder_name else f"<!-- Page {page_num} -->"
    return header + "\n\n" + "\n\n".join(parts) + "\n"
