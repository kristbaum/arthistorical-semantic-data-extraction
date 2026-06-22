"""Remove a stray heading immediately after the {{Artikel}} template.

Some formatted articles start, right after the closing ``}}`` of the
{{Artikel}} template, with a leftover ``== … ==`` heading — usually the OCR'd
location name repeated from the printed page header (e.g. ``== LEEDER ==``).
This heading is redundant (the location lives in the |Lemma=/|Ort= fields) and
should be dropped.

The script inspects the first non-blank line of each article body. If it is an
all-caps MediaWiki heading (``== … ==``) it is removed; any blank lines it
leaves behind are collapsed so the body still starts one blank line below the
template. Real section headings such as ``== Befund ==`` are kept, since they
are not all caps.

Default mode is a dry-run that lists every matching line; pass --apply to
write the changes to disk.

Usage:
    python -m src.articles.strip_leading_header [--band Band01] [--apply] [--verbose]
"""

import argparse
import re

from .helpers import REPO_ROOT, iter_formatted_articles, parse_article_file

# A line that is a MediaWiki heading: ==, ===, … on both sides after trimming.
# Group 1 captures the heading text between the equals signs.
_HEADER_RE = re.compile(r"^\s*={2,}\s*(.+?)\s*={2,}\s*$")


def _is_all_caps(text: str) -> bool:
    """True if the text has letters and none of them are lowercase.

    Leftover OCR page-header location names are typeset in all caps
    (``ELLIGHOFEN``, ``KAUFERING``), unlike real section headings such as
    ``Befund`` or ``Beschreibung und Ikonographie``.
    """
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def strip_leading_header(text: str) -> tuple[str, str | None]:
    """Return (new_text, removed_heading) for one article file.

    ``removed_heading`` is the stripped heading line if the body's first
    non-blank line was an all-caps heading, otherwise ``None`` and
    ``new_text == text``.
    """
    template_block, _fields, body = parse_article_file(text)
    if "{{Artikel" not in template_block:
        return text, None  # No template found — nothing to anchor on.

    lines = body.splitlines()
    idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if idx is None:
        return text, None  # Empty body.

    header = lines[idx]
    m = _HEADER_RE.match(header)
    if not m or not _is_all_caps(m.group(1)):
        return text, None  # Not an all-caps heading.

    # Drop the heading and any blank lines it leaves at the top of the body,
    # then re-attach the body one blank line below the template.
    rest = lines[idx + 1 :]
    while rest and not rest[0].strip():
        rest.pop(0)

    new_body = "\n" + "\n".join(rest)
    if body.endswith("\n") and not new_body.endswith("\n"):
        new_body += "\n"

    return template_block + new_body, header.strip()


def run(band: str | None, *, apply: bool, verbose: bool) -> int:
    """Process formatted articles. Returns the number of files affected."""
    affected = 0
    verb = "STRIP" if apply else "WOULD STRIP"

    for path in iter_formatted_articles(band):
        text = path.read_text(encoding="utf-8")
        new_text, header = strip_leading_header(text)
        if header is None:
            if verbose:
                print(f"  [OK] {path.relative_to(REPO_ROOT)}")
            continue

        affected += 1
        print(f"  [{verb}] {path.relative_to(REPO_ROOT)}: {header!r}")
        if apply:
            path.write_text(new_text, encoding="utf-8")

    return affected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--band",
        metavar="BAND",
        help="Process only this band, e.g. Band01 or Band03-1",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk (default: dry-run, only report)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    affected = run(args.band, apply=args.apply, verbose=args.verbose)

    mode = "Stripped heading from" if args.apply else "Found leading heading in"
    print(f"\n{mode} {affected} file(s).")


if __name__ == "__main__":
    main()
