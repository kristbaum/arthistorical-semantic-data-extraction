"""
Process all wiki pages in data/extracted/*/wiki/*.wiki

Replaces the existing positional comment:
  <!-- Band14_chunk006 Page 2 -->
with:
  <!-- dropbox: https://www.dropbox.com/preview/CbDD_Dienstordner/literatur/altes%20corpus/chunked/chunked/Band14_chunk006.pdf#page=2 -->
  <!-- citation-page-top: Band14 p252 -->

And appends at the end of the file:
  <!-- citation-page-bottom: Band14 p253 -->

Formula: page_top = (chunk_offset + chunk_num - 1) * 50 + page_in_chunk * 2 - 2
Band12-1 and Band12-2 share a continuous page count (Band12-2 starts at page 300).
All other volumes are independent.
"""

import re
from pathlib import Path

DROPBOX_BASE = (
    "https://www.dropbox.com/preview/CbDD_Dienstordner/literatur/"
    "altes%20corpus/chunked/chunked"
)
PAGES_PER_CHUNK = 50  # 25 double pages

# Sub-bands that get a shared base label in citations
BASE_LABEL: dict[str, str] = {
    "Band12-1": "Band12",
    "Band12-2": "Band12",
}

# Extra chunk offset for sub-bands that continue a previous part's page count
CHUNK_OFFSET: dict[str, int] = {
    "Band12-2": 6,  # Band12-1 has 7 chunks -> 6 full-chunk offset (300 pages)
}

HEADER_RE = re.compile(r"<!--\s*([\w-]+_chunk\d+)\s+Page\s+(\d+)\s*-->")
CHUNK_DIR_RE = re.compile(r"^([\w-]+)_chunk(\d+)$")

# Strip OCR-artefact "Original Page" comments from body
_ORIGINAL_PAGE_RE = re.compile(r"\n?<!-- [\w-]+_chunk\d+ Original Page \d+ -->\n?")

# Current processed format (URL with #page=)
_PROCESSED_RE = re.compile(
    r"^<!-- dropbox: [^\s]*/(?P<chunk>[\w-]+_chunk\d+)\.pdf#page=(?P<page>\d+) -->\n"
    r"<!-- citation-page-top:[^\n]*\n"
)
# Old format (chunk-page comment, no #page=) – for migration
_OLD_PROCESSED_RE = re.compile(
    r"^<!-- dropbox: [^\s]*/(?P<chunk>[\w-]+_chunk\d+)\.pdf -->\n"
    r"<!-- chunk-page: (?P<page>\d+) -->\n"
    r"<!-- citation-page-top:[^\n]*\n"
)
_FOOTER_RE = re.compile(r"\n<!-- citation-page-bottom:[^\n]*\n?$")


def process_wiki_file(wiki_file: Path) -> None:
    text = wiki_file.read_text(encoding="utf-8")

    chunk_dir_name: str
    page_in_chunk: int
    body: str

    m_proc = _PROCESSED_RE.match(text)
    m_old = _OLD_PROCESSED_RE.match(text) if not m_proc else None

    if m_proc:
        chunk_dir_name = m_proc.group("chunk")
        page_in_chunk = int(m_proc.group("page"))
        body = _FOOTER_RE.sub("", text[m_proc.end() :])
    elif m_old:
        chunk_dir_name = m_old.group("chunk")
        page_in_chunk = int(m_old.group("page"))
        body = _FOOTER_RE.sub("", text[m_old.end() :])
    else:
        lines = text.splitlines(keepends=True)
        if not lines:
            return
        m_orig = HEADER_RE.match(lines[0].strip())
        if not m_orig:
            return
        chunk_dir_name = m_orig.group(1)
        page_in_chunk = int(m_orig.group(2))
        body = "".join(lines[1:])

    body = _ORIGINAL_PAGE_RE.sub("", body)

    cm = CHUNK_DIR_RE.match(chunk_dir_name)
    if not cm:
        return
    sub_band = cm.group(1)
    chunk_num = int(cm.group(2))

    base = BASE_LABEL.get(sub_band, sub_band)
    offset = CHUNK_OFFSET.get(sub_band, 0)

    abs_page_top = (offset + chunk_num - 1) * PAGES_PER_CHUNK + page_in_chunk * 2 - 2
    abs_page_bottom = abs_page_top + 1

    dropbox_url = f"{DROPBOX_BASE}/{chunk_dir_name}.pdf#page={page_in_chunk}"
    new_header = (
        f"<!-- dropbox: {dropbox_url} -->\n"
        f"<!-- citation-page-top: {base} p{abs_page_top} -->\n"
    )
    footer = f"\n<!-- citation-page-bottom: {base} p{abs_page_bottom} -->\n"

    new_text = new_header + body.rstrip("\n") + footer

    if new_text != text:
        wiki_file.write_text(new_text, encoding="utf-8")
        print(f"  processed: {wiki_file}")


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    extracted_dir = base_dir / "data" / "extracted"

    processed = skipped = 0
    for chunk_dir in sorted(extracted_dir.iterdir()):
        if not chunk_dir.is_dir():
            continue
        wiki_dir = chunk_dir / "wiki"
        if not wiki_dir.exists():
            continue
        for wiki_file in sorted(wiki_dir.glob("*.wiki")):
            before = wiki_file.stat().st_mtime
            process_wiki_file(wiki_file)
            if wiki_file.stat().st_mtime != before:
                processed += 1
            else:
                skipped += 1

    print(
        f"\nDone: {processed} updated, {skipped} skipped (already processed or no header)."
    )


if __name__ == "__main__":
    main()
