"""Assign pass1 pages to articles or before/after buckets for a band.

Walks through ALL pass1 pages sequentially, matching each page to an article
from the CSV metadata based on page numbers.  Patrozinium / Zum Bauwerk
markers are used only to split pages that sit on a boundary between two
articles (or between "before" content and the first article).
"""

from pathlib import Path

from .boundaries import find_article_start_line, find_paragraph_before
from .helpers import extract_citation_page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_page(text: str) -> int | None:
    """Get the book page number from citation metadata (top preferred)."""
    page = extract_citation_page(text, "top")
    if page is None:
        page = extract_citation_page(text, "bottom")
    return page


def _find_all_markers(lines: list[str]) -> list[int]:
    """Return line indices of all '''Patrozinium:''' / '''Zum Bauwerk:''' markers."""
    markers: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("'''Patrozinium:") or stripped.startswith("'''Zum Bauwerk:"):
            markers.append(i)
    return markers


def clean_content(text: str) -> str:
    """Strip leading/trailing blank lines."""
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main assembly function
# ---------------------------------------------------------------------------

def assemble_band(
    ordered_files: list[tuple[Path, str]],
    articles: list[dict],
) -> tuple[list[str], list[list[str]], list[str]]:
    """Assign every pass1 page in a band to an article or before/after bucket.

    Parameters
    ----------
    ordered_files : list of (path, text) tuples, sorted by chunk then page.
    articles : list of dicts, sorted by ``_seite_von``.
        Each dict must contain ``_seite_von`` (int) and ``_seite_bis`` (int).

    Returns
    -------
    (before_parts, art_parts, after_parts)
        *before_parts*  – list of text segments for pages before the first article.
        *art_parts*     – ``art_parts[i]`` is a list of text segments for ``articles[i]``.
        *after_parts*   – list of text segments for pages after the last article.
    """
    n = len(articles)
    before: list[str] = []
    after: list[str] = []
    art_parts: list[list[str]] = [[] for _ in range(n)]

    if not articles or not ordered_files:
        return [t for _, t in ordered_files], art_parts, []

    first_sv = articles[0]["_seite_von"]
    last_sb = articles[-1]["_seite_bis"]

    for _fpath, ftext in ordered_files:
        page = _get_page(ftext)

        # Unknown page number – treat as "before" content
        if page is None:
            before.append(ftext)
            continue

        # ── Before all articles ──────────────────────────────────────
        if page < first_sv:
            before.append(ftext)
            continue

        # ── After all articles ───────────────────────────────────────
        if page > last_sb:
            after.append(ftext)
            continue

        # ── Find which article(s) claim this page ────────────────────
        claiming = [
            i for i in range(n)
            if articles[i]["_seite_von"] <= page <= articles[i]["_seite_bis"]
        ]

        # Gap between articles – assign to nearest previous article
        if not claiming:
            prev = [i for i in range(n) if articles[i]["_seite_bis"] < page]
            if prev:
                art_parts[prev[-1]].append(ftext)
            else:
                before.append(ftext)
            continue

        # ── Single article claims this page ──────────────────────────
        if len(claiming) == 1:
            idx = claiming[0]
            art = articles[idx]
            is_start = (page == art["_seite_von"])

            # Check if the previous article's range also reaches this page
            prev_here = (
                idx - 1
                if idx > 0 and articles[idx - 1]["_seite_bis"] >= page
                else None
            )

            if is_start and prev_here is not None:
                # Boundary: previous article ends here, current starts here
                _split_page(ftext, art_parts[prev_here], art_parts[idx])
            elif is_start:
                # First page of article with no overlap from previous
                lines = ftext.splitlines()
                marker = find_article_start_line(lines)
                if marker is not None:
                    para = find_paragraph_before(lines, marker)
                    if para > 0:
                        # Content above the article start → previous or before
                        target = art_parts[idx - 1] if idx > 0 else before
                        target.append("\n".join(lines[:para]))
                    art_parts[idx].append("\n".join(lines[para:]))
                else:
                    # No marker found – whole page to this article
                    art_parts[idx].append(ftext)
            else:
                # Interior / end page – full content to this article
                art_parts[idx].append(ftext)
            continue

        # ── Multiple articles claim this page (boundary) ─────────────
        _split_page_multi(ftext, claiming, articles, art_parts)

    return before, art_parts, after


# ---------------------------------------------------------------------------
# Page splitting helpers
# ---------------------------------------------------------------------------

def _split_page(
    ftext: str,
    prev_parts: list[str],
    curr_parts: list[str],
) -> None:
    """Split a page between two articles using the first marker found."""
    lines = ftext.splitlines()
    marker = find_article_start_line(lines)
    if marker is not None:
        para = find_paragraph_before(lines, marker)
        if para > 0:
            prev_parts.append("\n".join(lines[:para]))
        curr_parts.append("\n".join(lines[para:]))
    else:
        # No marker – give everything to the new article
        curr_parts.append(ftext)


def _split_page_multi(
    ftext: str,
    claiming: list[int],
    articles: list[dict],
    art_parts: list[list[str]],
) -> None:
    """Split a page claimed by multiple articles using all markers found."""
    lines = ftext.splitlines()
    markers = _find_all_markers(lines)

    if not markers:
        # No markers – assign to first claiming article
        art_parts[claiming[0]].append(ftext)
        return

    # Compute split points (paragraph starts before each marker)
    paras = [find_paragraph_before(lines, m) for m in markers]

    # Content before the first split → first claiming article
    if paras[0] > 0:
        art_parts[claiming[0]].append("\n".join(lines[: paras[0]]))

    # Each marker's content → the next claiming article
    for j, sp in enumerate(paras):
        end = paras[j + 1] if j + 1 < len(paras) else len(lines)
        # Map marker j to the appropriate claiming article
        art_idx = claiming[min(j + 1, len(claiming) - 1)]
        art_parts[art_idx].append("\n".join(lines[sp:end]))
