#!/usr/bin/env python3
"""Turn field identifiers into links to the image that shows them.

The image captions say which field an image shows:
    [[File:Band01_chunk001_p011_img002.jpg|thumb|A<sub>2</sub> Gericht]]
From those captions this script builds a map identifier → file and links
    - every entry head in the Beschreibung section (a paragraph starting with
      the identifier: `A<sub>2</sub> Ein Engel …`, `B '''ST. MARTIN …'''`),
    - every other subscripted identifier in the body (`in A<sub>2</sub>`),
as  [[:File:Band01_chunk001_p011_img002.jpg|A<sub>2</sub>]]
(the leading colon makes a link to the file page instead of embedding it).

Not linked: plain letters outside entry heads (`Fresko B` often refers to
another building), ranges (`A<sub>1–4</sub>`), identifiers without an image,
captions, headings, table rows. Existing [[:File:…|…]] links are removed and
rebuilt on every run, so links always follow the current captions (fix a
caption, run finalize.py again). For a field with several images the link goes
to the first full view, not an »Ausschnitt«/»Detail«. Used by finalize.py;
standalone for a dry run:

    uv run python .claude/skills/clean-cbd-skill/scripts/link_identifiers.py FILE.wiki
"""

import re
import sys

# identifier at the start of a caption / paragraph: A, A<sub>2</sub>, W<sub>12</sub>
_IDENT = r"[A-Z](?:<sub>\d+</sub>)?"
_HEAD_RE = re.compile(rf"^({_IDENT})(?=\s+(?:'''|\(|[A-ZÄÖÜ]))")
_SUB_RE = re.compile(r"(?<![\w:|])([A-Z]<sub>\d+</sub>)(?![\w–-])")
_LINK_OR_FILE_RE = re.compile(r"\[\[[^\]]*\]\]")
_DETAIL_RE = re.compile(r"\b(?:Ausschnitt|Detail|Teilansicht)\b")


def image_map(body: str) -> dict[str, str]:
    """identifier → file whose caption starts with it: the first full view,
    an »Ausschnitt«/»Detail« only when the field has no full view."""
    out: dict[str, tuple[str, bool]] = {}
    for line in body.splitlines():
        line = line.strip()
        if not re.match(r"\[\[(?:File|Datei):", line):
            continue
        parts = line.strip("[]").split("|")
        fname = parts[0].split(":", 1)[1].strip()
        caption = parts[-1].strip() if len(parts) > 2 or (
            len(parts) == 2 and parts[1].strip() not in ("thumb", "mini")) else ""
        m = re.match(rf"({_IDENT})(?:\s|$)", caption)
        if m:
            detail = bool(_DETAIL_RE.search(caption))
            if m.group(1) not in out or (out[m.group(1)][1] and not detail):
                out[m.group(1)] = (fname, detail)
    return {ident: v[0] for ident, v in out.items()}


def _link(ident: str, fname: str) -> str:
    return f"[[:File:{fname}|{ident}]]"


def _sub_links(text: str, images: dict[str, str]) -> str:
    """Link subscripted identifiers outside existing [[…]]."""
    pieces, pos = [], 0
    for m in _LINK_OR_FILE_RE.finditer(text):
        pieces.append(("t", text[pos:m.start()]))
        pieces.append(("l", m.group(0)))
        pos = m.end()
    pieces.append(("t", text[pos:]))
    return "".join(
        _SUB_RE.sub(lambda m: _link(m[1], images[m[1]]) if m[1] in images else m[0], s)
        if kind == "t" else s
        for kind, s in pieces
    )


_OLD_LINK_RE = re.compile(r"\[\[:(?:File|Datei):[^|\]]*\|([^\]]*)\]\]")


def link_body(body: str) -> str:
    # rebuild from scratch, so links always follow the current captions
    body = _OLD_LINK_RE.sub(r"\1", body)
    images = image_map(body)
    if not images:
        return body
    out = []
    in_beschreibung = False
    for line in body.split("\n"):
        stripped = line.strip()
        if re.match(r"^==[^=].*==$", stripped):
            in_beschreibung = stripped.strip("= ").startswith("Beschreibung")
            out.append(line)
            continue
        if (not stripped or stripped.startswith(("[[File:", "[[Datei:", "{|", "|", "!", "="))):
            out.append(line)
            continue
        head = ""
        if in_beschreibung:
            m = _HEAD_RE.match(line)
            if m and m[1] in images:
                head, line = _link(m[1], images[m[1]]), line[m.end():]
        out.append(head + _sub_links(line, images))
    return "\n".join(out)


def main() -> None:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "src"))
    from articles.helpers import parse_article_file
    for arg in sys.argv[1:]:
        text = open(arg, encoding="utf-8").read()
        _tpl, _f, body = parse_article_file(text)
        new = link_body(body)
        print(f"== {arg}: {len(image_map(body))} captioned images")
        for a, b in zip(body.split("\n"), new.split("\n")):
            if a != b:
                print(f"  - {a[:110]}\n  + {b[:160]}")


if __name__ == "__main__":
    main()
