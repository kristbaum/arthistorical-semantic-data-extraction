"""Split a {BandXX}_split.wiki file into individual article files.

Reads  data/splitting/{BandXX}/{BandXX}_split.wiki  (produced by
marker_inserter.py), which contains {{Artikel …}} / {{End}} blocks.
Each block is written to  data/formatted/{BandXX}/{Lemma}.wiki
where Lemma comes from the |Lemma= field in the {{Artikel}} template.

Text before the first {{Artikel}} → before_articles.wiki
Text after  the last  {{End}}     → after_articles.wiki

Usage (standalone):
    python -m src.articles.splitter [--dry-run] [--band Band01] [--verbose]
"""

import argparse
import re

from .helpers import OUTPUT_DIR, REPO_ROOT, sanitize_filename

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"

# Article size thresholds (characters).
_MIN_ARTICLE_SIZE = 1_000
_MAX_ARTICLE_SIZE = 50_000

_ARTIKEL_RE = re.compile(r"^\{\{Artikel\b")
_END_RE = re.compile(r"^\{\{End\}\}")
_LEMMA_RE = re.compile(r"^\|Lemma=(.+)$")


def _extract_lemma(block: str) -> str | None:
    """Extract the |Lemma= value from an {{Artikel …}} template block."""
    for line in block.splitlines():
        m = _LEMMA_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


def _clean(text: str) -> str:
    ls = text.split("\n")
    while ls and ls[0].strip() == "":
        ls.pop(0)
    while ls and ls[-1].strip() == "":
        ls.pop()
    return "\n".join(ls)


def split_band(
    band_prefix: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> tuple[int, int, list[str]]:
    """Split a _split.wiki file into article files.

    Returns (written_count, missing_lemmas).
    """
    split_path = SPLITTING_DIR / band_prefix / f"{band_prefix}_split.wiki"

    if not split_path.is_file():
        if verbose:
            print(f"  SKIP {band_prefix} — no {band_prefix}_split.wiki found")
        return 0, 0, []

    full_text = split_path.read_text(encoding="utf-8")
    lines = full_text.splitlines()

    out_dir = OUTPUT_DIR / band_prefix
    written = 0
    missing_lemmas: list[str] = []

    # Locate all {{Artikel}} start lines and {{End}} lines.
    artikel_lines: list[int] = []
    end_lines: list[int] = []
    for i, line in enumerate(lines):
        if _ARTIKEL_RE.match(line.strip()):
            artikel_lines.append(i)
        elif _END_RE.match(line.strip()):
            end_lines.append(i)

    if not artikel_lines:
        if verbose:
            print(f"  SKIP {band_prefix} — no {{{{Artikel}}}} markers found")
        return 0, 0, []

    # ── Articles ─────────────────────────────────────────────────────────────
    for idx, art_start in enumerate(artikel_lines):
        # Find the matching {{End}}: first end_line that is > art_start.
        art_end: int | None = next((e for e in end_lines if e > art_start), None)

        if art_end is None:
            # No {{End}} found — take everything up to the next {{Artikel}} or EOF.
            art_end = (
                artikel_lines[idx + 1] if idx + 1 < len(artikel_lines) else len(lines)
            )
            article_text = _clean("\n".join(lines[art_start:art_end]))
        else:
            article_text = _clean("\n".join(lines[art_start : art_end + 1]))

        lemma = _extract_lemma(article_text)
        if not lemma:
            print(
                f"  ERROR: could not extract |Lemma= from article at line {art_start + 1}"
            )
            missing_lemmas.append(f"<unknown at line {art_start + 1}>")
            continue

        lemma_filename = sanitize_filename(lemma) + ".wiki"
        out_path = out_dir / lemma_filename

        size = len(article_text)
        if dry_run:
            print(f"  WOULD WRITE: {out_path.relative_to(REPO_ROOT)}  ({size} chars)")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(article_text + "\n", encoding="utf-8")
            if verbose:
                print(f"  WROTE: {out_path.relative_to(REPO_ROOT)}  ({size} chars)")
        written += 1

        if size < _MIN_ARTICLE_SIZE or size > _MAX_ARTICLE_SIZE:
            tag = (
                f"SMALL ({size} chars)"
                if size < _MIN_ARTICLE_SIZE
                else f"LARGE ({size} chars)"
            )
            print(f"  WARN {tag}: {lemma!r}")

    return written, missing_lemmas


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print plan without writing."
    )
    parser.add_argument(
        "--band",
        type=str,
        default=None,
        help="Process only this Band prefix (e.g. Band01).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed progress."
    )
    args = parser.parse_args(argv)

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(
            d.name
            for d in SPLITTING_DIR.iterdir()
            if d.is_dir() and (d / f"{d.name}_split.wiki").is_file()
        )

    total_written = 0
    all_missing: list[str] = []

    for band_prefix in band_prefixes:
        print(f"Splitting {band_prefix} …")
        w, miss = split_band(
            band_prefix, dry_run=args.dry_run, verbose=args.verbose
        )
        total_written += w
        all_missing.extend(miss)

    print(f"\nWrote {total_written} articles.")
    if all_missing:
        print(f"Missing lemmas ({len(all_missing)}): {all_missing}")


if __name__ == "__main__":
    main()
