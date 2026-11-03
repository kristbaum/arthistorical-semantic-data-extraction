#!/usr/bin/env python3
"""Cut a region out of a page scan at full resolution, to read small print.

A whole spread is downscaled to 2576 px on its long edge when read, which
blurs subscripts, † and punctuation — and costs ~4.8k tokens. A crop of one
passage is sharper and a fraction of the cost. Find the region on the
`…_overview.jpg` from page_images.py first.

The box is given as fractions of the spread (0–1), x1,y1,x2,y2 from the top
left; the result goes to data/cache/page_images/{chunk}_{pNNN}_crop.png
(scaled down only if wider than 1600 px).

Shortcuts for the usual layout (two printed pages, two columns each):
    --col L1|L2|R1|R2   one column of the left/right page
    --rows 0.2,0.45     vertical range within it (fractions)

Usage:
    uv run python .claude/skills/clean-cbd-skill/scripts/scan_crop.py \\
        data/extracted/Band01_chunk007/pages/Band01_chunk007_p002_.jpg --box 0.52,0.30,0.75,0.40
    uv run python .claude/skills/clean-cbd-skill/scripts/scan_crop.py SCAN --col L2 --rows 0.6,0.8
"""

import argparse
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[4]
OUT_DIR = REPO_ROOT / "data" / "cache" / "page_images"
# approximate column bands of a spread (fractions of the width)
COLS = {"L1": (0.03, 0.27), "L2": (0.24, 0.49), "R1": (0.51, 0.76), "R2": (0.73, 0.97)}
MAX_W = 1600


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scan", type=Path)
    parser.add_argument("--box", help="x1,y1,x2,y2 as fractions")
    parser.add_argument("--col", choices=sorted(COLS))
    parser.add_argument("--rows", default="0,1", help="y1,y2 fractions for --col")
    args = parser.parse_args()

    if args.box:
        x1, y1, x2, y2 = (float(v) for v in args.box.split(","))
    elif args.col:
        x1, x2 = COLS[args.col]
        y1, y2 = (float(v) for v in args.rows.split(","))
    else:
        parser.error("give --box or --col")

    img = Image.open(args.scan)
    W, H = img.size
    crop = img.crop((round(x1 * W), round(y1 * H), round(x2 * W), round(y2 * H))).convert("RGB")
    if crop.width > MAX_W:
        crop = crop.resize((MAX_W, round(crop.height * MAX_W / crop.width)))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = args.scan.stem.replace(".jpg", "")
    out = OUT_DIR / f"{stem}_crop.png"
    crop.save(out)
    print(f"{out.relative_to(REPO_ROOT)}  {crop.width}×{crop.height} px "
          f"(~{round(crop.width * crop.height / 750)} tokens)")


if __name__ == "__main__":
    main()
