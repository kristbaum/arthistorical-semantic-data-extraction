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

The formatted body is the base text. For any doubtful word, consult the
page-level sources the body was merged from:

| Source | Path | Character |
|---|---|---|
| Surya OCR (wiki) | `data/extracted/{Band}_chunk{NNN}/wiki/p{NNN}.wiki` | good layout, images, `†`/`*` usually kept; drops bold labels, `<!-- header: … -->` comments mark running heads |
| Transkribus OCR | `data/extracted/{Band}_chunk{NNN}/add_txt/{NNNN}_p{NNN}.txt` | custom-trained model, better letters and punctuation; keeps line breaks, `¬` hyphens, page header in line 1 |
| LLM pass 1 | `data/extracted/{Band}_chunk{NNN}/pass1/p{NNN}.wiki` | merged result — **the usual origin of LLM slips** (e.g. a changed year) |
| Page scan | `data/scans/{Band}_chunk{NNN}/p{NNN}.{png,jpg,…}` | the printed page itself; the final authority (see §2.1) |

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

Read only the passages you need to resolve; do not re-transcribe the article.
When the two OCRs disagree and neither is clearly right, check the scan
(§2.1); without a scan, keep the formatted text and log the spot (see §5).
When both OCRs agree against the formatted text, follow the OCRs — the
formatted text then carries a pass-1 slip — and log it if it is a number or
name.

### 2.1 Checking the page scan

Scans of the printed pages will be placed in `data/scans/` (one folder per
chunk, one image per PDF page, named like the page: `p010.png`). Another
location can be set with the environment variable `CBDD_SCAN_DIR`.
`find_sources.py` shows the scan path in its `scan` line, or `—` when there is
none yet.

When a scan exists:
1. Open it with the Read tool (it displays images). The image holds both
   printed pages of the spread, two columns each; find the passage by its
   neighbouring words or by the image next to it.
2. Use it to settle what the OCRs cannot: numbers and dates, the subscript in
   `A1`/`A4`, punctuation at line ends, `†`/`*`, missing captions, garbled
   titles (`S./JOSEPH`), a word only one OCR reads.
3. The scan wins over both OCRs. Fix the text to what is printed and write
   `SCAN pNNN: …` in the report so the reviewer knows it was checked.
4. Check the scan only for the doubtful spots — don't proofread the whole
   page against it.

If there is no scan, nothing else changes: decide from the OCRs and log
doubtful spots as before.

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
- names, dates and numbers, unless an OCR source or the scan proves the
  misreading. Even an implausible printed date stays as printed — log it
  instead (Band01 Adelshausen: »Fresken von 1795« by Anwander, †1770).

---

## 4. Procedure per article

1. Read the article and run `find_sources.py` on it (§2) to get the page
   list. Read the Surya and Transkribus pages of the article once — short
   articles fit on 2–3 pages — and note the doubtful spots.
2. Edit the body by rules 3.1–3.10; resolve doubtful spots with
   `find_sources.py --grep` and the scan (§2.1). Write the result to the
   target path. To keep the template byte-identical, copy it rather than
   retyping it:
   ```bash
   sed -n '1,/^}}$/p' "$SRC" > "$TARGET"   # template only
   cat >> "$TARGET" <<'EOF'
   
   …cleaned body…
   EOF
   ```
3. Apply the deterministic cleanups (spaces before punctuation, blank lines,
   one blank line around `== headings ==`, trailing newline):
   ```bash
   uv run python .claude/skills/clean-cbd-skill/scripts/finalize.py "$TARGET"
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
- `== Quellen und Literatur ==` in early bands, where the book prints just
  `Literatur`, comes from an earlier normalisation step — keep it, don't
  revert it.
- Image captions are often garbled (`Joseph W`) or missing. Fix them only from
  an OCR source or the scan, and never invent a caption; otherwise log it.
- Garbled caps titles (`S./JOSEPH` for `ST. JOSEPH`) that both OCRs share:
  keep them and log them, or settle them with the scan.
- `postprocess()` once ate the spaces before `!!` in wikitable headers. That is
  fixed now, but if a table header ever comes out as `! Bereich!! Höhe`,
  check `_SPACE_BEFORE_PUNCT_RE` in `src/articles/postprocess.py`.
- Deterministic rules you find yourself applying over and over belong in
  `src/articles/postprocess.py` — suggest moving them there (see `AGENTS.md`).
