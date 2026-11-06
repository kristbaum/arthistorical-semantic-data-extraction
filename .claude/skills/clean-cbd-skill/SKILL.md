---
name: clean-cbd-skill
description: "Use when asked to clean, correct, proofread or finish formatting CbDD articles (Corpus der barocken Deckenmalerei) from data/formatted/ — one article, a list of lemmas, or a whole band — and write the result to a target folder. Goes beyond the run_pass2 LLM prompt: fixes OCR errors by cross-checking both OCR sources, removes running headers and page-break debris, rejoins split sentences, normalises section labels, Befund tables, identifiers (A<sub>1</sub>) and bibliographies, locates every image on the page scan to fix its position and restore lost captions, links identifiers to their images, and verifies nothing was lost. Opens the scan only where the OCRs contradict each other or the layout is in doubt. Trigger on 'clean this article', 'fix Band05', 'pass 2 by hand', 'proofread the CbDD text'."
---

# Clean CbDD articles

Turns an article from `data/formatted/{Band}/{Lemma}.wiki` into the cleanest
faithful MediaWiki text possible. It starts from the pass-2 prompt in
`src/run_pass2.py` (`PROMPT_TEMPLATE`, rules 1–7) and adds everything else that
can be fixed by reading the text against its sources.

For the band/chunk/page file layout and the page-comment metadata, see
`AGENTS.md` in the repo root.

**The prime directive: this is an edition of a printed book.** Correct what the
OCR and the layout broke; never change what the authors wrote. No new content,
no paraphrase, no modernised spelling, no expanded abbreviations.

---

## 1. Settle the job before touching anything

1. **Input** — a lemma, a list of lemmas, a band (`Band05`), or all bands.
   Resolve to paths with the shared helpers (see `AGENTS.md`):
   ```python
   import sys; sys.path.insert(0, "src")
   from articles.helpers import iter_formatted_articles, parse_article_file
   ```
2. **Target folder** — the user names it. If they did not, ask (one question,
   suggest `data/cleaned/`). Output mirrors the input tree:
   `{target}/{Band}/{Lemma}.wiki`. Never write into `data/formatted/` unless the
   user explicitly names it as the target.
3. **Skip** articles with a non-empty `|Meta=` (Register, Vorwort, Malerliste …)
   unless the user asks for them; they need different rules.
4. **Resume** — if `{target}/{Band}/{Lemma}.wiki` already exists, skip it unless
   the user says to redo.

For more than ~5 articles, work one article at a time; offer to fan a large
run out over subagents (one band each) only if the user wants that.

### Work quietly

The user reads the report and the final summary, not a running commentary.
While cleaning:
- **No narration between tool calls.** Don't announce each step ("Now running
  ocr_diff…", "Let me read the captions sheet…"), don't explain decisions
  that go by the rules, don't restate what a script printed.
- **Never echo article text, diffs, edit lists or script output** into chat.
  Findings go into `_cleaning_report.md` (§5), nowhere else.
- **Progress**: at most one short line per finished article
  (`Aich — done, 4 report entries`), and for runs over ~5 articles one line
  per band instead.
- Speak up mid-run only to ask the one question from step 2 above, or when
  something blocks the run (a script crashes, a source is missing, a
  `check_preservation.py` FAIL you cannot fix).
- Keep shell output small: pipe long outputs through `tail`/`grep` when you
  only need the result lines (e.g. on a whole-band `check_preservation.py`
  run, look only at the files that are not `[OK]`).

---

## 2. Gather the sources for each article

The formatted body is the base text. For any doubtful word, consult the
page-level sources the body was merged from:

| Source | Path | Character |
|---|---|---|
| Surya OCR (wiki) | `data/extracted/{Band}_chunk{NNN}/wiki/p{NNN}.wiki` | good layout, images, `†`/`*` usually kept; drops bold labels, `<!-- header: … -->` comments mark running heads |
| Transkribus OCR | `data/extracted/{Band}_chunk{NNN}/add_txt/{NNNN}_p{NNN}.txt` | custom-trained model, better letters and punctuation; keeps line breaks, `¬` hyphens, page header in line 1 |
| LLM pass 1 | `data/extracted/{Band}_chunk{NNN}/pass1/p{NNN}.wiki` | merged result — **the usual origin of LLM slips** (e.g. a changed year) |
| Page scan | `data/extracted/{Band}_chunk{NNN}/pages/{Band}_chunk{NNN}_p{NNN}.jpg` | the printed spread itself, 300 dpi; the final authority — but expensive to read, see §2.1 |
| Image crops | wiki `File:{Band}_chunk{NNN}_p{NNN}_img{NNN}.jpg`, cached in `data/cache/wiki_images/` | what each `[[File:…]]` shows; located on the scan by `page_images.py` (§2.2) |

`{NNNN}` is the same page number as `p{NNN}`, padded to 4 (`0010_p010.txt`).

**Find the pages with the helper**, don't work them out by hand:
```bash
uv run python .claude/skills/clean-cbd-skill/scripts/find_sources.py \
    "data/formatted/{Band}/{Lemma}.wiki"
# compare all readings of a doubtful passage (regex, case-insensitive):
uv run python .claude/skills/clean-cbd-skill/scripts/find_sources.py \
    "data/formatted/{Band}/{Lemma}.wiki" --grep "Fresken von \d+"
```
It matches the printed range (`|Originalseitenvon=`–`|Originalseitenbis=`)
against the `<!-- citation-page-top/bottom: … pNN -->` comments, lists every
PDF page with the paths of all four sources, and with `--grep` prints the
matching snippet from each OCR source side by side. Facts behind it:
- Each PDF page is a **two-page spread** (e.g. `p010` = printed S. 18/19).
- `|Chunkseite=` is **not reliable** as the first page — in Band01 it is one
  higher than the PDF page the article starts on, elsewhere it matches.
- An article can run into the next chunk; the helper checks it too.
- `[[File:Band01_chunk007_p007_img001.jpg]]` names tell you which PDF page an
  image sits on.

Transkribus quirks seen so far: line order is sometimes **reversed** for a
column next to an image (read the block bottom-up); subscript digits come out
as letters (`Ai`/`Al` = A1, `Az` = A2, `As` = A3 or A5); captions appear as
loose lines among the text. Surya quirks: lost periods (`St Martin`), `1.30`
for `1,30`, truncated words (`woh`).

**Get the disagreements, don't read both OCR pages in full:**
```bash
uv run python .claude/skills/clean-cbd-skill/scripts/ocr_diff.py \
    "data/formatted/{Band}/{Lemma}.wiki"
```
It aligns Surya against Transkribus for every page of the article and prints
only where they differ, restricted to the article's own text:
- `WORD` — a small disagreement with context (`[1.30]` vs `[1,30]`,
  `[A4]` vs `[Al]`). Known harmless differences are already filtered out:
  case, spacing, dash and `×` style, rejoined hyphens, and Transkribus' letter
  for a subscript digit when it agrees with Surya (`Ai` = A1, `Az` = A2,
  `As` = A3/A5). Disagreements the article already resolved the way
  Transkribus reads them are only counted in the `TOTAL` line. Each shown
  line ends with `(article = surya)` — check whether Transkribus is right — or
  `(article: other)` — the article follows neither OCR, often a pass-1 slip
  (a changed year, an inserted word): look at it first.
- `BLOCK` — a longer stretch only one OCR has, or that the two read
  differently: a caption read into the text, a skipped line, a reversed
  column. This is a layout question.
- `ORDER` — the same text in a different reading order (Transkribus often
  interleaves the two columns line by line); ignore.

**Check every `BLOCK` where Surya has `∅` or a few tokens and Transkribus a
full sentence: Surya often drops lines at page breaks and next to images,
and the article inherited the gap.** Grep the article for the Transkribus
words; if they are missing, restore them from Transkribus (`RESTORED` in the
report; verify numbers on a crop). Band01 Andechs Klosterkirche lost three
passages this way (»das [bedeutendste Heiltum von Andechs. Sie ist mit einem]
Mantel umkleidet«, »Die Wappen ver[sinnbildlichen …]«). Signs in the article
itself: a sentence or word cut off before an image or a heading (`… das`,
`… Die Wappen ver`), or a phrase that does not parse (`zusammen mit einer
Art Thronaufbau bildet`).

The article has usually been built from Surya's reading order, so a page with
many `ORDER` stretches and a few layout `BLOCK`s is normal and not a reason to
open the scan by itself.

Read only the passages you need to resolve; do not re-transcribe the article.
When both OCRs agree against the formatted text, follow the OCRs — the
formatted text then carries a pass-1 slip — and log it if it is a number or
name. When the two OCRs disagree, decide from context first (§2.1).

### 2.1 When to look at the page scan

Reading a whole spread costs about as many tokens as the article text itself,
so the scan is **not** checked by default. Open it only when one of these
holds and context cannot settle it:

1. **The OCRs contradict each other on something that matters** — a number,
   date, measurement, name, the subscript of an identifier (`A4` vs `Al`),
   `†`/`*`, a word only one OCR has, punctuation that changes the meaning.
   Not for disagreements where one reading is plainly a non-word
   (`Bildthena`, `MDK`) — fix those from the other OCR without looking.
2. **The layout is in question** — a `BLOCK` that touches the article's text,
   a sentence that seems to continue elsewhere, an entry whose order differs
   between the OCRs and the formatted text, text that may belong to the
   neighbouring article, a garbled caps title both OCRs share (`S./JOSEPH`).

Captions and image positions are always checked, but through the cheap
`page_images.py` outputs (§2.2), not the full scan.

How to look:
1. For **layout questions**, read the **overview** from §2.2
   (`…_overview.jpg`, ~2.3k tokens) — it shows which half and column a
   passage is in. Large print (Befund labels, signatures) is often readable
   there too.
2. For **small print** (subscripts, `†`, punctuation, digits, one word in a
   quotation) **crop** the spot at full resolution instead of reading the
   whole scan — sharper (the whole spread is downscaled when read) and
   ~0.5–1.5k tokens instead of ~4.8k:
   ```bash
   uv run python .claude/skills/clean-cbd-skill/scripts/scan_crop.py \
       data/extracted/{chunk}/pages/{chunk}_p{NNN}.jpg --col R1 --rows 0.2,0.31
   # or --box x1,y1,x2,y2 as fractions of the spread; columns L1 L2 R1 R2
   ```
   Then Read `data/cache/page_images/{chunk}_p{NNN}_crop.png`. Locate the
   rows from the overview or from the line position in the Transkribus file
   (line 96 of ~110 → near the bottom). If you miss, move the window — a
   second small crop is still cheaper than the full scan.
3. The scan wins over both OCRs. Fix the text to what is printed and write
   `SCAN pNNN: …` in the report so the reviewer knows it was checked.
4. Check only the doubtful spots — never proofread the whole page against it.

`find_sources.py` shows the scan path in its `scan` line, or `—` when there is
none. Without a scan, decide from the OCRs and log doubtful spots as before.

### 2.2 Locating the images (every article with `[[File:…]]`)

```bash
uv run python .claude/skills/clean-cbd-skill/scripts/page_images.py \
    "data/formatted/{Band}/{Lemma}.wiki"
```
It downloads the crops the article embeds from the wiki, finds each one on its
page scan (score ≥ 0.6 is a sure match; anything lower is flagged), and
prints per image the printed page (`L`/`R` half of the spread), its box and
the caption the article currently has. It writes per page into
`data/cache/page_images/`:

- `{chunk}_{pNNN}_captions.png` — **always read this.** One strip per image:
  the printed line(s) directly under it at full resolution — the caption as
  the book prints it. Small and cheap.
- `{chunk}_{pNNN}_overview.jpg` — the spread downscaled with every image boxed
  and labelled `img001`, `img002` … Read it when an image's position in the
  text is unclear (§3.11) or for a layout question (§2.1).

Reading the sheet:
- The caption is the short line in small type that starts with the identifier
  (`A₂ Johannes`). A strip may also catch a line of body text or a page
  number below it — ignore those.
- A strip with no text means the caption is beside or above the image, the
  image shares a caption with its neighbour (two medallions side by side under
  one `B₁₋₂ Verkündigung`), or it has none (floor plans) — look at the
  overview before deciding.
- A caption can also stand to the lower right of a tall image, so the strip
  only catches its edge (Fürstenzimmer p006 img003 `A₂ Genius`) — look at the
  overview.
- In the overview, look for **pictures without a red box**: Surya missed them
  (Band01 Aich p010: the `A₁ Matthäus` medallion has no crop). They cannot be
  added — log `MISSING`.
- Look also for **red boxes that do not fit a picture** — a crop that cuts
  across two pictures and the text column. Keep the image (the set must not
  change), give it no caption and log `BADCROP` so it can be re-cropped.
- One crop can hold **two pictures** (a fresco with the cartouche below it, two
  medallions side by side); the book then prints their captions side by side
  under it.

---

## 3. Cleaning rules

The `{{Artikel …}}` template is copied **byte for byte**. Only the body is
edited. Rules 3.1–3.7 are the original pass-2 prompt; the rest go further.
(§3.10 "abbreviations … separate, later pass" means: never *expand* them in
the text. Tagging them with `{{Abk|…}}`, §3.12, is not an expansion.)

### 3.1 Line breaks (pass-2 rule 1)
Join paragraphs broken by the column layout into running text. Rejoin
hyphenated words (`Chrono-gramm`, `Moos¬müller` → `Chronogramm`, `Moosmüller`)
but keep real compound hyphens (`Hell-Dunkel-Kontrasten`, `Barock-Stuck`).

### 3.2 Punctuation (pass-2 rule 2)
- Add a missing sentence-final period.
- Dashes: `–` (en dash) for parenthetical dashes and for ranges:
  years `1759–67`, pages `S. 203–07`, Bible verses `Tob 11,13–15`, field
  ranges `D–G`, `B–C`. Leave hyphens in compounds.
- Quotations `»…«`, nested `›…‹`. Convert stray `"…"`/`„…“` to `»…«`.
- `×` (not `X`/`x`) between dimensions: `7,95 × 4,75 m`.
- Restore lost `†` and `*` in life dates: `(*1735 München †1791 München)`,
  `(Profeß 1758 †1797)` — check the Surya page, which usually kept them.
- Spaces: `z. Z.`, `z. B.`, `S. 334 f.`, `Bd 1` (as printed — the book writes
  `Bd` without a period), no space before `,.;:!?`, one space after.

### 3.3 Befund: Maße as a table (pass-2 rule 3)
Only when there is more than one measurement line. Keep the label line
(`'''Maße:'''` or `'''Maße (lichte Maße):'''`) before the table.
```
'''Maße:'''
{| class="wikitable"
|-
! Bereich !! Höhe !! Maße
|-
| A || 3,70 m || 1,80 × 1,80
|-
| B–C || 3,10 m || 1,95 × 2,15
|}
```
Add a column only when the data needs it (`Stich` for domes, `Bemerkung` for
trailing text like `Durchmesser` or `im Lichten`). A measurement that was
split across lines or pages belongs in one row. No other part of Befund
becomes a table.

### 3.4 Field identifiers (pass-2 rule 4, extended)
- Letter + number → subscript: `A1` → `A<sub>1</sub>`, `D1-4` →
  `D<sub>1–4</sub>`, `G1` → `G<sub>1</sub>`. Applies everywhere: Befund,
  Beschreibung, running text, captions. Do not double-format existing `<sub>`.
- Plain letters (`A`, `B`, `W`) stay plain.
- An entry that opens a description paragraph gets its ALL-CAPS title in
  bold: `D '''DER TEICH BETHESDA''' Im Mittelgrund …`,
  `A<sub>1</sub> '''HIMMELFAHRT CHRISTI''' …`.
- Each such entry starts its own paragraph. If two entries were run together
  (`… Bibliothek. D<sub>3</sub> Abluor non Obruor …`), split them.
- A standalone caps line that introduces a group (`EMBLEME.`, `STUCK`,
  `ORNAMENTMALEREI`) becomes `=== Embleme ===` (title case, no period).

### 3.5 Quellen und Literatur as bullets (pass-2 rule 5, extended)
One `* ` bullet per entry. `finalize.py` puts a bullet on every line of the
section, so you only need to split run-together entries onto their own lines
(and leave label lines like `Zum Bauwerk:` alone). Unprinted sources
(archives) come first, as in the
book. Entry boundaries: an author name (`Gruber, Max, …`), a known short
title (`Mayer-Westermayer`, `KDB`, `Thieme-Becker`, `Dehio`), or an archive
siglum (`BHStA`, `StAM`, `AEM`, `PfA`, `HStAM`, `BayHStA`, `KAM`, `StadtA`).
A run like `… Fasz. 15 A und 15 B StAM, LRA 34569; 34583.` is two entries:
`BHStA …` and `StAM, LRA 34569; 34583.` Sub-lists headed `Zum Bauwerk:` /
`Zur Ausstattung:` stay as label lines with their bullets below.

### 3.6 Signatures (pass-2 rule 6)
Remove the author initials at the very end (`C.B.`, `H.B.`). The authors are
in the template already.

### 3.7 Keep existing markup (pass-2 rule 7)
- `[[File:…]]`: filename and `thumb` never change. The caption follows §3.11.
  Only exception: images of a series move into a `<gallery>` (§3.11
  "Series"), where they lose the `[[…|thumb|` wrapper but keep filename and
  caption.
- Do not rename `== headings ==` except for plain OCR errors
  (`== Befnnd ==` → `== Befund ==`). The book's own titles (`== Beschreibung ==`
  in early bands vs `== Beschreibung und Ikonographie ==`) stay as they are.
- Keep `<sub>`, `<sup>`, `'''…'''`, `<br>` inside quotations, `{{…}}`.
- Remove OCR garbage (meaningless character/number runs).

### 3.8 Page-break and layout debris (new)
- **Running page headers**: a line that is only a place name in caps
  (`ASCHERING`, `ANDECHS`) or a leftover `<!-- header: … -->` sits where a
  page broke. Delete it and join the sentence it interrupted
  (`… kein symbolischer Verweis ASCHERING vorhanden ist` → `… Verweis
  vorhanden ist`). Also delete bare page numbers and footer lines.
- **Sentences split by an image or page break**: rejoin them and move the
  `[[File:…]]` line to where §3.11 puts it.
- **Citation split across lines**: `Luc: 10. U` + `34. wiedergegebene` →
  `Luc. 10,34 wiedergegebene` — verify against the OCR page.
- **Text from a neighbouring article** (the head of the next lemma, or the
  tail of the previous one) — do not delete; log it in the report (§5).

### 3.9 Section labels (new)
The inline labels are bold with the colon inside, content on the same line:
`'''Patrozinium:'''`, `'''Zur Geschichte:'''`, `'''Zum Bauwerk:'''`,
`'''Auftraggeber:'''`, `'''Autor und Entstehungszeit:'''`, and inside Befund
`'''Träger der Deckenmalerei:'''`, `'''Rahmen:'''`, `'''Technik:'''`,
`'''Maße:'''`, `'''Erhaltungszustand und Restaurierungen:'''`. Fix OCR-broken
labels (`Auftragqeber`, `Zum Bauwcrk`) and labels that lost their bold.
Some early articles print just `Erhaltungszustand:` — bold it, don't extend it.
Each Befund label starts its own paragraph (a blank line between them —
single line breaks are joined by MediaWiki). Labels run into the previous
line (`stuckierte Flachdecke Rahmen · Stuckprofil`, `Öl auf Leinwand Maße: …`,
`… 1,60 × 1,00 Erhaltungszustand und Restaurierungen: Das …`) are split off.
Do not add a label the article lacks and do not reorder sections.
Befund lines that are OCR garbage (`T-1 1 F 1 1 1 cemin. Tresno, poryentom
Mala …`) are rebuilt from Transkribus and checked on a crop.

### 3.10 OCR word errors (new)
Fix letters the OCR misread when the right word is certain — from context
plus at least one of the OCR sources: `rn`↔`m`, `l`/`I`/`1`, `ii`→`ü`,
`c`↔`e`, `fi`/`ff` ligatures, `ſ`→`s`, split words (`Stichkap pen` →
`Stichkappen`), glued words (`imChor` → `im Chor`).
Chronograms are deliberate mixed case (`P. FeLIXpharMaCopaeVs`) — leave them.

**Never touch** — even if it looks wrong:
- the authors' 1976–2010 orthography (`läßt`, `Profeß`, `daß`, `Jh.s`),
- quotations from sources: Latin, Baroque German, inscriptions, archival
  spellings (`Churcöllnischen Hofmallern`, `Kürchen`, `bezalt`) — only fix a
  quote if an OCR source shows a different reading,
- abbreviations (`KDB`, `Bd`, `fl.`, `frdl. Mitt.`) — expanding them is a
  separate, later pass,
- names, dates and numbers, unless an OCR source or the scan proves the
  misreading. Even an implausible printed date stays as printed — log it
  instead (Band01 Adelshausen: »Fresken von 1795« by Anwander, †1770).

### 3.11 Images: captions, position, links (new)

Over half the images in the corpus have no caption, and existing captions
are often **on the wrong image**: Surya matched them to the nearest crop, so
whole runs are shifted by one (Band01 Aich: the caption of img002 sat on
img001, that of img004 on img003). Captions carry the identifier that ties an
image to its description, so check **every** caption against the
`…_captions.png` sheet (§2.2) — the present ones too, not just the missing.

**Captions**
- Write the caption as printed under the image, after the last `|`:
  `[[File:Band01_chunk001_p011_img001.jpg|thumb|A<sub>1</sub> Himmel]]`.
  Apply the body rules: subscripts (`A1` → `A<sub>1</sub>`, ranges
  `D<sub>1–4</sub>`), dashes, OCR fixes. Keep the book's wording and case
  (`St. Joseph`, not the caps title of the entry).
- A wrong caption (`Joseph W`, or another image's caption) is replaced by the
  printed one; a missing one is added. Each change is a `CAPTION` line in the
  report.
- One printed caption under two adjacent images goes on the image it is
  printed under; the other gets none (`NOCAPTION … shares caption`).
- Two captions printed side by side under one crop that holds both pictures
  are joined with `; `:
  `S<sub>1</sub> Die Stola des hl. Johannes; S<sub>b</sub> Putti mit …`.
  The image goes to the entry of the first identifier.
- If the strip shows no caption and the overview shows none either, leave the
  image without one and log `NOCAPTION`. Never invent a caption from the
  description text.
- A caption that is unreadable in the strip: keep what the article has (or
  nothing) and log `UNSURE`.

**Position**
- An image whose caption starts with an identifier goes directly **after the
  paragraph of that entry** (`[[File:…|thumb|A<sub>2</sub> Gericht]]` after
  the `A<sub>2</sub> Ein Engel …` paragraph). Not after a paragraph that only
  mentions the identifier.
- An entry can run over several paragraphs (entry A of a large fresco often
  does); its images go after the last of them, before the next entry.
- Several images for one entry stay together, in file order. A group heading
  entry (`A<sub>1–4</sub> ALLEGORISCHE DARSTELLUNGEN`) does not pull the
  single images — each goes to its own entry. If the single fields have no
  entries of their own (`A<sub>1–4</sub> EVANGELISTENBILDER … Matthäus (A1),
  Johannes (A2) …`), their images go after the group paragraph.
- When the article has a separate `== Ikonographie ==` section repeating the
  entries, images go to the entry in `== Beschreibung ==`.
- Floor plans (`Übersicht in Höhe des Kirchenraums`, or no caption) go to the
  end of `== Befund ==`, after Erhaltungszustand. So does the single image of
  an article with one fresco and no identifiers (Fürstensaal: »Das
  Wittelsbacher Wappen«) — never inside the Befund list.
- Other images without an identifier (general views, details) stay where the
  book prints them: after the paragraph that precedes them in reading order
  on the page (use the overview). Never between two halves of a sentence.
- An image whose entry is not in this article (it shows a neighbouring
  article's fresco) stays in the file — the image set must not change — at
  the end of the body; log it as `FOREIGN`.
- Entries marked `(keine Abbildung)` have no image; that is expected.

**Series → gallery**
- A series is ≥ 2 images of fields that belong together and are short entries
  of one group: the same letter with subscripts (`A<sub>1</sub>`–`A<sub>4</sub>`
  Zwickel, `M<sub>1–8</sub>` medallions, `W<sub>1</sub>`/`W<sub>2</sub>`), or
  images the book prints side by side in a row (overview). A main fresco with
  its `Ausschnitt`/`Detail` views is **not** a series — those stay `thumb`s.
- Put the whole series in one gallery, in identifier order (`A1, A2, A3, A4`,
  not file order), after the **last** entry of the series — or after the
  group paragraph when the fields have no entries of their own. This replaces
  the "after its own entry" rule for these images.
- Each image keeps its caption exactly as §3.11 "Captions" says, so it shows
  under the picture; a series image without a printed caption gets just the
  identifier (`File:…|A<sub>3</sub>`) — that is the printed label, not an
  invented caption — and is still logged `NOCAPTION`.
  ```
  <gallery mode="packed" heights="160">
  File:Band01_chunk001_p011_img001.jpg|A<sub>1</sub> Himmel
  File:Band01_chunk001_p011_img002.jpg|A<sub>2</sub> Gericht
  </gallery>
  ```
  `mode="packed"` shows the captions under the images (never use
  `packed-hover` / `packed-overlay`, which hide them). No `thumb`, no `[[ ]]`,
  one `File:` line per image, no blank lines inside.
- Log each gallery as `GALLERY <identifiers>` in the report.

**Links** — don't type them. `finalize.py` (§4 step 4) builds them from the
captions (`[[File:…|thumb|…]]` and gallery lines alike): every entry head in the Beschreibung section and every subscripted
identifier in the body (`in A<sub>2</sub>`) becomes
`[[:File:Band01_chunk001_p011_img002.jpg|A<sub>2</sub>]]` — a link to the
image's file page. A field with several images links to its first full view,
not to an `Ausschnitt`/`Detail`. Plain letters outside entry heads
(`Fresko B`, often another building), ranges and identifiers without an image
stay unlinked. Links are rebuilt from the captions on every `finalize.py`
run, so after a caption fix just run it again.

### 3.12 Abbreviations: `{{Abk|…}}` (new)

The book's glossary ([[Zur Benutzung]] on the Lab: general abbreviations,
Bible books, bibliographic short titles) is in `Modul:Abk/Daten`, kept in the
repo as `templates/Modul-Abk-Daten.lua`. `{{Abk|LHs}}` shows `LHs` with the
full form as a tooltip; bibliographic short titles also link to the
glossary section.

**Don't type them.** `finalize.py` (§4 step 4) runs `tag_abk.py`, which wraps
the **first occurrence per article** of every glossary key, exactly as
spelled in the table (`LKr.`, `z. Z.`, `Mayer-Westermayer`, `Lc` before
`1,26`). It skips quotations, links, bold titles, headings and `<sub>`, and
applies the context rules from the data (Bible books only before chapter
numbers, `f.`/`v.` only after a number, `F.`/`H.` only before one). Keys
marked `manuell` (`S`, `W`, `O`, `x`) are never tagged automatically.

What stays with you:
- Fix the OCR form of an abbreviation first (`LKr ,` → `LKr.`, `Bd.` as
  printed stays `Bd.`, which is *not* the key `Bd` and stays untagged). The
  tagger only finds exact keys.
- Add `{{Abk|S}}` / `{{Abk|W}}` / `{{Abk|O}}` by hand only where the letter
  is plainly a compass point (`Fenster von O und SO`). Never for field
  identifiers — they are linked to their images (§3.11). Picture-field codes
  can be written `{{Abk|EB|typ=Bildfeld}}`, but leave them plain unless
  asked.
- A wrongly tagged spot (a German word that happens to match): unwrap it and
  log `ABK` in the report so the context rule can be tightened.
- An abbreviation the book uses that is missing from the table: leave it
  plain and log `ABK missing: …` — new keys are added in
  `src/mediawiki/build_abk_data.py` (`BIBL_EXTRA` for other volumes'
  bibliographies), not in the article. Never write `{{Abk|…}}` for an
  unknown key; it would land in `Kategorie:Unbekannte Abkürzung`.

---

## 4. Procedure per article

1. Read the article. Run `ocr_diff.py` (§2) for the doubtful spots and, if
   the article has images, `page_images.py` (§2.2) and read the captions
   sheet. `find_sources.py --grep` gives the full readings of one spot when
   the diff context is too short.
2. Decide which spots need the scan by §2.1 — usually none or a few per
   article — and look at those (overview for layout, crop for small print).
3. Edit the body by rules 3.1–3.11 as a **list of exact replacements**
   applied to a copy of the original — never retype the article. Writing
   out the cleaned text is the largest cost of the whole skill (output
   tokens); the formatted text is already mostly right, so the edits are a
   fraction of its length. Typical edits: move an image line (delete it in
   one edit, insert it after its entry in another), fix a caption, rejoin a
   sentence split by an image, bold an entry title, subscript identifiers,
   build the Maße table.
   Write the edits to a file in the scratchpad first, then apply — if one
   edit fails, fix that block in the file instead of resending the list, and
   chain the following steps with `&&` so they do not run on a missing file:
   ```bash
   cat > "$SCRATCH/lemma.edits" <<'EOF'
   <<<
   Kapitelle und

   [[File:Band01_chunk008_p010_img001.jpg|thumb|A Ausschnitt Westseite: Sturz der Häretiker]]

   Balustraden
   ===
   Kapitelle und Balustraden
   >>>
   <<<
   A MARIA VOM SIEGE – TRIUMPH ÜBER SÜNDE UND SÜNDENSTRAFEN Das
   ===
   A '''MARIA VOM SIEGE – TRIUMPH ÜBER SÜNDE UND SÜNDENSTRAFEN''' Das
   >>>
   EOF
   S=.claude/skills/clean-cbd-skill/scripts
   uv run python $S/apply_edits.py "$SRC" "$TARGET" "$SCRATCH/lemma.edits" \
     && uv run python $S/finalize.py "$TARGET" \
     && uv run python $S/check_preservation.py "$SRC" "$TARGET"
   ```
   Each `old` must occur exactly once (add context until it does) and is
   matched against the **article**, not against the diff output — copy it
   from the article text (the diff shows Surya's reading, which may differ).
   Edits apply in order; if any fails, nothing is written. The template is
   never touched. A stretch of raw, unjoined OCR inside an article (lines
   with `¬`) is replaced as one block; only an article that needs rewriting
   throughout is written out in full.
4. Apply the deterministic cleanups (spaces before punctuation, blank lines,
   one blank line around `== headings ==`, bibliography bullets, trailing
   newline), build the identifier links from the captions (§3.11) and tag
   the abbreviations (§3.12):
   ```bash
   uv run python .claude/skills/clean-cbd-skill/scripts/finalize.py "$TARGET"
   ```
5. Verify:
   ```bash
   uv run python .claude/skills/clean-cbd-skill/scripts/check_preservation.py \
       "data/formatted/{Band}/{Lemma}.wiki" "{target}/{Band}/{Lemma}.wiki"
   # or a whole run:
   uv run python .claude/skills/clean-cbd-skill/scripts/check_preservation.py \
       --orig-root data/formatted --clean-root {target} --band {Band}
   ```
   `FAIL` (template changed, image lost/added, length off by >25 %) must be
   fixed. For `CHECK` lines, every lost or added word/number must be
   explainable by a rule above (removed header, signature, rejoined hyphen,
   OCR fix, restored caption). Anything else is a mistake — restore it.
   `WARN images reordered` is expected when §3.11 moved images — confirm each
   move follows a caption identifier or the printed reading order.

---

## 5. Report

Keep `{target}/_cleaning_report.md`, one section per article, only for things
a human must look at:

```markdown
## Band01 / Andechs, Ehem. Benediktinerabtei, Ehem. Klosterapotheke
- CHECK p008: »F<sub>3</sub> ist kein Emblem« — the book probably means F<sub>4</sub>; left as printed.
- UNSURE p007: »Luc: 10. U 34.« read as »Luc. 10,34«.
- FOREIGN: last paragraph »G1 … Misere.« may belong to the next article.
- SCAN p008: »A<sub>4</sub>« (Surya) vs »Al« (Transkribus) — scan shows A<sub>4</sub>.
- CAPTION p011 img003: »Joseph W« → »W<sub>1</sub> St. Joseph« (from scan).
- NOCAPTION p012 img002: no caption printed.
- LOWMATCH p013 img001: not found on the scan (score 0.41) — position not checked.
- ABK p014: »Mal 3« is the noun, not Malachias — unwrapped.
- RESTORED p023: »… das bedeutendste Heiltum von Andechs. Sie ist mit einem …« — line dropped by Surya, from Transkribus.
- MISSING p024: photo »S<sub>4</sub> Hl. Michael« has no crop.
- BADCROP p024 img002: crop cuts across two cartouches and the text.
```

Never put such notes into the article itself. Finish with a short summary to
the user — a few lines, no per-edit detail: articles cleaned, skipped (meta /
existing), failed checks, the number of report entries, and the path to the
report.

---

## Gotchas

- Run Python via `uv run python` (no bare `python` on this machine).
- The `<sub>` range uses an en dash: `D<sub>1–4</sub>`, not `D<sub>1-4</sub>`.
- Band directories with parts: `Band03-1`, `Band12-2`; their template `Band=`
  values are `31`, `122`.
- Preserve the trailing newline; files are UTF-8.
- `== Quellen und Literatur ==` in early bands, where the book prints just
  `Literatur`, comes from an earlier normalisation step — keep it, don't
  revert it.
- Image captions are often garbled (`Joseph W`) or missing. Restore them from
  the `…_captions.png` sheet (§2.2, §3.11); never invent one.
- Garbled caps titles (`S./JOSEPH`) that both OCRs share: settle them with the
  scan (§2.1 case 2). Band01 Adelshausen p011 really prints `S./JOSEPH` and
  `S./ANNA` in italics — keep such printed forms.
- `page_images.py` needs network access to the wiki the first time per image;
  crops are cached in `data/cache/wiki_images/` afterwards. An image that is
  not on the wiki cannot be located — log it as `LOWMATCH`.
- Spread scans are landscape (`page L`/`R`); a few chunks have single-page
  scans (portrait, `page -`).
- Pass-1 slips to look for (they show up as `(article: other)` in the diff):
  inserted connector words before an entry head (Band01 Aich:
  »Dementsprechend A MARIA VOM SIEGE …« — not in the book), changed years
  (Adelshausen »1695« for printed »1795«), normalised names in quotations
  (signature »Mathee Gindter« made »Mattheus«).
- A page break inside a hyphenated word can come out as a finished word plus a
  stray fragment at the top of the next paragraph:
  »… bezeichnen.« / »nen (Ripa, s. v. perfidia); …« → »… bezeichnen (Ripa …«.
  A paragraph that starts with a lowercase fragment is the sign.
- `ocr_diff.py` output is large for long multi-page articles (~1–2k tokens
  per page); read it once and work from the `(article: other)` lines first.
- `postprocess()` once ate the spaces before `!!` in wikitable headers. That is
  fixed now, but if a table header ever comes out as `! Bereich!! Höhe`,
  check `_SPACE_BEFORE_PUNCT_RE` in `src/articles/postprocess.py`.
- Deterministic rules you find yourself applying over and over belong in
  `src/articles/postprocess.py` — suggest moving them there (see `AGENTS.md`).
