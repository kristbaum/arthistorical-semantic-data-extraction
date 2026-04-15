"""Format articles in data/formatted/BandXX/ directories.

For every article:
  1. Remove all <!-- ... --> comments.
  2. Remove {{End}} template lines.

Usage:
    python -m src.articles.format_articles [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from .helpers import OUTPUT_DIR

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_COMMENT_LINE_RE = re.compile(r"^\s*<!--.*-->\s*$")
_END_LINE_RE = re.compile(r"^\s*\{\{End\}\}\s*$")

# Normalise all <br> variants to a common token first
_BR_NORM_RE = re.compile(r"<br\s*/?", re.IGNORECASE)


def _fix_br(text: str) -> str:
    """Replace <br> tags context-sensitively.

    Priority (applied in order after normalisation):
      1. ``word-<br>word``  → ``wordword``  (hyphenated line-break: drop hyphen)
      2. ``.<br>``          → ``.\n``        (sentence end: real line break)
      3. ``<br>``           → single space  (inline line-break)
    """
    # Normalise variants (<br />, <BR>, <br/> …) → <br>
    text = _BR_NORM_RE.sub("<br", text)  # strips trailing attrs/slash
    text = re.sub(r"<br[^>]*>", "<br>", text)  # close the tag cleanly

    # 1. Hyphenated word split across lines
    text = re.sub(r"-\s*<br>\s*", "", text)
    # 2. Sentence-ending punctuation before <br> → real line break (consume all consecutive)
    text = re.sub(r"([.!?])\s*(?:<br>\s*)+", r"\1\n", text)
    # 3. Remaining <br> → space
    text = re.sub(r"\s*<br>\s*", " ", text)
    return text


# ---------------------------------------------------------------------------
# Per-article transform
# ---------------------------------------------------------------------------


def format_article(text: str) -> str:
    """Remove all HTML comment lines, {{End}} lines, and fix <br> tags."""
    text = _fix_br(text)
    lines = text.splitlines()

    cleaned = [
        line
        for line in lines
        if not _COMMENT_LINE_RE.match(line) and not _END_LINE_RE.match(line)
    ]

    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    return "\n".join(cleaned) + "\n"


# ---------------------------------------------------------------------------
# Per-band processor
# ---------------------------------------------------------------------------


def format_band(
    band_prefix: str,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> int:
    """Format all articles in data/formatted/{band_prefix}/. Returns change count."""
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        if verbose:
            print(f"  SKIP {band_prefix}: directory not found")
        return 0

    changes = 0
    for path in sorted(band_dir.glob("*.wiki")):
        original = path.read_text(encoding="utf-8")
        new_text = format_article(original)

        if new_text != original:
            changes += 1
            if apply:
                path.write_text(new_text, encoding="utf-8")
                if verbose:
                    print(f"  [WROTE] {band_prefix}/{path.name}")
            else:
                print(f"  [WOULD CHANGE] {band_prefix}/{path.name}")

    if verbose and changes == 0:
        print(f"  OK {band_prefix}: no changes")
    return changes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--band", metavar="BAND", help="Process only this band, e.g. Band01"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes to disk (default: dry-run)"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    total = 0
    for bp in band_prefixes:
        n = format_band(bp, apply=args.apply, verbose=args.verbose)
        total += n

    mode = "Applied to" if args.apply else "Would change"
    print(f"\n{mode} {total} article(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
