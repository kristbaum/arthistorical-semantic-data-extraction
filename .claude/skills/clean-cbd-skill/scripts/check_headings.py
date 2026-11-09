#!/usr/bin/env python3
"""Check headings and labels of an article (rules 3.8, 3.9, 3.14).

Only formatting is ever changed — no section is renamed, reordered or added.

Fixed with --apply (deterministic, safe):
  ENTRY   a painting entry that came out as a heading:
            == A AUFFINDUNG DER GEBEINE DES SELIGEN RATHARD ==
          -> paragraph  A '''AUFFINDUNG DER GEBEINE DES SELIGEN RATHARD'''
          (identifiers A, A<sub>2</sub>, EB<sub>1</sub>, 4, a; the text after
          the heading stays the entry's text, joined onto the same line).
  LABEL   an inline label without bold or colon at the start of a line:
            Erhaltungszustand: …        -> '''Erhaltungszustand:''' …
            '''Maße''' …                -> '''Maße:''' …

Reported only (judgment — fix with an edit, log in the report):
  LEFTOVER  a heading left over from splitting the book into articles: the
            last non-empty line of the body (the next article's place or
            title: »HAGNBERG«, »LUSTHAUS IM NACHMALIGEN HOFGARTEN«), a book-part
            title (»EINGEMEINDETE VORORTE«, »ANHANG VERLORENE DECKENMALEREIEN«),
            or a caps heading before the first paragraph. Remove it; text after
            it that belongs to the next article is logged as FOREIGN, not
            deleted.
  CAPS      a caps heading inside the article: a running header (place name,
            »STADT FREISING«, »WIES BEI STEINGADEN«) -> remove; or the title of
            a group of entries (»PAULUSFOLGE«, »GLORREICHER ROSENKRANZ«) ->
            === Paulusfolge === (title case, rule 3.4).
  EMPTY     a known section with no text at the end of the article.
  NOLABEL   a label word without bold and colon (»Maße 9,10 × 6,00«) —
            probably the label, check and fix by hand.
  SECTION   (only with --sections) a section name outside the known variants (see the normalisation
            table in the deckenmalerei-lab skill) — usually fine, sometimes an
            OCR slip (»Ikonologi«) to correct.

Usage:
    uv run python .claude/skills/clean-cbd-skill/scripts/check_headings.py FILE.wiki [...] [--apply] [--sections]
"""

import re
import sys
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

_HEADING_RE = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$")
_ENTRY_HEADING_RE = re.compile(
    r"^(=+)\s*((?:[A-Z]{1,2}(?:<sub>[^<]+</sub>|\d+(?:[–-]\d+)?)?|\d{1,2}|[a-z](?:[–-][a-z])?))"
    r"\s+(.+?)\s*\1\s*$")
_CAPS_RE = re.compile(r"^[^a-zäöüß]*[A-ZÄÖÜ]{3}[^a-zäöüß]*$")
# an entry title: starts with a caps word (a lower-case tail like »(Act 1,9–11)« is fine)
_CAPS_START_RE = re.compile(r"^(?:[A-ZÄÖÜ][A-ZÄÖÜ.\-]+\b|ST\.)(?:\s+[A-ZÄÖÜ0-9][^\s]*)*")

LEAD_LABELS = ("Patrozinium", "Zur Geschichte", "Zum Bauwerk", "Auftraggeber",
               "Autor und Entstehungszeit")
BEFUND_LABELS = ("Träger der Deckenmalerei", "Rahmen", "Technik", "Maße",
                 "Erhaltungszustand und Restaurierungen", "Erhaltungszustand")
_LABELS = "|".join(re.escape(x) for x in sorted(LEAD_LABELS + BEFUND_LABELS, key=len, reverse=True))
_PLAIN_COLON_RE = re.compile(rf"^({_LABELS}):\s*")
_BOLD_NOCOLON_RE = re.compile(rf"^'''({_LABELS})'''\s*:?\s*")
_NOLABEL_RE = re.compile(rf"^({_LABELS})\s+(?=[\dA-ZÄÖÜ])")

# section names seen in the corpus (normalisation table); anything else is reported
KNOWN_SECTIONS = re.compile(
    r"^(?:Befund|Beschreibung(?: und Ikonographie| und Ikonologie)?|Ikonographie(?: und Ikonologie)?|"
    r"Ikonologie|Zur Ikonologie|Ergänzungen zur Ikonographie|Rekonstruierende Beschreibung(?: und Ikonographie)?|"
    r"Bildabfolge(?: und Inschriften)?|Rekonstruierte Bildabfolge|Rekonstruierende Bildabfolge|"
    r"Darstellungen?|Erste Ausstattung|Zeichnungen?|Entwurf|Entwurfszeichnungen|Quellen und Literatur|"
    r"Literatur(?: zur Ikonographie)?|Nachrichten in den Quellen|Spezialliteratur.*)$")


@lru_cache(maxsize=1)
def place_names() -> frozenset[str]:
    """Upper-case place names of all lemmas — a caps heading that is one is
    a running header or the neighbour article's place."""
    names = set()
    for p in (REPO_ROOT / "data" / "formatted").glob("*/*.wiki"):
        place = re.sub(r"\s*\(.*?\)", "", p.stem.split(",")[0]).strip()
        if len(place) > 3:
            names.add(place.upper())
    return frozenset(names)


SHOW_SECTIONS = "--sections" in sys.argv


def check_body(body: str) -> tuple[str, list[str]]:
    """Return (body with the safe fixes, report lines)."""
    lines = body.split("\n")
    out, report = [], []
    # index after which only headings, images and comments follow
    tail_start = len(lines)
    for k in range(len(lines) - 1, -1, -1):
        s = lines[k].strip()
        if s and not _HEADING_RE.match(s) and not s.startswith(("[[File:", "[[Datei:", "<!--")):
            break
        tail_start = k
    first_para = next((i for i, l in enumerate(lines) if l.strip() and not _HEADING_RE.match(l)), len(lines))
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        m = _ENTRY_HEADING_RE.match(s)
        if m and (_CAPS_START_RE.match(m.group(3)) or m.group(1) != "=="):
            # entry heading -> paragraph; join the next text line onto it
            head = f"{m.group(2)} '''{m.group(3)}'''"
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = lines[j].strip() if j < len(lines) else ""
            if nxt and not _HEADING_RE.match(nxt) and not nxt.startswith(("[[", "{|", "|", "*", "<")):
                out.append(f"{head} {nxt}")
                i = j + 1
            else:
                out.append(head)
                i += 1
            report.append(f"ENTRY   L{i}: {s[:70]} -> {head[:70]}")
            continue
        h = _HEADING_RE.match(s)
        if h:
            title = h.group(2)
            caps = bool(_CAPS_RE.match(title))
            place = any(title.upper().startswith(pn) for pn in place_names())
            if i >= tail_start and KNOWN_SECTIONS.match(title):
                report.append(f"EMPTY   L{i + 1}: {s[:70]} — section without content at the end; "
                              "is its text missing (check the OCR) or does it belong elsewhere?")
            elif i >= tail_start or ((caps or place) and i < first_para):
                report.append(f"LEFTOVER L{i + 1}: {s[:70]} — left over from splitting? remove; "
                              "text after it that belongs to the next article -> FOREIGN")
            elif caps:
                hint = "running header (place name) -> remove" if place else \
                       "running header -> remove, or group title -> === Title case ==="
                report.append(f"CAPS    L{i + 1}: {s[:70]} — {hint}")
            elif SHOW_SECTIONS and len(h.group(1)) == 2 and not KNOWN_SECTIONS.match(title):
                report.append(f"SECTION L{i + 1}: {s[:70]} — not a known variant (room heading? OCR slip?)")
            out.append(line)
            i += 1
            continue
        new = _PLAIN_COLON_RE.sub(lambda m: f"'''{m.group(1)}:''' ", line, count=1)
        if new == line:
            new = _BOLD_NOCOLON_RE.sub(lambda m: f"'''{m.group(1)}:''' ", line, count=1)
        if new != line:
            report.append(f"LABEL   L{i + 1}: {line[:50]} -> {new[:50]}")
        elif _NOLABEL_RE.match(line):
            report.append(f"NOLABEL L{i + 1}: {line[:70]} — label without bold and colon?")
        out.append(new)
        i += 1
    return "\n".join(out), report


def main() -> None:
    args = [a for a in sys.argv[1:] if a not in ("--apply", "--sections")]
    if not args:
        sys.exit(__doc__)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from articles.helpers import parse_article_file
    for arg in args:
        path = Path(arg)
        text = path.read_text(encoding="utf-8")
        tpl, fields, body = parse_article_file(text)
        if fields.get("Meta", "").strip():
            print(f"[skip: register/list page] {path}")
            continue
        new_body, report = check_body(body)
        print(f"[{len(report)}] {path}")
        for line in report:
            print("  " + line)
        if "--apply" in sys.argv and new_body != body:
            path.write_text(tpl.rstrip("\n") + "\n\n" + new_body.strip("\n") + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
