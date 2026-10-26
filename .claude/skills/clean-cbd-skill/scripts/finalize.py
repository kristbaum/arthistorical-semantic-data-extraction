#!/usr/bin/env python3
"""Apply the deterministic cleanups to a hand-cleaned article, in place.

Runs `postprocess()` from src/articles/postprocess.py over the body (spaces
before punctuation, blank lines, one blank line around == headings ==),
leaves the {{Artikel …}} template untouched, and ensures one trailing newline.

Usage:
    python .claude/skills/clean-cbd-skill/scripts/finalize.py \\
        "data/cleaned/Band01/Lemma.wiki" [more.wiki …]
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from articles.helpers import parse_article_file  # noqa: E402
from articles.postprocess import postprocess  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        path = Path(arg)
        text = path.read_text(encoding="utf-8")
        template_block, _fields, body = parse_article_file(text)
        new = template_block.rstrip("\n") + "\n\n" + postprocess(body).strip("\n") + "\n"
        if new != text:
            path.write_text(new, encoding="utf-8")
            print(f"  [FINALIZED] {path}")
        else:
            print(f"  [UNCHANGED] {path}")


if __name__ == "__main__":
    main()
