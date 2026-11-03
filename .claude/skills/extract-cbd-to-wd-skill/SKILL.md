---
name: extract-cbd-to-wd-skill
description: "Use when asked to extract structured data from CbDD articles (printed Corpus der barocken Deckenmalerei, data/formatted or cleaned output) into Wikidata statements — buildings, rooms, ceiling paintings, painters, stuccoists, commissioners, dates, techniques, patron saints, depicted subjects. Reconciles the buildings and people against Wikidata and the deckenmalerei.eu dump, writes QuickStatements batches cited to the printed volume and page, and uses {NEW:…} placeholders for items that still have to be created. Trigger on 'extract the data from this article', 'make Wikidata statements for Band05', 'put this church's paintings on Wikidata', 'QS batch from the corpus'."
---

# Extract CbDD articles to Wikidata

Turns one article, a list of lemmas, or a band of the printed *Corpus der
barocken Deckenmalerei in Deutschland* into reviewed QuickStatements batches.
**Use the `as-quickstatments` skill for all batch syntax, value formats and
validation** — load it first; this skill adds the CbDD data model, the
reconciliation rules and the placeholder workflow on top.

Nothing is sent to Wikidata. The user runs the batches.

Files:
- [references/data-model.md](references/data-model.md) — properties, classes,
  volume QIDs, certainty and date rules. **Read it before writing statements.**
- `scripts/cbdd_lookup.py` — article context + deckenmalerei.eu lookups.
- `scripts/placeholders.py` — check / lookup / fill `{NEW:…}` placeholders.

## Input

Cleaned articles (output of `clean-cbd-skill`, folder named by the user, e.g.
`data/cleaned-with-skill-v2/{Band}/`), falling back to
`data/formatted/{Band}/{Lemma}.wiki`. Skip articles with a non-empty `|Meta=`
and front/back matter (`Vorwort`, `Register`, …).

## Output

A folder the user names (default `data/wikidata/{Band}/`), shared by all
articles of the run:

| File | Content |
|---|---|
| `create.qs` | one `CREATE` block per new item; only self-contained statements (terms, `P31`, own dates/technique/measurements, `P1343`) — **no placeholder as a value** |
| `statements.qs` | everything else: statements on existing items and every statement that links two items; may contain placeholders as entity or value |
| `placeholders.tsv` | `placeholder  kind  label_de  description_de  qid` (qid empty until created) |
| `report.md` | per article: matched items with evidence, new items, skipped facts with reason, conflicts, open questions |

If the folder already has these files (earlier run), append and reuse existing
placeholders — never define the same person twice. Before creating a person
also `grep` other bands' `data/wikidata/*/placeholders.tsv`.

## Workflow (per article)

### 1. Context

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/cbdd_lookup.py article "<path>.wiki"
```

Gives lemma, band, volume QID, page range, the ready `reference`
(`S248 <volume> S304 "<pages>"`), labelled fields (Patrozinium, Technik, …),
field identifiers with titles, the Maße table, room words, and the matching
deckenmalerei.eu building with its QID and whatever rooms/paintings CbDD holds
below it. The CBDDsync checkout defaults to `~/Projects/CBDDsync`
(`--cbddsync` / `$CBDDSYNC_DIR`). Then read the whole article yourself — the
script only finds structure; meaning comes from the text.

### 2. Main subject(s): the building(s) — thorough

Usually one building: the lemma. Some lemmas name a part (`Andechs, Ehem.
Benediktinerabtei, Fürstenzimmer`): the room is the subject and the parent
building is reconciled the same thorough way. An article about "Kirche und
Kloster" has two buildings.

Find the QID in this order and record the evidence in the report:

1. **deckenmalerei.eu**: `cbdd_buildings` from step 1 (exact appellation match,
   QID via `P10626`). Still open the item: check `P31`, `P131`, coordinates and
   dedication against the article — CbDD links are occasionally wrong.
2. **Wikidata**: `search_items` with the lemma, the Ort, the patron saint;
   SPARQL for buildings with `P131` = the municipality (resolve it first) and
   a matching `P825` or label. Bavarian monument items (`P4244`, description
   like "einschiffiger Saalbau … mit Ausstattung") are often the only item and
   are the right one — the printed lemma as an alias on the item is a strong
   signal (CBDDsync adds those).
3. Decide: one confirmed item → use it. Two plausible items (church item +
   separate monument item, church vs. monastery complex) → choose the one that
   is the building itself, list the other in the report. Nothing after 1 and 2
   → new building item with a placeholder (`{NEW:building:<lemma-slug>}`).

Confirm with at least two independent agreements (place + dedication, place +
P4244 alias, CbDD ID + location). Never pick a building because the name alone
matches — "St. Martin" exists in every second village.

### 3. People — thorough

Everyone named as painter, stuccoist, architect, commissioner, template
provider (data-model.md, "People"). For each:

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/cbdd_lookup.py person "Johann Baptist Anwander"
```

then Wikidata (`search_items`, SPARQL on label + `P106` + dates), and the
`normdata-search` skill (GND) when ambiguous. Match only when life dates and
activity fit the article: the work date must fall inside the life span, the
place inside the activity region. CbDD matches on surname + first given name
are **candidates, not answers**:

> Adelshausen, Kapelle St. Martin (Bd 1): frescoes near 1795 "Johann Baptist
> Anwanders". CbDD's only Anwander is "Anwander, Johann" → Q1530000, who died
> 1770 — impossible. The right item is Q1692498 Johann Baptist Anwander
> (1750–1800, Landsberg/Augsburg).

Institutions and families as commissioners (`Grafen Fugger von Kirchberg und
Weißenhorn`, a monastery, an abbot in office) — resolve to the family /
institution / person item; abbots and provosts by name + office years.

No match after this → new person item with a placeholder
(`{NEW:person:<surname>-<given>}`), only if the article (or the biography in
another article of the band) gives enough to describe them: at least a role
and a date or place. Otherwise leave the statement out and list it in the
report.

### 4. Rooms and paintings — lax

1. Look at what already exists: the CbDD tree from step 1, and
   ```sparql
   SELECT ?x ?xLabel ?class WHERE { ?x wdt:P276|wdt:P361 wd:<building>. OPTIONAL { ?x wdt:P31 ?class } }
   ```
   (repeat with a room QID for paintings). Reuse an item when label/field and
   room clearly correspond; otherwise create.
2. Rooms: create only where data-model.md says so.
3. Paintings: one item per identified field, terms and classes as in
   data-model.md. Labels and descriptions must be unique per pair — the
   description carries the field ID and lemma.

Depicted subjects (`P180`), Iconclass (`P1257`) and template sources (`P144`)
are best-effort: add what resolves cleanly, skip the rest without a report
entry per item (just a count).

### 5. Write the batches

- Follow data-model.md for properties and the as-quickstatments skill for
  syntax. Every substantive statement gets the volume reference from step 1.
- Every touched item gets `P1343 <volume> P304 "<pages>"`; the main subject also
  `P1810 "<Lemma>"`.
- **Check first** (`get_statements`) on every existing item: skip values it
  already has; to add the corpus reference to an existing value, repeat the
  statement with the reference. Conflicts (other date, other painter) → report,
  don't overwrite.
- Keep the authors' certainty (data-model.md, "Certainty"). Never upgrade
  `wohl` to fact, never guess a date more precise than printed.
- `create.qs`: the placeholder goes in a comment on the label line, nothing
  else may reference a placeholder inside a CREATE block:
  ```
  CREATE
  LAST	Lde	"St. Martin in der Glorie"	/* {NEW:painting:adelshausen-kapelle-st-martin-b} */
  LAST	Dde	"Deckenbild B in Adelshausen (Weil), Kapelle St. Martin"
  LAST	Den	"ceiling painting B in Adelshausen (Weil), Kapelle St. Martin"
  LAST	P31	Q1181933	S248	Q118117102	S304	"19-21"
  LAST	P2079	Q134194	S248	Q118117102	S304	"19-21"
  LAST	P571	+1795-00-00T00:00:00Z/9	P1480	Q5727902	S248	Q118117102	S304	"19-21"
  LAST	P180	Q133704	S248	Q118117102	S304	"19-21"
  LAST	P1343	Q118117102	P304	"19-21"
  ```
- `statements.qs`: the links, existing items first:
  ```
  Q41254096	P825	Q133704	S248	Q118117102	S304	"19-21"
  Q41254096	P1343	Q118117102	P304	"19-21"	P1810	"Adelshausen (Weil), Kapelle St. Martin"
  Q41254096	P527	{NEW:room:adelshausen-kapelle-st-martin-ar}	S248	Q118117102	S304	"19-21"
  {NEW:room:adelshausen-kapelle-st-martin-ar}	P361	Q41254096	S248	Q118117102	S304	"19-21"
  {NEW:room:adelshausen-kapelle-st-martin-ar}	P276	Q41254096	S248	Q118117102	S304	"19-21"
  {NEW:painting:adelshausen-kapelle-st-martin-b}	P276	{NEW:room:adelshausen-kapelle-st-martin-ar}	S248	Q118117102	S304	"19-21"
  {NEW:painting:adelshausen-kapelle-st-martin-b}	P170	Q1692498	P5102	Q230768	P1932	"Johann Baptist Anwander"	S248	Q118117102	S304	"19-21"
  ```
- Placeholder syntax: `{NEW:<person|building|room|painting|other>:<slug>}`,
  slug = lowercase ASCII, digits, hyphens (`ä`→`ae`), painting/room slugs
  prefixed with the lemma slug so they are unique across the band.
- Add a row to `placeholders.tsv` for each new item; `label_de` and
  `description_de` must be exactly the `Lde` / `Dde` in `create.qs`.

### 6. Validate

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/placeholders.py check \
    --map <out>/placeholders.tsv <out>/create.qs <out>/statements.qs
```

Swaps placeholders for dummy QIDs, runs the as-quickstatments validator, and
flags undefined/unused placeholders, placeholders used as values inside CREATE
blocks, and non-unique label+description pairs. Fix every error.

### 7. Hand over

Report (as-quickstatments "Report" format, plus per article: building and
people matches with their evidence; number of new rooms/paintings; skipped
facts). Tell the user the run order:

1. Run `create.qs` in QuickStatements.
2. `placeholders.py lookup --map placeholders.tsv --apply` — finds each new item
   by its unique German label + description and writes the QID into the map
   (or fill the `qid` column by hand).
3. `placeholders.py fill --map placeholders.tsv statements.qs` → writes
   `statements.filled.qs` (ready) and `statements.pending.qs` (lines whose
   placeholders still have no QID).
4. Run `statements.filled.qs`.

## Section → data cheat sheet

| Section | Goes to |
|---|---|
| first paragraph | context only (parish, diocese, *z. Z. der Ausmalung*) — not written |
| `'''Patrozinium:'''` | building `P825` |
| `'''Zum Bauwerk:'''` | building `P571`, `P84`; room names |
| `'''Auftraggeber:'''` | paintings `P88` |
| `'''Autor und Entstehungszeit:'''` | paintings `P170` (+ certainty), `P571`; people's biographies |
| `== Befund ==` | rooms (Träger), `P2079`/`P186` (Technik), `P2043`/`P2049`/`P2386` (Maße), `P5816` (Erhaltungszustand) |
| `== Beschreibung (und Ikonographie) ==` | painting items (one per field), labels, `P180`, `P1257`, `P1684`, `P144` |
| `== Quellen und Literatur ==` | not written (the corpus is the source); may help disambiguate people |

## Open questions (ask the user when they matter)

- Order of `a × b` in Maße: assumed length × width as in CbDD; not confirmed
  from the volumes' prefaces.
- Whether to also create items for picture cycles / room sequences.
- Whether to add `P10626` to buildings found only by Wikidata search, or leave
  that to CBDDsync's `agentic-reconcile`.
