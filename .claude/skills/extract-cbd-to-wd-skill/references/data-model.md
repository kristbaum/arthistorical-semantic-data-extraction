# Data model: CbDD article → Wikidata

Mirrors how the online CbDD (deckenmalerei.eu) is synced to Wikidata by
`~/Projects/CBDDsync` (`src/config.py`, `relations.json`), so items made from
the printed volumes look like the ones CBDDsync already produced. All IDs below
were verified on Wikidata (2026-11). Anything not listed: resolve at runtime
with `search_items` / `search_properties` and confirm with `get_statements`.

## Hierarchy

CbDD stores `PART` relations: building → (building division / room sequence) →
room → (picture cycle) → painting → painting part. On Wikidata:

| Item | Links up with | Example on Wikidata |
|---|---|---|
| painting | `P276` location → room (or building when no room item) | Q131842169 → Q139817768 |
| room | `P361` part of **and** `P276` location → building | Q139817768 → Q2240519 |
| building | `P527` has part(s) → room (inverse, optional but recommended) | |

No items for room sequences or picture cycles — they are expressed as links
between the rooms / paintings themselves (see "Cycles and room sequences").

## Reference (every statement)

```
S248	<volume QID>	S304	"<Originalseitenvon>-<Originalseitenbis>"
```

Single page → `S304 "22"`. Pages come from the `{{Artikel}}` template, not
from guesses. `cbdd_lookup.py article` prints the ready-made `reference`.

Printed volumes (`P31` volume Q1238720, `P179` → Q107174967):

| Band dir | QID | | Band dir | QID |
|---|---|---|---|---|
| Band01 | Q118117102 | | Band08 | Q116088082 |
| Band02 | Q118117169 | | Band09 | Q116088253 |
| Band03-1 | Q118117218 | | Band10 | Q116105729 |
| Band03-2 | Q118117237 | | Band11 | Q116105732 |
| Band04 | Q118117256 | | Band12-1, Band12-2 | Q116117329 (one item, continuous pages) |
| Band05 | Q118117284 | | Band13 | Q116127930 |
| Band06 | Q118117296 | | Band14 | Q118117417 |
| Band07 | Q116077486 | | | |

Do **not** cite Q107174967 (the CbDD project / online database) for facts from
the printed text. CBDDsync uses `S248 Q107174967 S10626 "<uuid>"` for facts from
deckenmalerei.eu; that is a different source.

Every item touched also gets (no reference needed, it *is* the source):

```
<item>	P1343	<volume QID>	P304	"19-21"	P1810	"<Lemma as printed>"
```

`P1810` (subject named as) only on the article's main subject(s).

## Building (main subject; thorough)

| Article | Property | Value / rule |
|---|---|---|
| Lemma, `Typ` | `P31` | only on new items: church building Q16970, chapel Q108325, … confirm class |
| — | `P17` / `P131` | new items only: Q183 / municipality from `Ort` (resolve) |
| `'''Patrozinium:'''` | `P825` dedicated to | saint item (e.g. Martin of Tours Q133704); former patrocinia (`vor 1452 Maria`) get `P582` end time if dated |
| `'''Zum Bauwerk:'''` | `P571` inception | construction date; only if the item has none or a less precise one |
| `'''Zum Bauwerk:'''` | `P84` architect | person (reconcile thoroughly) |

**Never write `P10626` (deckenmalerei.eu ID)** — on buildings, people or any
other item. The CbDD dump is used read-only for matching; adding the ID is
CBDDsync's job. Likewise never touch `P625`, `P4244`, `P1435` or addresses on
existing building items — CBDDsync and the BLfD import own those.

## Room (lax)

Create a room item only when the article's paintings sit in ≥ 2 distinct
rooms, or the lemma itself is a room (`…, Fürstenzimmer`). A one-room chapel:
paintings `P276` → building directly.

| Field | Value |
|---|---|
| `Lde` | room name as in the article, spelled out: `Langhaus`, `Altarraum`, `Fürstensaal` (CbDD style, cf. "Hauptsaal") |
| `Dde` / `Den` | `Raum in <Lemma>` / `room in <Lemma>` (keeps label+description unique) |
| `P31` | Langhaus Q607600 · Altarraum/Chor Q207707 · Empore Q648224 · Kirchenkapelle Q2196917 · Treppenhaus Q2451751 · Festsaal Q31838271 · otherwise resolve, fallback room Q180516 |
| `P361`, `P276` | building |
| `P571` | only when the article dates the room separately |
| `P2048` height | room height as printed with `Höhe` (`AR Höhe 5,40 m`, or the Maße table's `Höhe` column when it is one value for the room), unit metre |

Abbreviations: `LHs` Langhaus, `AR` Altarraum, `N`/`S`/`O`/`W` compass
(`W` before a subscript is a wall field, not west).

## Painting (lax)

One item per identified field (`A`, `B`, `A<sub>1</sub>` …). Group fields such
as `A<sub>1–4</sub>` become four items only when each sub-field has its own
description; otherwise one item labelled with the group title. Skip pure
ornament without a subject.

| Article | Property | Value / rule |
|---|---|---|
| caption / `'''TITLE'''` | `Lde` | title in sentence case: the image caption if present (`Mantelspende des hl. Martin`), else the capitals title de-capitalised |
| — | `Dde` / `Den` | `Deckenbild <ID> in <Lemma>` / `ceiling painting <ID> in <Lemma>`; `Wandbild` / `wall painting` for W fields. ID without `<sub>`: `A1` |
| field position | `P31` | ceiling painting Q1181933 · wall field (W) → mural Q219423 |
| room | `P276` | room item, else building |
| `'''Technik:'''` | `P2079` fabrication method | Fresko Q134194 · Secco Q2263612 · Öl Q174705 |
| `'''Technik:'''` | `P186` made from material | Öl auf Leinwand → oil paint Q296955 + canvas Q12321255 (CBDDsync map) |
| `'''Autor und Entstehungszeit:'''` | `P170` creator | see "Certainty" below |
| same | `P571` inception | see "Dates" below |
| `'''Auftraggeber:'''` | `P88` commissioned by | person, family or institution (as CbDD: commissioners sit on the paintings) |
| `'''Maße:'''` `a × b` | `P2043` length = a, `P2049` width = b, unit metre `U11573` | the corpus prints length × width. Height is always written out as `Höhe` (or `H`): only then `P2048`. Labelled axes win over the order (`H 2,10 × B 1,40` → `P2048` + `P2049`; `B`/`T` → width). `Durchmesser` → `P2386`; `ca.` → `P1480 Q5727902`. The Maße table's `Höhe` column is the room's height above floor → `P2048` on the **room**, never on the painting |
| `'''Erhaltungszustand…'''` | `P5816` state of conservation | zerstört Q56556915 · beschädigt Q106379705 · restauriert Q75505084 (+ `P585` year) · verschollen Q62077203 |
| description | `P180` depicts | clearly named persons/saints/allegories with an item; lax |
| entry title + description | `P1257` Iconclass | via the `iconclass-cbdd` skill (fallback: Iconclass MCP, every notation confirmed with `resolve`); from the text, one notation per clearly named subject, most specific supported; value is the notation as a quoted string `"11H(MARTIN)"` |
| inscriptions | `P1684` inscription | monolingual, verbatim: `la:"…"` |
| `Vorlage`, Stich, Emblembuch | `P144` based on | only if the print/book item exists |
| stuccoist | `P767` contributor + `P3831` stuccoist Q18435135 | on the room (or building if no room item) |

## Cycles and room sequences (no extra item)

A picture cycle or a room sequence is not an item of its own; its members are
linked to each other, and the grouping lives in the description.

**Picture cycles** (`A<sub>1–4</sub> ALLEGORISCHE DARSTELLUNGEN`, Zwickel,
medallion rows, Evangelists, months, Stations of the Cross):

| Link | When | Statement |
|---|---|---|
| reading order | every cycle with ≥ 3 members | `P155` follows / `P156` followed by between neighbours, in the order of the corpus identifiers (`A1 → A2 → A3 → A4`); no wrap-around |
| pair | exactly two companion fields (`W1`/`W2`, two medallions) | `P1639` pendant of, both directions; no `P155`/`P156` |
| shared programme | the article names the cycle's theme and it has an item (Four Last Things, the four Evangelists, the four seasons …) | `P921` main subject = theme on each member; the individual subject stays in `P180` |
| group name | always | in the description: `Deckenbild A1 der Folge »Allegorische Darstellungen« in <Lemma>` |

All members of one cycle share the same `P276` room. Members are linked by
placeholders, so the links go in `statements.qs`.

**Room sequences** (Appartement, Enfilade, Raumfolge):

| Link | Statement |
|---|---|
| physical connection | `P2789` connects with, between rooms with a door between them, both directions — only if the article says so (`anschließend`, `Enfilade`, `folgt`) |
| order of an enfilade / suite | additionally `P155` / `P156` in the order the article walks through it |
| sequence name | description only: `Raum im Appartement der Kurfürstin in <Lemma>` (not as an alias — aliases name the room itself) |

Each room keeps `P361` + `P276` → building.

## People (thorough)

Painters, stuccoists, architects, commissioners, template providers.

| Property | Rule |
|---|---|
| `P31` Q5, `Lde` "Given Surname", `Dde` "deutscher Maler (1750–1800)" style | new items only; dates only if the corpus states them |
| `P106` | painter Q1028181 · stuccoist Q18435135 · architect (resolve) |
| `P569` / `P570` | year precision unless the corpus gives the day; `um` → `P1480 Q5727902` |
| qualifier on `P170`/`P88`/`P84` | `P1932` object named as = the name exactly as printed |

Biographies are usually in the article where the artist first appears ("Angaben
zur Biographie siehe dort") — grep the band for the name before deciding.

## Certainty (on `P170`, also `P84`, `P88`)

| Article says | Qualifier |
|---|---|
| signiert / bez. / datiert / urkundlich / archivalisch belegt | none |
| zugeschrieben / zuzuschreiben / Zuschreibung | `P5102` Q230768 (attribution) |
| wohl / vermutlich | `P1480` Q18122778 (presumably) |
| wahrscheinlich | `P1480` Q56644435 (probably) |
| Umkreis des X | `P170 somevalue` + `P1776` circle of X |
| Werkstatt des X | `P170 somevalue` + `P1774` workshop of X |
| Schule des X | `P170 somevalue` + `P1780` school of X |
| Autor unbekannt | `P170 somevalue` |

Contradicting attributions in the literature → one statement each, both
referenced, normal rank; mention in the report.

## Dates (`P571`, `P569`, `P570`)

| Article | Value | Qualifiers |
|---|---|---|
| 1752 | `+1752-00-00T00:00:00Z/9` | |
| um 1752 / in zeitlicher Nähe zu 1752 | `+1752-00-00T00:00:00Z/9` | `P1480 Q5727902` |
| 1752–54 | `+1750-00-00T00:00:00Z/8` | `P1319 +1752…/9` `P1326 +1754…/9` |
| 2. Viertel 18. Jh. | `+1750-00-00T00:00:00Z/7` | `P1319 +1726…/9` `P1326 +1750…/9` |
| 18. Jh. | `+1750-00-00T00:00:00Z/7` | |

Century values use the mid-century year (`1750/7`) so no renderer shows the
wrong century. Pick the coarsest precision that contains the whole range.
