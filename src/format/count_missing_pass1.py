#!/usr/bin/env python3
"""Count missing pass1 pages by comparing with existing wiki/ pages per chunk.

For each Band*_chunk* directory, lists wiki/*.wiki files that have no
corresponding pass1/*.wiki sibling.
"""

from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
extracted_dir = repo_root / "data" / "extracted"

total_wiki = 0
total_pass1 = 0
total_missing = 0
missing_by_band: dict[str, int] = {}

for chunk_dir in sorted(extracted_dir.iterdir()):
    if not chunk_dir.is_dir() or not chunk_dir.name.startswith("Band"):
        continue

    wiki_dir = chunk_dir / "wiki"
    pass1_dir = chunk_dir / "pass1"

    if not wiki_dir.is_dir():
        continue

    wiki_files = sorted(wiki_dir.glob("p*.wiki"))
    pass1_files = {f.name for f in pass1_dir.glob("p*.wiki")} if pass1_dir.is_dir() else set()

    total_wiki += len(wiki_files)
    total_pass1 += len(pass1_files)

    missing = [f for f in wiki_files if f.name not in pass1_files]
    if missing:
        band = chunk_dir.name.split("_chunk")[0]
        missing_by_band[band] = missing_by_band.get(band, 0) + len(missing)
        total_missing += len(missing)
        print(f"{chunk_dir.name}: {len(missing)} missing pass1 files")
        for f in missing:
            print(f"    {f.name}")

print("\n--- Summary ---")
print(f"Total wiki pages:   {total_wiki}")
print(f"Total pass1 pages:  {total_pass1}")
print(f"Total missing:      {total_missing}")

if missing_by_band:
    print("\nMissing by band:")
    for band, count in sorted(missing_by_band.items()):
        print(f"  {band}: {count}")
