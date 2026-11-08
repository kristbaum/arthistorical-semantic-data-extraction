#!/usr/bin/env python3
"""Turn per-article claims files into checked, triaged Wikidata output.

The LLM writes one claims file per article (<out>/claims/<slug>.json, format
in references/claims-format.md): atomic claims with the verbatim passage each
rests on. Everything after that is deterministic and lives here:

  1. resolve item keys to QIDs or {NEW:…} placeholders, add bookkeeping
     statements (P1343 on every touched item, P1810 on the main subject,
     P527 as inverse of P361)
  2. check every claim: passage verbatim in the article, certainty qualifiers
     backed by cue words in the passage, every QID exists, statement not
     already on the item
  3. triage: direct (QS), game (Como), audit (sample of direct, Como game
     without action), curator (needs a person)
  4. write create.qs, direct.qs, curator.qs, placeholders.tsv, claims.tsv,
     games/<game>.json + .csv, report.md

Labels shown to players are fetched from Wikidata and iconclass.org, never
taken from the claims file. Passage links point at the deckenmalerei-lab page
with a text fragment (#:~:text=…) chosen from text that exists on the lab
page, which still carries the older OCR text.

Usage:
  build.py --articles data/cleaned-with-skill-v2/Band01 --out data/wikidata/Band01
           [--offline] [--audit-rate 0.1]
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
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_quotes import check as quote_check  # noqa: E402
from check_quotes import plain  # noqa: E402

UA = "cbdd-extract/1.0 (Wikidata batch helper; deckenmalerei corpus)"
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
P31_BY_KIND = {"ceiling": "Q1181933", "wall": "Q219423"}
CERTAINTY = {  # qualifier value -> cue regex that must occur in the passage
    "Q18122778": r"\b(wohl|vermutlich|vermutet|dürfte|möglicherweise|vielleicht)\b",
    "Q56644435": r"\bwahrscheinlich\b",
    "Q230768": r"zuschreib|zugeschrieben|Zuschreibung|einzureihen|Übereinstimmung|Ähnlichkeit|stilistisch",
    "Q5727902": r"\b(um|ca\.|etwa|gegen)\s+\d|zeitliche[rn]? Nähe|Umkreis",
}
CERTAINTY_PROPS = {"P1480", "P5102"}
HEDGE = re.compile(r"\b(wohl|vermutlich|wahrscheinlich|vielleicht|möglicherweise|dürfte|offenbar)\b|zuschreib|zugeschrieben|\?\)", re.I)
STRUCTURAL = {"P1343", "P527", "P155", "P156", "P1639", "P31"}
DIRECT_PROPS = {"P31", "P2079", "P186", "P2043", "P2049", "P2048", "P2386", "P825", "P361", "P276", "P527", "P17", "P131",
                "P1684"}
CHOICE_GAMES = {"maler", "datierung"}  # players pick the certainty; hedged passages are fine
GAMES = {"P170": "maler", "P571": "datierung", "P1257": "iconclass", "P180": "motiv", "P5816": "zustand"}
PH_RE = re.compile(r"\{NEW:(person|building|room|painting|other):[a-z0-9][a-z0-9-]*\}")
QID_RE = re.compile(r"^Q\d+$")


# ---------------------------------------------------------------- helpers
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


class Cache:
    """Wikidata entities, Iconclass labels and lab page texts, kept on disk."""

    def __init__(self, path: Path, offline: bool):
        self.path, self.offline = path, offline
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for k in ("wd", "ic", "lab", "labimg"):
            self.data.setdefault(k, {})
        self.paintings: set[str] = set()

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def entities(self, ids: set[str]) -> None:
        missing = sorted(i for i in ids if i not in self.data["wd"])
        if self.offline:
            return
        for i in range(0, len(missing), 50):
            chunk = missing[i:i + 50]
            d = http_json(WD_API, {"action": "wbgetentities", "ids": "|".join(chunk), "format": "json",
                                   "props": "labels|descriptions|claims|info", "languages": "de|en"})
            for qid, e in d.get("entities", {}).items():
                if "missing" in e:
                    self.data["wd"][qid] = {"missing": True}
                    continue
                lab, des = e.get("labels", {}), e.get("descriptions", {})
                claims = {p: sorted({json.dumps(s["mainsnak"].get("datavalue", {}).get("value"), sort_keys=True)
                                     for s in v}) for p, v in e.get("claims", {}).items()}
                self.data["wd"][qid] = {
                    "label": (lab.get("de") or lab.get("en") or {}).get("value", qid),
                    "desc": (des.get("de") or des.get("en") or {}).get("value", ""),
                    "redirect": e.get("id") != qid,
                    "claims": claims,
                }
            time.sleep(0.3)

    def label(self, qid: str) -> str:
        return self.data["wd"].get(qid, {}).get("label", qid)

    def desc(self, qid: str) -> str:
        return self.data["wd"].get(qid, {}).get("desc", "")

    def iconclass(self, notation: str) -> str | None:
        if not self.data["ic"].get(notation) and not self.offline:
            try:
                d = http_json(f"https://iconclass.org/{urllib.parse.quote(notation)}.json")
                self.data["ic"][notation] = d.get("txt", {}).get("de") or d.get("txt", {}).get("en")
            except Exception:  # noqa: BLE001 - not cached, retried next run
                print(f"warning: no Iconclass label for {notation}", file=sys.stderr)
        return self.data["ic"].get(notation)

    def lab_plain(self, lemma: str) -> str | None:
        if lemma not in self.data["lab"] and not self.offline:
            d = http_json(f"{LAB}/api.php", {"action": "query", "prop": "revisions", "rvprop": "content",
                                             "rvslots": "main", "format": "json", "formatversion": "2",
                                             "titles": lemma})
            page = d.get("query", {}).get("pages", [{}])[0]
            text = None if page.get("missing") else page["revisions"][0]["slots"]["main"]["content"]
            self.data["lab"][lemma] = plain(text) if text else None
        return self.data["lab"].get(lemma)


    def lab_images(self, names: set[str]) -> None:
        """Direct file URLs of the scan images on the lab wiki (None if the file
        is not there). Como shows them through its image proxy."""
        missing = sorted(n for n in names if n not in self.data["labimg"])
        if self.offline:
            return
        for i in range(0, len(missing), 50):
            chunk = missing[i:i + 50]
            d = http_json(f"{LAB}/api.php", {"action": "query", "prop": "imageinfo", "iiprop": "url",
                                             "format": "json", "formatversion": "2",
                                             "titles": "|".join(f"File:{n}" for n in chunk)})
            found = {}
            for page in d.get("query", {}).get("pages", []):
                info = (page.get("imageinfo") or [{}])[0]
                if info.get("url"):
                    found[page["title"].split(":", 1)[1].replace(" ", "_")] = info["url"]
            for n in chunk:
                self.data["labimg"][n] = found.get(n)

    def lab_image(self, name: str | None) -> str | None:
        return self.data["labimg"].get(name) if name else None


FILE_RE = re.compile(r"(?:\[\[:?)?(?:File|Datei):([^|\]\n]+?)\|([^\]\n]*)")


def field_images(wiki: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Scan image files of an article, from the image links the cleaning step put
    on the identifiers, the thumbs and the gallery lines: field identifier (A,
    A2, W1; a range like A1–4 covers each field) -> file, and (caption, file)
    pairs for paintings without an identifier."""
    by_field: dict[str, str] = {}
    captions: list[tuple[str, str]] = []
    for name, rest in FILE_RE.findall(wiki):
        name = name.strip().replace(" ", "_")
        label = re.sub(r"</?sub>", "", rest.split("|")[-1]).strip()
        if not label or label == "thumb":
            continue
        captions.append((label, name))
        lead = label.split()[0].rstrip(",.;:")
        if lead.isdigit():  # numbered fields: "3 Hl. Florian"
            by_field.setdefault(lead, name)
        # every identifier in the caption ("A Kreuzabnahme und A1–4 Szenen …"),
        # the leading one first
        for m in re.finditer(r"(?<![\w-])([A-Z]{1,3})(\d*)(?:[–-](\d+))?(?![\w-])", label):
            nums = range(int(m[2]), int(m[3]) + 1) if m[2] and m[3] else [m[2]]
            for n in nums:
                by_field.setdefault(f"{m[1]}{n}", name)
    return by_field, captions


def painting_image(spec: dict, tok: str) -> str | None:
    """The scan image of one painting: by its field identifier, else the image
    whose caption contains its title."""
    by_field, captions = spec["images"]
    field = spec["_fields"].get(tok)
    if field and field in by_field:
        return by_field[field]
    title = spec["_titles"].get(tok, "").casefold()
    return next((f for c, f in captions if title and title in c.casefold()), None)


def lab_url(lemma: str) -> str:
    return f"{LAB}/index.php/" + urllib.parse.quote(lemma.replace(" ", "_"), safe="(),")


def _frag(s: str) -> str:
    return urllib.parse.quote(s, safe="").replace("-", "%2D")


def text_fragment(quote: str, lab_text: str | None, min_words: int = 3) -> str | None:
    """A #:~:text= fragment for the longest run of the quote's words that
    occurs on the lab page. Matching ignores case, like browsers do."""
    if not lab_text:
        return None
    lab = lab_text.lower()
    best: list[str] = []
    for seg in re.split(r"\s*\[…\]\s*", quote.strip("»«")):
        words = seg.split()
        for n in range(len(words), max(len(best), min_words - 1), -1):
            hit = next((words[i:i + n] for i in range(len(words) - n + 1)
                        if " ".join(words[i:i + n]).lower() in lab), None)
            if hit:
                best = hit
                break
    if len(best) < min_words:
        return None
    if len(best) <= 8:
        return "#:~:text=" + _frag(" ".join(best))
    return "#:~:text=" + _frag(" ".join(best[:4])) + "," + _frag(" ".join(best[-4:]))


# ------------------------------------------------------------------ model
class Stmt:
    __slots__ = ("id", "lemma", "pages", "entity", "prop", "value", "quals", "quote",
                 "structural", "route", "game", "reason", "lab_link", "named_as", "volume")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))
        self.quals = self.quals or []

    def qs(self, with_ref: bool = True) -> str:
        parts = [self.entity, self.prop, self.value]
        for p, v in self.quals:
            parts += [p, v]
        if self.named_as:
            parts += ["P1932", f'"{self.named_as}"']
        if self.prop == "P1343":
            parts += ["P304", f'"{self.pages}"']
        elif with_ref:
            parts += ["S248", self.volume, "S304", f'"{self.pages}"']
        return "\t".join(parts)


def load_article(path: Path, articles: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    wiki = (articles / f"{spec['lemma']}.wiki").read_text(encoding="utf-8")
    tpl = dict(re.findall(r"^\|(\w+)=(.*)$", wiki.split("}}", 1)[0], re.M))
    spec["pages"] = tpl["Originalseitenvon"] + (
        f"-{tpl['Originalseitenbis']}" if tpl.get("Originalseitenbis") not in (None, "", tpl["Originalseitenvon"]) else "")
    spec["plain"] = plain(wiki)
    spec["images"] = field_images(wiki)
    return spec


def expand(spec: dict, band: str, created: dict[str, str]) -> tuple[list[Stmt], list[dict]]:
    """Claims file -> statements + new item definitions."""
    lemma, pages = spec["lemma"], spec["pages"]
    volume = VOLUMES[band][0]
    lslug = slugify(lemma)
    items = spec["items"]
    tok: dict[str, str] = {}
    new_items: list[dict] = []
    for key, it in items.items():
        if it.get("qid"):
            tok[key] = it["qid"]
            continue
        kind = it["new"]
        ph = f"{{NEW:{'painting' if kind in ('ceiling', 'wall') else kind}:{lslug}-{slugify(key)}}}"
        if QID_RE.match(created.get(ph, "")):  # created since the last run: use the real item
            tok[key] = created[ph]
            if kind in ("ceiling", "wall"):
                spec.setdefault("_paintings", set()).add(created[ph])
            continue
        tok[key] = ph
        if kind in ("ceiling", "wall"):
            word_de, word_en = ("Deckenbild", "ceiling painting") if kind == "ceiling" else ("Wandbild", "wall painting")
            cyc_de = f" der Folge »{it['cycle']}«" if it.get("cycle") else ""
            cyc_en = f" of the series “{it['cycle']}”" if it.get("cycle") else ""
            fid = f" {it['field']}" if it.get("field") else ""
            dde = it.get("desc_de") or f"{word_de}{fid}{cyc_de} in {lemma}"
            den = it.get("desc_en") or f"{word_en}{fid}{cyc_en} in {lemma}"
            p31 = it.get("p31") or P31_BY_KIND[kind]
        elif kind == "room":
            dde, den, p31 = f"Raum in {lemma}", f"room in {lemma}", it["p31"]
        else:
            dde, den, p31 = it["desc_de"], it.get("desc_en", ""), it["p31"]
        new_items.append({"key": key, "placeholder": ph, "kind": kind, "label": it["label"],
                          "dde": dde, "den": den, "p31": p31, "field": it.get("field")})

    spec["_fields"] = {tok[k]: it["field"] for k, it in items.items() if it.get("field")}
    spec["_titles"] = {tok[k]: it["label"] for k, it in items.items() if it.get("new") in ("ceiling", "wall")}

    def val(v):
        return tok.get(v, v) if isinstance(v, str) else v

    out: list[Stmt] = []
    n = 0

    def add(entity, prop, value, quals=(), quote=None, structural=False, named_as=None):
        nonlocal n
        n += 1
        out.append(Stmt(id=f"{lslug}#{n:03d}", lemma=lemma, pages=pages, entity=entity, prop=prop,
                        value=value, quals=list(quals), quote=quote, structural=structural,
                        named_as=named_as, volume=volume))

    for ni in new_items:
        add(ni["placeholder"], "P31", ni["p31"], structural=True)
    for c in spec["claims"]:
        if "seq" in c:
            keys = c["seq"]
            for a, b in zip(keys, keys[1:]):
                add(tok[a], "P156", tok[b], structural=True)
                add(tok[b], "P155", tok[a], structural=True)
            continue
        if "pair" in c:
            a, b = c["pair"]
            add(tok[a], "P1639", tok[b], structural=True)
            add(tok[b], "P1639", tok[a], structural=True)
            continue
        subjects = c["s"] if isinstance(c["s"], list) else [c["s"]]
        for s in subjects:
            quals = [(p, val(v)) for p, v in (c.get("q") or {}).items()]
            add(tok[s], c["p"], val(c["v"]), quals, c.get("quote"),
                bool(c.get("structural")) or (c["p"] in STRUCTURAL and not c.get("quote")), c.get("named_as"))
            if c["p"] == "P361":
                add(val(c["v"]), "P527", tok[s], structural=True)
    for key, it in items.items():
        if it.get("main"):
            add(tok[key], "P1343", volume, structural=True)
    for ni in new_items:
        add(ni["placeholder"], "P1343", volume, structural=True)
    return out, new_items


# ----------------------------------------------------------------- checks
def check_and_route(st: Stmt, spec: dict, cache: Cache, sample: bool) -> None:
    def route(r, game=None, reason=""):
        st.route, st.game, st.reason = r, game, reason

    if st.structural:
        return route("direct", reason="structural")
    if not st.quote:
        return route("curator", reason="no passage")
    if quote_check(st.quote, spec["plain"]):
        return route("curator", reason="passage not verbatim in the article")
    for p, v in st.quals:
        if p in CERTAINTY_PROPS and v in CERTAINTY and not re.search(CERTAINTY[v], st.quote):
            return route("curator", reason=f"qualifier {p}={v} not backed by a cue word in the passage")
    for t in [st.entity, st.value, *[v for _, v in st.quals]]:
        if QID_RE.match(t or ""):
            e = cache.data["wd"].get(t)
            if e is None and not cache.offline:
                return route("curator", reason=f"{t} could not be looked up")
            if e and (e.get("missing") or e.get("redirect")):
                return route("curator", reason=f"{t} is missing or a redirect")
    m = re.match(r'^[a-z]+:"(.*)"$', st.value)
    if m and m[1] not in st.quote:
        return route("curator", reason="inscription text not found in the passage")
    if QID_RE.match(st.entity) and already_there(st, cache):
        return route("direct", reason="already on the item; adds the corpus reference")
    hedged = bool(HEDGE.search(st.quote))
    game = GAMES.get(st.prop)
    if not PH_RE.match(st.entity) and st.entity not in cache.paintings:
        game = None  # games ask about paintings only
    if game == "datierung" and not st.value.endswith("T00:00:00Z/9"):
        game = None
    if game == "maler" and not QID_RE.match(st.value):
        game = None
    if game and game not in CHOICE_GAMES and (hedged or any(p in CERTAINTY_PROPS for p, _ in st.quals)):
        return route("curator", reason="hedged passage; the yes/no game has no certainty choice")
    if game and (PH_RE.match(st.entity) is None or "painting" in st.entity):
        return route("game", game, "interpretation of the passage")
    if st.prop in DIRECT_PROPS and not hedged:
        return route("audit" if sample else "direct", "stichprobe" if sample else None,
                     "copied from a labelled field or table")
    if st.prop in DIRECT_PROPS:
        return route("curator", reason="hedged passage for a direct property")
    return route("curator", reason=f"no game for {st.prop}")


def already_there(st: Stmt, cache: Cache) -> bool:
    have = cache.data["wd"].get(st.entity, {}).get("claims", {}).get(st.prop, [])
    if QID_RE.match(st.value):
        return json.dumps({"entity-type": "item", "numeric-id": int(st.value[1:]), "id": st.value}, sort_keys=True) in have
    m = re.match(r"^\+(\d{4})-00-00T00:00:00Z/9$", st.value)
    if m:
        return any(json.loads(h).get("time", "").startswith(f"+{m[1]}-") and json.loads(h).get("precision") == 9
                   for h in have if h.startswith("{"))
    return False


def audit_sample(stmts: list[Stmt], rate: float) -> set[str]:
    """Deterministic sample of the text-backed direct candidates, at least one
    per article."""
    cand = [s for s in stmts if not s.structural and s.quote and s.prop in DIRECT_PROPS]
    h = {s.id: int(hashlib.sha1(s.id.encode()).hexdigest(), 16) / 16**40 for s in cand}
    picked = {s.id for s in cand if h[s.id] < rate}
    by_lemma = defaultdict(list)
    for s in cand:
        by_lemma[s.lemma].append(s)
    for group in by_lemma.values():
        if not any(s.id in picked for s in group):
            picked.add(min(group, key=lambda s: h[s.id]).id)
    return picked


# ------------------------------------------------------------------ games
REF = ('{"parts": [{"property": {"id": "P248"}, "value": {"type": "value", "content": "%var_volume%"}}, '
       '{"property": {"id": "P304"}, "value": {"type": "value", "content": "%var_pages%"}}]}')
URL = "https://www.wikidata.org/w/rest.php/wikibase/v1/entities/items/%custom_value1%/statements"
COMMENT = "Textstelle aus dem Corpus der barocken Deckenmalerei bestätigt via Como"


def statement_body(prop: str, content: str, qualifiers: list[str] = ()) -> str:
    q = ", ".join(qualifiers)
    return ('{"statement": {"property": {"id": "' + prop + '"}, "value": {"type": "value", "content": ' + content +
            '}, "qualifiers": [' + q + '], "references": [' + REF + ']}, "comment": "' + COMMENT + '"}')


def qual(prop: str, content: str) -> str:
    return '{"property": {"id": "' + prop + '"}, "value": {"type": "value", "content": ' + content + '}}'


NAMED_AS = qual("P1932", '"%var_named_as%"')
TIME = '{"time": "+%custom_value2%-00-00T00:00:00Z", "precision": 9, "calendarmodel": "http://www.wikidata.org/entity/Q1985727"}'


def tpl(body: str, trigger: int | None = None) -> dict:
    t = {"request_method": "POST", "request_url": URL, "request_body": body}
    if trigger:
        t["trigger_option"] = trigger
    return t


def ach(prefix: str, n: int) -> list[dict]:
    half = max(2, n // 2 - 1)
    return [
        {"title": f"Erste {prefix}", "subtitle": "Die erste Textstelle geprüft", "goal_type": "D", "goal_value": 1},
        {"title": f"{prefix} im Blick", "subtitle": f"{min(10, half)} Textstellen geprüft", "goal_type": "D", "goal_value": min(10, half)},
        {"title": "Drei Tage Barock", "subtitle": "An drei Tagen in Folge gespielt", "goal_type": "S", "goal_value": 3},
        {"title": "Schlussstein", "subtitle": "Die letzte offene Textstelle entschieden", "goal_type": "L", "goal_value": 0},
    ]


# Shared parts of the long descriptions. {vol_no}/{vol_qid} are filled per band.
# The volume is the same on every prompt, so it is named here and not shown in
# a block; the page is shown after each passage.
SOURCE = ("Als Beleg wird der »Corpus der barocken Deckenmalerei in Deutschland«, Band {vol_no} "
          "(https://www.wikidata.org/wiki/{vol_qid}), mit der Seitenzahl hinter der Textstelle eingetragen.")
LAB_NOTE = ("Ein Tipp auf die Textstelle öffnet den Artikel auf https://deckenmalerei-lab.badw.de an genau "
            "dieser Stelle. Das Foto ist die Abbildung aus dem Band, soweit es eine gibt.")

# Blocks: claim block only where players need more than the question gives,
# then the passage (the one link into the article), then the scan image. The
# image comes last and unlabelled: prompts without one shift no label.
# Double confirmation (E) only for the judgment calls: certainty and Iconclass.
GAME_DEFS = {
    "maler": dict(
        name="Wer hat das gemalt?", short="Wie sicher nennen die Autoren den Maler eines Deckenbilds?",
        prompt="TTI", labels=["Maler", "Textstelle"], response="SC", confidence="E",
        question="Wie sicher schreibt die Textstelle %subject% %painter_label% zu?",
        long=("Wer hat ein barockes Deckenbild gemalt, und wie sicher ist das? Ein Sprachmodell hat Zuschreibungen "
              "aus dem gedruckten »Corpus der barocken Deckenmalerei in Deutschland« herausgelesen. Du entscheidest "
              "anhand der Textstelle, wie sicher die Autoren sind:\n"
              "• Belegt: Signatur, Datierung, Rechnung, Vertrag oder eine andere Quelle nennt den Maler.\n"
              "• Zugeschrieben: Die Autoren schließen aus Stil oder Vergleich auf ihn.\n"
              "• Vermutlich: Der Text sagt »wohl« oder »vermutlich«.\n"
              "• Wahrscheinlich: Der Text sagt »wahrscheinlich«.\n"
              "Wähle »Keine davon«, wenn die Textstelle ein anderes Bild meint, den Künstler in anderer Rolle nennt "
              "(etwa als Stuckateur) oder die Zuschreibung ablehnt. Unter »Maler« steht, wie Wikidata ihn beschreibt, "
              "und wie er im Text heißt; ein Tipp öffnet seinen Eintrag.\n"
              "Zwei Spieler müssen sich einig sein. Dann wird auf Wikidata Urheber (P170) mit der gewählten "
              "Sicherheit und dem Namen wie im Text (P1932) angelegt. ")),
    "datierung": dict(
        name="Wann wurde das gemalt?", short="Genau datiert oder nur ungefähr? Prüfe die Datierung barocker Deckenbilder.",
        prompt="TI", labels=["Textstelle"], response="SC", confidence="E",
        question="Wie sicher datiert die Textstelle %subject% in das Jahr %custom_value2%?",
        long=("Wann ist ein barockes Deckenbild entstanden? Ein Sprachmodell hat Jahreszahlen aus dem gedruckten "
              "»Corpus der barocken Deckenmalerei in Deutschland« herausgelesen. Du entscheidest anhand der "
              "Textstelle, wie sicher das Jahr ist:\n"
              "• so datiert oder belegt: Das Bild trägt die Jahreszahl, oder eine Quelle nennt sie.\n"
              "• um …: Der Text gibt das Jahr nur ungefähr an (»um«, »gegen«, »etwa«).\n"
              "• vermutlich …: Die Autoren erschließen das Jahr (»wohl«, »vermutlich«).\n"
              "Wähle »Keine davon«, wenn die Jahreszahl etwas anderes datiert: den Bau, eine Renovierung, ein "
              "anderes Bild.\n"
              "Zwei Spieler müssen sich einig sein. Dann wird auf Wikidata Entstehungsdatum (P571) mit der "
              "gewählten Sicherheit eingetragen. ")),
    "iconclass": dict(
        name="Iconclass-Detektiv", short="Passt der Bildinhalt zur Iconclass-Notation?",
        prompt="TTI", labels=["Iconclass", "Textstelle"], response="YN", confidence="E",
        question="Passt diese Iconclass-Notation zu %subject%?",
        long=("Iconclass ist ein Klassifikationssystem für Bildinhalte: Jede Notation steht für ein Thema, von "
              "allgemein (11H = Heilige) bis speziell (11H(MARTIN) = der hl. Martin). Ein Sprachmodell hat aus den "
              "Bildbeschreibungen des gedruckten »Corpus der barocken Deckenmalerei in Deutschland« Notationen "
              "vorgeschlagen; ihre Beschreibung kommt direkt von iconclass.org.\n"
              "Antworte »Ja«, wenn die Notation den Inhalt des Bildes laut Textstelle trifft, auch wenn sie "
              "allgemeiner ist als die Beschreibung. Antworte »Nein«, wenn sie etwas anderes bezeichnet oder nur "
              "ein Nebenmotiv eines anderen Bildes. Ein Tipp auf die Notation zeigt sie im Iconclass-Baum.\n"
              "Zwei Spieler müssen sich einig sein. Dann wird die Notation auf Wikidata als Iconclass-Notation "
              "(P1257) eingetragen. ")),
    "motiv": dict(
        name="Wer ist zu sehen?", short="Heilige, Allegorien, Szenen: Wer ist auf dem Deckenbild dargestellt?",
        prompt="TTI", labels=["Dargestellt", "Textstelle"], response="YN", confidence="L",
        question="Zeigt %subject% laut Textstelle %value_label%?",
        long=("Wer oder was ist auf einem barocken Deckenbild zu sehen? Ein Sprachmodell hat aus den "
              "Bildbeschreibungen des gedruckten »Corpus der barocken Deckenmalerei in Deutschland« Personen, "
              "Figuren und Themen herausgelesen.\n"
              "Antworte »Ja«, wenn die Textstelle diese Person oder dieses Thema auf genau diesem Bild beschreibt. "
              "Antworte »Nein«, wenn sie es nur nebenbei erwähnt (als Vergleich, als Stifter), wenn es auf einem "
              "anderen Bild des Raums zu sehen ist (achte auf die Buchstaben A, B, A1 …) oder wenn unter "
              "»Dargestellt« jemand anderes gleichen Namens steht. Ein Tipp darauf öffnet den Wikidata-Eintrag.\n"
              "Bei »Ja« wird auf Wikidata »stellt dar« (P180) eingetragen. ")),
    "zustand": dict(
        name="Zustandsbericht", short="Erhalten, beschädigt, zerstört? Prüfe den Zustand barocker Deckenbilder.",
        prompt="TI", labels=["Textstelle"], response="YN", confidence="L",
        question="Beschreibt die Textstelle %subject% als »%value_label%«?",
        long=("Ist ein barockes Deckenbild gut erhalten, beschädigt oder zerstört? Ein Sprachmodell hat das aus den "
              "Abschnitten zum Erhaltungszustand im gedruckten »Corpus der barocken Deckenmalerei in Deutschland« "
              "herausgelesen.\n"
              "Oben steht, welches Bild gemeint ist und welcher Zustand behauptet wird. Antworte »Ja«, wenn die "
              "Textstelle genau diesem Bild diesen Zustand zuschreibt; gilt sie für alle Bilder des Raums, zählt "
              "das auch. Antworte »Nein«, wenn sie ein anderes Bild meint (achte auf die Buchstaben A, B, A1 …), "
              "einen anderen Zustand nennt oder nur Restaurierungen aufzählt. Entscheidend ist der Text: Das Foto "
              "ist oft Jahrzehnte alt.\n"
              "Bei »Ja« wird auf Wikidata Erhaltungszustand (P5816) eingetragen. ")),
    "stichprobe": dict(
        name="Stichprobe Corpus", short="Stimmt die Angabe? Prüfe automatisch übernommene Daten.",
        prompt="TTI", labels=["Aussage", "Textstelle"], response="YN", confidence="S",
        question="Belegt die Textstelle für %subject% diese Aussage?",
        long=("Die meisten Angaben im gedruckten »Corpus der barocken Deckenmalerei in Deutschland« stehen in "
              "festen Feldern (Technik, Maße, Patrozinium) und werden ohne Spiel nach Wikidata übernommen. Diese "
              "Stichprobe prüft, ob das stimmt: Antworte »Ja«, wenn die Textstelle die Aussage genau so belegt, "
              "sonst »Nein«. Aus den Antworten wird die Fehlerquote der automatischen Übernahme berechnet.\n"
              "Dieses Spiel ändert nichts auf Wikidata. ")),
}
# The game templates, kept apart from the texts above.
TEMPLATES = {
    "maler": [tpl(statement_body("P170", '"%custom_value2%"', [NAMED_AS]), 1),
              tpl(statement_body("P170", '"%custom_value2%"', [qual("P5102", '"Q230768"'), NAMED_AS]), 2),
              tpl(statement_body("P170", '"%custom_value2%"', [qual("P1480", '"Q18122778"'), NAMED_AS]), 3),
              tpl(statement_body("P170", '"%custom_value2%"', [qual("P1480", '"Q56644435"'), NAMED_AS]), 4)],
    "datierung": [tpl(statement_body("P571", TIME), 1),
                  tpl(statement_body("P571", TIME, [qual("P1480", '"Q5727902"')]), 2),
                  tpl(statement_body("P571", TIME, [qual("P1480", '"Q18122778"')]), 3)],
    "iconclass": [tpl(statement_body("P1257", '"%custom_value2%"'))],
    "motiv": [tpl(statement_body("P180", '"%custom_value2%"'))],
    "zustand": [tpl(statement_body("P5816", '"%custom_value2%"'))],
    "stichprobe": [],
}
COVER = "https://upload.wikimedia.org/wikipedia/commons/2/2b/St._Martin_Adelshausen_02.jpg"


def write_games(stmts: list[Stmt], new_items: dict[str, dict], cache: Cache, out: Path, band: str,
                images: dict[str, str]) -> dict:
    gdir = out / "games"
    gdir.mkdir(exist_ok=True)
    vol_qid, vol_no = VOLUMES[band]
    counts = {}
    rows_by_game: dict[str, list[dict]] = defaultdict(list)

    def subject(st: Stmt) -> str:
        """The painting (or room) the question is about, named in the question."""
        if QID_RE.match(st.entity):
            d = cache.desc(st.entity)
            return f"»{cache.label(st.entity)}«" + (f", {d}," if d else "")
        ni = new_items[st.entity]
        return f"»{ni['label']}«, {ni['dde']},"

    def label(tok: str) -> str:
        return new_items[tok]["label"] + " (neu)" if tok in new_items else cache.label(tok)

    for st in stmts:
        if st.route not in ("game", "audit"):
            continue
        row = {"custom_value1": st.entity, "custom_value2": st.value, "var_pages": st.pages, "var_volume": vol_qid,
               "var_claim": st.id, "subject": subject(st)}
        passage = (f"»{st.quote}« (S. {st.pages})", st.lab_link or lab_url(st.lemma))
        claim = None
        g = st.game
        if g == "maler":
            named = st.named_as or cache.label(st.value)
            shown_as = f" · im Text: »{named}«" if named != cache.label(st.value) else ""
            claim = (f"{cache.label(st.value)} – {cache.desc(st.value)}{shown_as}",
                     f"https://www.wikidata.org/wiki/{st.value}")
            row.update(var_named_as=named, painter_label=cache.label(st.value),
                       option1="Belegt: signiert, datiert oder durch Quellen gesichert",
                       option2="Zugeschrieben: aus dem Stil erschlossen",
                       option3="Vermutlich: »wohl«, »vermutlich«",
                       option4="Wahrscheinlich: »wahrscheinlich«")
        elif g == "datierung":
            year = st.value[1:5]
            row.update(custom_value2=year, option1=f"{year} – so datiert oder belegt",
                       option2=f"um {year} – nur ungefähr", option3=f"vermutlich {year} – erschlossen, »wohl«")
        elif g == "iconclass":
            note = st.value.strip('"')
            row["custom_value2"] = note
            claim = (f"{note}: {cache.iconclass(note) or '(keine Beschreibung gefunden)'}",
                     "https://iconclass.org/" + urllib.parse.quote(note))
        elif g == "motiv":
            claim = (f"{label(st.value)} – {cache.desc(st.value)}".rstrip(" –"),
                     f"https://www.wikidata.org/wiki/{st.value}")
            row["value_label"] = label(st.value)
        elif g == "zustand":
            row["value_label"] = label(st.value)  # in the question; closed vocabulary, no block needed
        elif g == "stichprobe":
            quals = "; ".join(f"{cache.label(p)}: {render(v, cache, new_items)}" for p, v in st.quals)
            claim = (f"{cache.label(st.prop)}: {render(st.value, cache, new_items)}" + (f" ({quals})" if quals else ""),
                     None)
        n = 1
        for text, link in ([claim] if claim else []) + [passage]:
            row[f"text{n}"], row[f"text{n}_link"] = text, link or ""
            n += 1
        # the scan of the painting; clicking it opens the painting's Wikidata item once there is one
        row["image1_url"] = images.get(st.entity, "")
        row["image1_description_link"] = (f"https://www.wikidata.org/wiki/{st.entity}"
                                          if QID_RE.match(st.entity) and row["image1_url"] else "")
        rows_by_game[g].append(row)

    for g, rows in rows_by_game.items():
        d = GAME_DEFS[g]
        templates = TEMPLATES[g]
        long = d["long"] + (SOURCE if templates else "") + " " + LAB_NOTE
        long = long.format(vol_no=vol_no, vol_qid=vol_qid).replace("  ", " ")
        config = {"version": 1, "game": {
            "name": d["name"], "short_description": d["short"], "long_description": long,
            "language": "de", "is_listed": False, "question_template": d["question"],
            "confidence_type": d["confidence"], "prompt_type": d["prompt"],
            "prompt_labels_list": d["labels"], "response_type": d["response"],
            "action_type": "WA" if templates else None, "daily_streak_target": 10,
            "image_url": COVER},
            "action_request_templates": templates, "achievements": ach("Prüfung", len(rows))}
        slug = slugify(d["name"])
        (gdir / f"{slug}.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cols: list[str] = []
        for r in rows:
            cols += [k for k in r if k not in cols]
        with open(gdir / f"{slug}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        counts[slug] = len(rows)
    return counts


def render(v: str, cache: Cache, new_items: dict) -> str:
    if v in new_items:
        return new_items[v]["label"] + " (neu)"
    if QID_RE.match(v):
        return cache.label(v)
    m = re.match(r"^\+(\d{4})-00-00T00:00:00Z/(\d+)$", v)
    if m:
        return {"9": m[1], "8": f"{m[1][:3]}0er", "7": f"{int(m[1][:2]) + 1}. Jh."}.get(m[2], v)
    m = re.match(r"^([\d.]+)U(\d+)$", v)
    if m:
        return f"{m[1].replace('.', ',')} {cache.label('Q' + m[2])}"
    return v.strip('"')


# ------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--articles", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--offline", action="store_true", help="use only the cache, no network")
    ap.add_argument("--audit-rate", type=float, default=0.1)
    a = ap.parse_args()
    band = a.out.name
    cache = Cache(a.out / "cache.json", a.offline)

    created = {}
    if (a.out / "placeholders.tsv").exists():
        for r in csv.DictReader((a.out / "placeholders.tsv").open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            created[r["placeholder"]] = (r.get("qid") or "").strip()
    specs, stmts, new_items = [], [], {}
    for p in sorted((a.out / "claims").glob("*.json")):
        spec = load_article(p, a.articles)
        st, ni = expand(spec, band, created)
        cache.paintings |= {it["qid"] for it in spec["items"].values() if it.get("qid") and it.get("painting")}
        cache.paintings |= spec.get("_paintings", set())
        specs.append(spec)
        stmts += st
        new_items.update({n["placeholder"]: n for n in ni})
    labels = Counter((n["label"], n["dde"]) for n in new_items.values())
    dup = [k for k, c in labels.items() if c > 1]
    if dup:
        sys.exit(f"label+description not unique: {dup}")

    ids = {VOLUMES[band][0]}
    for s in stmts:
        for t in [s.entity, s.value, s.prop, *[x for q in s.quals for x in q]]:
            if QID_RE.match(t or "") or re.match(r"^P\d+$", t or ""):
                ids.add(t)
            m = re.match(r"^[\d.]+U(\d+)$", t or "")
            if m:
                ids.add("Q" + m[1])
    cache.entities(ids)

    spec_by_lemma = {s["lemma"]: s for s in specs}
    sample = audit_sample(stmts, a.audit_rate)
    for s in stmts:
        check_and_route(s, spec_by_lemma[s.lemma], cache, s.id in sample)
    followers: list[tuple[Stmt, Stmt]] = []
    reps: dict[tuple, Stmt] = {}
    for s in stmts:
        if s.route != "game":
            continue
        key = (s.lemma, s.prop, s.value, tuple(s.quals), s.quote)
        if key in reps:  # same claim, same passage, another field: decided together
            s.route, s.game, s.reason = "follows", None, f"follows the game decision on {reps[key].id}"
            followers.append((reps[key], s))
        else:
            reps[key] = s
    for s in stmts:
        if s.quote:
            s.lab_link = lab_url(s.lemma) + (text_fragment(s.quote, cache.lab_plain(s.lemma)) or "")
    cache.save()

    out = a.out
    # create.qs: terms, P31, P1343 and direct statements that need no other new item
    by_entity = defaultdict(list)
    for s in stmts:
        by_entity[s.entity].append(s)
    create, in_create = [], set()
    for ph, ni in new_items.items():
        create += ["CREATE", f'LAST\tLde\t"{ni["label"]}"\t/* {ph} */', f'LAST\tDde\t"{ni["dde"]}"']
        if ni["den"]:
            create.append(f'LAST\tDen\t"{ni["den"]}"')
        for s in by_entity[ph]:
            if s.route in ("direct", "audit") and not PH_RE.search(s.value):
                create.append(s.qs().replace(ph, "LAST", 1))
                in_create.add(s.id)
    direct = [s.qs() for s in stmts if s.route in ("direct", "audit") and s.id not in in_create]
    curator = [f"{s.qs()}\t/* {s.reason} */" for s in stmts if s.route == "curator"]
    (out / "create.qs").write_text("\n".join(create) + "\n", encoding="utf-8")
    (out / "direct.qs").write_text("\n".join(direct) + "\n", encoding="utf-8")
    (out / "curator.qs").write_text("\n".join(curator) + ("\n" if curator else ""), encoding="utf-8")
    old_rows = {}
    if (out / "placeholders.tsv").exists():
        for r in csv.DictReader((out / "placeholders.tsv").open(encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
            old_rows[r["placeholder"]] = r
    with open(out / "placeholders.tsv", "w", encoding="utf-8") as f:
        f.write("placeholder\tkind\tlabel_de\tdescription_de\tqid\n")
        for ph, ni in new_items.items():
            f.write(f"{ph}\t{ni['kind']}\t{ni['label']}\t{ni['dde']}\t\n")
        for ph, r in old_rows.items():  # already created: keep the row with its QID
            if ph not in new_items and QID_RE.match((r.get("qid") or "").strip()):
                f.write(f"{ph}\t{r['kind']}\t{r['label_de']}\t{r['description_de']}\t{r['qid'].strip()}\n")
    with open(out / "claims.tsv", "w", encoding="utf-8") as f:
        f.write("id\tlemma\tpages\troute\tgame\treason\tentity\tproperty\tvalue\tqualifiers\tquote\tlab_link\tqs\n")
        for s in stmts:
            q = ";".join(f"{p}={v}" for p, v in s.quals)
            f.write("\t".join([s.id, s.lemma, s.pages, s.route, s.game or "", s.reason, s.entity, s.prop, s.value, q,
                               s.quote or "", s.lab_link or "", s.qs()]) + "\n")
    files = {tok: painting_image(spec, tok) for spec in specs for tok in {*spec["_fields"], *spec["_titles"]}}
    cache.lab_images({f for f in files.values() if f})
    images = {tok: cache.lab_image(f) for tok, f in files.items() if cache.lab_image(f)}
    for qid in cache.paintings - set(images):  # already on Wikidata: its Commons image, if any
        p18 = cache.data["wd"].get(qid, {}).get("claims", {}).get("P18")
        if p18:
            images[qid] = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(
                json.loads(p18[0]).replace(" ", "_"))
    cache.save()
    game_counts = write_games(stmts, new_items, cache, out, band, images)
    with open(out / "followers.tsv", "w", encoding="utf-8") as f:
        f.write("rep_id\tgame\tfollower_id\tentity\tproperty\tvalue\tnamed_as\tpages\tvolume\n")
        for rep, fol in followers:
            f.write("\t".join([rep.id, rep.game, fol.id, fol.entity, fol.prop, fol.value, fol.named_as or "",
                               fol.pages, fol.volume]) + "\n")

    # report
    routes = Counter(s.route for s in stmts if not s.structural)
    lines = [f"# {band}: build report", "",
             f"{len(specs)} articles, {len(new_items)} new items, {len(stmts)} statements "
             f"({sum(s.structural for s in stmts)} structural).", "",
             "| route | text-backed statements |", "|---|---|"]
    lines += [f"| {r} | {routes.get(r, 0)} |" for r in ("direct", "audit", "game", "follows", "curator")]
    lines += ["", "| game | prompts |", "|---|---|"] + [f"| {g} | {n} |" for g, n in sorted(game_counts.items())]
    lines += ["", "## Curator queue", ""] + [f"- `{s.id}` {s.prop} {render(s.value, cache, new_items)}: {s.reason}"
                                            for s in stmts if s.route == "curator"]
    nolab = [s.id for s in stmts if s.quote and "#:~:text=" not in (s.lab_link or "")]
    lines += ["", f"Passages without a lab text anchor (page link only): {len(nolab)}"]
    (out / "build-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[: lines.index("## Curator queue")]))


if __name__ == "__main__":
    main()
