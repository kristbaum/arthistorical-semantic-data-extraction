"""Format articles in data/formatted/BandXX/ directories.

For every article:
  1. Extract Chunk/Chunkseite from the first <!-- dropbox: ... --> comment
     (if the article has none, look up the "davor" article for its dropbox).
  2. Set |Chunk= and |Chunkseite= in the {{Artikel}} template.
  3. Remove all <!-- dropbox: ... --> comments.
  4. Remove all <!-- header: XXX --> comments.
  5. Remove {{End}} template lines.

"List articles" — Lemma contains "(Band XX)" or starts with "Im 18. Jh" —
receive steps 1-5 only (no bibliography formatting).

For all other articles:
  6. Find the first bibliography section heading (containing "Literatur" or
     "Quellen"/"Ouellen" in any capitalisation / OCR variant).
  7. Format all non-special content lines from that heading to the end of the
     file as MediaWiki bullet list items ("* ...").
     Lines that are left as-is: headings (==), [[File:...]], <!-- comments -->,
     lines already starting with *, or lines starting with { / }.

Usage:
    python -m src.articles.format_articles [--band Band01] [--apply] [--verbose]
"""

import argparse
import re
from pathlib import Path

from .helpers import OUTPUT_DIR, sanitize_filename

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_DROPBOX_LINE_RE = re.compile(r"<!--\s*dropbox:\s*https?://\S+\s*-->")
_HEADER_LINE_RE = re.compile(r"<!--\s*header:\s*[^>]+-->")
_END_LINE_RE = re.compile(r"^\s*\{\{End\}\}\s*$")

# Extract (chunk_slug, page_num) from a dropbox URL
_DROPBOX_INFO_RE = re.compile(
    r"<!--\s*dropbox:.*?_(chunk\d+)\.pdf#page=(\d+)\s*-->"
)

# Template field line: leading whitespace, pipe, name, equals, value
_FIELD_RE = re.compile(r"^(\s*\|(\w+)=)(.*)$")

# Bibliography / sources section heading (level 2 or deeper)
_BIB_HEADING_RE = re.compile(
    r"^==+\s*.{0,80}(?:liter|quell|ouell).{0,80}\s*==+\s*$",
    re.IGNORECASE,
)

_HEADING_RE = re.compile(r"^==")
_FILE_RE = re.compile(r"^\[\[File:")
_COMMENT_RE = re.compile(r"^<!--")
_BULLET_RE = re.compile(r"^\*")


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------


def _get_template_fields(lines: list[str]) -> dict[str, str]:
    """Return |field=value mapping from the {{Artikel}} template."""
    fields: dict[str, str] = {}
    in_tpl = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{{Artikel"):
            in_tpl = True
        elif stripped == "}}" and in_tpl:
            break
        elif in_tpl:
            m = _FIELD_RE.match(line)
            if m:
                fields[m.group(2)] = m.group(3).strip()
    return fields


def _set_template_field(lines: list[str], field: str, value: str) -> list[str]:
    """Replace the value of |field= inside the {{Artikel}} template block."""
    pat = re.compile(rf"^(\s*\|{re.escape(field)}=).*$")
    result: list[str] = []
    in_tpl = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{{Artikel"):
            in_tpl = True
        elif stripped == "}}" and in_tpl:
            in_tpl = False
        if in_tpl and not replaced:
            m = pat.match(line)
            if m:
                result.append(m.group(1) + value)
                replaced = True
                continue
        result.append(line)
    return result


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _first_dropbox_info(text: str) -> tuple[str, str] | None:
    """Return (chunk_number, page_number) from the first dropbox comment, or None."""
    m = _DROPBOX_INFO_RE.search(text)
    if not m:
        return None
    chunk_int = int(re.sub(r"\D", "", m.group(1)))  # "chunk006" → 6
    return str(chunk_int), m.group(2)


def _is_list_article(lemma: str) -> bool:
    """Return True for register/index articles that must not have bib reformatted."""
    return bool(re.search(r"\(Band\s+\d", lemma, re.IGNORECASE)) or \
           bool(re.search(r"^Im 18\. Jh", lemma, re.IGNORECASE))


def _format_bib_section_lines(lines: list[str]) -> list[str]:
    """Add '* ' to each content line that is not a heading / file / comment / bullet."""
    result: list[str] = []
    for line in lines:
        s = line.rstrip()
        if not s:
            result.append("")
        elif _HEADING_RE.match(s):
            result.append(s)
        elif _FILE_RE.match(s):
            result.append(s)
        elif _COMMENT_RE.match(s):
            result.append(s)
        elif _BULLET_RE.match(s):
            result.append(s)
        elif s.startswith("{") or s.startswith("}"):
            result.append(s)
        else:
            result.append("* " + s)
    return result


# ---------------------------------------------------------------------------
# Per-article transform
# ---------------------------------------------------------------------------


def format_article(
    text: str,
    lemma: str,
    davor_text: str | None = None,
) -> str:
    """Apply all transformations and return the new article text."""
    lines = text.splitlines()

    # 1. Determine Chunk/Chunkseite from this article or davor fallback
    dropbox_info = _first_dropbox_info(text)
    if dropbox_info is None and davor_text is not None:
        dropbox_info = _first_dropbox_info(davor_text)

    # 2. Set template fields
    if dropbox_info is not None:
        chunk, chunkseite = dropbox_info
        lines = _set_template_field(lines, "Chunk", chunk)
        lines = _set_template_field(lines, "Chunkseite", chunkseite)

    # 3. Strip dropbox comments, header comments, {{End}}
    cleaned: list[str] = []
    for line in lines:
        if _DROPBOX_LINE_RE.search(line):
            continue
        if _HEADER_LINE_RE.search(line):
            continue
        if _END_LINE_RE.match(line):
            continue
        cleaned.append(line)
    lines = cleaned

    # 4. Strip trailing blank lines
    while lines and not lines[-1].strip():
        lines.pop()

    # 5. Bibliography formatting (non-list articles only)
    if not _is_list_article(lemma):
        bib_start: int | None = None
        for i, line in enumerate(lines):
            if _BIB_HEADING_RE.match(line.strip()):
                bib_start = i
                break
        if bib_start is not None:
            formatted_tail = _format_bib_section_lines(lines[bib_start + 1:])
            lines = lines[: bib_start + 1] + formatted_tail

    # 6. Strip trailing blank lines again after formatting
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Per-band processor
# ---------------------------------------------------------------------------


def format_band(
    band_prefix: str,
    all_band_dirs: dict[str, Path] | None = None,
    *,
    apply: bool = False,
    verbose: bool = False,
) -> int:
    """Format all articles in data/formatted/{band_prefix}/. Returns change count."""
    band_dir = OUTPUT_DIR / band_prefix
    if not band_dir.is_dir():
        if verbose:
            print(f"  SKIP {band_prefix}: directory not found")
        return 0

    if all_band_dirs is None:
        all_band_dirs = {p.name: p for p in OUTPUT_DIR.iterdir() if p.is_dir()}

    # Build lemma → (path, text) map for this band (for davor lookup)
    band_cache: dict[str, tuple[Path, str]] = {}
    for f in band_dir.glob("*.wiki"):
        t = f.read_text(encoding="utf-8")
        fields = _get_template_fields(t.splitlines())
        lemma = fields.get("Lemma", f.stem)
        band_cache[lemma] = (f, t)

    def get_davor_text(davor_lemma: str) -> str | None:
        if not davor_lemma:
            return None
        entry = band_cache.get(davor_lemma)
        if entry:
            return entry[1]
        # Cross-band fallback
        fname = sanitize_filename(davor_lemma) + ".wiki"
        for bd_path in all_band_dirs.values():
            candidate = bd_path / fname
            if candidate.exists():
                return candidate.read_text(encoding="utf-8")
        return None

    changes = 0
    for lemma, (path, original) in sorted(band_cache.items()):
        fields = _get_template_fields(original.splitlines())
        # Only fetch davor text if we actually need it
        need_davor = _first_dropbox_info(original) is None
        davor_text = get_davor_text(fields.get("davor", "")) if need_davor else None

        new_text = format_article(original, lemma, davor_text)

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
    parser.add_argument("--band", metavar="BAND", help="Process only this band, e.g. Band01")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk (default: dry-run)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_dir())

    all_band_dirs = {p.name: p for p in OUTPUT_DIR.iterdir() if p.is_dir()}

    total = 0
    for bp in band_prefixes:
        n = format_band(bp, all_band_dirs, apply=args.apply, verbose=args.verbose)
        total += n

    mode = "Applied to" if args.apply else "Would change"
    print(f"\n{mode} {total} article(s) across {len(band_prefixes)} band(s).")


if __name__ == "__main__":
    main()
