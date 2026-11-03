#!/usr/bin/env python3
"""List the page-level OCR sources (and scans) behind a CbDD article.

Each PDF page of a chunk is a two-page spread: the comments
`<!-- citation-page-top: Band01 p18 -->` / `<!-- citation-page-bottom: … p19 -->`
in `wiki/p{NNN}.wiki` name the two printed pages it holds. The article's
printed range (`|Originalseitenvon=` … `|Originalseitenbis=`) is matched
against those comments, so the pages are found even though `|Chunkseite=` is
usually one higher than the first PDF page, and even when the article runs
into the next chunk.

For every page it prints the paths of:
  surya   data/extracted/{Band}_chunk{NNN}/wiki/p{NNN}.wiki
  trkb    data/extracted/{Band}_chunk{NNN}/add_txt/{NNNN}_p{NNN}.txt
  pass1   data/extracted/{Band}_chunk{NNN}/pass1/p{NNN}.wiki
  scan    data/extracted/{Band}_chunk{NNN}/pages/{Band}_chunk{NNN}_p{NNN}.jpg (if present)

With --grep, it also prints the lines of every source page that match a
regex (case-insensitive), to compare the two OCR readings of a doubtful word.

Usage:
    python .claude/skills/clean-cbd-skill/scripts/find_sources.py \\
        "data/formatted/Band01/Lemma.wiki" [--grep "Fresken von \\d+"]
"""

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from articles.helpers import parse_article_file  # noqa: E402

EXTRACTED = REPO_ROOT / "data" / "extracted"
# Page scans: data/extracted/{chunk}/pages/{chunk}_p{NNN}.jpg; fallback CBDD_SCAN_DIR/{chunk}/p{NNN}.<ext>
SCANS = Path(os.environ.get("CBDD_SCAN_DIR", REPO_ROOT / "data" / "scans"))
SCAN_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")

_CITATION_RE = re.compile(r"citation-page-(?:top|bottom):\s*\S+\s+p(\d+)")


def _printed_pages(wiki_page: Path) -> list[int]:
    return [int(n) for n in _CITATION_RE.findall(wiki_page.read_text(encoding="utf-8"))]


def _chunk_dirs(band: str, first_chunk: int) -> list[Path]:
    """The article's chunk and the following one (articles may cross chunks)."""
    return [
        d
        for n in (first_chunk, first_chunk + 1)
        if (d := EXTRACTED / f"{band}_chunk{n:03d}").is_dir()
    ]


def find_pages(band: str, chunk: int, von: int, bis: int) -> list[tuple[Path, str, list[int]]]:
    """(chunk_dir, 'pNNN', printed pages) for every PDF page overlapping von..bis."""
    hits = []
    for cdir in _chunk_dirs(band, chunk):
        for page in sorted((cdir / "wiki").glob("p*.wiki")):
            printed = _printed_pages(page)
            if printed and min(printed) <= bis and max(printed) >= von:
                hits.append((cdir, page.stem, printed))
    return hits


def find_scan(cdir: Path, stem: str) -> Path | None:
    """Rendered page: data/extracted/{chunk}/pages/{chunk}_{pNNN}.jpg, or CBDD_SCAN_DIR."""
    candidates = [cdir / "pages" / f"{cdir.name}_{stem}{ext}" for ext in SCAN_EXTS]
    candidates += [SCANS / cdir.name / f"{stem}{ext}" for ext in SCAN_EXTS]
    return next((p for p in candidates if p.exists()), None)


def source_paths(cdir: Path, stem: str) -> dict[str, Path | None]:
    num = int(stem[1:])
    scan = find_scan(cdir, stem)
    return {
        "surya": cdir / "wiki" / f"{stem}.wiki",
        "trkb": cdir / "add_txt" / f"{num:04d}_{stem}.txt",
        "pass1": cdir / "pass1" / f"{stem}.wiki",
        "scan": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("article", type=Path, help="data/formatted/{Band}/{Lemma}.wiki")
    parser.add_argument("--grep", help="Regex to look up in every source page")
    args = parser.parse_args()

    _tpl, fields, _body = parse_article_file(args.article.read_text(encoding="utf-8"))
    band = args.article.parent.name
    try:
        chunk = int(fields["Chunk"])
        von = int(fields["Originalseitenvon"])
        bis = int(fields.get("Originalseitenbis") or von)
    except (KeyError, ValueError):
        sys.exit(f"{args.article}: template lacks Chunk/Originalseitenvon")

    pages = find_pages(band, chunk, von, bis)
    print(f"{band} chunk{chunk:03d}  printed S. {von}–{bis}  "
          f"(Chunkseite={fields.get('Chunkseite')})")
    if not pages:
        print("  no page with matching citation comments found")
    pattern = re.compile(args.grep, re.IGNORECASE) if args.grep else None

    for cdir, stem, printed in pages:
        print(f"\n{cdir.name}/{stem}  printed p{'/'.join(map(str, printed))}")
        for name, path in source_paths(cdir, stem).items():
            shown = path.relative_to(REPO_ROOT) if path and path.exists() else "—"
            print(f"  {name:6} {shown}")
            if pattern and name != "scan" and path and path.exists():
                for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    for m in pattern.finditer(line):
                        start, end = max(m.start() - 60, 0), m.end() + 60
                        print(f"         {i:4}: …{line[start:end].strip()}…")


if __name__ == "__main__":
    main()
