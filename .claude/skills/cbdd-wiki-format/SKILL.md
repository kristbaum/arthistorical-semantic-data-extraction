---
name: cbdd-wiki-format
description: "Use when: working with CbDD wiki files, writing scan/fix scripts for .wiki files, analyzing article sections like Befund or Autor und Entstehungszeit, understanding page/chunk/band file layout, or authoring new count_*.py / format scripts for this project."
---

# CbDD Wiki Format Knowledge

## Project Background

**CbDD** = *Corpus der barocken Deckenmalerei in Deutschland* — 15 printed volumes
(1976–2010) covering all baroque ceiling paintings in Upper Bavaria. The goal is to
digitise and structure all ~3,127 pages as MediaWiki articles for
[deckenmalerei.eu](https://www.deckenmalerei.eu).

Volumes are named **Band 1–14 + Gesamtindex**. Band 3 and Band 12 are each split
into two parts (`Band03-1`, `Band03-2`, `Band12-1`, `Band12-2`).

---

## File System Layout

```
data/extracted/
└── {Band}{part?}_chunk{NNN}/     e.g. Band01_chunk003, Band03-1_chunk002
    └── wiki/
        └── p{NNN}.wiki           e.g. p001.wiki … p120.wiki
```

- **Band** directory names: `Band01` … `Band14`, `Band03-1`, `Band03-2`,
  `Band12-1`, `Band12-2`
- **Chunks** subdivide each volume's PDF into manageable segments (~20–60 pages each)
- **Pages** correspond 1-to-1 with PDF pages; numbering is zero-padded to 3 digits
- Sort order for processing: Band number → Band sub-part → chunk number → page number

### Python sort key for chunk directories

```python
import re
def band_chunk_key(chunk_dir):
    m = re.match(r"Band(\d+)(?:-(\d+))?_chunk(\d+)", chunk_dir.name)
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3))) if m else (999, 999, 999)
```

---

## Wiki Page Structure

Each `.wiki` file is a single PDF page in MediaWiki markup. A fully structured
article page looks like this (order is top → bottom):

```mediawiki
<!-- dropbox: https://www.dropbox.com/preview/.../Band01_chunk001.pdf#page=5 -->
<!-- citation-page-top: Band01 p12 -->

<!-- header: ORTSNAME -->

[[File:Band01_chunk001_p005_img001.jpg|thumb|Caption text]]

Fließtext / running prose …

== Quellen und Literatur ==

Bibliographic entries …

Zum Bauwerk: …
Patrozinium: …
Auftraggeber: …

**Autor und Entstehungszeit:** Full attribution sentence …
(no space before closing **)

== Befund ==

Träger der Deckenmalerei: …
Rahmen: …
Technik: …
Maße (lichte Maße): …
Erhaltungszustand und Restaurierungen: …

== Beschreibung und Ikonographie ==

Detailed iconographic description …

[[File:Band01_chunk001_p005_img002.jpg|thumb|Caption]]
<!-- citation-page-bottom: Band01 p13 -->
```

### HTML comment metadata

| Comment | Meaning |
|---|---|
| `<!-- dropbox: URL -->` | Direct PDF page link for source verification |
| `<!-- citation-page-top: Band01 p12 -->` | Original printed book page number (top of page) |
| `<!-- citation-page-bottom: Band01 p13 -->` | Original printed book page number (bottom of page) |
| `<!-- header: ORTSNAME -->` | Repeated page-header text from the printed book (location name) |

---

## Standard Article Sections

Articles describe a **single church or secular building** containing baroque
ceiling paintings. The expected sections, in order:

| Section | Format | Notes |
|---|---|---|
| Patrozinium | inline prose or `== Patrozinium ==` heading | Patron saint(s) of the building |
| Zum Bauwerk | inline prose | Architectural description |
| Auftraggeber | inline prose | Commissioning patron |
| **Autor und Entstehungszeit** | `**Autor und Entstehungszeit:** <text>` | Attribution of the artist(s) and date. Inline bold prefix, no space before closing `**`, rest of content on same line. **Target format.** |
| **Befund** | `== Befund ==` | Technical survey: carrier, frame, technique, dimensions, conservation state. Standalone `== heading ==`. **Anchor section.** |
| Beschreibung und Ikonographie | `== Beschreibung und Ikonographie ==` | Iconographic description |
| Quellen und Literatur | `== Quellen und Literatur ==` | Sources and bibliography |
| Photographische Dokumentation | `== Photographische Dokumentation ==` | Photo credits |
| Planskizzen | `== Planskizzen ==` | Floor plan sketches |

---

## Known OCR / Formatting Variants

Because OCR is imperfect, section markers appear in many broken forms. Scripts
must fuzzy-match them (Levenshtein distance thresholds tested in production):

---


## Shared Script Conventions

All `count_*.py` scripts follow these patterns:

- `repo_root = Path(__file__).parent` — repo root is always the script's parent
- `wiki_files = sorted(repo_root.rglob("*.wiki"))` — or use `build_ordered_wiki_files()` for chunk-aware order
- `DRY_RUN = not args.apply` — default is dry-run; `--apply` writes to disk
- `from Levenshtein import distance as levenshtein` — python-Levenshtein package
- Files are read/written as UTF-8
- Output lines are joined with `"\n"` and a trailing newline is preserved if the
  original had one: `"\n".join(lines) + ("\n" if text.endswith("\n") else "")`

---

## Image File Naming

Images embedded in wiki pages follow:
```
Band{NN}_chunk{NNN}_p{NNN}_img{NNN}.jpg
```
Example: `Band13_chunk002_p009_img003.jpg` — Band 13, chunk 2, page 9, image 3.

---

## Stats (as of March 2026)

| Metric | Value |
|---|---|
| Total `.wiki` files | 3,127 |
| Total words | ~2,347,256 |
| Total characters | ~16,934,886 |
| Exact `== Befund ==` matches | 853 |
| Bands | 14 volumes + index (Band03 and Band12 in two parts each) |
