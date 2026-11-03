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

No room-sequence or picture-cycle items from the printed corpus unless the user
asks.

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
| CbDD dump | `P10626` | only if the item lacks it and the CbDD match is certain — normally left to the `agentic-reconcile` skill in CBDDsync |

Never touch `P625`, `P4244`, `P1435`, addresses on existing building items —
CBDDsync and the BLfD import own those.

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
| `'''Maße:'''` `a × b` | `P2043` length = a, `P2049` width = b, unit metre `U11573` | CbDD's convention; `Durchmesser` → `P2386`; `ca.` → `P1480 Q5727902`. The `Höhe` column is the ceiling's height above floor → **not** `P2048` |
| `'''Erhaltungszustand…'''` | `P5816` state of conservation | zerstört Q56556915 · beschädigt Q106379705 · restauriert Q75505084 (+ `P585` year) · verschollen Q62077203 |
| description | `P180` depicts | clearly named persons/saints/allegories with an item; lax |
| description | `P1257` Iconclass | optional, via the Iconclass MCP; one notation per clear subject |
| inscriptions | `P1684` inscription | monolingual, verbatim: `la:"…"` |
| `Vorlage`, Stich, Emblembuch | `P144` based on | only if the print/book item exists |
| stuccoist | `P767` contributor + `P3831` stuccoist Q18435135 | on the room (or building if no room item) |

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
