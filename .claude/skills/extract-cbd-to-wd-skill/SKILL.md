---
name: extract-cbd-to-wd-skill
description: "Use when asked to extract structured data from CbDD article text (Corpus der barocken Deckenmalerei) for Wikidata — painters, dates, patrons, patron saints, techniques, depicted subjects — e.g. 'extract the data from this article', 'make Wikidata statements for Band05'. DRAFT: the target data model is not final yet."
---

# Extract CbDD data for Wikidata

> **Status: draft.** The user will specify the exact scope, target items and
> output format. Until then, follow the defaults below and ask before writing
> anything to Wikidata or producing large batches.

## Input

Cleaned articles (output of `clean-cbd-skill`, target folder named by the
user), falling back to `data/formatted/{Band}/{Lemma}.wiki`. Read them with
`articles.helpers.parse_article_file`; the `{{Artikel …}}` template already
gives `Band`, `Originalseitenvon/-bis`, `Lemma`, `Typ`, `Ort`, `AutorIn1–6`.
Skip articles with a non-empty `|Meta=`.

## What the sections hold

| Section | Candidate data |
|---|---|
| Lemma / first line | building, place, former function (`Ehem. …`, `z. Z. …`) |
| `'''Patrozinium:'''` | patron saint(s) → dedicated to |
| `'''Zum Bauwerk:'''` | construction dates, architect, room form |
| `'''Auftraggeber:'''` | commissioning person/institution, years in office |
| `'''Autor und Entstehungszeit:'''` | painter(s), stuccator(s), life dates, date of the paintings, signature vs. attribution (certain / probable / uncertain) |
| `== Befund ==` | technique (Fresko / Secco / Öl), carrier, frame, measurements per field, restorations with years |
| `== Beschreibung (und Ikonographie) ==` | per field (A, B, D<sub>1</sub> …): title, depicted subjects, inscriptions, Bible references, emblem sources |
| `== Quellen und Literatur ==` | references (archives, literature) |

## Defaults until specified

- Every extracted value keeps its evidence: the quoted sentence, the field
  identifier, and the CbDD reference (Band, printed page) — for use as a
  Wikidata reference (`stated in` + `page(s)`).
- Keep the authors' certainty: `zugeschrieben`, `wohl`, `vermutlich` → mark as
  uncertain, never as fact.
- Match people/places to existing items before proposing new ones (see the
  `normdata-search` and `agentic-reconcile` skills; deckenmalerei.eu ID is
  P10626).
- Output to a file in a folder the user names; nothing is sent to Wikidata
  without explicit confirmation.

## Open questions (to be filled in)

- Which entities become items: building, room, individual ceiling painting
  (per field), or all three?
- Which properties and qualifiers (e.g. creator P170, inception P571,
  made from material P186, depicts P180, commissioned by P88, dedicated to
  P825, described by source P1343)?
- Output format: QuickStatements, JSON, CSV for OpenRefine?
- Items for the 15 CbDD volumes to cite as source.
