#!/usr/bin/env python3
"""Write a cleaned article as the formatted original plus a list of edits.

Retyping a whole article costs as many output tokens as the article is long —
the largest part of the cleaning bill. Instead, copy the original and apply
exact replacements. The edits file holds blocks of

    <<<
    old text (exact, may span lines)
    ===
    new text
    >>>

Every `old` must occur exactly once in the current text (edits apply in
order, so a later edit sees the result of earlier ones); otherwise the script
stops and writes nothing. The {{Artikel …}} template cannot be edited.

Usage:
    uv run python .claude/skills/clean-cbd-skill/scripts/apply_edits.py \\
        SRC.wiki TARGET.wiki EDITS.txt      # EDITS.txt may be - for stdin
"""

import re
import sys
from pathlib import Path

_BLOCK_RE = re.compile(r"^<<<\n(.*?)\n===\n(.*?)\n?>>>$", re.S | re.M)


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, target, edits_arg = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    edits_text = sys.stdin.read() if edits_arg == "-" else Path(edits_arg).read_text(encoding="utf-8")
    text = src.read_text(encoding="utf-8")
    tpl_end = text.index("\n}}\n") + 4
    template, body = text[:tpl_end], text[tpl_end:]

    edits = _BLOCK_RE.findall(edits_text)
    if not edits:
        sys.exit("no <<< === >>> blocks found")
    errors = []
    for i, (old, new) in enumerate(edits, 1):
        n = body.count(old)
        if n != 1:
            errors.append(f"edit {i}: old text found {n}× — {old[:70]!r}")
            continue
        body = body.replace(old, new)
    if errors:
        sys.exit("nothing written:\n  " + "\n  ".join(errors))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template + body, encoding="utf-8")
    print(f"  [{len(edits)} edits] {target}")


if __name__ == "__main__":
    main()
