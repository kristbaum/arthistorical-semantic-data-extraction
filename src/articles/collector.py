"""Concatenate all pass1 pages per band and write a per-band CSV into data/splitting/.

For each band this produces:
  data/splitting/{BandXX}/{BandXX}.wiki   – all pass1 pages concatenated
  data/splitting/{BandXX}/{BandXX}.csv    – CSV rows for that band only

Run the splitter (src.articles.splitter) afterwards to cut articles out of
the concatenated files.
"""

import csv

from .helpers import REPO_ROOT
from .page_index import build_ordered_files

SPLITTING_DIR = REPO_ROOT / "data" / "splitting"


def clean_content(text: str) -> str:
    """Strip leading/trailing blank lines."""
    lines = text.split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def collect_band(
    band_prefix: str,
    band_articles: list[dict],
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> bool:
    """Concatenate pass1 pages and write band CSV into data/splitting/.

    Returns True if files were written (or would be written in dry-run mode).
    """
    ordered_files = build_ordered_files(band_prefix)
    if not ordered_files:
        if verbose:
            print(f"  SKIP {band_prefix} — no pass1 files")
        return False

    # ── Concatenate all pages ────────────────────────────────────────────────
    parts = [text for _path, text in ordered_files]
    full_text = "\n".join(parts)

    out_dir = SPLITTING_DIR / band_prefix
    wiki_path = out_dir / f"{band_prefix}.wiki"
    csv_path = out_dir / f"{band_prefix}.csv"

    if dry_run:
        print(
            f"  WOULD WRITE: {wiki_path.relative_to(REPO_ROOT)}  ({len(full_text)} chars, {len(ordered_files)} pages)"
        )
        print(
            f"  WOULD WRITE: {csv_path.relative_to(REPO_ROOT)}  ({len(band_articles)} rows)"
        )
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text(full_text + "\n", encoding="utf-8")
        if verbose:
            print(
                f"  WROTE: {wiki_path.relative_to(REPO_ROOT)}  ({len(full_text)} chars, {len(ordered_files)} pages)"
            )

        # Write band CSV (strip internal keys)
        clean_rows = [
            {k: v for k, v in row.items() if not k.startswith("_")}
            for row in band_articles
        ]
        if clean_rows:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=clean_rows[0].keys())
                writer.writeheader()
                writer.writerows(clean_rows)
            if verbose:
                print(
                    f"  WROTE: {csv_path.relative_to(REPO_ROOT)}  ({len(clean_rows)} rows)"
                )

    return True
