"""Article boundary detection: find where articles start/end in wiki pages."""

import re


def find_article_start_line(lines: list[str]) -> int | None:
    """Find the line index of '''Patrozinium:''' or '''Zum Bauwerk:''' in a page.

    Returns the 0-based line index, or None if neither marker is found.
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("'''Patrozinium:'''") or stripped.startswith("'''Patrozinium:"):
            return i
        if stripped.startswith("'''Zum Bauwerk:'''") or stripped.startswith("'''Zum Bauwerk:"):
            return i
    return None


def find_paragraph_before(lines: list[str], marker_line: int) -> int:
    """Find the start of the prose paragraph just above the marker line.

    Walks upward from marker_line-1, skipping blank lines, then collecting
    non-blank lines until a blank line or a comment/header/heading line.
    Returns the 0-based line index where the paragraph starts.
    """
    i = marker_line - 1
    while i >= 0 and lines[i].strip() == "":
        i -= 1

    if i < 0:
        return marker_line

    while i >= 0:
        stripped = lines[i].strip()
        if stripped == "":
            return i + 1
        if stripped.startswith("<!--") and ("citation-page" in stripped or "header:" in stripped):
            return i + 1
        if re.match(r"^==\s+.*\s+==$", stripped):
            return i
        if stripped.startswith("[[File:") or stripped.startswith("[[Datei:"):
            return i + 1
        i -= 1

    return 0


def find_next_article_start(lines: list[str], after_line: int) -> int | None:
    """Find the next '''Patrozinium:''' or '''Zum Bauwerk:''' after after_line.

    Returns the line index of the prose paragraph start before the next marker,
    or None if no next article is found.
    """
    for i in range(after_line, len(lines)):
        stripped = lines[i].strip()
        if (stripped.startswith("'''Patrozinium:'''") or stripped.startswith("'''Patrozinium:")
                or stripped.startswith("'''Zum Bauwerk:'''") or stripped.startswith("'''Zum Bauwerk:")):
            return find_paragraph_before(lines, i)
    return None
