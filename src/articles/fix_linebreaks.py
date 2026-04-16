"""Fix [[File:…]] blocks that interrupt mid-sentence paragraphs.

For every non-Meta article in data/formatted/BandXX/ this script detects
the OCR/layout artefact where one or more [[File:…]] embeds have been placed
in the middle of a sentence split across multiple lines, e.g.

    …sind drei Personen

    [[File:Band05_chunk006_p018_img002.jpg|thumb|Der Kirchenraum]]

    [[File:Band05_chunk006_p018_img003.jpg|thumb|Stifterbild …]]

    dargestellt, rechts Pfarrer Hueber in schwarzem Gewand…

and moves the file block(s) to after the completed paragraph:

    …sind drei Personen
    dargestellt, rechts Pfarrer Hueber in schwarzem Gewand…

    [[File:Band05_chunk006_p018_img002.jpg|thumb|Der Kirchenraum]]
    [[File:Band05_chunk006_p018_img003.jpg|thumb|Stifterbild …]]

Only articles with an empty |Meta= field are processed.

Usage:
    python -m src.articles.fix_linebreaks [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from .helpers import OUTPUT_DIR

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_FILE_LINE_RE = re.compile(r"^\[\[File:", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?»›)\]]\s*$")
_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")

# ---------------------------------------------------------------------------
# Meta detection (mirrors format_articles._infer_meta logic)
# ---------------------------------------------------------------------------

_META_LEMMA_RE = re.compile(
    r"\bVorwort\b|\bDank\b|\bErinnerung\b"
    r"|Ortsregister|Personenregister"
    r"|Ikonographisches Register"
    r"|Embleme-Register|Bildnachweis"
    r"|^Im 18\. Jh",
    re.IGNORECASE,
)


def _is_meta(text: str) -> bool:
    """Return True if the article has a non-empty |Meta= or a meta Lemma."""
    for line in text.splitlines():
        s = line.strip()
        m = _FIELD_RE.match(s)
        if m:
            if m.group(1) == "Meta" and m.group(2).strip():
                return True
            if m.group(1) == "Lemma" and _META_LEMMA_RE.search(m.group(2)):
                return True
    return False


# ---------------------------------------------------------------------------
# Core fix
# ---------------------------------------------------------------------------


def fix_file_interruptions(text: str) -> str:
    """Move [[File:…]] blocks that split a paragraph to after the paragraph.

    Detects the pattern:
        …text ending without sentence-final punctuation…
        <blank line(s)>
        [[File:…]]          ← one or more file blocks (possibly with blanks between)
        <blank line(s)>
        continuation starting with a lowercase letter or comma/punctuation…

    The file block(s) are moved to after the completed paragraph.
    The function iterates until no more such patterns remain.
    """

    def is_file(line: str) -> bool:
        return bool(_FILE_LINE_RE.match(line.strip())) if line.strip() else False

    def is_blank(line: str) -> bool:
        return line.strip() == ""

    def ends_mid_sentence(line: str) -> bool:
        s = line.rstrip()
        return bool(s) and not _SENTENCE_END_RE.search(s)

    def continues_sentence(line: str) -> bool:
        s = line.lstrip()
        return bool(s) and (s[0].islower() or s[0] in ",;:")

    lines = text.splitlines()
    changed = True
    while changed:
        changed = False
        lines_out: list[str] = []
        i = 0
        while i < len(lines):
            if (
                not is_blank(lines[i])
                and not is_file(lines[i])
                and ends_mid_sentence(lines[i])
            ):
                # Skip over any blank lines after the prose line
                j = i + 1
                while j < len(lines) and is_blank(lines[j]):
                    j += 1

                # Collect a run of file lines (with optional blank lines between)
                file_block: list[str] = []
                k = j
                while k < len(lines):
                    if is_file(lines[k]):
                        file_block.append(lines[k])
                        k += 1
                    elif is_blank(lines[k]):
                        # Peek past blanks: continue only if a file line follows
                        m = k + 1
                        while m < len(lines) and is_blank(lines[m]):
                            m += 1
                        if m < len(lines) and is_file(lines[m]):
                            while k < m:
                                file_block.append(lines[k])
                                k += 1
                        else:
                            break
                    else:
                        break

                # Skip trailing blanks after file block
                while k < len(lines) and is_blank(lines[k]):
                    k += 1

                # Only act if the next line continues the interrupted sentence
                if file_block and k < len(lines) and continues_sentence(lines[k]):
                    # Join prose line and continuation: drop trailing hyphen or add space
                    prose = lines[i].rstrip()
                    cont = lines[k].lstrip()
                    if prose.endswith("-"):
                        joined = prose[:-1] + cont
                    else:
                        joined = prose + " " + cont
                    lines_out.append(joined)
                    lines_out.append("")
                    lines_out.extend(l for l in file_block if not is_blank(l))
                    i = k + 1
                    changed = True
                    continue

            lines_out.append(lines[i])
            i += 1
        lines = lines_out

    return "\n".join(lines)


def _normalize_blank_lines(text: str) -> str:
    """Enforce MediaWiki blank-line conventions:

    - No more than one consecutive blank line anywhere.
    - Exactly one blank line before and after every == heading == line.
    - No leading or trailing blank lines.
    """
    lines = text.splitlines()
    out: list[str] = []

    for line in lines:
        is_heading = line.strip().startswith("==") and line.strip().endswith("==")

        if is_heading:
            # Ensure exactly one blank line before heading (remove extras, add if missing)
            while out and out[-1] == "":
                out.pop()
            out.append("")
            out.append(line)
            # Blank line after heading will be enforced on next iteration naturally,
            # but we insert one now so the next content line is separated
            out.append("")
        else:
            # Collapse consecutive blank lines to at most one
            if line == "" and out and out[-1] == "":
                continue
            out.append(line)

    # Strip leading blank lines
    while out and out[0] == "":
        out.pop(0)
    # Strip trailing blank lines
    while out and out[-1] == "":
        out.pop()

    return "\n".join(out)




def fix_band(
    band_prefix: str,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> int:
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        if verbose:
            print(f"  SKIP {band_prefix}: directory not found")
        return 0

    changes = 0
    for path in sorted(band_dir.glob("*.wiki")):
        original = path.read_text(encoding="utf-8")

        if _is_meta(original):
            continue

        new_text = fix_file_interruptions(original)
        new_text = _normalize_blank_lines(new_text)

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
        total += fix_band(bp, apply=args.apply, verbose=args.verbose)

    mode = "Applied to" if args.apply else "Would change"
    print(f"\n{mode} {total} article(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
