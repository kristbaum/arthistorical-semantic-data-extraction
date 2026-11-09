# Arthistorical Semantic Data Extraction

A comprehensive pipeline designed to extract semantic triplets from arthistorical texts using advanced natural language processing and knowledge graph alignment techniques. This project bridges the gap between unstructured art historical texts and structured semantic data, enabling researchers to discover relationships and patterns in art historical knowledge.

## Overview

This pipeline processes arthistorical texts to extract meaningful semantic relationships in the form of triplets (subject-predicate-object), which are then aligned with Wikidata entities to ensure consistency and interoperability with existing knowledge graphs.

## Repository layout

```text
.
├── src/
│   ├── ocr/               # Step 1–2: PDF → page images → Surya layout/OCR → per-page wiki
│   ├── run_pass1.py       # Step 4: LLM merge of Surya wiki + Transkribus text (per page)
│   ├── articles/          # Step 5–7: collect, mark, split into articles; article-level fixes/checks
│   ├── format/            # Page-level fix/count scripts (count_*.py, fix_pass1_metadata, …)
│   ├── run_pass2.py       # Step 8: LLM cleanup of each article body
│   ├── mediawiki/         # Step 9: upload images, sync articles, create categories
│   ├── dropbox_links.py   # Step 3: add Dropbox + citation-page comments to wiki pages
│   ├── move_additional_ocr.py  # Step 3: move Transkribus OCR into data/extracted/*/add_txt
│   └── format_chunks.py   # Legacy: early Ollama formatting of whole text chunks
├── data/
│   ├── pdf_chunked/       # Source scans, split into chunks: {Band}_chunk{NNN}.pdf
│   ├── raw/               # Input folder read by pdf_to_images.py (and legacy .txt chunks)
│   ├── extracted/{Band}_chunk{NNN}/
│   │   ├── pages/         # Full-page JPGs (300 dpi)            – gitignored
│   │   ├── images/        # Picture/Figure crops from Surya     – gitignored
│   │   ├── processed_images/  # Margin-trimmed crops            – gitignored
│   │   ├── wiki/p{NNN}.wiki   # Surya OCR output, one file per PDF page
│   │   ├── add_txt/       # Transkribus OCR text per page
│   │   └── pass1/p{NNN}.wiki  # LLM-merged page (Pass 1)
│   ├── splitting/{Band}/  # {Band}.wiki (all pass1 pages), {Band}.csv, {Band}_split.wiki (with markers)
│   ├── formatted/{Band}/{Lemma}.wiki  # One file per article – main working tree
│   ├── pass2/{Band}/{Lemma}.wiki      # Pass 2 LLM output
│   ├── cleaned-with-skill-v2/{Band}/{Lemma}.wiki  # Articles cleaned with clean-cbd-skill (+ _cleaning_report.md)
│   ├── wikidata/{Band}/   # extract-cbd-to-wd-skill: claims/*.json, QS batches, games, refs.tsv, placeholders.tsv
│   └── meta/              # Liste_Bände.csv (article list per band), Hauptseite, Struktur notes
├── .claude/skills/        # clean-cbd-skill, extract-cbd-to-wd-skill (instructions + scripts)
├── templates/             # MediaWiki templates and Lua modules: Artikel, BandString, BildQuelle,
│                          #   Abk (+ Modul-Abk*.lua), Entität (+ Modul-Entität.lua, Entität-styles.css)
├── examples/              # Sample pages and files.csv
├── batch_pass1.sh / batch_pass2.sh / submit.sh   # SLURM jobs for the LRZ cluster (see LRZ_USAGE_GUIDE.md)
├── excel_to_csv.py        # Liste_Bände.xlsx → data/meta/Liste_Bände.csv
├── result_table.py        # Aggregate statistics over data/formatted/
├── count_wiki.py          # Word/char counts across all .wiki files
├── pipe_to_wikitable.py   # Convert pipe-separated lines into a wikitable
└── assemble_articles.py   # Legacy single-step article assembly (replaced by src/articles/)
```

## Pipeline steps

| # | Step | Script | Input → Output |
|---|------|--------|----------------|
| 0 | Article metadata | `excel_to_csv.py` | `Liste_Bände.xlsx` → `data/meta/Liste_Bände.csv` |
| 1 | Split PDF chunks into page images | `src/ocr/pdf_to_images.py` | `data/raw/{Band}_chunk{NNN}.pdf` → `data/extracted/{chunk}/pages/{chunk}_p{NNN}.jpg` |
| 2 | Layout detection, image extraction, OCR | `src/ocr/surya_pipeline.py` (uses `surya_layout`, `surya_ocr`, `surya_mediawiki`, `surya_models`, `surya_config`) | `pages/` → `images/`, `wiki/p{NNN}.wiki` |
| 2b | Trim white margins of crops | `src/ocr/preprocess_images.py` | `images/` → `processed_images/` |
| 3 | Add Transkribus OCR | `src/move_additional_ocr.py` | `data/additional_ocr/…` → `extracted/{chunk}/add_txt/` |
| 3b | Citation/page comments | `src/dropbox_links.py` (+ `src/format/shift_band10_pages.py` for Band10) | edits `wiki/p{NNN}.wiki` in place |
| 4 | **Pass 1** – LLM merge Surya + Transkribus | `src/run_pass1.py` (cluster: `submit.sh batch_pass1.sh`) | `wiki/` + `add_txt/` → `pass1/p{NNN}.wiki` |
| 4b | Pass 1 repairs | `src/format/fix_pass1_metadata.py`, `src/articles/fix_zitat.py`, `src/format/count_missing_pass1.py` | fixes `pass1/` |
| 5 | Collect pages per band | `python -m src.articles.assemble` (`collector.py`) | `pass1/` → `data/splitting/{Band}/{Band}.wiki` + `.csv` |
| 6 | Insert article markers | `python -m src.articles.marker_inserter`, then check with `src.articles.fix_split` | → `{Band}_split.wiki` (review manually) |
| 7 | Split into articles | `python -m src.articles.splitter` | `_split.wiki` → `data/formatted/{Band}/{Lemma}.wiki` |
| 7b | Deterministic article fixes | `src.articles.format_articles`, `normalize_structure`, `check_headers`, `check_bib_tail`, `fix_linebreaks`, `format_register_tables`, `src/articles/postprocess.py`; checks: `check_ort`, `check_pages` | edits `data/formatted/` |
| 8 | **Pass 2** – LLM article cleanup | `src/run_pass2.py` (cluster: `submit.sh batch_pass2.sh`) | `data/formatted/` → `data/pass2/{Band}/` |
| 9 | Publish to MediaWiki | `python -m src.mediawiki.upload_images`, `sync_articles`, `create_categories` (`list_files` exports uploaded files) | → deckenmalerei-lab wiki |

Most fix scripts are dry-run by default and write only with `--apply`; `--band BandXX` restricts a run to one band (see [AGENTS.md](AGENTS.md)).

## Cleaning and reconciliation pipeline

After step 7, articles can be finished by hand with the help of two Claude Code skills instead of Pass 2. The skills hold the instructions; deterministic scripts do everything that needs no judgment. The result is an edited article whose building, rooms, people and paintings carry stable ids, Wikidata statements cited to the printed volume, and QIDs written back into the article.

```text
data/formatted/{Band}/          ──clean-cbd-skill──▶  data/cleaned-with-skill-v2/{Band}/
                                                          │  {{Abk}}, {{Entität|…|id=…}}
                                                          ▼
                                  extract-cbd-to-wd-skill ──▶  data/wikidata/{Band}/
                                                          │  claims/*.json (item → ref), *.qs, games
                                                          ▼
                     QuickStatements / Como  ──▶  new items  ──▶  placeholders.tsv (qid)
                                                          │
                                  apply_qids.py write ◀───┘   qid= set on {{Entität|…|id=…}}
                                                          │
                                  upload_pages.py ────────▶  deckenmalerei-lab wiki
```

### 1. Clean (`.claude/skills/clean-cbd-skill`)

Turns `data/formatted/{Band}/{Lemma}.wiki` into a faithful edition of the printed text. Trigger: "clean Band01" / "clean this article". Main tasks:

- OCR fixes by cross-checking the Surya and Transkribus readings; the page scan only where they disagree.
- Remove what splitting the volumes left behind (the next article's heading at the end, book-part titles, running headers) and normalise headings and labels — formatting only, no section is renamed.
- Images: correct captions from the scan, positions after their entry, series as galleries.
- Mark entities with `{{Entität}}` — the building (first sentence), rooms with paintings, persons (Auftraggeber, Maler, Stuckateur, Baumeister, Stecher, Kistler, Vergolder, Person) and paintings (with `titel` and `bild`) — once per entity.
- Tag the book's own abbreviations with `{{Abk}}`; generic ones (St., S., vgl., hl. …, `generisch = true` in `templates/Modul-Abk-Daten.lua`) stay plain.

| Script (`.claude/skills/clean-cbd-skill/scripts/`) | Does |
|---|---|
| `find_sources.py`, `ocr_diff.py`, `page_images.py`, `scan_crop.py` | gather OCR readings, image positions and scan crops |
| `check_headings.py` | leftover headings, entry headings, labels (`--apply` for the safe formatting fixes) |
| `apply_edits.py` | apply the model's list of exact replacements to a copy |
| `finalize.py` | `postprocess()`, bibliography bullets, `{{Entität}}` for building and paintings (`entities.py`), a stable `id` for every `{{Entität}}` |
| `tag_abk.py` | wrap non-generic abbreviations in `{{Abk}}` |
| `check_preservation.py` | verify no word, number or image was lost |

```bash
S=.claude/skills/clean-cbd-skill/scripts
uv run python $S/apply_edits.py "$SRC" "$TARGET" edits.txt \
  && uv run python $S/check_headings.py "$TARGET" --apply \
  && uv run python $S/finalize.py "$TARGET" \
  && uv run python $S/check_preservation.py "$SRC" "$TARGET"
uv run python $S/tag_abk.py "$TARGET" --apply
```

`{{Entität}}` ids (8 characters a-z0-9) are assigned once and never changed — they are the key between an article spot and its Wikidata item.

### 2. Extract and reconcile (`.claude/skills/extract-cbd-to-wd-skill`)

Reconciles buildings and people against Wikidata and the deckenmalerei.eu dump and writes one claims file per article (`data/wikidata/{Band}/claims/<slug>.json`) with the verbatim passage behind every statement. Each item notes the `id` of its `{{Entität}}` as `"ref"` (`cbdd_lookup.py article` lists them). `build.py` derives everything else:

| Output | Content |
|---|---|
| `create.qs`, `direct.qs`, `curator.qs` | QuickStatements batches, referenced to volume and page; `{NEW:…}` placeholders for items still to be created |
| `games/*.json` + `.csv` | Como games for interpretive statements (painter, dating, Iconclass, depicted subjects) |
| `claims.tsv` | every statement with route, passage, lab link and `entity_ref` / `value_ref` |
| `refs.tsv` | ref → lemma, item, QID or placeholder |
| `placeholders.tsv` | placeholder → label, description, QID once created |

### 3. Write QIDs back and publish

```bash
X=.claude/skills/extract-cbd-to-wd-skill/scripts
uv run python $X/placeholders.py lookup --map data/wikidata/Band01/placeholders.tsv --apply   # after running create.qs
uv run python $X/apply_qids.py write --out data/wikidata/Band01 --articles data/cleaned-with-skill-v2/Band01          # dry run
uv run python $X/apply_qids.py write --out data/wikidata/Band01 --articles data/cleaned-with-skill-v2/Band01 --apply
uv run python -m src.mediawiki.upload_pages --articles data/cleaned-with-skill-v2/Band01
```

`apply_qids.py write` sets `qid=` on the `{{Entität}}` whose `id` matches an item's ref; it never overwrites a different existing QID (reported as `CONFLICT`) and lists refs still waiting for their item. `apply_qids.py link` adds refs to claims files written before refs existed.

`src/mediawiki/upload_pages.py` is interactive: it asks for a normal wiki account (no bot password), logs in via `clientlogin`, shows which pages are new or changed and uploads after confirmation. Besides the articles it uploads the Lua modules (`templates/Modul-*.lua` → `Modul:…`), stylesheets (`*-styles.css` → `Vorlage:…/styles.css`) and templates (`*.template` → `Vorlage:…`).

The [deckenmalerei-lab-skill](https://github.com/kristbaum/deckenmalerei-lab-skill) documents the resulting article format (labels, `{{Abk}}`, `{{Entität}}`, heading variants) for research questions against the wiki.

## Features

- **Multi-model LLM support**: Leverage different language models for text parsing and entity extraction
- **Wikidata alignment**: Automatically align extracted entities with Wikidata entries
- **Human-in-the-loop validation**: Export results to CSV for manual review and correction
- **Flexible input formats**: Support for various text formats and sources
- **Semantic triplet extraction**: Extract relationships between artworks, artists, movements, and historical contexts

## Pipeline Architecture

The pipeline consists of three main stages:

### 1. Text Parsing with LLM Models

- **Input**: Raw arthistorical texts (books, articles, exhibition catalogs)
- **Process**: Natural language processing using configurable LLM models
- **Output**: Structured entities and relationships
- **Supported Models**:
  - GPT-3.5/GPT-4 (OpenAI)
  - Claude (Anthropic)
  - Local models via Ollama
  - Custom fine-tuned models

### 2. Wikidata Alignment

- **Input**: Extracted entities from stage 1
- **Process**: Entity linking and disambiguation using Wikidata API
- **Output**: Aligned semantic triplets with Wikidata QIDs
- **Features**:
  - Fuzzy matching for entity names
  - Confidence scoring for alignments
  - Fallback strategies for unmatched entities

### 3. Export and Validation

- **Input**: Aligned semantic triplets
- **Process**: Format results for human review
- **Output**: CSV files with validation columns
- **Features**:
  - Confidence scores for each triplet
  - Source text references
  - Validation status tracking

### Sample Output

The pipeline generates CSV files with the following structure (later a snippet of the text source will be included here):

| text1 | text1_link | text2 | text2_link | text3 | text3_link |
| --------- | ----------- | --------- | ------------- | --------------- | ------------ |
| Gut Altenkamp | <https://www.wikidata.org/wiki/Q668492> | commissioned by | <https://www.wikidata.org/wiki/Property:P88> | Hermann Anton Bernhard von Velen | <https://www.wikidata.org/wiki/Q61658390> |
| Gut Altenkamp | <https://www.wikidata.org/wiki/Q668492> | street address | <https://www.wikidata.org/wiki/Property:P6375> | Am Altenkamp 1, 26871 Papenburg | |

## Prompt hints for formatting

Clean and format this scanned German art historical text. Fix line breaks, obvious OCR errors and remove random, wrongly scanned headlines, text from maps or artwork, or image captions in the text.

- Fehler bei hochgestellten und tiefgestellten Nummern und Buchstaben beheben. (am häufigsten) Fehler im Index sind rießig
- X bei Centimeter Angaben sollten klein sein
- Durchmesser und durchschnitt Symbole sowie Kreuze werden nicht erkannt (häufiger)
- Zitate nicht korrigieren
- Falsch erkannt circonflexe anstatt UmlautmarkeireungFix

## After First Setup

```bash
  salloc -p lrz-v100x2 --gres=gpu:1 --time=01:00:00  # 1-hour limit
  srun --pty bash
  enroot start --mount /your/data/path:/workspace/data llm-workspace
  ollama serve &
  cat > mistral_format.py << 'EOF'
  (Copy and paste the content of mistral_format)
  chmod +x mistral_format.py
  python mistral_format.py
```

sbatch batch_format_container.sh "/dss/dsshome1/02/USERNAME_HERE/Band01_chunk001_full.txt" "/dss/dsshome1/02/USERNAME_HERE/Band01_chunk001_formatted.md"

tail -f log_5393747.out

sbatch batch_format.sh "/dss/dsshome1/02/USERNAME_HERE/arthistorical-semantic-data-extraction/data/raw/Band01_chunk001_full.txt" "/dss/dsshome1/02/USERNAME_HERE/arthistorical-semantic-data-extraction/data/formatted/Band01_chunk001_formatted.md"

SBATCH --container-image=docker://nvcr.io/nvidia/pytorch:25.10-py3

‘docker://nvcr.io#nvidia/pytorch:25.10-py3’
