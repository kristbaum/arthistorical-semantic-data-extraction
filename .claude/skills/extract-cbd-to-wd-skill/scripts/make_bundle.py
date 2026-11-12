#!/usr/bin/env python3
"""CbDD drafts -> one claim bundle (version 2) per band.

What this script knows is the Corpus der barocken Deckenmalerei; everything
generic (checks, evidence, routing, links, batches, games) is the
`claim-bundle` tool of the como-game-creator skill. Per band it

  - reads the drafts (<out>/drafts/<id>.json, references/draft-format.md)
    and the cleaned articles: pages from {{Artikel}}, the lab page URL, the
    {{Entität|…|id=…}} refs (checked: exist, used once)
  - writes the source texts: texts/<id>.txt (the cleaned article as plain
    text, markup of the CbDD templates resolved; quotes are checked against
    it) and texts/<id>.lab.txt (the older text on deckenmalerei-lab, which
    the passage links must point into)
  - expands the CbDD shorthands: painting/room descriptions from field and
    cycle, default classes, P31 + P1343 (P304 pages) on every entity to
    create or reconcile, P1343 + P1810 on the main building, P527 for every
    P361, P155/P156 for sequences, P1639 for pairs, P1932 from named_as
  - turns hedged attributions and dates of paintings into certainty
    choices (belegt / zugeschrieben / vermutlich / wahrscheinlich; so
    datiert / um / vermutlich), unless the draft gives a route
  - adds the reference (volume P248 + pages P304) to every claim, the
    Iconclass text to P1257 values, the properties table (labels and
    datatypes from Wikidata)

Then run the como-game-creator tools on <out>/bundle.json:
  claim-bundle verify  bundle.json --write
  claim-bundle route   bundle.json --policy <skill>/references/policy.json --write
  claim-bundle anchors bundle.json --write
  claim-bundle check   bundle.json

Usage:
  make_bundle.py --articles data/cleaned-with-skill-v2/Band01 --out data/claim-bundles/Band01 [--refresh]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_quotes import plain  # noqa: E402

UA = "cbdd-extract/3.0 (claim bundle helper; deckenmalerei corpus)"
WD_API = "https://www.wikidata.org/w/api.php"
LAB = "https://deckenmalerei-lab.badw.de"
VOLUMES = {
    "Band01": ("Q118117102", "1"), "Band02": ("Q118117169", "2"), "Band03-1": ("Q118117218", "3/1"),
    "Band03-2": ("Q118117237", "3/2"), "Band04": ("Q118117256", "4"), "Band05": ("Q118117284", "5"),
    "Band06": ("Q118117296", "6"), "Band07": ("Q116077486", "7"), "Band08": ("Q116088082", "8"),
    "Band09": ("Q116088253", "9"), "Band10": ("Q116105729", "10"), "Band11": ("Q116105732", "11"),
    "Band12-1": ("Q116117329", "12"), "Band12-2": ("Q116117329", "12"), "Band13": ("Q116127930", "13"),
    "Band14": ("Q118117417", "14"),
}
KINDS = {"building", "room", "painting", "person", "other"}
P31_DEFAULT = {"painting": "Q1181933"}
CERTAINTY_PROPS = {"P1480", "P5102"}
HEDGE = re.compile(r"\b(wohl|vermutlich|wahrscheinlich|vielleicht|möglicherweise|dürfte)\b|zuschreib|zugeschrieben",
                   re.I)
# The corpus's certainty vocabulary (references/data-model.md, "Certainty"), as game options.
CHOICES = {
    "P170": [
        {"label": "belegt", "description": "Signatur, Rechnung oder Archivquelle nennen den Maler", "qualifiers": []},
        {"label": "zugeschrieben", "description": "nach Stil oder Vergleich",
         "qualifiers": [{"property": "P5102", "value": "Q230768"}]},
        {"label": "vermutlich", "description": "»wohl«, »vermutlich«",
         "qualifiers": [{"property": "P1480", "value": "Q18122778"}]},
        {"label": "wahrscheinlich", "description": "»wahrscheinlich«",
         "qualifiers": [{"property": "P1480", "value": "Q56644435"}]},
    ],
    "P571": [
        {"label": "so datiert", "description": "Jahreszahl, Signatur oder Rechnung", "qualifiers": []},
        {"label": "um", "description": "»um«, »in zeitlicher Nähe«",
         "qualifiers": [{"property": "P1480", "value": "Q5727902"}]},
        {"label": "vermutlich", "description": "»wohl«, »vermutlich«",
         "qualifiers": [{"property": "P1480", "value": "Q18122778"}]},
    ],
}
QID_RE = re.compile(r"^Q\d+$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def slugify(s: str) -> str:
    s = s.lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def http_json(url: str, params: dict | None = None) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001 - retry any network hiccup
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def lab_url(lemma: str) -> str:
    return f"{LAB}/index.php/" + urllib.parse.quote(lemma.replace(" ", "_"), safe="(),")


def lab_text(lemma: str) -> str | None:
    d = http_json(f"{LAB}/api.php", {"action": "query", "prop": "revisions", "rvprop": "content",
                                     "rvslots": "main", "format": "json", "formatversion": "2", "titles": lemma})
    page = d.get("query", {}).get("pages", [{}])[0]
    return None if page.get("missing") else plain(page["revisions"][0]["slots"]["main"]["content"])


def parse_value(v, resolve):
    """Draft shorthand -> typed bundle value."""
    if isinstance(v, dict):
        return {**v, "id": resolve(v["id"])} if v.get("type") == "item" else dict(v)
    if v in ("somevalue", "novalue"):
        return {"type": v}
    m = re.match(r"^([+-]\d{4,}-\d\d-\d\dT00:00:00Z)/(\d+)$", v)
    if m:
        return {"type": "time", "time": m[1], "precision": int(m[2])}
    m = re.match(r"^(-?\d+(?:\.\d+)?)U(\d+)$", v)
    if m:
        return {"type": "quantity", "amount": m[1], "unit": f"Q{m[2]}"}
    m = re.match(r'^([a-z-]+):"(.*)"$', v, re.S)
    if m:
        return {"type": "monolingualtext", "text": m[2], "lang": m[1]}
    m = re.match(r'^"(.*)"$', v, re.S)
    if m:
        return {"type": "string", "value": m[1]}
    return {"type": "item", "id": resolve(v)}


def canon(v: dict) -> str:
    return json.dumps({k: v[k] for k in sorted(v) if k not in ("label", "link")}, sort_keys=True, ensure_ascii=False)


class Builder:
    def __init__(self, band: str, articles: Path, out: Path, refresh: bool):
        self.band, self.articles, self.out, self.refresh = band, articles, out, refresh
        self.volume, self.vol_no = VOLUMES[band]
        self.sources: dict[str, dict] = {}
        self.entities: dict[str, dict] = {}
        self.entity_article: dict[str, str] = {}
        self.claims: list[dict] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.refs_used: dict[str, str] = {}
        self.ref_rows: list[tuple[str, str, str, str]] = []
        self.arts: dict[str, dict] = {}
        self.cache_path = out / "cache.json"
        self.cache = json.loads(self.cache_path.read_text(encoding="utf-8")) if self.cache_path.exists() else {}
        self.cache.setdefault("props", {})
        self.cache.setdefault("ic", {})

    # -- articles ----------------------------------------------------------

    def load(self, draft_path: Path) -> None:
        d = json.loads(draft_path.read_text(encoding="utf-8"))
        art = d.get("id") or draft_path.stem
        if not ID_RE.match(art):
            self.errors.append(f"{draft_path.name}: id {art!r} must be lowercase a-z0-9-")
            return
        lemma = d["lemma"]
        wiki = (self.articles / f"{lemma}.wiki").read_text(encoding="utf-8")
        tpl = dict(re.findall(r"^\|(\w+)=(.*)$", wiki.split("}}", 1)[0], re.M))
        von, bis = tpl["Originalseitenvon"], tpl.get("Originalseitenbis") or ""
        pages = von if bis in ("", von) else f"{von}-{bis}"
        texts = self.out / "texts"
        texts.mkdir(parents=True, exist_ok=True)
        (texts / f"{art}.txt").write_text(plain(wiki) + "\n", encoding="utf-8")
        lab_file = texts / f"{art}.lab.txt"
        if self.refresh or not lab_file.exists():
            lab = lab_text(lemma)
            if lab:
                lab_file.write_text(lab + "\n", encoding="utf-8")
            else:
                self.warnings.append(f"{art}: no lab page for {lemma!r}; links go to the page without anchor")
        src = f"src:{art}"
        self.sources[src] = {
            "label": f"Corpus der barocken Deckenmalerei, Bd. {self.vol_no}: {lemma}",
            "url": lab_url(lemma),
            "snaks": [{"property": "P248", "value": self.volume}],
            "text_path": f"texts/{art}.txt",
            **({"anchor_text_path": f"texts/{art}.lab.txt"} if lab_file.exists() else {}),
        }
        self.arts[art] = {"lemma": lemma, "pages": pages, "src": src, "draft": d,
                          "refs": set(re.findall(r"\|id=([a-z0-9]{8})\b", wiki))}

    def eid(self, art: str, key: str) -> str:
        return key if key.startswith("_:") else f"_:{art}:{key}"

    def resolver(self, art: str, keys: set[str]):
        def resolve(x: str) -> str:
            if QID_RE.match(x) or x.startswith("_:"):
                return x
            if x in keys:
                return self.eid(art, x)
            self.errors.append(f"{art}: unknown item key {x!r}")
            return x
        return resolve

    # -- entities ----------------------------------------------------------

    def add_entities(self, art: str) -> None:
        a = self.arts[art]
        lemma = a["lemma"]
        resolve = self.resolver(art, set(a["draft"]["entities"]))
        for key, e in a["draft"]["entities"].items():
            eid = self.eid(art, key)
            e = dict(e)
            kind, status = e.get("kind"), e.get("status")
            if kind not in KINDS:
                self.errors.append(f"{art}/{key}: kind {kind!r} not in {sorted(KINDS)}")
            ref, main = e.pop("ref", None), e.pop("main", False)
            p31 = e.pop("p31", None) or P31_DEFAULT.get(kind)
            field, cycle = e.pop("field", None), e.pop("cycle", None)
            if field and field.startswith("W") and p31 == "Q1181933":
                p31 = "Q219423"
            if ref:
                if ref not in a["refs"]:
                    self.errors.append(f"{art}/{key}: ref {ref} not in the article")
                if self.refs_used.get(ref, eid) != eid:
                    self.errors.append(f"{art}/{key}: ref {ref} already used by {self.refs_used[ref]}")
                self.refs_used[ref] = eid
                self.ref_rows.append((eid, art, lemma, ref))
            out = {k: v for k, v in e.items() if k not in ("candidates", "facts")}
            out["source"] = a["src"]
            if status in ("create", "reconcile"):
                if not out.get("descriptions"):
                    out["descriptions"] = self.generated_desc(kind, field, cycle, lemma)
                if status == "create":
                    out.setdefault("route", "direct")
                    if kind in ("painting", "room"):
                        out.setdefault("route_reason", (
                            "Paintings and rooms of the printed corpus have no Wikidata items yet; the building's "
                            "P527 and items with P276/P361 = building list none for it. Label and description "
                            "come from the article's structure."))
            if e.get("candidates") is not None:
                out["candidates"] = [self.candidate(c) for c in e["candidates"]]
            if e.get("facts"):
                out["facts"] = [{"property": f["property"], "value": parse_value(f["value"], resolve)}
                                for f in e["facts"]]
            if eid in self.entities:
                prev = self.entities[eid]
                for k in ("kind", "status", "qid"):
                    if prev.get(k) != out.get(k):
                        self.errors.append(f"{eid}: {k} differs between {self.entity_article[eid]} and {art}")
                continue
            self.entities[eid] = out
            self.entity_article[eid] = art
            if status in ("create", "reconcile") and p31:
                self.bookkeeping(art, eid, "P31", p31, out, f"Class from the article's structure ({kind}).")
            if status in ("create", "reconcile") or main:
                quals = [{"property": "P304", "value": {"type": "string", "value": a["pages"]}}]
                if main:
                    quals.append({"property": "P1810", "value": {"type": "string", "value": lemma}})
                self.bookkeeping(art, eid, "P1343", self.volume, out,
                                 "The printed volume that describes it, pages from the article header.", quals)

    @staticmethod
    def generated_desc(kind, field, cycle, lemma) -> dict:
        if kind == "painting":
            fid = f" {field}" if field else ""
            wall = bool(field and field.startswith("W"))
            de, en = ("Wandbild", "wall painting") if wall else ("Deckenbild", "ceiling painting")
            cde = f" der Folge »{cycle}«" if cycle else ""
            cen = f" of the series “{cycle}”" if cycle else ""
            return {"de": f"{de}{fid}{cde} in {lemma}", "en": f"{en}{fid}{cen} in {lemma}"}
        if kind == "room":
            return {"de": f"Raum in {lemma}", "en": f"room in {lemma}"}
        return {}

    @staticmethod
    def candidate(c) -> dict:
        """Draft candidates are QIDs or {qid|id, reason}; `claim-bundle verify` fills names."""
        if isinstance(c, str):
            c = {"id": c}
        qid = c.get("id") or c.get("qid")
        out = {"id": qid, "name": c.get("name") or qid, "match": False}
        for k in ("description", "reason", "evidence", "score"):
            if c.get(k):
                out[k] = c[k]
        return out

    def bookkeeping(self, art, subject, prop, value, ent, reason, quals=None) -> None:
        c = {"subject": subject, "property": prop, "value": {"type": "item", "id": value},
             "qualifiers": quals or [], "extraction": "field", "route_reason": reason, "_art": art}
        hint = ent.get("hint") or ent.get("quote")
        if hint and ent["status"] != "match":
            c["hint"] = f"{(ent.get('labels') or {}).get('de', '')}: {hint}"
        if ent["status"] == "reconcile":
            c.update(only_if_created=True, route="curator", route_reason=reason + " Only written if it is created.")
        elif ent["status"] == "create":
            c["route"] = ent.get("route", "direct")
        if prop == "P1343":
            c["_no_ref"] = True  # it is the source itself
        self.claims.append(c)

    # -- claims ------------------------------------------------------------

    def add_claims(self, art: str) -> None:
        a = self.arts[art]
        resolve = self.resolver(art, set(a["draft"]["entities"]))
        for raw in a["draft"]["claims"]:
            if "seq" in raw:
                ids = [resolve(k) for k in raw["seq"]]
                for x, y in zip(ids, ids[1:]):
                    self.struct(art, x, "P156", y, "Reading order of the corpus identifiers.")
                    self.struct(art, y, "P155", x, "Reading order of the corpus identifiers.")
                continue
            if "pair" in raw:
                x, y = (resolve(k) for k in raw["pair"])
                self.struct(art, x, "P1639", y, "Companion fields of the article.")
                self.struct(art, y, "P1639", x, "Companion fields of the article.")
                continue
            subjects = raw["subject"] if isinstance(raw["subject"], list) else [raw["subject"]]
            quals = raw.get("qualifiers") or []
            if isinstance(quals, dict):
                quals = [{"property": p, "value": v} for p, v in quals.items()]
            quals = [{"property": q["property"], "value": parse_value(q["value"], resolve)} for q in quals]
            if raw.get("named_as"):
                quals.append({"property": "P1932", "value": {"type": "string", "value": raw["named_as"]}})
            for s in subjects:
                c = {"subject": resolve(s), "property": raw["property"],
                     "value": parse_value(raw["value"], resolve), "qualifiers": [dict(q) for q in quals],
                     "_art": art}
                for k in ("route", "route_reason", "extraction", "quote", "hint", "game", "only_if_created",
                          "choices"):
                    if k in raw:
                        c[k] = raw[k]
                if raw.get("structural"):
                    c.setdefault("extraction", "field")
                self.certainty_choices(c)
                self.claims.append(c)
                if raw["property"] == "P361" and c["value"]["type"] == "item":
                    self.struct(art, c["value"]["id"], "P527", c["subject"], "Inverse of P361 (part of).")

    def certainty_choices(self, c: dict) -> None:
        """A hedged attribution or date of a painting: players choose the
        certainty, the model's qualifier is not written."""
        if c.get("route") or c.get("choices") or c["property"] not in CHOICES:
            return
        if (self.entities.get(c["subject"]) or {}).get("kind") != "painting":
            return
        if c["property"] == "P571" and c["value"].get("precision") != 9:
            return
        certainty = [q for q in c["qualifiers"] if q["property"] in CERTAINTY_PROPS]
        other = [q for q in c["qualifiers"] if q["property"] not in CERTAINTY_PROPS | {"P1932"}]
        if other or not (certainty or HEDGE.search(c.get("quote") or "")):
            return
        c["qualifiers"] = [q for q in c["qualifiers"] if q["property"] not in CERTAINTY_PROPS]
        c["choices"] = json.loads(json.dumps(CHOICES[c["property"]]))

    def struct(self, art, s, p, v, reason) -> None:
        self.claims.append({"subject": s, "property": p, "value": {"type": "item", "id": v}, "qualifiers": [],
                            "extraction": "field", "route_reason": reason, "_art": art})

    # -- finishing ---------------------------------------------------------

    def finish(self) -> None:
        seen: set[str] = set()
        out = []
        for c in self.claims:
            a = self.arts[c["_art"]]
            if not c.pop("_no_ref", False):
                c["reference"] = {"source": a["src"],
                                  "snaks": [{"property": "P304", "value": {"type": "string", "value": a["pages"]}}]}
            if c["property"] == "P1257" and c["value"]["type"] == "string":
                n = c["value"]["value"]
                c["value"].update(label=self.iconclass(n) or n,
                                  link=f"https://iconclass.org/{urllib.parse.quote(n)}")
            for ref in [c["subject"], *([c["value"]["id"]] if c["value"]["type"] == "item" else [])]:
                if ref.startswith("_:") and ref not in self.entities:
                    self.errors.append(f"{c['_art']}: {ref} used in a claim but not defined")
            key = json.dumps([c["subject"], c["property"], canon(c["value"])], ensure_ascii=False)
            subj = c["subject"].split(":")[-1] if c["subject"].startswith("_:") else c["subject"]
            c["id"] = f"{c['_art']}:{subj}:{c['property']}:{hashlib.sha1(key.encode()).hexdigest()[:6]}"
            if c["id"] in seen:
                self.warnings.append(f"{c['id']}: same statement twice, second dropped")
                continue
            seen.add(c["id"])
            if not c.get("route"):
                c.pop("route_reason", None)  # `claim-bundle route` writes the reason with the route
            out.append(c)
        self.claims = out

    def iconclass(self, notation: str) -> str | None:
        if notation not in self.cache["ic"]:
            try:
                d = http_json(f"https://iconclass.org/{urllib.parse.quote(notation)}.json")
                self.cache["ic"][notation] = d.get("txt", {}).get("de") or d.get("txt", {}).get("en")
            except Exception:  # noqa: BLE001 - not cached, retried next run
                self.cache["ic"][notation] = None
        if self.cache["ic"][notation] is None:
            self.errors.append(f"Iconclass notation {notation} not found")
        return self.cache["ic"][notation]

    def properties(self) -> dict:
        used = {"P248", "P304"}
        for c in self.claims:
            used.add(c["property"])
            used |= {q["property"] for q in c["qualifiers"]}
            used |= {q["property"] for ch in c.get("choices") or [] for q in ch["qualifiers"]}
        used |= {f["property"] for e in self.entities.values() for f in e.get("facts") or []}
        missing = sorted(p for p in used if p not in self.cache["props"])
        for i in range(0, len(missing), 50):
            d = http_json(WD_API, {"action": "wbgetentities", "ids": "|".join(missing[i:i + 50]), "format": "json",
                                   "props": "labels|datatype", "languages": "de|en"})
            for pid, e in d.get("entities", {}).items():
                lab = e.get("labels", {})
                self.cache["props"][pid] = {"label": (lab.get("de") or lab.get("en") or {}).get("value", pid),
                                            "datatype": e.get("datatype", "string")}
        return {p: self.cache["props"][p] for p in sorted(used, key=lambda x: int(x[1:]))}

    def bundle(self, band_id: str) -> dict:
        claims = []
        for c in self.claims:
            o = {k: c[k] for k in ("id", "subject", "property", "value")}
            for k in ("qualifiers", "reference", "route", "route_reason", "extraction", "quote", "hint", "game",
                      "only_if_created", "choices"):
                if c.get(k) not in (None, "", False, []):
                    o[k] = c[k]
            claims.append(o)
        return {"format": "claim-bundle", "version": 2, "id": band_id,
                "project": f"CbDD Bd. {self.vol_no} – {len(self.arts)} Artikel ({self.band})",
                "language": "de", "min_statements": 2, "target": {"name": "Wikidata"},
                "sources": self.sources, "properties": self.properties(), "entities": self.entities,
                "claims": claims}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--articles", required=True, type=Path, help="folder with the cleaned <Lemma>.wiki")
    ap.add_argument("--out", required=True, type=Path, help="band folder with drafts/; bundle.json goes here")
    ap.add_argument("--id", help="bundle id (default cbdd-<band>)")
    ap.add_argument("--only", nargs="*", help="draft ids to include (default: all)")
    ap.add_argument("--refresh", action="store_true", help="fetch the lab page texts again")
    a = ap.parse_args()
    band = a.articles.name
    b = Builder(band, a.articles, a.out, a.refresh)
    drafts = sorted((a.out / "drafts").glob("*.json"))
    if a.only:
        drafts = [d for d in drafts if d.stem in a.only]
    for d in drafts:
        b.load(d)
    for art in b.arts:
        b.add_entities(art)
    for art in b.arts:
        b.add_claims(art)
    b.finish()
    bundle = b.bundle(a.id or f"cbdd-{band.lower()}")
    b.cache_path.write_text(json.dumps(b.cache, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (a.out / "refs.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["entity", "article", "lemma", "ref"])
        w.writerows(b.ref_rows)
    status = Counter(e["status"] for e in b.entities.values())
    print(f"{len(b.arts)} articles, {len(b.entities)} entities {dict(status)}, {len(b.claims)} claims "
          f"({sum(1 for c in b.claims if c.get('choices'))} with certainty choices, "
          f"{sum(1 for c in b.claims if not c.get('route'))} to route)")
    for art, info in b.arts.items():
        unused = sorted(info["refs"] - set(b.refs_used))
        if unused:
            print(f"note: {art}: {{{{Entität}}}} refs without entity: {' '.join(unused)}")
    for w_ in b.warnings:
        print("WARNING", w_)
    for e in b.errors:
        print("ERROR", e)
    sys.exit(1 if b.errors else 0)


if __name__ == "__main__":
    main()
