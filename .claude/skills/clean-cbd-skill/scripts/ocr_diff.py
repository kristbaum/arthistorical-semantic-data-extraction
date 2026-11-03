#!/usr/bin/env python3
"""Show where the two OCRs (Surya and Transkribus) disagree on an article's pages.

Both page texts are normalised (comments, markup, [[File:…]] lines and
`<sub>` tags removed, line-end hyphens rejoined, whitespace collapsed),
tokenised into words and punctuation and aligned with difflib. Output per page:

  WORD  small disagreements (≤ 6 tokens a side) with context — these are the
        candidate OCR errors: »1.30« vs »1,30«, »A4« vs »Al«, a lost »†«.
  BLOCK larger unaligned stretches — usually reading order, a caption read
        into the text, a column read in reverse, or text one OCR missed. A
        BLOCK is a layout question.

Only disagreements whose context occurs in the formatted article are shown
(pages are shared with neighbouring articles); --all shows everything.
Disagreements that are only case or only a missing space are skipped.

The scan needs to be checked only for disagreements that matter and that the
context cannot settle (see SKILL.md §2.1).

Usage:
    uv run python .claude/skills/clean-cbd-skill/scripts/ocr_diff.py \\
        "data/formatted/Band01/Lemma.wiki" [--all]
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_sources import REPO_ROOT, find_pages, source_paths  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from articles.helpers import parse_article_file  # noqa: E402

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
SMALL = 6
CONTEXT = 4


def normalise(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    # keep caption text of [[File:…|thumb|caption]], drop the rest of the tag
    text = re.sub(r"\[\[(?:File|Datei):[^\]|]*(?:\|thumb)?(?:\|([^\]]*))?\]\]",
                  lambda m: f" {m.group(1) or ''} ", text)
    text = re.sub(r"\[\[:(?:File|Datei):[^|\]]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"</?(?:sub|sup|b|i|br)\s*/?>", "", text)
    text = re.sub(r"'{2,}|^=+|=+$|^[*#:]+|\{\||\|\}|\|-|!!|\|\|", " ", text, flags=re.M)
    text = re.sub(r"(\w)[-¬]\s*\n\s*(\w)", r"\1\2", text)   # line-end hyphens
    text = text.replace("¬", "")
    return re.sub(r"\s+", " ", text)


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalise(text))


# Transkribus reads subscript digits as letters: Ai/Al/AI = A1, Az = A2, As = A3 or A5
_TRKB_SUB = {"i": "1", "l": "1", "I": "1", "z": "2", "Z": "2", "s": "35", "S": "35"}
_DASHES = str.maketrans({"–": "-", "—": "-", "×": "x", "X": "x", "¬": ""})


def _trivial(a: list[str], b: list[str]) -> bool:
    """Differences that never need the scan: case, spacing, dash/× style,
    rejoined hyphens, and Transkribus' letter-for-subscript habit when it
    agrees with Surya's digit."""
    ja, jb = "".join(a).translate(_DASHES), "".join(b).translate(_DASHES)
    if ja.lower() == jb.lower() or ja.replace("-", "") == jb.replace("-", ""):
        return True
    if len(a) == len(b):
        return all(_same_ident(x, y) or x.translate(_DASHES) == y.translate(_DASHES)
                   for x, y in zip(a, b))
    return False


def _same_ident(s_tok: str, t_tok: str) -> bool:
    m = re.fullmatch(r"([A-Z])(\d+)", s_tok)
    if not m or len(t_tok) < 2 or t_tok[0] != m[1]:
        return False
    digits = t_tok[1:]
    return len(digits) == len(m[2]) and all(
        d == c or c in _TRKB_SUB.get(d, "") for d, c in zip(digits, m[2]))


def _coverage(part: list[str], grams: set[tuple[str, ...]]) -> float:
    """Share of part's 3-grams found anywhere in the other OCR's page."""
    own = [tuple(part[k:k + 3]) for k in range(len(part) - 2)]
    return sum(g in grams for g in own) / len(own) if own else 0.0


def diff_page(surya: list[str], trkb: list[str], article: set[tuple[str, ...]],
              show_all: bool) -> list[str]:
    out = []
    s_grams = {tuple(surya[k:k + 3]) for k in range(len(surya) - 2)}
    t_grams = {tuple(trkb[k:k + 3]) for k in range(len(trkb) - 2)}
    moved = 0
    sm = difflib.SequenceMatcher(None, surya, trkb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        a, b = surya[i1:i2], trkb[j1:j2]
        if _trivial(a, b):
            continue
        left = surya[max(0, i1 - CONTEXT):i1]
        right = surya[i2:i2 + CONTEXT]
        ctx = left[-3:] + right[:3]
        grams = {tuple(ctx[k:k + 3]) for k in range(max(1, len(ctx) - 2))}
        if not show_all and not (grams & article):
            continue
        if len(a) <= SMALL and len(b) <= SMALL:
            out.append(f"  WORD  …{' '.join(left)} [{' '.join(a) or '∅'}] {' '.join(right)}…"
                       f"\n        trkb: [{' '.join(b) or '∅'}]")
        elif _coverage(a, t_grams) >= 0.6 and _coverage(b, s_grams) >= 0.6:
            moved += 1  # same text, other reading order — not a content conflict
        else:
            sa = " ".join(a[:12]) + (" …" if len(a) > 12 else "")
            sb = " ".join(b[:12]) + (" …" if len(b) > 12 else "")
            out.append(f"  BLOCK after »{' '.join(left)}«: surya {len(a)} tok / trkb {len(b)} tok"
                       f"\n        surya: {sa or '∅'}\n        trkb:  {sb or '∅'}")
    if moved:
        out.append(f"  ORDER {moved} stretch(es) read in a different order by Transkribus "
                   f"(text present in both) — ignore unless the article's order is in doubt")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("article", type=Path)
    parser.add_argument("--all", action="store_true", help="include neighbour text")
    args = parser.parse_args()

    _tpl, fields, body = parse_article_file(args.article.read_text(encoding="utf-8"))
    art = tokens(body)
    article = {tuple(art[k:k + 3]) for k in range(len(art) - 2)}

    band = args.article.parent.name
    chunk = int(fields["Chunk"])
    von = int(fields["Originalseitenvon"])
    bis = int(fields.get("Originalseitenbis") or von)

    total_w = total_b = 0
    for cdir, stem, printed in find_pages(band, chunk, von, bis):
        src = source_paths(cdir, stem)
        if not (src["surya"].exists() and src["trkb"].exists()):
            print(f"\n{cdir.name}/{stem}: only one OCR source — nothing to compare")
            continue
        lines = diff_page(tokens(src["surya"].read_text(encoding="utf-8")),
                          tokens(src["trkb"].read_text(encoding="utf-8")),
                          article, args.all)
        w = sum(l.startswith("  WORD") for l in lines)
        b = sum(l.startswith("  BLOCK") for l in lines)
        total_w, total_b = total_w + w, total_b + b
        print(f"\n{cdir.name}/{stem}  printed p{'/'.join(map(str, printed))}  "
              f"{w} word / {b} block disagreements")
        print("\n".join(lines))
    print(f"\nTOTAL {total_w} word / {total_b} block disagreements")


if __name__ == "__main__":
    main()
