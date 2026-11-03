#!/usr/bin/env python3
"""Compare an original CbDD article with its cleaned version.

Cleaning may reformat, rejoin and correct OCR, but it must not drop or invent
content. This script reports what a reviewer should look at:

  - the {{Artikel …}} template block differs (must be byte-identical)
  - [[File:…]] targets that are missing, added or reordered
  - numbers (years, measurements, page numbers) lost or added
  - words lost or added, ignoring markup, punctuation, hyphenation and case
    (identifier links [[:File:…|A<sub>2</sub>]] count as their label only)
  - the body shrinking or growing by more than --max-ratio

Usage:
    python .claude/skills/clean-cbd-skill/scripts/check_preservation.py \\
        data/formatted/Band01/Lemma.wiki out/Band01/Lemma.wiki

    # every article of a cleaned folder against data/formatted
    python .claude/skills/clean-cbd-skill/scripts/check_preservation.py \\
        --orig-root data/formatted --clean-root out [--band Band01]

Exit code 1 if any article has a blocking problem (template changed, images
lost, length out of bounds); word/number differences are only reported.
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from articles.helpers import parse_article_file  # noqa: E402

_FILE_RE = re.compile(r"\[\[(?:File|Datei):([^|\]]+)")
_NUMBER_RE = re.compile(r"\d+(?:[,.]\d+)?")
_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[^\W\d_]+")
# Joins hyphenated line-end remnants: "Chrono- gramm", "Moos¬ müller"
_HYPHEN_GAP_RE = re.compile(r"(\w)[-¬]\s+(\w)")


# [[:File:X.jpg|A<sub>2</sub>]] identifier links -> their label
_FILE_LINK_RE = re.compile(r"\[\[:(?:File|Datei):[^|\]]*\|([^\]]*)\]\]")


def _unlink(body: str) -> str:
    return _FILE_LINK_RE.sub(r"\1", body)


def _strip_markup(body: str) -> str:
    text = _FILE_RE.sub(" ", _unlink(body))
    text = re.sub(r"\[\[(?:File|Datei):[^\]]*\]\]", " ", text)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"^\{\|.*$", " ", text, flags=re.M)  # table start + attributes
    text = re.sub(r"'{2,}|={2,}|\{\||\|\}|\|-|!!|\|\||^[*!|]", " ", text, flags=re.M)
    return _HYPHEN_GAP_RE.sub(r"\1\2", text)


def _words(body: str) -> Counter:
    return Counter(w.lower() for w in _WORD_RE.findall(_strip_markup(body)))


def _numbers(body: str) -> Counter:
    text = _FILE_RE.sub(" ", _unlink(body))
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return Counter(_NUMBER_RE.findall(text))


def _files(body: str) -> list[str]:
    return [m.strip() for m in _FILE_RE.findall(body)]


def _fmt(counter: Counter, limit: int = 25) -> str:
    items = [f"{k}×{v}" if v > 1 else k for k, v in counter.most_common(limit)]
    more = len(counter) - limit
    return ", ".join(items) + (f" … (+{more})" if more > 0 else "")


def compare(orig_text: str, clean_text: str, max_ratio: float) -> tuple[list[str], bool]:
    """Return (report lines, blocking) for one article pair."""
    o_tpl, _, o_body = parse_article_file(orig_text)
    c_tpl, _, c_body = parse_article_file(clean_text)
    report: list[str] = []
    blocking = False

    if o_tpl.strip() != c_tpl.strip():
        report.append("BLOCK template block differs")
        blocking = True

    o_files, c_files = _files(o_body), _files(c_body)
    if Counter(o_files) != Counter(c_files):
        lost = Counter(o_files) - Counter(c_files)
        added = Counter(c_files) - Counter(o_files)
        if lost:
            report.append(f"BLOCK images lost: {_fmt(lost)}")
        if added:
            report.append(f"BLOCK images added: {_fmt(added)}")
        blocking = True
    elif o_files != c_files:
        report.append("WARN  images reordered")

    o_len, c_len = len(_strip_markup(o_body)), len(_strip_markup(c_body))
    if o_len and not (1 / max_ratio <= c_len / o_len <= max_ratio):
        report.append(f"BLOCK text length {o_len} → {c_len} chars")
        blocking = True

    o_nums, c_nums = _numbers(o_body), _numbers(c_body)
    if o_nums - c_nums:
        report.append(f"CHECK numbers lost: {_fmt(o_nums - c_nums)}")
    if c_nums - o_nums:
        report.append(f"CHECK numbers added: {_fmt(c_nums - o_nums)}")

    o_words, c_words = _words(o_body), _words(c_body)
    if o_words - c_words:
        report.append(f"CHECK words lost: {_fmt(o_words - c_words)}")
    if c_words - o_words:
        report.append(f"CHECK words added: {_fmt(c_words - o_words)}")

    return report, blocking


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("orig", nargs="?", type=Path, help="Original article")
    parser.add_argument("clean", nargs="?", type=Path, help="Cleaned article")
    parser.add_argument("--orig-root", type=Path, help="Root of original articles")
    parser.add_argument("--clean-root", type=Path, help="Root of cleaned articles")
    parser.add_argument("--band", help="Restrict root comparison to one band")
    parser.add_argument("--max-ratio", type=float, default=1.25,
                        help="Allowed length change factor (default 1.25)")
    args = parser.parse_args()

    if args.orig and args.clean:
        pairs = [(args.orig, args.clean)]
    elif args.orig_root and args.clean_root:
        pattern = f"{args.band}/*.wiki" if args.band else "*/*.wiki"
        pairs = [
            (args.orig_root / p.relative_to(args.clean_root), p)
            for p in sorted(args.clean_root.glob(pattern))
        ]
    else:
        parser.error("give ORIG CLEAN or --orig-root/--clean-root")

    any_blocking = False
    for orig, clean in pairs:
        if not orig.exists():
            print(f"[MISSING ORIGINAL] {orig}")
            continue
        report, blocking = compare(
            orig.read_text(encoding="utf-8"), clean.read_text(encoding="utf-8"),
            args.max_ratio,
        )
        any_blocking |= blocking
        status = "FAIL" if blocking else ("REVIEW" if report else "OK")
        print(f"[{status}] {clean}")
        for line in report:
            print(f"    {line}")

    sys.exit(1 if any_blocking else 0)


if __name__ == "__main__":
    main()
