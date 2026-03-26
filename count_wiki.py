#!/usr/bin/env python3
"""Count words and characters across all .wiki files in the repo."""

from pathlib import Path

repo_root = Path(__file__).parent
wiki_files = sorted(repo_root.rglob("*.wiki"))

total_words = 0
total_chars = 0

print(f"{'File':<60} {'Words':>8} {'Chars':>10}")
print("-" * 80)

for path in wiki_files:
    text = path.read_text(encoding="utf-8")
    words = len(text.split())
    chars = len(text)
    total_words += words
    total_chars += chars
    rel = path.relative_to(repo_root)
    print(f"{str(rel):<60} {words:>8,} {chars:>10,}")

print("-" * 80)
print(f"{'TOTAL':<60} {total_words:>8,} {total_chars:>10,}")
print(f"\n{len(wiki_files)} files")
