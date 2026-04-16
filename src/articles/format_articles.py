"""Format and validate articles in data/formatted/BandXX/ directories.

For every article:
  1. Remove all <!-- ... --> comments.
  2. Remove {{End}} template lines.
  3. Replace <br> tags context-sensitively.
  4. Infer and set |Meta= in the {{Artikel}} template based on the Lemma:
       Vorwort               – lemma contains "Vorwort", "Dank", or "Erinnerung"
       Ortsregister          – lemma contains "Ortsregister"
       Personenregister      – lemma contains "Personenregister"
       Ikonographisches Register – lemma starts with "Ikonographisches Register"
       Embleme-Register      – lemma contains "Embleme-Register"
       Bildnachweis          – lemma contains "Bildnachweis"
       Malerliste            – lemma starts with "Im 18. Jh"
       (empty)               – all other articles
  5. Validate required template fields and print [ERROR] for any missing:
       All articles:         Band, Chunk, Chunkseite, Originalseitenvon,
                             Originalseitenbis, Lemma, davor, danach
       Non-Meta articles:    Typ, Ort, and at least one AutorIn field

Usage:
    python -m src.articles.format_articles [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from Levenshtein import distance as _levenshtein

from .helpers import OUTPUT_DIR

# ---------------------------------------------------------------------------
# Compiled patterns – formatting
# ---------------------------------------------------------------------------

_COMMENT_LINE_RE = re.compile(r"^\s*<!--.*-->\s*$")
_END_LINE_RE = re.compile(r"^\s*\{\{End\}\}\s*$")
_BR_NORM_RE = re.compile(r"<br\s*/?", re.IGNORECASE)


def _fix_br(text: str) -> str:
    """Replace <br> tags context-sensitively.

    Priority (applied in order after normalisation):
      1. ``word-<br>word``  → ``wordword``  (hyphenated line-break: drop hyphen)
      2. ``.<br>``          → ``.\n``        (sentence end: real line break)
      3. ``<br>``           → single space  (inline line-break)
    """
    text = _BR_NORM_RE.sub("<br", text)
    text = re.sub(r"<br[^>]*>", "<br>", text)
    text = re.sub(r"-\s*<br>\s*", "", text)
    text = re.sub(r"([.!?])\s*(?:<br>\s*)+", r"\1\n", text)
    text = re.sub(r"\s*<br>\s*", " ", text)
    return text


# ---------------------------------------------------------------------------
# Befund section label normalisation
# ---------------------------------------------------------------------------

_BEFUND_SECTION_RE = re.compile(r"^==\s*Befund\s*==\s*$")

# Canonical forms of the four labels to be bolded (fuzzy-matched against OCR)
_BEFUND_LABELS = [
    "Rahmen:",
    "Technik:",
    "Maße:",
    "Erhaltungszustand und Restaurierungen:",
    "Träger der Deckenmalerei:",
]


def _befund_label_threshold(label: str) -> int:
    """Levenshtein distance threshold – 15 % of label length, min 1."""
    return max(1, int(len(label) * 0.15))


def _fix_befund_labels(lines: list[str]) -> list[str]:
    """In == Befund ==: bold and OCR-normalise the standard sub-section labels.

    For each line in the Befund section the text up to the first colon is
    compared (case-insensitively) against the canonical label list using
    Levenshtein distance.  If the distance is within the per-label threshold
    the prefix is replaced with the bold canonical form.
    """
    result: list[str] = []
    in_befund = False

    for line in lines:
        if _BEFUND_SECTION_RE.match(line):
            in_befund = True
            result.append(line)
            continue
        if in_befund and re.match(r"^==[^=]", line):
            in_befund = False

        if in_befund and not line.startswith("'''") and ":" in line:
            colon_pos = line.index(":")
            candidate = line[: colon_pos + 1]
            for canonical in _BEFUND_LABELS:
                # Only compare when candidate length is close to canonical length
                if abs(len(candidate) - len(canonical)) > 6:
                    continue
                dist = _levenshtein(candidate.lower(), canonical.lower())
                if dist <= _befund_label_threshold(canonical):
                    rest = line[colon_pos + 1 :].lstrip()
                    sep = " " if rest else ""
                    line = f"'''{canonical}'''{sep}{rest}".rstrip()
                    break

        result.append(line)

    return result


# ---------------------------------------------------------------------------
# Meta inference
# ---------------------------------------------------------------------------

_META_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bVorwort\b|\bDank|\bErinnerung\b", re.IGNORECASE), "Vorwort"),
    (
        re.compile(r"^Ikonographisches Register\b", re.IGNORECASE),
        "Ikonographisches Register",
    ),
    (re.compile(r"\bOrtsregister\b", re.IGNORECASE), "Ortsregister"),
    (re.compile(r"\bPersonenregister\b", re.IGNORECASE), "Personenregister"),
    (
        re.compile(r"\bEmleme-Register\b|\bEmbleme-Register\b", re.IGNORECASE),
        "Embleme-Register",
    ),
    (re.compile(r"\bBildnachweis\b", re.IGNORECASE), "Bildnachweis"),
    (re.compile(r"^Im 18\. Jh", re.IGNORECASE), "Malerliste"),
]


def _infer_meta(lemma: str) -> str:
    for pattern, value in _META_RULES:
        if pattern.search(lemma):
            return value
    return ""


# ---------------------------------------------------------------------------
# Template read/write helpers
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")


def _read_template(lines: list[str]) -> dict[str, str]:
    """Return all |field=value pairs from the {{Artikel}} template."""
    fields: dict[str, str] = {}
    in_tpl = False
    for line in lines:
        s = line.strip()
        if s.startswith("{{Artikel"):
            in_tpl = True
        elif s == "}}" and in_tpl:
            break
        elif in_tpl:
            m = _FIELD_RE.match(line)
            if m:
                fields[m.group(1)] = m.group(2).strip()
    return fields


def _set_meta(lines: list[str], meta_value: str) -> list[str]:
    """Update |Meta= in the template, or insert it after |Lemma=."""
    pat_meta = re.compile(r"^(\s*\|Meta=).*$")
    pat_lemma = re.compile(r"^(\s*\|Lemma=).*$")
    in_tpl = False
    result: list[str] = []
    replaced = False

    for line in lines:
        s = line.strip()
        if s.startswith("{{Artikel"):
            in_tpl = True
        elif s == "}}" and in_tpl:
            in_tpl = False

        if in_tpl and not replaced:
            m = pat_meta.match(line)
            if m:
                result.append(m.group(1) + meta_value)
                replaced = True
                continue

        result.append(line)

        if in_tpl and not replaced:
            m = pat_lemma.match(line)
            if m:
                indent = re.match(r"^(\s*)", line).group(1)
                result.append(f"{indent}|Meta={meta_value}")
                replaced = True

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_ALWAYS_REQUIRED = [
    "Band",
    "Chunk",
    "Chunkseite",
    "Originalseitenvon",
    "Originalseitenbis",
    "Lemma",
]
_CONTENT_REQUIRED = ["Typ", "Ort"]


def _validate(fields: dict[str, str]) -> list[str]:
    """Return a list of error strings for this article's template."""
    errors: list[str] = []
    meta = fields.get("Meta", "")

    for f in _ALWAYS_REQUIRED:
        if not fields.get(f, "").strip():
            errors.append(f"missing |{f}=")

    for f in ("davor", "danach"):
        if f not in fields:
            errors.append(f"field |{f}= not present in template")

    if not meta:
        for f in _CONTENT_REQUIRED:
            if not fields.get(f, "").strip():
                errors.append(f"missing |{f}=")
        has_autor = any(
            k.startswith("AutorIn") and v.strip() for k, v in fields.items()
        )
        if not has_autor:
            errors.append("no |AutorIn1= (or higher) set")

    return errors


# ---------------------------------------------------------------------------
# Per-article processor
# ---------------------------------------------------------------------------


def process_article(text: str, *, apply: bool) -> tuple[str, list[str]]:
    """Format, set Meta, and validate. Returns (new_text, errors)."""
    # Step 1: formatting transforms
    text = _fix_br(text)
    lines = text.splitlines()
    lines = [
        l for l in lines if not _COMMENT_LINE_RE.match(l) and not _END_LINE_RE.match(l)
    ]
    lines = _fix_befund_labels(lines)
    while lines and not lines[-1].strip():
        lines.pop()

    # Step 2: infer and set Meta
    fields = _read_template(lines)
    lemma = fields.get("Lemma", "")
    meta = _infer_meta(lemma)
    if fields.get("Meta") != meta:
        lines = _set_meta(lines, meta)
        fields = _read_template(lines)

    # Step 3: validate
    errors = _validate(fields)

    new_text = "\n".join(lines) + "\n"
    return new_text, errors


# ---------------------------------------------------------------------------
# Per-band processor
# ---------------------------------------------------------------------------


def format_band(
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
        new_text, errors = process_article(original, apply=apply)

        if new_text != original:
            changes += 1
            if apply:
                path.write_text(new_text, encoding="utf-8")
                if verbose:
                    print(f"  [WROTE] {band_prefix}/{path.name}")
            else:
                print(f"  [WOULD CHANGE] {band_prefix}/{path.name}")

        for err in errors:
            print(f"  [ERROR] {band_prefix}/{path.name}: {err}")

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
        total += format_band(bp, apply=args.apply, verbose=args.verbose)

    mode = "Applied to" if args.apply else "Would change"
    print(f"\n{mode} {total} article(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
