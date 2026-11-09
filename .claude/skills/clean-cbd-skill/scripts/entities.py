#!/usr/bin/env python3
"""Mark the building and the paintings with {{Entität}} (rule 3.13), give
every {{Entität}} a stable id.

The deterministic part of the entity markup; persons are marked by hand.
Every entity gets exactly one template — its first (best) mention.

1. Building: the part of the article's first sentence that names it, up to
   the first comma or semicolon:
       {{Entität|Pfarrkirche|rolle=Bauwerk}}, Pfarrei …, Diözese Augsburg; …
2. Paintings with identifiers, in the painting sections (Beschreibung,
   Beschreibung und Ikonographie, Bildabfolge, Bildabfolge und Inschriften,
   Darstellung, Rekonstruierende …, Erste Ausstattung, Ikonographie,
   Ikonologie, room headings — every section except Befund, Quellen/Literatur,
   Zeichnung/Entwurf and registers). The template goes on
     - the entry head (a paragraph starting with the identifier: `A '''TITEL'''`,
       `A<sub>2</sub> Ein Engel …`, `B Huldigung an die Immaculata; …`,
       numbered medallions `1 Zacharias …`), else
     - the first subscripted mention in a painting section (`D<sub>2</sub> Gregor`
       inside another entry), else
     - the first subscripted mention anywhere, if the field has an image:
   {{Entität|A<sub>2</sub>|rolle=Deckenbild|titel=Gericht|bild=Band01_….jpg}}
   `titel` = the caption without its identifier, else the bold caps title of
   the entry, else the text before the first `;` (≤ 80 chars), else the whole
   entry if it is a short phrase. `bild` = the image whose caption starts with
   the identifier (first full view, not »Ausschnitt«/»Detail«).
3. Articles without identifier entries: each bold caps title opening a
   paragraph in a painting section becomes
   '''{{Entität|ENGELSTURZ|rolle=Deckenbild|titel=Engelsturz|bild=…}}''';
   `bild`/`titel` from the image captioned with that title, else the only
   non-plan image.

Building and painting templates are removed and rebuilt on every run, so they
follow the current captions; a `qid=` or `titel=` already set is carried
over (keyed by role and shown text) — so a hand-fixed titel survives; delete
it to have it rebuilt from a changed caption. Finally every {{Entität}} —
also the persons marked by hand — without `id=` gets a new unique id
(8 characters a-z0-9); an existing id is never changed. The id is the key the
Wikidata extraction notes for each item, and apply_qids.py writes the QID back
by it. Painting templates set by hand elsewhere in a sentence
(a subject phrase) are left alone. Old [[:File:…|A]] links and the former
names {{StructuredData}} and {{DynamicInfoPopover}} are converted. Used by finalize.py; standalone for
a dry run:

    uv run python .claude/skills/clean-cbd-skill/scripts/entities.py FILE.wiki
"""

import re
import secrets
import string
import sys

TPL = "Entität"
_TPL_NAMES = r"(?:Entität|StructuredData|DynamicInfoPopover)"  # old names are migrated
# shown text may contain {{Abk|…}}
_INNER = r"(?:[^{}]|\{\{[^{}]*\}\})*?"
_PARAMS = r"((?:\|(?:rolle|titel|bild|qid|id)=[^|{}]*)*)"
_ANY_TPL_RE = re.compile(r"\{\{" + _TPL_NAMES + r"\|(?:1=)?(" + _INNER + r")" + _PARAMS + r"\}\}")
_OLD_LINK_RE = re.compile(r"\[\[:(?:File|Datei):[^|\]]*\|([^\]]*)\]\]")
_QID_RE = re.compile(r"\|qid=(Q\d+)")
_TITEL_RE = re.compile(r"\|titel=([^|{}]*)")
_ROLLE_RE = re.compile(r"\|rolle=([^|{}]*)")
_ID_RE = re.compile(r"\|id=([a-z0-9]+)")
# every Entität template, for the id pass
_EVERY_TPL_RE = re.compile(r"\{\{Entität\|" + _INNER + r"\}\}")
ROLLEN = ("Bauwerk", "Raum", "Auftraggeber", "Maler", "Stuckateur", "Baumeister",
          "Stecher", "Kistler", "Vergolder", "Person", "Deckenbild")

_IDENT = r"[A-Z]{1,2}(?:<sub>\d+</sub>)?"
_HEAD_IDENT = r"(?:[A-Z]{1,2}(?:<sub>\d+(?:–\d+)?</sub>)?|\d{1,2})"
_HEAD_RE = re.compile(rf"^({_HEAD_IDENT})(?=\s+(?:'''|\(|[A-ZÄÖÜ]))")
_SUB_RE = re.compile(r"(?<![\w:|=])([A-Z]{1,2}<sub>\d+</sub>)(?![\w–-])")
_LINK_OR_TPL_RE = re.compile(r"\[\[[^\]]*\]\]|\{\{(?:[^{}]|\{\{[^{}]*\}\})*\}\}")
_DETAIL_RE = re.compile(r"\b(?:Ausschnitt|Detail|Teilansicht)\b")
_PLAN_RE = re.compile(r"\b(?:Übersicht|Grundriss|Grundriß|Schnitt)\b")
_GALLERY_OPEN_RE = re.compile(r"<gallery\b[^>]*>")
_TITLE_HEAD_RE = re.compile(r"^'''([A-ZÄÖÜ0-9][^'a-zäöüß]{2,})'''(?=\s)")
_BOLD_AFTER_HEAD_RE = re.compile(r"^\s*(?:\(keine Abbildung\)\s*)?'''([^']+)'''")
_NEXT_FIELD_RE = re.compile(r"\s*(?:\bund\b|;)\s*(?=[A-Z]{1,2}(?:<sub>|\s))")
_ABK_RE = re.compile(r"\{\{Abk\|([^|}]*)(?:\|([^|}]*))?[^}]*\}\}")
_NOT_PAINTINGS_RE = re.compile(
    r"^(?:Befund|Quellen|Literatur|Spezialliteratur|Nachrichten in den Quellen|"
    r"Zeichnung|Entwurf|Entwurfszeichnung|.*[Rr]egister|.*Lemmata|Bildmotive|Dank)", re.I)


def _plain(s: str) -> str:
    return _ABK_RE.sub(lambda m: m.group(2) or m.group(1), s)


def _captioned_files(body: str):
    """Yield (file, caption) for every thumb and gallery line."""
    in_gallery = False
    for line in body.splitlines():
        line = line.strip()
        if _GALLERY_OPEN_RE.match(line):
            in_gallery = True
            continue
        if line.startswith("</gallery"):
            in_gallery = False
            continue
        if in_gallery and re.match(r"(?:File|Datei):", line):
            fname, _, caption = line.partition("|")
            yield fname.split(":", 1)[1].strip(), caption.strip()
        elif re.match(r"\[\[(?:File|Datei):", line):
            parts = line.strip("[]").split("|")
            fname = parts[0].split(":", 1)[1].strip()
            caption = parts[-1].strip() if len(parts) > 2 or (
                len(parts) == 2 and parts[1].strip() not in ("thumb", "mini")) else ""
            yield fname, caption


def image_map(body: str) -> dict[str, tuple[str, str]]:
    """identifier → (file, caption without identifier): the first full view,
    an »Ausschnitt«/»Detail« only when the field has no full view."""
    out: dict[str, tuple[str, str, bool]] = {}
    for fname, caption in _captioned_files(body):
        m = re.match(rf"({_IDENT}|\d{{1,2}})(?:\s+|$)", caption)
        if m:
            detail = bool(_DETAIL_RE.search(caption))
            if m.group(1) not in out or (out[m.group(1)][2] and not detail):
                # "Kreuzabnahme und A<sub>1–4</sub> Szenen …" -> "Kreuzabnahme"
                own = _NEXT_FIELD_RE.split(caption[m.end():], 1)[0].strip()
                out[m.group(1)] = (fname, own, detail)
    return {k: (v[0], v[1]) for k, v in out.items()}


def _sd(text: str, rolle: str, titel: str | None = None, bild: str | None = None,
        qid: str | None = None, ref: str | None = None) -> str:
    first = f"1={text}" if "=" in _plain(text) else text
    titel = _plain(titel).strip().rstrip(".").strip() if titel else None
    return ("{{" + TPL + f"|{first}|rolle={rolle}"
            + (f"|titel={titel}" if titel else "")
            + (f"|bild={bild}" if bild else "")
            + (f"|qid={qid}" if qid else "")
            + (f"|id={ref}" if ref else "") + "}}")


def _strip(body: str) -> tuple[str, dict[tuple[str, str], dict[str, str]]]:
    """Remove the templates this script makes (all Bauwerk, identifier and
    title-head Deckenbild ones) and old file links; keep their qid and titel
    (keyed by role and shown text)."""
    kept: dict[tuple[str, str], dict[str, str]] = {}

    def unwrap(m: re.Match) -> str:
        text, params = m.group(1), m.group(2)
        rolle = (_ROLLE_RE.search(params) or [None, ""])[1]
        line_start = body.rfind("\n", 0, m.start()) + 1
        title_head = body[line_start:m.start()] == "'''"
        ours = rolle == "Bauwerk" or (rolle == "Deckenbild" and (
            re.fullmatch(_HEAD_IDENT, text) or title_head))
        if not ours:
            # hand-made: keep, but under the current template name
            return re.sub(r"^\{\{" + _TPL_NAMES + r"\|", "{{" + TPL + "|", m.group(0))
        k = kept.setdefault((rolle, text), {})
        for name, rx in (("qid", _QID_RE), ("titel", _TITEL_RE), ("id", _ID_RE)):
            v = rx.search(params)
            if v and v.group(1).strip():
                k.setdefault(name, v.group(1).strip())
        return text

    body = _ANY_TPL_RE.sub(unwrap, body)
    return _OLD_LINK_RE.sub(r"\1", body), kept


def _title_image(body: str, title: str) -> tuple[str | None, str | None]:
    """(file, caption) of the image captioned with this title, else of the
    article's only image that is not a plan."""
    norm = lambda s: re.sub(r"\W+", " ", s).strip().casefold()  # noqa: E731
    files = list(_captioned_files(body))
    for f, cap in files:
        if cap and norm(cap) == norm(title):
            return f, cap
    files = [(f, cap) for f, cap in files if not _PLAN_RE.search(cap)]
    return files[0] if len(files) == 1 else (None, None)


def _entry_title(rest: str) -> str | None:
    """Title of an entry from the text after its identifier."""
    m = _BOLD_AFTER_HEAD_RE.match(rest)
    if m:
        return m.group(1)
    rest = re.sub(r"^\s*\(keine Abbildung\)\s*", "", rest).strip()
    plain = _plain(rest)
    head = plain.split(";", 1)[0]
    if ";" in plain and len(head) <= 80 and ". " not in head:
        return head
    if len(plain) <= 60 and ". " not in plain.rstrip("."):
        return plain
    return None


def _outside_markup(text: str):
    """Yield (offset, chunk) of the parts of a line outside [[…]] / {{…}}."""
    pos = 0
    for m in _LINK_OR_TPL_RE.finditer(text):
        yield pos, text[pos:m.start()]
        pos = m.end()
    yield pos, text[pos:]


def mark_body(body: str) -> str:
    body, kept = _strip(body)
    qid = lambda rolle, text: kept.get((rolle, text), {}).get("qid")  # noqa: E731
    ref = lambda rolle, text: kept.get((rolle, text), {}).get("id")  # noqa: E731
    old_titel = lambda text: kept.get(("Deckenbild", text), {}).get("titel")  # noqa: E731
    images = image_map(body)
    lines = body.split("\n")

    # --- classify lines: section, gallery, skippable -------------------------
    section, in_gallery, info = "", False, []
    for line in lines:
        s = line.strip()
        if _GALLERY_OPEN_RE.match(s):
            in_gallery = True
        skip = in_gallery or not s or s.startswith(("[[File:", "[[Datei:", "{|", "|", "!", "="))
        if in_gallery and s.startswith("</gallery"):
            in_gallery = False
        if re.match(r"^==[^=].*==$", s):
            section = s.strip("= ")
        paint = bool(section) and not _NOT_PAINTINGS_RE.match(section)
        info.append((skip, paint))

    # --- candidates for each painting: (priority, line, start, end, ident) ----
    cand: dict[str, tuple] = {}

    def offer(key, prio, li, start, end):
        c = (prio, li, start, end)
        if key not in cand or c < cand[key]:
            cand[key] = c

    has_ident_heads = False
    for li, line in enumerate(lines):
        skip, paint = info[li]
        if skip:
            continue
        if paint:
            m = _HEAD_RE.match(line)
            if m:
                has_ident_heads = True
                offer(m[1], 0, li, m.start(1), m.end(1))
        for off, chunk in _outside_markup(line):
            for m in _SUB_RE.finditer(chunk):
                if paint:
                    offer(m[1], 1, li, off + m.start(1), off + m.end(1))
                elif m[1] in images:
                    offer(m[1], 2, li, off + m.start(1), off + m.end(1))

    # --- wraps per line: (start, end, replacement) ----------------------------
    wraps: dict[int, list] = {}
    for ident, (prio, li, start, end) in cand.items():
        bild, cap = images.get(ident, (None, None))
        titel = old_titel(ident) or cap or (_entry_title(lines[li][end:]) if prio == 0 else None)
        rep = _sd(ident, "Deckenbild", titel, bild, qid("Deckenbild", ident), ref("Deckenbild", ident))
        wraps.setdefault(li, []).append((start, end, rep))

    if not has_ident_heads:
        seen = set()
        for li, line in enumerate(lines):
            skip, paint = info[li]
            m = _TITLE_HEAD_RE.match(line) if paint and not skip else None
            if m and m[1] not in seen:
                seen.add(m[1])
                bild, cap = _title_image(body, m[1])
                rep = "'''" + _sd(m[1], "Deckenbild", old_titel(m[1]) or cap or m[1], bild,
                                  qid("Deckenbild", m[1]), ref("Deckenbild", m[1])) + "'''"
                wraps.setdefault(li, []).append((0, m.end(), rep))

    # building: first sentence of the first plain paragraph of the body
    for li, line in enumerate(lines):
        if info[li][0] or line.startswith(("'''", "{{", "<")):
            continue
        if info[li][1] or li and any(re.match(r"^==", x) for x in lines[:li]):
            break  # first paragraph is already inside a section: no lead
        m = re.match(r"^([^,;]{3,120}?)(?=[,;]|\s*$)", line)
        if m:
            name = m.group(1).rstrip()
            wraps.setdefault(li, []).append(
                (0, len(name), _sd(name, "Bauwerk", qid=qid("Bauwerk", name), ref=ref("Bauwerk", name))))
        break

    for li, ws in wraps.items():
        line = lines[li]
        for start, end, rep in sorted(ws, reverse=True):
            line = line[:start] + rep + line[end:]
        lines[li] = line
    return assign_ids("\n".join(lines))


def new_id(taken: set[str]) -> str:
    """8 characters a-z0-9, starting with a letter; never reused."""
    while True:
        s = secrets.choice(string.ascii_lowercase) + "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7))
        if s not in taken:
            taken.add(s)
            return s


def assign_ids(body: str) -> str:
    """Give every {{Entität}} without `id=` (automatic or hand-made) a new id.
    Existing ids are never changed — they link the claims of the Wikidata
    extraction to this spot (apply_qids.py)."""
    taken = set(_ID_RE.findall(body))

    def add(m: re.Match) -> str:
        tpl = m.group(0)
        if _ID_RE.search(tpl):
            return tpl
        return tpl[:-2] + f"|id={new_id(taken)}}}}}"

    return _EVERY_TPL_RE.sub(add, body)


def main() -> None:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "src"))
    from articles.helpers import parse_article_file
    for arg in sys.argv[1:]:
        text = open(arg, encoding="utf-8").read()
        _tpl, _f, body = parse_article_file(text)
        new = mark_body(body)
        print(f"== {arg}: {len(image_map(body))} captioned images")
        for a, b in zip(body.split("\n"), new.split("\n")):
            if a != b:
                print(f"  - {a[:110]}\n  + {b[:220]}")


if __name__ == "__main__":
    main()
