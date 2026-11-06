#!/usr/bin/env python3
"""Apply the deterministic cleanups to a hand-cleaned article, in place.

Runs `postprocess()` from src/articles/postprocess.py over the body (spaces
before punctuation, blank lines, one blank line around == headings ==), puts
one `* ` bullet on every line of the bibliography, links field identifiers to
their images (link_identifiers.py), wraps the first occurrence of each
glossary abbreviation in {{Abk|…}} (tag_abk.py), leaves the
{{Artikel …}} template untouched, and ensures one trailing newline.
Run it again after fixing captions — it is idempotent.

Usage:
    python .claude/skills/clean-cbd-skill/scripts/finalize.py \\
        "data/cleaned/Band01/Lemma.wiki" [more.wiki …]
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "src"))

from articles.helpers import parse_article_file  # noqa: E402
from articles.postprocess import postprocess  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_identifiers import link_body  # noqa: E402
from tag_abk import tag_body  # noqa: E402

# a line that is only a label: '''Zum Bauwerk:''' / Zur Ausstattung:
_LABEL_LINE_RE = re.compile(r"^(?:'{3}[^']+'{3}|[A-ZÄÖÜ][\w ]+:)\s*$")


def bullet_bibliography(body: str) -> str:
    """One `* ` bullet per line under == Quellen … / Literatur == (rule 3.5).
    Label lines, sub-headings, tables and existing bullets stay as they are.
    Splitting run-together entries is judgment — that stays with the model."""
    out, in_lit = [], False
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith("=="):
            in_lit = s.strip("= ").startswith(("Quellen", "Literatur"))
        elif (in_lit and s and not s.startswith(("*", "{", "|", "[[", "<!--"))
              and not _LABEL_LINE_RE.match(s)):
            line = "* " + s
        out.append(line)
    return "\n".join(out)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        path = Path(arg)
        text = path.read_text(encoding="utf-8")
        template_block, _fields, body = parse_article_file(text)
        new = template_block.rstrip("\n") + "\n\n" + tag_body(link_body(bullet_bibliography(postprocess(body)))).strip("\n") + "\n"
        if new != text:
            path.write_text(new, encoding="utf-8")
            print(f"  [FINALIZED] {path}")
        else:
            print(f"  [UNCHANGED] {path}")


if __name__ == "__main__":
    main()
