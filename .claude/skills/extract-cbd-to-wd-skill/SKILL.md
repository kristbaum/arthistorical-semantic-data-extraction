---
name: extract-cbd-to-wd-skill
description: "Use when asked to extract structured data from CbDD articles (printed Corpus der barocken Deckenmalerei, data/formatted or cleaned output) into Wikidata statements — buildings, rooms, ceiling paintings, painters, stuccoists, commissioners, dates, techniques, patron saints, depicted subjects, Iconclass. Knows the deckenmalerei-lab markup ({{Entität}} ids, {{Abk}}, Maße tables, labelled fields), the deckenmalerei.eu structure (building → room → painting) and the ceiling paintings and rooms already on Wikidata; writes one draft per article and turns a band into a claim bundle (version 2) for the como-game-creator skill, which reconciles, verifies, routes, uploads and builds the games. Trigger on 'extract the data from this article', 'make Wikidata statements for Band05', 'put this church's paintings on Wikidata', 'claim bundle from the corpus'."
---

# CbDD articles → claim bundle

Turns one article, a list of lemmas, or a band of the printed *Corpus der
barocken Deckenmalerei in Deutschland* into a claim bundle: the entities
the article names (to reconcile) and the statements it makes (to validate),
each with the verbatim passage behind it.

**This skill knows the corpus; the como-game-creator skill knows the rest.**

| This skill | como-game-creator (`claim-bundle`) |
|---|---|
| the article markup, ids and pages; the lab page | the bundle format, temporary ids as placeholders, evidence |
| which statements a ceiling-painting article holds ([data-model.md](references/data-model.md)) | candidate generators and validators against Wikidata |
| the deckenmalerei.eu structure and existing items | routing from verified evidence ([policy.json](references/policy.json) is ours) |
| the certainty vocabulary of the authors | batches, games (reconciliation, validation), results |
| writing QIDs back into the articles | progress |

**Load first** the como-game-creator skill (`~/Projects/como-game-creator-skill/skill`):
`reference/claim-bundle.md`, `reference/reconciliation.md`,
`reference/validation.md`, `reference/evidence.md`. Its command is
`CB=~/Projects/como-game-creator-skill/skill/scripts/claim-bundle`.
Nothing is sent to Wikidata.

Files:
- [references/data-model.md](references/data-model.md): properties, classes,
  volume QIDs, certainty and date rules. **Read before writing.**
- [references/draft-format.md](references/draft-format.md): the draft you
  write and the shorthands make_bundle expands. **Read before writing.**
- [references/policy.json](references/policy.json): the routing policy for
  `claim-bundle route`.
- `scripts/cbdd_lookup.py`: article context, deckenmalerei.eu lookups.
- `scripts/make_bundle.py`: drafts → `bundle.json`, `refs.tsv`, `texts/`.
- `scripts/check_quotes.py`: the CbDD markup → plain text (used by
  make_bundle for the texts quotes are checked against).
- `scripts/apply_qids.py`: QIDs from bundle + state → `qid=` in the
  articles' `{{Entität}}` templates.

## The markup

Cleaned articles (`clean-cbd-skill` output, e.g.
`data/cleaned-with-skill-v2/{Band}/`; fallback `data/formatted/{Band}/`).
Skip articles with a non-empty `|Meta=` and front/back matter.

- `{{Artikel|…}}`: `Originalseitenvon`/`-bis` are the pages of every
  reference; the band directory gives the volume QID.
- `{{Entität|<text>|rolle=…|titel=…|bild=…|qid=…|id=<ref>}}` marks the
  building, rooms, people and paintings. Note the `id` as `ref` on the
  entity it stands for; `apply_qids.py` later writes the QID there. A
  `qid=` already present is a candidate match: verify it like any other.
  Templates for cycles (`A<sub>1–4</sub>`) and for the only room of a
  one-room building get no entity.
- Quote the plain text: `{{Abk|St.}}` → `St.`, `{{Entität|Pfarrkirche|…}}`
  → `Pfarrkirche`, `A<sub>1</sub>` → `A1`, `'''Technik:'''` → `Technik:`,
  table rows as `A – 3,30 m – 1,75 × 1,40` (empty cells: `– –`).
  `texts/<id>.txt`, written by make_bundle, is exactly that text.
- The lab wiki (`https://deckenmalerei-lab.badw.de`) holds the **older,
  uncleaned** text. Quotes come from the cleaned file; make_bundle saves the
  lab text as `texts/<id>.lab.txt`, and `claim-bundle anchors` builds the
  passage links from it.

## Workflow (per article, then per band)

### 1. Context

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/cbdd_lookup.py article "<path>.wiki"
```

Lemma, band, volume QID, pages, labelled fields, identifiers with titles,
the Maße table, room words, the `{{Entität}}` list, and the matching
deckenmalerei.eu building with its QID. Then read the whole article.

### 2. Building: thorough

Usually the lemma (`"main": true`); a lemma naming a part makes the room
the subject.

1. deckenmalerei.eu: `cbdd_buildings` (QID via `P10626`); open the item and
   check `P31`, `P131`, dedication. **Never write `P10626`**.
2. Wikidata: name, place, patron saint; Bavarian monument items are often
   right, the printed lemma as alias is a strong signal. For a building
   without a match, give `facts` (P625 when known, P131) and `types`, set
   `status: reconcile`, and run `$CB candidates --method geo`.
3. One confirmed item → `match` with the evidence in `route_reason` (two
   independent agreements; never the name alone).

### 3. Existing paintings and rooms

Earlier runs and other projects created items (Beuern: batch 66344;
Dießen: three Bergmüller frescoes). Look before creating:

```sparql
SELECT ?b ?x ?xLabel ?xDescription WHERE {
  VALUES ?b { wd:Q41254590 wd:Q1254306 }                 # the band's buildings
  { ?x wdt:P276 ?b } UNION { ?x wdt:P361 ?b } UNION { ?b wdt:P527 ?x }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "de". } }
```

or, per painting entity, `status: reconcile`, `on_no_match: create`,
`types: ["Q1181933"]` and `$CB candidates --method relation --property P276
--value <building>`. Reuse an existing item as `match` with its `ref`.

### 4. People: thorough

Painters, stuccoists, architects, commissioners: `cbdd_lookup.py person`,
then Wikidata. Every `{{Entität}}` person becomes an entity (global id
`_:person:<slug>`, shared across articles):

- confirmed (dates fit the work, place fits the region, two agreements) →
  `match`, evidence in `route_reason`;
- otherwise `reconcile` with `types: ["Q5"]`, `on_no_match` (usually
  `curator`), `facts` from the article (`P569`/`P570` life dates; `P2031`/
  `P2032` term of office; `P1317` activity year), and the candidates you
  know (QIDs). Then `$CB candidates --method label --keep 4 --entity …
  --write` for those without; remove the implausible ones yourself.

CbDD matches on surname + first given name are candidates, not answers
(Anwander: "Johann" †1770 vs. Johann Baptist 1750–1800 for c. 1795).

### 5. Rooms, paintings, subjects: lax

Rooms only when paintings sit in ≥ 2 rooms; one painting per described
field; cycles get no entity (`seq`, `pair`). `a × b` = length × width; the
Maße table's `Höhe` is the **room** height. Depicted subjects (`P180`):
clearly named persons/saints with an item (one SPARQL query for all saints
of the band, sitelinks > 8). Iconclass (`P1257`): one confirmed notation per
clearly named subject (Iconclass MCP `resolve`).

### 6. Write the draft

`data/claim-bundles/{Band}/drafts/<id>.json` ([draft-format.md](references/draft-format.md)):
every statement the article supports and the data model covers, quotes
verbatim, the authors' certainty as qualifiers (make_bundle turns hedged
attributions and dates of paintings into certainty choices), `named_as`
as printed, `route` only where the policy would be wrong for this text
(with a `route_reason`).

### 7. Build, then the como tools

```bash
S=.claude/skills/extract-cbd-to-wd-skill
CB=~/Projects/como-game-creator-skill/skill/scripts/claim-bundle
B=data/claim-bundles/{Band}/bundle.json
python3 $S/scripts/make_bundle.py --articles data/cleaned-with-skill-v2/{Band} --out data/claim-bundles/{Band}
$CB candidates $B --method label --keep 4 --entity <reconcile entities without candidates> --write
#   remove implausible candidates from the bundle
$CB verify  $B --write                        # names, dates, classes, passages, existing statements
$CB route   $B --policy $S/references/policy.json --write
$CB anchors $B --write
$CB check   $B
```

make_bundle stops on CbDD errors (unknown keys, refs missing or used twice,
unknown Iconclass notations, a shared entity defined differently). `note:`
lines list `{{Entität}}` refs without an entity: add them or say why not.
make_bundle rewrites the bundle from the drafts, so the como steps run
again after every rebuild; fix the draft when a check shows *you* got it
wrong, leave real ambiguity to the curator.

### 8. Hand over

Report per article (`report.md`: matches with evidence, skipped facts,
conflicts, open questions) and `$CB report $B`. Uploading and the games are
the como-game-creator skill's loop (`next`, `resolve`, `como`,
`game-config`, `como-sync`). Once items exist, write their QIDs into the
articles:

```bash
python3 $S/scripts/apply_qids.py --bundle $B --articles data/cleaned-with-skill-v2/{Band}   # dry run, then --apply
uv run python -m src.mediawiki.upload_pages --articles data/cleaned-with-skill-v2/{Band}
```

A `CONFLICT` (the template already has another qid) is never overwritten.

## Settled decisions

- Maße `a × b` = length × width; height only when written as `Höhe`.
- No items for picture cycles or room sequences; members are linked directly.
- Never add `P10626`.
- "Autor unbekannt" is `P170 somevalue`, routed direct.
- Certainty of attributions and dates is chosen by players (or a curator),
  not copied from the model.
