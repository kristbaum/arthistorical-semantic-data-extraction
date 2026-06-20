#!/usr/bin/env python3
"""
Format CbDD *Register* articles into two-column MediaWiki tables.

Index registers in the printed volumes are run-on lists of the form

    Headword <page refs> NextHeadword <page refs> ...

e.g.  ``Adler 130 f., 186, 270, 315 Amboß 107 f. Anker 579``

This script finds every article whose ``|Meta=`` field is one of the four
register types and rewrites the index parts into wikitables:

    {| class="wikitable"
    ! Stichwort !! Fundstellen
    |-
    | Adler || 130 f., 186, 270, 315
    |-
    | Amboß || 107 f.
    |}

What is preserved verbatim:
  * the ``{{Artikel}}`` template header
  * ``== Section ==`` headings
  * explanatory prose paragraphs, Errata, and anything that does not look
    like a dense list of "headword + page numbers" (colon-bearing lines are
    always treated as prose).

Existing wikitables (some Ortsregister are already wrapped, often with several
print-columns merged into one row) are unwrapped and re-split, so re-running
the script is stable.

Heuristic limitations (noisy OCR — output is meant to be proof-read):
  * Cross-reference targets are taken as a single token after each ``→``.
    Multi-word targets such as ``→ Bad Aibling`` keep only ``Bad``; the rest
    is attached to the following headword.
  * Where the source merged several print-columns onto one line, entries from
    different columns are split correctly but interleaved in reading order.

Usage:
    python3 format_register_tables.py            # dry run, prints a summary
    python3 format_register_tables.py --apply    # write changes to disk
    python3 format_register_tables.py --apply --show "Embleme"  # filter by lemma/path
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent
FORMATTED = REPO_ROOT / "data" / "formatted"

# Meta values that are index-style registers we want to tabulate.
REGISTER_META = {
    "Embleme-Register",
    "Ortsregister",
    "Personenregister",
    "Ikonographisches Register",
}

ITALIC_RE = re.compile(r"</?i>")
ARROW_RE = re.compile(r"\s*(?:->|→)\s*")
HEADING_RE = re.compile(r"^\s*==.*==\s*$")
META_RE = re.compile(r"^\|Meta=(.*)$", re.MULTILINE)

ARROW = "→"


def normalize_arrows(text: str) -> str:
    """Make every cross-reference arrow a stand-alone ``→`` token."""
    return ARROW_RE.sub(f" {ARROW} ", text)


def _core(tok: str) -> str:
    """Strip italic tags and surrounding punctuation from a token."""
    return ITALIC_RE.sub("", tok).strip(" ,.;:")


def is_arrow(tok: str) -> bool:
    return tok == ARROW


def has_digit(tok: str) -> bool:
    return any(ch.isdigit() for ch in tok)


def is_numberish(tok: str) -> bool:
    """True for page-reference tokens: numbers, ranges, ``f.``/``ff.``."""
    c = _core(tok)
    if c == "":
        # token was pure punctuation -> keep it attached to the ref run
        return tok.strip() in (",", ".", ";")
    if has_digit(c):
        return True
    return c in ("f", "ff")


def is_ref_start(tok: str) -> bool:
    return is_numberish(tok) or is_arrow(tok)


def parse_entries(text: str) -> list[tuple[list[str], list[str]]]:
    """Split run-on register text into (headword tokens, reference tokens)."""
    tokens = normalize_arrows(text).split()
    entries: list[tuple[list[str], list[str]]] = []
    i, n = 0, len(tokens)

    while i < n:
        # Headword: everything up to the first page-ref / arrow token.
        head: list[str] = []
        while i < n and not is_ref_start(tokens[i]):
            head.append(tokens[i])
            i += 1

        # References: page numbers, ranges and arrow + single target token.
        refs: list[str] = []
        while i < n:
            tok = tokens[i]
            if is_arrow(tok):
                refs.append(tok)
                i += 1
                if i < n and not is_arrow(tokens[i]):
                    refs.append(tokens[i])  # one cross-reference target token
                    i += 1
                continue
            if is_numberish(tok):
                refs.append(tok)
                i += 1
                continue
            break  # a new headword starts here

        if head or refs:
            entries.append((head, refs))
        else:  # safety: never stall on an unexpected token
            i += 1

    return entries


def entry_has_number(refs: list[str]) -> bool:
    return any(has_digit(t) for t in refs)


def _index_stats(block: str) -> tuple[int, int, float]:
    """Return (number-bearing entries, total entries, page-number token ratio)."""
    if ":" in block:  # Errata / explanatory notes use colons; indexes don't
        return 0, 0, 0.0
    tokens = normalize_arrows(block).split()
    if not tokens:
        return 0, 0, 0.0
    ratio = sum(1 for t in tokens if has_digit(t)) / len(tokens)
    entries = parse_entries(block)
    good = sum(1 for _, refs in entries if entry_has_number(refs))
    return good, len(entries), ratio


def looks_like_index(block: str) -> bool:
    """Decide whether a paragraph is a register list (vs. prose).

    Relies on entry *structure* (most entries are ``headword + page numbers``)
    rather than token density, so long-sentence lemmata such as the Latin and
    German emblem mottos are tabulated too. Colon-bearing notes (Errata,
    explanatory paragraphs) are excluded up front.
    """
    good, total, ratio = _index_stats(block)
    return good >= 3 and total > 0 and good / total >= 0.5 and ratio >= 0.05


def is_index_continuation(block: str) -> bool:
    """Looser test: a short index block continuing an already-open table.

    Used only while a table is being accumulated, so short letter-groups such
    as ``Eiche, Eichenlaub 583 f Elefant 584`` are not split off as prose.
    """
    good, total, ratio = _index_stats(block)
    return good >= 1 and total > 0 and good / total >= 0.6 and ratio >= 0.05


def cell_escape(text: str) -> str:
    return text.replace("|", "&#124;")


def normalize_entries(
    entries: list[tuple[list[str], list[str]]],
) -> list[tuple[list[str], list[str]]]:
    """Repair fragmented entries so each row is one headword + its page refs.

    * A bare page number with no headword (a page list that wrapped across a
      print-column or page break) is attached to the entry above it.
    * A headword with no references (an OCR fragment whose page number was lost
      or split off) is merged into the following headword.

    Both repairs also make the output stable: re-running the formatter on its
    own output reproduces it exactly.
    """
    # Pass 1: headword-less entries -> previous entry's references.
    step: list[tuple[list[str], list[str]]] = []
    for head, refs in entries:
        if not head and step:
            step[-1] = (step[-1][0], step[-1][1] + refs)
        else:
            step.append((head, refs))

    # Pass 2: reference-less headwords -> prepended to the next entry.
    out: list[tuple[list[str], list[str]]] = []
    i = 0
    while i < len(step):
        head, refs = step[i]
        if not refs:
            carried: list[str] = []
            while i < len(step) and not step[i][1]:
                carried += step[i][0]
                i += 1
            if i < len(step):
                out.append((carried + step[i][0], step[i][1]))
                i += 1
            else:
                out.append((carried, []))  # trailing fragment, nothing to join
        else:
            out.append((head, refs))
            i += 1
    return out


def render_table(entries: list[tuple[list[str], list[str]]]) -> str:
    """Render parsed entries as a two-column wikitable."""
    parts = ['{| class="wikitable"', "! Stichwort !! Fundstellen"]
    for head, refs in normalize_entries(entries):
        headword = cell_escape(" ".join(head).strip())
        fundstellen = cell_escape(" ".join(refs).strip())
        parts.append("|-")
        parts.append(f"| {headword} || {fundstellen}")
    parts.append("|}")
    return "\n".join(parts)


def strip_table_markup(body: str) -> str:
    """Reduce any existing MediaWiki table markup back to plain index text.

    Some registers are already (partly) tabulated, sometimes malformed: stray
    ``|-`` / ``| ...`` lines scattered through plain text, or several
    print-columns packed into one row as single-pipe columns. Dropping the
    scaffolding lines and turning cell separators back into spaces lets the
    normal parser re-segment everything and makes the formatter idempotent.
    """
    out: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith(("{|", "|}", "|-", "|+", "!")):
            continue  # drop table scaffolding / header rows
        # Any remaining raw pipe is a column separator (true literal pipes are
        # stored as &#124;), so flatten it to whitespace.
        out.append(line.replace("|", " "))
    return "\n".join(out)


def split_header(text: str) -> tuple[str, str]:
    """Split off the leading ``{{Artikel ... }}`` template block."""
    lines = text.splitlines()
    if not lines or not lines[0].lstrip().startswith("{{"):
        return "", text
    for idx, line in enumerate(lines):
        if line.strip() == "}}":
            header = "\n".join(lines[: idx + 1])
            rest = "\n".join(lines[idx + 1 :])
            return header, rest
    return "", text


def split_blocks(body: str) -> list[str]:
    """Split body into blank-line-separated blocks; isolate heading lines."""
    raw_blocks = re.split(r"\n\s*\n", body)
    blocks: list[str] = []
    for raw in raw_blocks:
        block = raw.strip("\n")
        if not block.strip():
            continue
        # A heading on its own line is always a standalone block.
        if HEADING_RE.match(block.splitlines()[0]) and len(block.splitlines()) > 1:
            first, *rest = block.splitlines()
            blocks.append(first)
            remainder = "\n".join(rest).strip("\n")
            if remainder.strip():
                blocks.append(remainder)
        else:
            blocks.append(block)
    return blocks


def process_text(text: str) -> str:
    header, body = split_header(text)
    blocks = split_blocks(strip_table_markup(body))

    out_parts: list[str] = []
    if header:
        out_parts.append(header)

    pending: list[tuple[list[str], list[str]]] = []  # buffered index entries

    def flush() -> None:
        if pending:
            out_parts.append(render_table(pending))
            pending.clear()

    for block in blocks:
        if HEADING_RE.match(block):
            flush()
            out_parts.append(block)
        elif looks_like_index(block):
            pending.extend(parse_entries(block))
        elif pending and is_index_continuation(block):
            pending.extend(parse_entries(block))
        else:
            flush()
            out_parts.append(block)

    flush()

    result = "\n\n".join(out_parts)
    if text.endswith("\n"):
        result += "\n"
    return result


def get_meta(text: str) -> str | None:
    match = META_RE.search(text)
    return match.group(1).strip() if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes to disk")
    parser.add_argument("--show", metavar="SUBSTR", help="print full output for files whose path contains SUBSTR")
    args = parser.parse_args()
    dry_run = not args.apply

    wiki_files = sorted(FORMATTED.rglob("*.wiki"))
    changed = 0
    by_meta: dict[str, int] = {}

    for path in wiki_files:
        text = path.read_text(encoding="utf-8")
        meta = get_meta(text)
        if meta not in REGISTER_META:
            continue

        new_text = process_text(text)
        if new_text == text:
            continue

        changed += 1
        by_meta[meta] = by_meta.get(meta, 0) + 1
        rel = path.relative_to(REPO_ROOT)
        print(f"{'[would change]' if dry_run else '[changed]'} {rel}  (Meta={meta})")

        if args.show and args.show in str(path):
            print("-" * 70)
            print(new_text)
            print("-" * 70)

        if not dry_run:
            path.write_text(new_text, encoding="utf-8")

    print()
    print(f"{'Would change' if dry_run else 'Changed'} {changed} file(s).")
    for meta in sorted(by_meta):
        print(f"  {meta}: {by_meta[meta]}")
    if dry_run:
        print("\nDry run only. Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
