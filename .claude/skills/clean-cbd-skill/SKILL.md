---
name: clean-cbd-skill
description: "Use when asked to clean, correct, proofread or finish formatting CbDD articles (Corpus der barocken Deckenmalerei) from data/formatted/ — one article, a list of lemmas, or a whole band — and write the result to a target folder. Goes beyond the run_pass2 LLM prompt: fixes OCR errors by cross-checking both OCR sources, removes running headers and page-break debris, rejoins split sentences, normalises section labels, Befund tables, identifiers (A<sub>1</sub>), bibliographies and captions, and verifies nothing was lost. Trigger on 'clean this article', 'fix Band05', 'pass 2 by hand', 'proofread the CbDD text'."
---

# Clean CbDD articles

Turns an article from `data/formatted/{Band}/{Lemma}.wiki` into the cleanest
faithful MediaWiki text possible. It starts from the pass-2 prompt in
`src/run_pass2.py` (`PROMPT_TEMPLATE`, rules 1–7) and adds everything else that
can be fixed by reading the text against its sources.

Read the `cbdd-wiki-format` skill for the file layout if you have not yet.

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

For more than ~5 articles, work one article at a time and report progress per
band; offer to fan a large run out over subagents (one band each) only if the
user wants that.

---

## 2. Gather the sources for each article

The formatted body is the base text. For any doubtful word, consult the two
page-level OCR sources the body was merged from:

| Source | Path | Character |
|---|---|---|
| Surya OCR (wiki) | `data/extracted/{Band}_chunk{NNN}/wiki/p{NNN}.wiki` | good layout, images, `†`/`*` usually kept |
| Transkribus OCR | `data/extracted/{Band}_chunk{NNN}/add_txt/{NNNN}_p{NNN}.txt` | custom-trained model, better letters; keeps line breaks, `¬` hyphens, page header in line 1 |
| LLM pass 1 | `data/extracted/{Band}_chunk{NNN}/pass1/p{NNN}.wiki` | merged result, may contain LLM slips |

Locate the pages from the template: `|Chunk=` → `chunk{NNN}` (zero-padded to
3), `|Chunkseite=` → first page `p{NNN}`. The article continues on the
following pages; `|Originalseitenvon=`/`|Originalseitenbis=` give the printed
range, and the `<!-- citation-page-top/bottom: … -->` comments in the page
files map PDF pages to printed pages. `[[File:Band01_chunk007_p007_img001.jpg]]`
names tell you which PDF page an image sits on — a quick way to find the right
page for a passage.

Read only the passages you need to resolve; do not re-transcribe the article.
When the two OCRs disagree and neither is clearly right, keep the formatted
text and log the spot (see §5).

---

## 3. Cleaning rules

The `{{Artikel …}}` template is copied **byte for byte**. Only the body is
edited. Rules 3.1–3.7 are the original pass-2 prompt; the rest go further.

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
One `* ` bullet per entry. Unprinted sources (archives) come first, as in the
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
- `[[File:…]]`: filename and options never change. Caption text (after the
  last `|`) may get the same OCR, dash and `<sub>` fixes as the body
  (`D Der Teich Bethesda D1-4` → `D Der Teich Bethesda D<sub>1–4</sub>`).
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
  `[[File:…]]` line to the next paragraph boundary. Keep image order.
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
Do not add a label the article lacks and do not reorder sections.

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
- names, dates and numbers, unless an OCR source proves the misreading.

---

## 4. Procedure per article

1. Read the article; note template fields (Band, Chunk, Chunkseite, pages).
2. Edit the body by rules 3.1–3.10, consulting the page sources for doubtful
   spots. Write the result to the target path.
3. Apply the deterministic cleanups (spaces before punctuation, blank lines,
   one blank line around `== headings ==`):
   ```python
   import sys; sys.path.insert(0, "src")
   from articles.helpers import parse_article_file
   from articles.postprocess import postprocess
   tpl, _, body = parse_article_file(text)
   text = tpl.rstrip("\n") + "\n\n" + postprocess(body) + "\n"
   ```
4. Verify:
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
   OCR fix). Anything else is a mistake — restore it.

---

## 5. Report

Keep `{target}/_cleaning_report.md`, one section per article, only for things
a human must look at:

```markdown
## Band01 / Andechs, Ehem. Benediktinerabtei, Ehem. Klosterapotheke
- CHECK p008: »F<sub>3</sub> ist kein Emblem« — the book probably means F<sub>4</sub>; left as printed.
- UNSURE p007: »Luc: 10. U 34.« read as »Luc. 10,34«.
- FOREIGN: last paragraph »G1 … Misere.« may belong to the next article.
```

Never put such notes into the article itself. Finish with a short summary to
the user: articles cleaned, skipped (meta / existing), failed checks, and the
number of report entries.

---

## Gotchas

- Run Python via `uv run python` (no bare `python` on this machine).
- The `<sub>` range uses an en dash: `D<sub>1–4</sub>`, not `D<sub>1-4</sub>`.
- Band directories with parts: `Band03-1`, `Band12-2`; their template `Band=`
  values are `31`, `122`.
- Preserve the trailing newline; files are UTF-8.
- Deterministic rules you find yourself applying over and over belong in
  `src/articles/postprocess.py` — suggest moving them there (see `AGENTS.md`).
