#!/usr/bin/env python3
"""
Convert groups of pipe-separated lines in a wiki file to MediaWiki Wikitable format.

Lines containing '|' that are adjacent (separated only by blank lines) are grouped
into a single wikitable. A non-blank line without '|' breaks the current group.

Usage: python3 pipe_to_wikitable.py <input_file> [output_file]
       If output_file is omitted, the input file is overwritten in-place.
"""

import sys
from pathlib import Path


def lines_to_wikitable(pipe_lines: list[str]) -> str:
    """Convert a list of pipe-separated strings to a MediaWiki wikitable block."""
    rows = []
    for line in pipe_lines:
        cols = [c.strip() for c in line.split('|')]
        rows.append(cols)

    max_cols = max(len(r) for r in rows)

    parts = ['{| class="wikitable"']
    for row in rows:
        while len(row) < max_cols:
            row.append('')
        parts.append('|-')
        parts.append('| ' + ' || '.join(row))
    parts.append('|}')
    return '\n'.join(parts)


def process(text: str) -> str:
    """Process wiki text, converting pipe-line groups to wikitables."""
    lines = text.splitlines()
    output: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if '|' in line:
            # Collect consecutive pipe-lines, skipping blank-line gaps between them
            group = [line]
            j = i + 1
            while j < len(lines):
                if '|' in lines[j]:
                    group.append(lines[j])
                    j += 1
                elif lines[j].strip() == '':
                    # Peek ahead: continue group only if the next non-blank line also has |
                    k = j + 1
                    while k < len(lines) and lines[k].strip() == '':
                        k += 1
                    if k < len(lines) and '|' in lines[k]:
                        j = k  # skip blanks, land on next pipe-line
                    else:
                        break
                else:
                    break  # non-blank, non-pipe line ends the group

            output.append(lines_to_wikitable(group))
            i = j
        else:
            output.append(line)
            i += 1

    return '\n'.join(output)


def main() -> None:
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <input_file> [output_file]', file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path

    text = input_path.read_text(encoding='utf-8')
    result = process(text)
    output_path.write_text(result, encoding='utf-8')
    print(f'Written: {output_path}')


if __name__ == '__main__':
    main()
