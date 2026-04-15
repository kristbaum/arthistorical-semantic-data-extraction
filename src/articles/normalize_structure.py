"""Normalise structural markup in formatted article files.

For each non-list article:
  1. Ensures the five pre-section bold fields use the canonical ''bold:'' form:
       '''Patrozinium:'''
       '''Zur Geschichte:'''
       '''Zum Bauwerk:'''
       '''Auftraggeber:'''
       '''Autor und Entstehungszeit:'''
     Handles variants: plain-text "Field: text", level-2 headings "== Field ==",
     bold-without-colon "'''Field''' text", OCR errors, etc.

  2. Normalises the main bibliography section heading:
     all pure Quellen/Literatur variants  →  == Quellen und Literatur ==
     (topic-specific sub-headings like "Literatur zu Augustinus" are left alone).
     Headings with embedded archival content after the name have the content
     moved to a new bullet-list line below the normalised heading.

List articles (Lemma contains "(Band XX)" or starts with "Im 18. Jh") receive
step 2 only.

Usage:
    python -m src.articles.normalize_structure [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from .helpers import OUTPUT_DIR

# ---------------------------------------------------------------------------
# List-article detection (must match format_articles.py)
# ---------------------------------------------------------------------------


def _is_list_article(lemma: str) -> bool:
    return bool(re.search(r"\(Band\s+\d", lemma, re.IGNORECASE)) or bool(
        re.search(r"^Im 18\. Jh", lemma, re.IGNORECASE)
    )


# ---------------------------------------------------------------------------
# Template field reader
# ---------------------------------------------------------------------------


def _get_lemma(lines: list[str]) -> str:
    for line in lines:
        m = re.match(r"^\s*\|Lemma=(.+)$", line)
        if m:
            return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Bold-field normalisation
# ---------------------------------------------------------------------------

# Each entry: (canonical label, fuzzy regex matched against stripped line text)
_BOLD_FIELDS: list[tuple[str, str]] = [
    ("Patrozinium", r"Patroz\w*"),
    ("Zur Geschichte", r"Zur\s+Geschichte\b"),
    ("Zum Bauwerk", r"Zum\s+Bauwerk\b"),
    ("Auftraggeber", r"Auftragg?eber\b"),
    ("Autor und Entstehungszeit", r"Autor\s+und\s+Entstehungszeit\b"),
]

# Precompile per-field patterns for the three malformed variants
_BOLD_COMPILED: list[tuple[str, re.Pattern, re.Pattern, re.Pattern]] = []
for _label, _pat in _BOLD_FIELDS:
    # Variant A: section heading (with optional trailing colon + embedded content)
    #   == Field ==  |  == Field: ==  |  == Field: some extra text ==
    _re_heading = re.compile(
        rf"^(==+)\s*(?:''')?{_pat}(?:''')?\s*:?\s*(.*?)\s*==+\s*$",
        re.IGNORECASE,
    )
    # Variant B-1: plain text with colon  →  "Field: content"
    _re_plain = re.compile(
        rf"^{_pat}\s*:\s*(.+)$",
        re.IGNORECASE,
    )
    # Variant B-2: plain text without colon, and no colon anywhere else on the
    # line (prevents matching sub-headings like "Zur Geschichte der Wallfahrt:")
    _re_plain_nocolon = re.compile(
        rf"^{_pat}\s+(?=[^:]*$)(.+)$",
        re.IGNORECASE,
    )
    # Variant C: bold but missing colon
    #   '''Field''' content   |   ''' Field ''' content
    _re_bold_no_colon = re.compile(
        rf"^'''\s*{_pat}\s*'''\s*(.*?)$",
        re.IGNORECASE,
    )
    _BOLD_COMPILED.append((_label, _re_heading, _re_plain, _re_plain_nocolon, _re_bold_no_colon))

# Correct form prefix (any trailing content after the bold marker is fine)
_ALREADY_CORRECT: list[re.Pattern] = [
    re.compile(rf"^'''{re.escape(label)}:'''", re.IGNORECASE)
    for label, _ in _BOLD_FIELDS
]


def _fix_bold_line(line: str) -> str | None:
    """If line has a malformed bold field, return corrected line; else None."""
    s = line.strip()
    if not s:
        return None

    for i, (label, re_h, re_p, re_pnc, re_b) in enumerate(_BOLD_COMPILED):
        # Skip if already in correct form
        if _ALREADY_CORRECT[i].match(s):
            return None

        # Variant A: section heading
        m = re_h.match(s)
        if m:
            extra = m.group(2).strip().rstrip(":").strip()
            if extra:
                return f"'''{label}:''' {extra}"
            return f"'''{label}:'''"

        # Variant B-1: plain text with colon
        m = re_p.match(s)
        if m:
            rest = m.group(1).strip()
            return f"'''{label}:''' {rest}" if rest else f"'''{label}:'''"

        # Variant B-2: plain text without colon (no colon anywhere on line)
        m = re_pnc.match(s)
        if m:
            rest = m.group(1).strip()
            return f"'''{label}:''' {rest}" if rest else f"'''{label}:'''"

        # Variant C: bold without colon
        m = re_b.match(s)
        if m:
            rest = m.group(1).strip().lstrip(":").strip()
            return f"'''{label}:''' {rest}" if rest else f"'''{label}:'''"

    return None


def _normalize_bold_fields(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        fixed = _fix_bold_line(line)
        result.append(fixed if fixed is not None else line)
    return result


# ---------------------------------------------------------------------------
# Bibliography heading normalisation
# ---------------------------------------------------------------------------

# Inner text patterns for "pure" bib headings (no topic specifier)
_NAME_PART = (
    r"(?:(?:[OQ]u?|Ou)\s*[eu]?ll?[ae]n?"          # Quellen / Ouellen / OCR variant
    r"(?:\s*(?:und|u\.)\s*"                         # …und…
    r"(?:Literat[aui]r?\s*:?\s*|Literat\s*:?\s*))?" # …Literatur
    r"|Literat[aui]r?\s*:?\s*)"                     # or bare Literatur
)
# Optional suffix allowed in "pure" heading (Auswahl, trailing colon, trailing spaces)
_SUFFIX_PURE = r"(?:\??:?\s*|\(Auswahl\)\s*)"

_BIB_PURE_RE = re.compile(
    rf"^{_NAME_PART}{_SUFFIX_PURE}$",
    re.IGNORECASE,
)

# Headings that start with the bib name but have extra (non-topic) embedded content.
# Topic-starting words (zu / zur / zum / und / nur etc.) → leave heading alone.
_BIB_PREFIX_RE = re.compile(
    rf"^{_NAME_PART}",
    re.IGNORECASE,
)
_TOPIC_WORD_RE = re.compile(
    r"^\s*(?:zu[rm]?\b|und\b|nur\b|über\b|der\b|des\b|die\b|Antoniusliterati\b|s\.\s*S\.\b)",
    re.IGNORECASE,
)

# Strip HTML <b> tags that wrap the heading text
_HTML_BOLD_RE = re.compile(r"</?b>", re.IGNORECASE)

_CANONICAL_BIB = "== Quellen und Literatur =="


def _normalize_bib_headings(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        m = re.match(r"^(==+)\s*(.*?)\s*==+\s*$", line)
        if not m:
            result.append(line)
            continue

        inner_raw = m.group(2)
        # Strip HTML bold tags, e.g. <b>Quellen und Literatur</b>
        inner = _HTML_BOLD_RE.sub("", inner_raw).strip()

        if _BIB_PURE_RE.match(inner):
            # Pure bib heading → canonical
            result.append(_CANONICAL_BIB)
            continue

        if _BIB_PREFIX_RE.match(inner):
            # Starts with bib prefix — check for embedded content after the prefix
            prefix_m = _BIB_PREFIX_RE.match(inner)
            remainder = inner[prefix_m.end():].strip().lstrip(":").strip()
            if remainder and not _TOPIC_WORD_RE.match(remainder):
                # Embedded archival content — normalize heading and move content below
                result.append(_CANONICAL_BIB)
                result.append(f"* {remainder}")
                continue

        result.append(line)
    return result


# ---------------------------------------------------------------------------
# Per-article transform
# ---------------------------------------------------------------------------


def normalize_article(text: str, lemma: str) -> str:
    lines = text.splitlines()

    # Step 1: bold fields (non-list articles only)
    if not _is_list_article(lemma):
        lines = _normalize_bold_fields(lines)

    # Step 2: bibliography headings (all articles)
    lines = _normalize_bib_headings(lines)

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Per-band processor
# ---------------------------------------------------------------------------


def normalize_band(
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
        lemma = _get_lemma(original.splitlines())
        new_text = normalize_article(original, lemma)

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
    parser.add_argument("--band", metavar="BAND")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    total = 0
    for bp in band_prefixes:
        n = normalize_band(bp, apply=args.apply, verbose=args.verbose)
        total += n

    mode = "Applied to" if args.apply else "Would change"
    print(f"\n{mode} {total} article(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
