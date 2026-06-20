"""Deterministic MediaWiki formatting rules applied in Python (not by the LLM).

These rules need no language judgment, so run_pass2 applies them in code after
the LLM step instead of asking the model to do them:
  - Remove spaces before punctuation (, . ; : ! ?)
  - Collapse runs of blank lines to a single one
  - Ensure exactly one blank line before and after each == heading ==
  - Strip leading/trailing blank lines

Can also be run standalone to reformat every article in the formatted folder
(the article template is left untouched; only the body is normalised):

    # dry-run over all bands
    python src/acticles/postprocess.py

    # write changes for one band
    python src/acticles/postprocess.py --band Band01 --apply
"""

import re
from pathlib import Path

_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([,.;:!?])")


def is_heading(line: str) -> bool:
    """True for a level-2 MediaWiki heading ("== Befund =="), not "=== Sub ==="."""
    s = line.strip()
    return s.startswith("== ") and s.endswith(" ==") and not s.startswith("=== ")


def postprocess(text: str) -> str:
    """Apply the deterministic formatting rules in Python."""
    # Remove spaces before punctuation.
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)

    lines = [ln.rstrip() for ln in text.splitlines()]

    out: list[str] = []
    for ln in lines:
        if is_heading(ln):
            # Exactly one blank line before the heading (unless at start).
            if out and out[-1] != "":
                out.append("")
            out.append(ln)
            out.append("")  # one blank line after; collapsed below if doubled
        else:
            # Collapse consecutive blank lines.
            if ln == "" and out and out[-1] == "":
                continue
            out.append(ln)

    # Strip leading/trailing blank lines.
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()

    return "\n".join(out)


def _format_article(text: str, parse_article_file) -> str:
    """Reformat one article file: normalise the body, leave the template as-is.

    Files without an {{Artikel}} template (e.g. before_articles.wiki) are
    normalised whole.
    """
    template_block, _fields, body = parse_article_file(text)
    if template_block:
        return template_block.rstrip("\n") + "\n\n" + postprocess(body) + "\n"
    return postprocess(text) + "\n"


def main() -> None:
    """Standalone entry point: reformat every article in data/formatted."""
    import argparse
    import sys

    # Make src/ importable when run as `python src/format/postprocess.py`.
    src_dir = Path(__file__).resolve().parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from articles.helpers import iter_formatted_articles, parse_article_file

    parser = argparse.ArgumentParser(
        description="Apply deterministic MediaWiki post-processing to formatted articles."
    )
    parser.add_argument("--band", metavar="BAND", help="Only this band, e.g. Band01")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk (default: dry-run, only report).",
    )
    args = parser.parse_args()

    changed = total = 0
    for path in iter_formatted_articles(args.band):
        total += 1
        text = path.read_text(encoding="utf-8")
        new_text = _format_article(text, parse_article_file)
        if new_text == text:
            continue
        changed += 1
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
            print(f"  [WROTE] {path.name}", flush=True)
        else:
            print(f"  [WOULD CHANGE] {path.name}", flush=True)

    mode = "Changed" if args.apply else "Would change"
    print(f"\n{mode} {changed}/{total} article(s).", flush=True)


if __name__ == "__main__":
    main()
