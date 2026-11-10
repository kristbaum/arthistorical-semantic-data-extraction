# Claims file format

One JSON file per article: `data/wikidata/{Band}/claims/<lemma-slug>.json`.
It is the only thing the model writes; `build.py` derives everything else.

```json
{
  "lemma": "Adelshausen (Weil), Kapelle St. Martin",
  "items": {
    "bld": {"qid": "Q41254096", "main": true, "ref": "e9yssbz5"},
    "anwander": {"qid": "Q1692498", "ref": "gfhveak5"},
    "langhaus": {"new": "room", "label": "Langhaus", "p31": "Q607600", "ref": "lrcj32hd"},
    "b": {"new": "ceiling", "field": "B", "label": "St. Martin in der Glorie", "ref": "fea4ldbw"},
    "a1": {"new": "ceiling", "field": "A1", "label": "Himmel", "cycle": "Allegorische Darstellungen", "ref": "wbyvanzd"},
    "w1": {"new": "wall", "field": "W1", "label": "St. Joseph", "ref": "shhi462b"},
    "kuppel": {"new": "ceiling", "label": "Das Gnadenbild von Bischofsried",
               "desc_de": "Kuppelfresko in Bischofsried, Maria-Schnee-Kapelle",
               "desc_en": "dome fresco in Bischofsried, Maria-Schnee-Kapelle"},
    "d": {"qid": "Q106548750", "painting": true}
  },
  "claims": [
    {"s": "bld", "p": "P825", "v": "Q133704", "quote": "Patrozinium: St. Martin"},
    {"s": ["a", "b"], "p": "P170", "v": "anwander", "q": {"P5102": "Q230768"},
     "named_as": "Johann Baptist Anwander", "quote": "… daß man sie dem Augsburger Meister zuschreiben muß."},
    {"s": "b", "p": "P2043", "v": "1.00U11573", "quote": "Maße: […] B – 3,45 m – 1,00 × 1,30"},
    {"s": "b", "p": "P1257", "v": "\"11H(MARTIN)\"", "quote": "…"},
    {"s": "b", "p": "P1684", "v": "la:\"QUIS / UT / DEUS\"", "quote": "… mit der Inschrift QUIS / UT / DEUS."},
    {"s": ["c1", "c2"], "p": "P276", "v": "bld", "structural": true},
    {"seq": ["a1", "a2", "a3", "a4"]},
    {"pair": ["w1", "w2"]}
  ]
}
```

## `items`

Keys are free short names used in `claims`. Each item is either

- **existing**: `{"qid": "Q…"}`. `"main": true` marks the article's subject
  (gets `P1343` + `P1810` lemma). `"painting": true` marks an existing painting
  item so its claims can go into the games.
- **new**: `{"new": kind, "label": …}` with kind
  - `ceiling` / `wall`: a painting. `field` = identifier without markup
    (`A1`, `W2`, `EB1`); `cycle` = the group title for members of a cycle.
    Description is generated: `Deckenbild A1 der Folge »…« in <Lemma>`.
    Without a field give `desc_de` / `desc_en`. `p31` optional (default
    ceiling painting Q1181933 / mural Q219423).
  - `room`: `p31` required (Langhaus Q607600, Altarraum Q207707, Empore
    Q648224, Vierung Q728243 …). Description `Raum in <Lemma>`.
  - `building`, `person`, `other`: `p31`, `desc_de`, `desc_en` required.
- **unreconciled**: `{"rec": kind, "label": …, "hint": …, "candidates": […],
  "quote": …}`, kind `person` / `building` / `room` / `painting` / `other`.
  For an entity of the article that has no confirmed Wikidata item yet and is
  not worth a new item from this article alone. `label` = the name as printed,
  `hint` = what the text says about it (role, dates, place: shown to players),
  `candidates` = up to 4 QIDs that could be it (may be empty), `quote` = the
  verbatim passage that identifies it. Claims on it are written as usual; they
  become `{REC:…}` statements with route `pending` until the entity is
  resolved in `reconcile.tsv` (game "Wer ist gemeint?" or by hand).

Every item may carry **`"ref"`**: the `id` of the `{{Entität}}` template
that marks this entity in the cleaned article (8 characters a-z0-9, listed by
`cbdd_lookup.py article` under `entities`). Copy it exactly; one ref per item,
each ref once. `build.py` copies refs into `claims.tsv` (`entity_ref`,
`value_ref`) and `refs.tsv`; `apply_qids.py write` uses them to put the item's
QID into the template once the item exists. Items without a template (no
`{{Entität}}` for them) have no ref.

Label + German description must be unique across the band (the build stops
otherwise).

## `claims`

| Key | Meaning |
|---|---|
| `s` | subject item key, or a list of keys (same fact, same passage) |
| `p` | property |
| `v` | value: an item key, a QID, `"\"string\""`, `+1795-00-00T00:00:00Z/9`, `1.75U11573`, `la:"…"` |
| `q` | qualifiers `{"P1480": "Q5727902"}`; values may be item keys |
| `named_as` | name as printed → `P1932` qualifier (P170, P84, P88) |
| `quote` | the verbatim passage; `[…]` for cuts |
| `structural` | `true`: no passage needed, written directly (only for P276 → building when the room is unknown) |
| `seq` | list of keys in reading order → P155/P156 |
| `pair` | two keys → P1639 both ways |

Added by `build.py`, never write them: P31 of new items, P1343 on every new
and main item, P1810 on the main item, P527 as inverse of every P361,
references (`S248 <volume> S304 "<pages>"`).
