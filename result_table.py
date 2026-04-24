"""Show aggregate statistics for all articles in data/formatted/.

Differentiates between Meta articles (|Meta= is non-empty in {{Artikel}})
and non-Meta (content) articles.

Metrics per article:
  - characters
  - words
  - [[File:]] embeds
  - estimated LLM tokens  (chars / 4, a common rough estimate)

Only averages and totals are printed, not per-article rows.

Usage:
    python result_table.py [--band Band01]
"""

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = REPO_ROOT / "data" / "formatted"

_FIELD_RE = re.compile(r"^\s*\|Meta=(.*)$", re.MULTILINE)
_FILE_RE = re.compile(r"\[\[File:", re.IGNORECASE)


def extract_meta(text: str) -> str:
    """Return the value of |Meta= from the {{Artikel}} template, or ''."""
    m = _FIELD_RE.search(text)
    return m.group(1).strip() if m else ""


@dataclass
class Stats:
    count: int = 0
    chars: int = 0
    words: int = 0
    files: int = 0

    def add(self, text: str) -> None:
        self.count += 1
        self.chars += len(text)
        self.words += len(text.split())
        self.files += len(_FILE_RE.findall(text))

    @property
    def tokens(self) -> int:
        """Rough estimate: 1 token ≈ 4 characters."""
        return self.chars // 4

    def averages(self) -> dict:
        if self.count == 0:
            return {"chars": 0, "words": 0, "files": 0.0, "tokens": 0}
        return {
            "chars": self.chars / self.count,
            "words": self.words / self.count,
            "files": self.files / self.count,
            "tokens": self.tokens / self.count,
        }


def collect(band_prefix: str | None = None) -> tuple[Stats, Stats]:
    meta_stats = Stats()
    content_stats = Stats()

    if band_prefix:
        dirs = [OUTPUT_DIR / band_prefix]
    else:
        dirs = sorted(OUTPUT_DIR.iterdir()) if OUTPUT_DIR.is_dir() else []

    for band_dir in dirs:
        if not band_dir.is_dir():
            continue
        for path in sorted(band_dir.glob("*.wiki")):
            text = path.read_text(encoding="utf-8")
            meta_value = extract_meta(text)
            if meta_value:
                meta_stats.add(text)
            else:
                content_stats.add(text)

    return meta_stats, content_stats


def print_table(meta: Stats, content: Stats) -> None:
    total = Stats()
    total.count = meta.count + content.count
    total.chars = meta.chars + content.chars
    total.words = meta.words + content.words
    total.files = meta.files + content.files

    col_w = 14

    def row(label: str, *values) -> str:
        return f"  {label:<30}" + "".join(f"{v:>{col_w}}" for v in values)

    header = row("", "Non-Meta", "Meta", "Total")
    sep = "  " + "-" * (30 + col_w * 3)

    print()
    print(header)
    print(sep)
    print(row("Articles (count)", content.count, meta.count, total.count))
    print()

    # Totals
    print(row("Total characters", content.chars, meta.chars, total.chars))
    print(row("Total words", content.words, meta.words, total.words))
    print(row("Total [[File:]]s", content.files, meta.files, total.files))
    print(row("Total est. tokens", content.tokens, meta.tokens, total.tokens))
    print()

    # Averages
    ca = content.averages()
    ma = meta.averages()
    ta = total.averages()
    print(row("Avg characters", f"{ca['chars']:.0f}", f"{ma['chars']:.0f}", f"{ta['chars']:.0f}"))
    print(row("Avg words", f"{ca['words']:.0f}", f"{ma['words']:.0f}", f"{ta['words']:.0f}"))
    print(row("Avg [[File:]]s", f"{ca['files']:.2f}", f"{ma['files']:.2f}", f"{ta['files']:.2f}"))
    print(row("Avg est. tokens", f"{ca['tokens']:.0f}", f"{ma['tokens']:.0f}", f"{ta['tokens']:.0f}"))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--band", metavar="BAND", help="Limit to one band, e.g. Band01")
    args = parser.parse_args()

    meta, content = collect(args.band)
    print_table(meta, content)


if __name__ == "__main__":
    main()
