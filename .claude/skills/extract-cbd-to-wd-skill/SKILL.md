---
name: extract-cbd-to-wd-skill
description: "Use when asked to extract structured data from CbDD articles (printed Corpus der barocken Deckenmalerei, data/formatted or cleaned output) into Wikidata statements — buildings, rooms, ceiling paintings, painters, stuccoists, commissioners, dates, techniques, patron saints, depicted subjects. Reconciles the buildings and people against Wikidata and the deckenmalerei.eu dump, writes one claims file per article with the verbatim passage behind every claim, and builds from it (deterministically): QuickStatements batches cited to the printed volume and page with {NEW:…} placeholders for items still to be created, a direct batch for high-certainty statements, a curator queue, and Como games (config JSON + prompt CSV) for the interpretive statements, with links into the deckenmalerei-lab page that scroll to the passage. Trigger on 'extract the data from this article', 'make Wikidata statements for Band05', 'put this church's paintings on Wikidata', 'QS batch from the corpus', 'Como game for the corpus statements'."
---

# Extract CbDD articles to Wikidata

Turns one article, a list of lemmas, or a band of the printed *Corpus der
barocken Deckenmalerei in Deutschland* into checked Wikidata statements.

**The split of work:** you (the model) read, reconcile and write one
**claims file** per article: atomic claims, each with the verbatim passage it
rests on. Everything after that is deterministic and done by
`scripts/build.py`: placeholders, bookkeeping statements, checks, triage, QS
files, Como games, links. Never hand-write QS lines, game CSVs or request
bodies.

Load first: `as-quickstatments` (QS syntax and value formats), and for the
games the `como-game-creator` skill (`~/Projects/como-game-creator-skill`,
especially `reference/llm-extracted-claims.md`). Iconclass: the
`iconclass-cbdd` skill if installed, otherwise the Iconclass MCP (step 4).

Nothing is sent to Wikidata. The user runs the batches and uploads the games.

Files:
- [references/data-model.md](references/data-model.md) — properties, classes,
  volume QIDs, certainty and date rules. **Read it before writing claims.**
- [references/claims-format.md](references/claims-format.md) — the claims
  file you write. **Read it before writing one.**
- `scripts/cbdd_lookup.py` — article context + deckenmalerei.eu lookups.
- `scripts/build.py` — claims files → everything else (see Output).
- `scripts/check_quotes.py` — standalone verbatim check of passages.
- `scripts/placeholders.py` — check / lookup / fill `{NEW:…}` placeholders.
- `scripts/apply_qids.py` — `link` notes refs for items of older claims files;
  `write` puts the QIDs into the articles' `{{Entität}}` templates by ref.

## Input

**Entity refs.** The cleaned articles mark the building, rooms, people and
paintings with `{{Entität|<text>|rolle=…|titel=…|bild=…|id=<ref>}}`, one
template per entity. The `id` is a stable key: **note it as `"ref"` on the
item** that stands for this entity (claims-format.md), so the QID can later be
written back to exactly that spot. `cbdd_lookup.py article` lists them under
`entities` (id, rolle, text, titel, bild). Otherwise ignore the template's
parameters — quote only its shown text.

Cleaned articles (output of `clean-cbd-skill`, folder named by the user, e.g.
`data/cleaned-with-skill-v2/{Band}/`), falling back to
`data/formatted/{Band}/{Lemma}.wiki`. Skip articles with a non-empty `|Meta=`
and front/back matter (`Vorwort`, `Register`, …).

The deckenmalerei-lab wiki (`https://deckenmalerei-lab.badw.de`) holds the
**older, uncleaned** text of the same articles (OCR errors such as "1695" for
"1795"). Quotes always come from the cleaned file; `build.py` finds the part
of each quote that also exists on the lab page for the link anchor.

## Output (folder `data/wikidata/{Band}/`, shared by all articles of the run)

| File | Written by | Content |
|---|---|---|
| `claims/<lemma-slug>.json` | you | items + claims + passages, one file per article |
| `create.qs` | build.py | one CREATE block per new item: terms, P31, P1343 and the direct statements that need no other new item |
| `direct.qs` | build.py | high-certainty statements on existing items and links between new items (placeholders until filled); includes "already on Wikidata, add the reference" lines |
| `curator.qs` | build.py | statements a person must look at, each with the reason as a comment |
| `games/<slug>.json` + `.csv` | build.py | Como game configs and prompt CSVs (see Games) |
| `claims.tsv` | build.py | every statement: id, route, game, reason, entity, property, value, qualifiers, quote, lab link, `entity_ref`/`value_ref` (the `{{Entität}}` ids of subject and value), QS line |
| `refs.tsv` | build.py | ref → lemma, item key, target (QID or placeholder) |
| `placeholders.tsv` | build.py | placeholder → label, description, qid (fill qid after creation) |
| `build-report.md` | build.py | counts per route and game, curator queue |
| `cache.json` | build.py | Wikidata / Iconclass / lab lookups (delete to refresh) |
| `report.md` | you | per article: matches with evidence, skipped facts, conflicts, open questions |

## Workflow (per article)

### 1. Context

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/cbdd_lookup.py article "<path>.wiki"
```

Gives lemma, band, volume QID, page range, labelled fields, field identifiers
with titles, the Maße table, room words and the matching deckenmalerei.eu
building with its QID. Then read the whole article — the script only finds
structure; meaning comes from the text.

### 2. Main subject(s): the building(s) — thorough

Usually one building: the lemma. Some lemmas name a part (`…, Fürstenzimmer`):
the room is the subject and the parent building is reconciled the same way.

Find the QID in this order and record the evidence in the report:

1. **deckenmalerei.eu**: `cbdd_buildings` from step 1 (QID via `P10626`).
   Still open the item: check `P31`, `P131`, dedication against the article.
   **Never write `P10626`** — that is CBDDsync's job.
2. **Wikidata**: `search_items` with lemma, place, patron saint; SPARQL on
   `P131` = municipality. Bavarian monument items (description "einschiffiger
   Saalbau … mit Ausstattung") are often the right item; the printed lemma as
   an alias is a strong signal.
3. One confirmed item → use it. Nothing → new building (`"new": "building"`).

At least two independent agreements (place + dedication, place + alias, CbDD
ID + location). Never pick a building because the name alone matches.

Also look for **existing painting items** on the building (`P527`, or
`?x wdt:P276|wdt:P361 wd:<building>`); reuse them with `"qid": …,
"painting": true` (Dießen: the cupola fresco Q106548750 already existed).

### 3. People — thorough

Painters, stuccoists, architects, commissioners: `cbdd_lookup.py person`,
then Wikidata (label + dates in one SPARQL query for all names of the band),
`normdata-search` when ambiguous. Match only when life dates fit the work date
and the place fits the activity region. CbDD matches on surname + first given
name are candidates, not answers (Anwander: "Johann" †1770 vs. Johann Baptist
1750–1800 for frescoes of c. 1795). No match and too little to describe a new
person → leave the claim out and list it in the report.

### 4. Rooms, paintings, subjects — lax

Rooms only when paintings sit in ≥ 2 rooms; paintings one item per described
field; cycles get no item (`seq`, `pair` in the claims file). Dimensions:
`a × b` = length × width; the Maße table's `Höhe` is the **room** height.

Depicted subjects (`P180`): clearly named persons/saints with an item. Look up
all saints of the band in one SPARQL query on German labels with a sitelink
filter (`wikibase:sitelinks ?sl FILTER(?sl > 8)`), then check descriptions.

Iconclass (`P1257`): one notation per clearly named subject, the most
specific the text supports; confirm every notation (Iconclass MCP `resolve`,
or `https://iconclass.org/<notation>.json`). The passage must name what the
notation encodes. Skip local legends without a notation.

### 5. Write the claims file

`data/wikidata/{Band}/claims/<lemma-slug>.json`, format in
[references/claims-format.md](references/claims-format.md). Rules:

- **Refs**: every item that has an `{{Entität}}` in the article gets its
  `id` as `"ref"` — the main building (`rolle=Bauwerk`), each painting (by its
  identifier or title), each person, each room. Never invent a ref; an entity
  without a template (a person only named in a quotation) simply has none.
  `build.py` stops on a ref used twice and reports refs not found in the
  article.
- **Quotes verbatim** from the cleaned article with markup removed
  (`{{Abk|St.}}` → `St.`, `{{Entität|Pfarrkirche|…}}` → `Pfarrkirche`,
  `A<sub>1</sub>` → `A1`, file links → their text).
  Cut with `[…]`. Table rows are quoted as rendered:
  `Maße: […] A – 3,30 m – 1,75 × 1,40`.
- Keep the authors' certainty as qualifiers (data-model.md, "Certainty");
  the passage must contain the cue word (*wohl, vermutlich, um, zuschreiben*…)
  or the claim lands in the curator queue.
- `named_as` = the name as printed (becomes `P1932`).
- One claim per fact; a list in `"s"` when the same passage supports the same
  fact for several fields.

### 6. Build, check, triage

```bash
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/build.py \
    --articles data/cleaned-with-skill-v2/{Band} --out data/wikidata/{Band}
python3 .claude/skills/extract-cbd-to-wd-skill/scripts/placeholders.py check \
    --map data/wikidata/{Band}/placeholders.tsv data/wikidata/{Band}/create.qs data/wikidata/{Band}/direct.qs
for j in data/wikidata/{Band}/games/*.json; do
  python3 ~/Projects/como-game-creator-skill/scripts/validate.py "$j" "${j%.json}.csv"; done
```

Checks per claim: passage verbatim in the article; certainty qualifiers backed
by a cue word; inscription text found in the passage; every QID exists and is
no redirect; statement not already on the item (then: direct, reference only).

Routes:

| Route | When |
|---|---|
| direct | structural statements; labelled-field/table properties (P2079, P186, P2043, P2049, P2048, P2386, P825, P361, P276, P1684 …) with an unhedged passage; statements already on Wikidata (reference only) |
| audit | deterministic 10 % sample of the direct text claims, ≥ 1 per article → game "Stichprobe Corpus" (no action) |
| game | P170, P571 (year precision), P1257, P180, P5816 on paintings, checks passed; Yes/No games only for unhedged claims |
| curator | any failed check; hedged claim for a Yes/No game; P84, P88, P921, date ranges … |

Fix the claims file (not the outputs) when a check fails because *you* got
something wrong; leave real ambiguities in the curator queue.

### 7. Games

| Game (slug) | Response | Confidence | Action (REST, `POST …/items/%custom_value1%/statements`) |
|---|---|---|---|
| Wer hat das gemalt? | SC: belegt / zugeschrieben / vermutlich / wahrscheinlich | E | P170 + qualifier per option (`trigger_option`), P1932 = `%var_named_as%` |
| Wann wurde das gemalt? | SC: so datiert / um / vermutlich | E | P571 year + qualifier per option |
| Iconclass-Detektiv | YN | E | P1257 notation, label from iconclass.org |
| Wer ist zu sehen? | YN | L | P180 |
| Zustandsbericht | YN | L | P5816 |
| Stichprobe Corpus | YN | S | none (measures the error rate of the direct route) |

Double confirmation (`E`) only for the judgment calls (certainty, Iconclass);
the plain Yes/No checks need one logged-in answer (`L`).

Prompts carry only what players use, one link per piece of evidence:

- **Question**: names the painting (`%subject%`: »title«, description) and
  the claim, so no separate painting block is needed.
- **Claim block**: only where the question isn't enough: painter (Wikidata
  link, name as printed), Iconclass notation (text from iconclass.org, link
  into the tree), depicted subject (Wikidata link, to tell namesakes apart),
  the audit statement. Zustand and Datierung have none (value in the question
  or the options).
- **Textstelle**: »quote« (S. pages), the single link into the article: the
  lab page with a `#:~:text=` fragment.
- **Image**, last and unlabelled: the scan from the lab
  (`/images/x/xy/<file>`, found via the `[[:File:…|A]]` links, the captions,
  or caption ranges like `A1–4`), else P18 of an existing painting. Como shows
  lab images through its proxy. Prompts without an image just lose the block.
  Because the image comes last, no labels shift.

The volume is the same on every prompt, so it is not a block. The long
description names it with a link to its Wikidata item, says the page is
added from the passage, and explains how to decide (what counts as Yes/No,
what each option means). Every reference is `P248 %var_volume%` +
`P304 %var_pages%`. Requires Como with `var_*` columns and `trigger_option`
(migration 0052).

### 8. Hand over and run order

1. Run `create.qs` in QuickStatements.
2. `placeholders.py lookup --map placeholders.tsv --apply` (finds new items by
   unique German label + description) or fill the `qid` column by hand.
3. Rerun `build.py`: created items are now used by QID everywhere — the game
   CSVs and `direct.qs` no longer contain placeholders.
4. Run `direct.qs`. Review `curator.qs`.
4a. Write the QIDs into the articles and re-upload them:
   ```bash
   S=.claude/skills/extract-cbd-to-wd-skill/scripts
   uv run python $S/apply_qids.py write --out data/wikidata/{Band} --articles data/cleaned-with-skill-v2/{Band}          # dry run
   uv run python $S/apply_qids.py write --out data/wikidata/{Band} --articles data/cleaned-with-skill-v2/{Band} --apply
   uv run python -m src.mediawiki.upload_pages --articles data/cleaned-with-skill-v2/{Band}
   ```
   Reconciled items are written at once; created ones after step 2. A
   `CONFLICT` (the template already has another qid) is never overwritten —
   resolve it by hand. For claims files written before refs existed,
   `apply_qids.py link` suggests the refs (`--apply` writes them; it lists
   ambiguous items for you to settle).
5. Create the games from `games/*.json`, upload the CSVs, ask for activation.
   Games may be played on placeholders for testing only (unlisted): their
   actions would fail.

## Settled decisions

- Maße `a × b` = length × width; height only when written as `Höhe`.
- No items for picture cycles or room sequences; members are linked directly.
- Never add `P10626`.
- One claim per Como prompt; certainty is chosen by players, not copied from
  the model.
