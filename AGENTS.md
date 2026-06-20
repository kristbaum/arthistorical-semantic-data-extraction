# AGENTS.md

Guidance for working on the CbDD (*Corpus der barocken Deckenmalerei in
Deutschland*) digitisation scripts under `src/`. For the wiki file/section
layout and OCR quirks, see the `cbdd-wiki-format` skill in
`.claude/skills/cbdd-wiki-format/`.

## Data layout (the two trees)

- **`data/extracted/{Band}_chunk{NNN}/wiki/p{NNN}.wiki`** — one file per PDF
  page. Iterated with chunk/page-aware ordering (`band_chunk_key`,
  `page_sort_key` in `src/articles/helpers.py`). Used by the `count_*` scripts.
- **`data/formatted/{Band}/{Lemma}.wiki`** — one file per article, grouped by
  band. This is the tree most pipeline steps operate on.

## Iterating over formatted articles — use the shared helpers

Do **not** re-implement the `for band: glob("*.wiki")` boilerplate. Every script
that walks the formatted tree uses these helpers from
[`src/articles/helpers.py`](src/articles/helpers.py):

```python
from articles.helpers import (
    formatted_band_prefixes,   # band dirs, sorted; or just [band] when given
    iter_formatted_articles,   # yields every article .wiki path, ordered
    parse_article_file,        # -> (template_block, fields, body)
)

# all bands, or one with --band
for path in iter_formatted_articles(args.band):
    text = path.read_text(encoding="utf-8")
    template_block, fields, body = parse_article_file(text)
    ...
```

- `iter_formatted_articles(band=None, *, base=OUTPUT_DIR)` — yields paths ordered
  by band then filename. Pass `base=` to point at a different root (run_pass2's
  `--input-dir`).
- `formatted_band_prefixes(band=None, *, base=OUTPUT_DIR)` — the band-selection
  logic for a `--band` CLI flag (returns the single band, or all of them).
- `parse_article_file(text)` — splits the `{{Artikel …}}` template from the body.

Current consumers: `src/run_pass2.py`, `src/articles/format_articles.py`,
`src/articles/check_headers.py`, `src/format/postprocess.py`.

## Script conventions

- **Dry-run by default.** A `--apply` flag writes to disk; without it, only
  report what *would* change.
- Optional `--band BANDXX` restricts a run to one band.
- Read/write UTF-8. Preserve a trailing newline.
- Run modes differ by package:
  - root scripts: `python src/run_pass2.py …` (relies on `src/` being on
    `sys.path`, so imports read `from articles.helpers import …`).
  - `articles` package: `python -m src.articles.check_headers …` (relative
    imports, `from .helpers import …`).
  - A standalone script in `src/format/` that needs the helpers must add `src/`
    to `sys.path` first — see `main()` in `src/format/postprocess.py`.

## Deterministic vs. LLM formatting

`src/format/postprocess.py` holds the **deterministic** MediaWiki cleanups
(spaces before punctuation, blank-line normalisation, one blank line around
`== headings ==`). Anything needing language judgment stays in the LLM prompt in
`run_pass2.py`. Keep that split: if a rule can be a regex/line transform, move it
to `postprocess.py` rather than asking the model.

`postprocess.py` is both imported (by `run_pass2`) and runnable standalone over
the whole formatted tree:

```bash
python src/format/postprocess.py                 # dry-run, all bands
python src/format/postprocess.py --band Band01 --apply
```

When run standalone it normalises only the article **body**; the
`{{Artikel …}}` template is left byte-for-byte unchanged.
