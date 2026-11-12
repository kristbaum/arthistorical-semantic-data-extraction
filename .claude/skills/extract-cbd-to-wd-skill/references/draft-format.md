# Draft format (what you write per article)

One JSON file per article: `data/claim-bundles/{Band}/drafts/<id>.json`.
`scripts/make_bundle.py` turns all drafts of a band into **one claim
bundle, version 2** (`bundle.json`; format in the como-game-creator skill,
`reference/claim-bundle.md`). The draft uses the bundle's key names; it
leaves out what make_bundle derives and allows CbDD shorthands. Checks,
evidence, routes and links come afterwards from `claim-bundle verify`,
`route` and `anchors`.

```json
{
  "id": "beuern",
  "lemma": "Beuern, Pfarrkirche St. Michael",
  "entities": {
    "bld":        {"kind": "building", "status": "match", "qid": "Q41254590", "main": true, "ref": "ft9cjb9q",
                   "route_reason": "QID in the cleaned article's {{Entität}}; deckenmalerei.eu building with P10626 → same item; dedication St. Michael."},
    "engelsturz": {"kind": "painting", "status": "match", "qid": "Q142089560", "ref": "xl48lbz8",
                   "route_reason": "Created from the earlier extraction (batch 66344); QID in the article's {{Entität}}."},
    "lhs":        {"kind": "room", "status": "create", "p31": "Q607600", "labels": {"de": "Langhaus"}, "ref": "pt1aoalg"},
    "a1":         {"kind": "painting", "status": "create", "field": "A1", "cycle": "Allegorische Darstellungen",
                   "labels": {"de": "Himmel"}, "ref": "wbyvanzd"},
    "_:person:joseph-schmuzer": {"kind": "person", "status": "match", "qid": "Q1707978", "ref": "indqsa5j",
                   "route_reason": "QID in the article's {{Entität}}; Wessobrunn architect (1683–1752), fits 1724–25."},
    "_:person:haid": {"kind": "person", "status": "reconcile", "on_no_match": "curator", "p31": "Q5", "ref": "k5e5ct54",
                   "types": ["Q5"], "facts": [{"property": "P1317", "value": "+1750-00-00T00:00:00Z/9"}],
                   "labels": {"de": "Haid"},
                   "descriptions": {"de": "Kupferstecher eines Porträts von Johann Adam Schöpf nach Bergmüller"},
                   "candidates": [{"qid": "Q1694808", "reason": "Augsburg engraver of portraits after Bergmüller."}, "Q5783104"],
                   "route_reason": "Only the surname is printed; several Haid engravers fit.",
                   "quote": "Johann Adam Schöpf nannte sich auch »von Schöpf« (vgl. den Porträtstich von Haid nach Bergmüller, Abb. 55 bei Schulten)."}
  },
  "claims": [
    {"subject": "bld", "property": "P825", "value": "Q45581", "quote": "Patrozinium: St. Michael"},
    {"subject": "a1", "property": "P276", "value": "lhs", "structural": true},
    {"subject": "engelsturz", "property": "P2043", "value": "9.10U11573", "quote": "Maße: Höhe 13,15 m; 9,10 × 6,00"},
    {"subject": "engelsturz", "property": "P1257", "value": "\"11G33\"", "quote": "…"},
    {"subject": "engelsturz", "property": "P1684", "value": "la:\"QUIS /UT / DEUS\"", "quote": "…"},
    {"subject": ["a1", "a2"], "property": "P170", "value": "_:person:johann-baptist-anwander",
     "qualifiers": {"P5102": "Q230768"}, "named_as": "Johann Baptist Anwander",
     "quote": "… daß man sie dem Augsburger Meister zuschreiben muß."},
    {"subject": "engelsturz", "property": "P170", "value": "_:person:johann-adam-schoepf", "named_as": "J de Schoepf",
     "quote": "Daher kommt nur Johann Adam Schöpf […] in Frage.",
     "route": "curator", "route_reason": "The authors argue against the usual attribution; a curator decides."},
    {"seq": ["a1", "a2", "a3", "a4"]},
    {"pair": ["w1", "w2"]}
  ]
}
```

## Top level

| Key | |
|---|---|
| `id` | short stable article id, a-z0-9-, unique in the band (`beuern`, `diessen`). Prefixes the article's entity and claim ids, which become Como prompt keys |
| `lemma` | exactly the file name of the cleaned article without `.wiki` |
| `entities`, `claims` | below |

## Entities

Keys: a short name (`bld`, `lhs`, `a1`) becomes `_:<id>:<name>`. **People,
and anything else that can occur in several articles, get a global id**
written in full: `_:person:<slug of the full name>`. A global entity must
have the same `kind`, `status` and `qid` in every draft; the first
definition's other fields win.

Bundle keys: `kind` (`building`, `room`, `painting`, `person`, `other`),
`status` (`match`, `create`, `reconcile`), `qid`, `route`, `route_reason`,
`labels`, `descriptions`, `aliases`, `quote`, `hint`, and for
reconciliation `on_no_match` (`create`, `drop`, `curator`), `types`
(classes a match must have) and `facts` (snaks: what the article says
about the entity; values in the claim shorthands below).

CbDD shorthands:

| Key | Meaning |
|---|---|
| `ref` | the `id` of this entity's `{{Entität}}` (`cbdd_lookup.py article` lists them). One per entity in an article; goes to `refs.tsv`, not the bundle |
| `main` | the article's subject building: `P1343` volume with `P304` pages and `P1810` lemma |
| `p31` | class of an entity to create or reconcile → a `P31` claim. Paintings default to ceiling painting Q1181933, fields `W…` to mural Q219423 |
| `field`, `cycle` | painting identifier and cycle title → description `Deckenbild A1 der Folge »…« in <Lemma>` |
| `candidates` | QIDs, or `{qid, reason}`; names, descriptions and evidence come from `claim-bundle verify` |

Derived: `source`, descriptions of new rooms and paintings, the default
route of new items (`direct`) and their `route_reason`, the `P31` and
`P1343` claims of every entity to create or reconcile (curator and
`only_if_created` for `reconcile`). `route_reason` is required for `match`
(the evidence) and for new people and buildings (how absence was
established); for `reconcile` entities with candidates `claim-bundle route`
writes it from the verified evidence.

## Claims

| Key | |
|---|---|
| `subject` | entity key or QID; a list for the same fact from the same passage on several subjects |
| `property` | PID |
| `value` | entity key, QID, `"\"11G33\""` string, `"la:\"…\""` monolingual, `"9.10U11573"` quantity, `"+1759-00-00T00:00:00Z/9"` time, `somevalue`, `novalue`, or a typed bundle value |
| `qualifiers` | `{"P5102": "Q230768"}` or a list of `{property, value}`; values may be entity keys |
| `named_as` | name as printed → `P1932` qualifier (P170, P84, P88) |
| `quote` | the passage, verbatim from the cleaned article with markup removed; `[…]` for cuts; about two sentences |
| `structural` | `true`: no passage, from the article's structure (P276 / P361 of rooms and paintings) |
| `route`, `route_reason`, `extraction`, `hint`, `game`, `only_if_created`, `choices` | as in the bundle; optional |
| `seq` | entity keys in reading order → P155/P156 |
| `pair` | two keys → P1639 both ways |

Derived: claim `id` (`<id>:<subject>:<P>:<hash of the value>`, stable
across re-extraction), `reference` (volume P248 via the source, pages
P304), `P527` as inverse of every `P361`, Iconclass text and link on
`P1257` values.

**Certainty choices.** A `P170` (attribution) or `P571` (year) claim on a
painting whose passage is hedged or that carries a certainty qualifier
(`P5102`, `P1480`) becomes a certainty game: make_bundle removes the
qualifier and adds the corpus's choices (belegt / zugeschrieben /
vermutlich / wahrscheinlich; so datiert / um / vermutlich). Give the claim
a `route` to keep it out of that (an argument against the literature goes
to the curator). Date ranges (`P1319`/`P1326`) are not converted; they go
to the curator.

## Routes

Leave `route` out unless the policy ([policy.json](policy.json)) is wrong
for this text. `claim-bundle route` then decides from the verified
evidence: failed passage → curator; structural → direct; labelled fields,
table values, inscriptions (P2079, P186, P2043, P2049, P2048, P2386, P825,
P1684) unhedged → direct, with a 10 % audit sample to the game
`stichprobe`; P180, P1257, P5816, P170, P571 on paintings, unhedged and
without hidden qualifiers → Yes/No games `motiv`, `iconclass`, `zustand`,
`urheber`, `datierung`; certainty choices → `urheber-sicherheit`,
`datierung-sicherheit`; anything else (P84, P88, P921, ranges) → curator.

Set `route` yourself when the text calls for it, always with a
`route_reason`: an attribution the authors argue against the literature →
curator; an unhedged prose statement whose value is in the source markup
(architect with QID in `{{Entität}}`) → direct; "Autor unbekannt"
(`P170 somevalue`) → direct.
