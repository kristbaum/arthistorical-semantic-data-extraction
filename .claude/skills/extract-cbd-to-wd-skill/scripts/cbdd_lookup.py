#!/usr/bin/env python3
"""Article context + CbDD (deckenmalerei.eu) lookups for Wikidata extraction.

Subcommands
-----------
  article PATH [PATH ...]   Template data, citation reference, field identifiers,
                            measurements, and the matching CbDD building (with
                            its Wikidata QID and the rooms/paintings CbDD holds
                            below it).
  building NAME [NAME ...]  CbDD buildings whose appellation / alternative name
                            matches NAME (exact first, then substring).
  person NAME [NAME ...]    CbDD people matching NAME ("Johann Baptist Anwander"
                            or "Anwander, Johann"), with QID, GND, and the
                            buildings they are related to (evidence for
                            disambiguation).

Output is JSON on stdout. The CbDD dump is read from the CBDDsync checkout
(default ~/Projects/CBDDsync, override with --cbddsync or $CBDDSYNC_DIR):
sources/entities.json, sources/relations.json, sources/query.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from functools import cache
from pathlib import Path

# Printed volumes of the Corpus der barocken Deckenmalerei in Deutschland on
# Wikidata (all P179 -> Q107174967). Keyed by data/formatted band directory.
# Band 12 is one Wikidata item for both physical parts (continuous pagination).
VOLUMES = {
    "Band01": "Q118117102",
    "Band02": "Q118117169",
    "Band03-1": "Q118117218",
    "Band03-2": "Q118117237",
    "Band04": "Q118117256",
    "Band05": "Q118117284",
    "Band06": "Q118117296",
    "Band07": "Q116077486",
    "Band08": "Q116088082",
    "Band09": "Q116088253",
    "Band10": "Q116105729",
    "Band11": "Q116105732",
    "Band12-1": "Q116117329",
    "Band12-2": "Q116117329",
    "Band13": "Q116127930",
    "Band14": "Q118117417",
}

# Room abbreviations / words used in the articles -> (label, Wikidata class).
# None = resolve at runtime (search_items) or fall back to room Q180516.
ROOM_TERMS = {
    r"\bLHs\b": ("Langhaus", "Q607600"),
    r"\bAR\b": ("Altarraum", "Q207707"),
    r"\bChor\b": ("Chor", "Q207707"),
    r"\bEmpore\b": ("Empore", "Q648224"),
    r"\bSakristei\b": ("Sakristei", None),
    r"\bVorhalle\b": ("Vorhalle", None),
    r"\bKapelle\b": ("Kapelle", "Q2196917"),
    r"\bTreppenhaus\b": ("Treppenhaus", "Q2451751"),
    r"\bFestsaal\b": ("Festsaal", "Q31838271"),
    r"\b(?:Kaiser|Fürsten|Bibliotheks|Kapitel)?[Ss]aal\b": ("Saal", None),
    r"\bQuerhaus\b": ("Querhaus", None),
    r"\bVierung\b": ("Vierung", None),
    r"\bOratorium\b": ("Oratorium", None),
}

IDENT_RE = re.compile(
    r"^(?:\[\[:File:[^|\]]+\|)?"  # optional image link wrapper
    r"([A-Z]{1,2}(?:<sub>[^<]+</sub>)?)"  # identifier: A, B, W<sub>1</sub>, A<sub>1–4</sub>
    r"(?:\]\])?\s+"
    r"(?:\(keine Abbildung\)\s*)?"
    r"(?:'''(.+?)''')?"
)
ENTITY_RE = re.compile(
    r"\{\{Entität\|(?:1=)?((?:[^{}]|\{\{[^{}]*\}\})*?)((?:\|(?:rolle|titel|bild|qid|id)=[^|{}]*)*)\}\}")
ABK_RE = re.compile(r"\{\{Abk\|([^|}]*)(?:\|([^|}]*))?[^}]*\}\}")


def entities(text: str) -> list[dict]:
    """The {{Entität}} templates of a cleaned article: id (the key to note as
    the item's "ref" in the claims file), rolle, text, titel, bild, qid."""
    out = []
    for m in ENTITY_RE.finditer(text):
        e = {"text": ABK_RE.sub(lambda a: a.group(2) or a.group(1), m.group(1))}
        e.update(dict(re.findall(r"\|(rolle|titel|bild|qid|id)=([^|{}]*)", m.group(2))))
        out.append(e)
    return out
HEADING_RE = re.compile(r"^==+\s*(.+?)\s*==+\s*$")
LABEL_RE = re.compile(r"^'''([^']+?):?'''\s*:?\s*(.*)$")


def cbddsync_dir(arg: str | None) -> Path:
    return Path(arg or os.environ.get("CBDDSYNC_DIR") or Path.home() / "Projects" / "CBDDsync")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.replace("ß", "ss")
    return re.sub(r"[^\w]+", " ", s).strip()


class CbDD:
    def __init__(self, root: Path):
        src = root / "sources"
        for f in ("entities.json", "relations.json", "query.csv"):
            if not (src / f).exists():
                sys.exit(f"missing {src / f} (run setup.py in CBDDsync, or pass --cbddsync)")
        self.E = {e["ID"]: e for e in json.loads((src / "entities.json").read_text(encoding="utf-8"))}
        self.qid = {
            r["deckenmalerei_eu_ID"]: r["item"].rsplit("/", 1)[1]
            for r in csv.DictReader((src / "query.csv").open(encoding="utf-8"))
        }
        self.children: dict[str, list[str]] = {}
        self.parent: dict[str, list[str]] = {}
        self.rels: dict[str, list[tuple[str, str]]] = {}  # object -> [(type, actor)]
        self.actor_rels: dict[str, list[tuple[str, str]]] = {}  # actor -> [(type, object)]
        skip = {"LEAD_RESOURCE", "DOCUMENTS", "IMAGE", "RIGHTS_HOLDERS", "ORIGINATORS", "AUTHORS"}
        for r in json.loads((src / "relations.json").read_text(encoding="utf-8")):
            if r["relDir"] != "->" or r["sType"] in skip:
                continue
            a, b = r["ID"], r["relTar"]
            if r["sType"] == "PART":
                self.children.setdefault(a, []).append(b)
                self.parent.setdefault(b, []).append(a)
            else:
                self.rels.setdefault(a, []).append((r["sType"], b))
                self.actor_rels.setdefault(b, []).append((r["sType"], a))

    def card(self, i: str) -> dict:
        e = self.E.get(i, {})
        out = {
            "cbdd_id": i,
            "type": e.get("sType"),
            "appellation": e.get("appellation"),
            "qid": self.qid.get(i),
            "url": f"https://www.deckenmalerei.eu/{i}",
        }
        for k in ("verbaleDating", "alternativeNames", "addressLocality", "functions", "gender"):
            if e.get(k):
                out[k] = e[k]
        if e.get("normdata"):
            out["normdata"] = e["normdata"]
        return out

    def tree(self, i: str, depth: int = 0) -> dict:
        c = self.card(i)
        actors = [
            {"role": t, **{k: v for k, v in self.card(a).items() if k in ("appellation", "qid", "cbdd_id")}}
            for t, a in self.rels.get(i, [])
        ]
        if actors:
            c["actors"] = actors
        if depth < 6:
            kids = [self.tree(k, depth + 1) for k in self.children.get(i, [])]
            if kids:
                c["parts"] = kids
        return c

    def buildings(self, name: str) -> list[dict]:
        n = norm(name)
        exact, partial = [], []
        for e in self.E.values():
            if e.get("sType") not in ("OBJECT_BUILDING", "OBJECT_BUILDING_DIVISION", "OBJECT_ENSEMBLE"):
                continue
            names = [e.get("appellation", "")] + e.get("alternativeNames", [])
            nn = [norm(x) for x in names if x]
            if n in nn:
                exact.append(e["ID"])
            elif any(n in x for x in nn):
                partial.append(e["ID"])
        return [dict(self.card(i), match="exact") for i in exact] + [
            dict(self.card(i), match="substring") for i in partial[:15]
        ]

    def people(self, name: str) -> list[dict]:
        if "," in name:
            surname, given = [x.strip() for x in name.split(",", 1)]
        else:
            parts = name.split()
            surname, given = parts[-1], " ".join(parts[:-1])
        ns, ng = norm(surname), norm(given).split()
        hits = []
        for e in self.E.values():
            if e.get("sType") not in ("ACTOR_PERSON", "ACTOR_SOCIETY"):
                continue
            for cand in [e.get("appellation", "")] + e.get("alternativeNames", []):
                if "," in cand:
                    cs, cg = [norm(x) for x in cand.split(",", 1)]
                else:
                    p = norm(cand).split()
                    cs, cg = (p[-1] if p else ""), " ".join(p[:-1])
                if cs != ns:
                    continue
                score = "surname"
                if ng and cg.split() and cg.split()[0] == ng[0]:
                    score = "surname+first-given"
                if ng and cg == " ".join(ng):
                    score = "full"
                c = self.card(e["ID"])
                c["match"] = score
                objs = []
                for t, o in self.actor_rels.get(e["ID"], []):
                    b = self.host_building(o)
                    objs.append(f"{t}: {self.E.get(b, {}).get('appellation', '?')}")
                c["works"] = sorted(set(objs))[:12]
                hits.append(c)
                break
        order = {"full": 0, "surname+first-given": 1, "surname": 2}
        return sorted(hits, key=lambda c: order[c["match"]])

    def host_building(self, i: str) -> str:
        seen = set()
        while i not in seen:
            seen.add(i)
            if self.E.get(i, {}).get("sType") == "OBJECT_BUILDING":
                return i
            ps = self.parent.get(i)
            if not ps:
                return i
            i = ps[0]
        return i


def split_sections(body: str) -> dict[str, str]:
    sec, cur = {"_intro": []}, "_intro"
    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if m:
            cur = m.group(1)
            sec.setdefault(cur, [])
            continue
        sec[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in sec.items()}


def labelled(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = LABEL_RE.match(line.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def article(path: Path, db: CbDD | None) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
    try:
        from articles.helpers import parse_article_file
    except ImportError:  # running outside the repo
        parse_article_file = None
    text = path.read_text(encoding="utf-8")
    ents = entities(text)
    # {{Entität|A|rolle=…|bild=…}} -> A (the markup from the cleaning step)
    text = ENTITY_RE.sub(r"\1", text)
    if parse_article_file:
        _, fields, body = parse_article_file(text)
    else:
        m = re.search(r"\{\{Artikel(.*?)\n\}\}\n", text, re.S)
        fields = dict(re.findall(r"^\|(\w+)=(.*)$", m.group(1), re.M)) if m else {}
        body = text[m.end():] if m else text
    band_dir = path.parent.name
    von, bis = fields.get("Originalseitenvon", ""), fields.get("Originalseitenbis", "")
    pages = von if (not bis or bis == von) else f"{von}-{bis}"
    vol = VOLUMES.get(band_dir)
    sections = split_sections(body)
    lab = {}
    for k in ("_intro", *[s for s in sections if "Befund" in s]):
        lab.update(labelled(sections.get(k, "")))

    desc_key = next((s for s in sections if re.search(r"Beschreib|Bildabfolg|Ikonograph", s)), None)
    idents = []
    for line in (sections.get(desc_key, "") if desc_key else "").splitlines():
        m = IDENT_RE.match(line.strip())
        if m and not line.strip().startswith("[[File:"):
            idents.append({"id": m.group(1), "title": (m.group(2) or "").strip()})

    measures = re.findall(r"^\|\s*([^|\n]+?)\s*\|\|\s*([^|\n]*?)\s*\|\|\s*([^|\n]+?)\s*$", body, re.M)
    rooms = {}
    for pat, (label, cls) in ROOM_TERMS.items():
        n = len(re.findall(pat, body))
        if n:
            rooms[label] = {"class": cls, "mentions": n}

    out = {
        "file": str(path),
        "lemma": fields.get("Lemma") or path.stem,
        "meta": fields.get("Meta", ""),
        "band_dir": band_dir,
        "typ": fields.get("Typ"),
        "ort": fields.get("Ort"),
        "authors": [fields[k] for k in sorted(fields) if k.startswith("AutorIn") and fields[k]],
        "volume_qid": vol,
        "pages": pages,
        "reference": f"S248\t{vol}\tS304\t\"{pages}\"" if vol and pages else None,
        "labelled_fields": lab,
        "description_section": desc_key,
        "identifiers": idents,
        "entities": ents,
        "measurements": [
            {"field": a, "room_height": b, "size": c} for a, b, c in measures if a not in ("Bereich",)
        ],
        "room_terms": rooms,
    }
    if db:
        lemma = out["lemma"]
        segs = [s.strip() for s in lemma.split(",")]
        matches, tried = [], []
        # exact lemma first, then strip trailing ", part" segments for lemmas
        # that are rooms/chapels inside a building
        for k in range(len(segs), 1, -1):
            cand = ", ".join(segs[:k])
            tried.append(cand)
            matches = [m for m in db.buildings(cand) if m["match"] == "exact"]
            if matches:
                break
        out["cbdd_building_lookup"] = {"tried": tried, "matched_on": cand if matches else None}
        out["cbdd_buildings"] = [db.tree(m["cbdd_id"]) for m in matches]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cbddsync", help="path to the CBDDsync checkout")
    ap.add_argument("--no-cbdd", action="store_true", help="article: skip the CbDD dump lookup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("article", "building", "person"):
        sub.add_parser(name).add_argument("args", nargs="+")
    a = ap.parse_args()

    need_db = not (a.cmd == "article" and a.no_cbdd)
    db = CbDD(cbddsync_dir(a.cbddsync)) if need_db else None
    if a.cmd == "article":
        res = [article(Path(p), db) for p in a.args]
    elif a.cmd == "building":
        res = {n: db.buildings(n) for n in a.args}
    else:
        res = {n: db.people(n) for n in a.args}
    json.dump(res if len(a.args) > 1 or a.cmd != "article" else res[0], sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
