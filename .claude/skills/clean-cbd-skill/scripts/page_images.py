#!/usr/bin/env python3
"""Locate an article's images on the page scans and cut out their captions.

Surya cropped every Picture/Figure region out of the rendered page and the
crops were uploaded to the wiki as `Band01_chunk001_p011_img001.jpg`, but the
crop positions were not stored. This script downloads each crop the article
references (cached under data/cache/wiki_images/), finds it on the page scan
by normalised cross-correlation, and writes two small images per page into
data/cache/page_images/:

  {chunk}_{pNNN}_overview.jpg   the spread, downscaled, every image boxed and
                                labelled img001, img002 … — shows where each
                                image sits relative to the text columns
  {chunk}_{pNNN}_captions.png   one strip per image: the printed line(s)
                                directly below it at full resolution, i.e. the
                                caption as printed (»A1 Himmel«)

and prints, per image: printed page (left/right half), box, match score and
the caption the article currently has. Read the two PNG/JPGs with the Read
tool — together they cost far fewer tokens than the full scan.

Usage:
    uv run python .claude/skills/clean-cbd-skill/scripts/page_images.py \\
        "data/formatted/Band01/Lemma.wiki" [--refresh]
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_sources import REPO_ROOT, find_pages, source_paths  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "src"))
from articles.helpers import parse_article_file  # noqa: E402

WIKI_API = "https://badwcbd-lab.srv.mwn.de/api.php"
USER_AGENT = "cbdd-clean-skill/1.0 (CbDD digitisation)"
IMG_CACHE = REPO_ROOT / "data" / "cache" / "wiki_images"
OUT_DIR = REPO_ROOT / "data" / "cache" / "page_images"

_FILE_LINE_RE = re.compile(r"\[\[(?:File|Datei):([^|\]]+)((?:\|[^\]]*)?)\]\]")
_IMG_NAME_RE = re.compile(r"^(?P<chunk>.+_chunk\d+)_(?P<page>p\d+)_img\d+")

COARSE = 8          # downscale factor for the coarse search
SCALES = (1.0, 0.97, 1.03, 0.94, 1.06, 0.9, 1.1, 0.8, 1.25, 0.67, 1.5, 0.5, 2.0)
OVERVIEW_EDGE = 1600
CAPTION_FRAC = 0.045  # caption strip height as fraction of the page height


# ── wiki download ─────────────────────────────────────────────────────────────

def fetch_images(names: list[str], refresh: bool = False) -> dict[str, Path | None]:
    IMG_CACHE.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path | None] = {}
    todo = []
    for n in names:
        p = IMG_CACHE / n
        if p.exists() and not refresh:
            result[n] = p
        else:
            todo.append(n)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        r = session.get(WIKI_API, timeout=30, params={
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url", "titles": "|".join(f"File:{n}" for n in batch),
        })
        r.raise_for_status()
        data = r.json()["query"]
        # map normalised titles back to our names
        norm = {d["to"]: d["from"] for d in data.get("normalized", [])}
        for page in data["pages"].values():
            title = norm.get(page["title"], page["title"])
            name = title.split(":", 1)[1].replace(" ", "_")
            info = page.get("imageinfo")
            if not info:
                result[name] = None
                continue
            img = session.get(info[0]["url"], timeout=60)
            img.raise_for_status()
            (IMG_CACHE / name).write_bytes(img.content)
            result[name] = IMG_CACHE / name
    for n in names:
        result.setdefault(n, None)
    return result


# ── template matching (numpy only) ────────────────────────────────────────────

def _gray(img: Image.Image, factor: float) -> np.ndarray:
    w, h = img.size
    small = img.convert("L").resize(
        (max(1, round(w / factor)), max(1, round(h / factor))), Image.BILINEAR)
    return np.asarray(small, dtype=np.float64)


def _ncc(image: np.ndarray, tpl: np.ndarray) -> tuple[float, int, int]:
    """Best normalised cross-correlation of tpl inside image -> (score, y, x)."""
    H, W = image.shape
    h, w = tpl.shape
    if h > H or w > W or h < 4 or w < 4:
        return -1.0, 0, 0
    t = tpl - tpl.mean()
    t_norm = np.sqrt((t ** 2).sum())
    if t_norm == 0:
        return -1.0, 0, 0
    shape = (H + h, W + w)
    corr = np.fft.irfft2(np.fft.rfft2(image, shape) * np.fft.rfft2(t[::-1, ::-1], shape), shape)
    corr = corr[h - 1:H, w - 1:W]
    # local sums via integral images
    ii = np.pad(image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    ii2 = np.pad(image ** 2, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def box(a):
        return a[h:, w:] - a[:-h, w:] - a[h:, :-w] + a[:-h, :-w]

    s, s2 = box(ii), box(ii2)
    var = s2 - s ** 2 / (h * w)
    denom = np.sqrt(np.clip(var, 1e-9, None)) * t_norm
    score = corr / denom
    y, x = np.unravel_index(np.argmax(score), score.shape)
    return float(score[y, x]), int(y), int(x)


def locate(scan: Image.Image, crop: Image.Image) -> tuple[float, tuple[int, int, int, int]]:
    """(score, (x1, y1, x2, y2)) of crop on scan, in scan pixels."""
    big = _gray(scan, COARSE)
    best = (-1.0, 1.0, 0, 0)
    for s in SCALES:
        score, y, x = _ncc(big, _gray(crop, COARSE / s))
        if score > best[0]:
            best = (score, s, y, x)
        if score > 0.9:
            break
    score, s, y, x = best
    cw, ch = crop.size
    w, h = round(cw * s), round(ch * s)
    x1, y1 = x * COARSE, y * COARSE
    # refine at full resolution in a small window
    pad = COARSE * 2
    win = scan.crop((max(0, x1 - pad), max(0, y1 - pad),
                     min(scan.width, x1 + w + pad), min(scan.height, y1 + h + pad)))
    fine, fy, fx = _ncc(_gray(win, 2), _gray(crop, 2 / s))
    if fine > 0:
        x1, y1 = max(0, x1 - pad) + fx * 2, max(0, y1 - pad) + fy * 2
        score = max(score, fine)
    return score, (x1, y1, x1 + w, y1 + h)


# ── output images ─────────────────────────────────────────────────────────────

def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def write_overview(scan: Image.Image, boxes: dict[str, tuple], path: Path) -> None:
    f = OVERVIEW_EDGE / max(scan.size)
    ov = scan.convert("RGB").resize((round(scan.width * f), round(scan.height * f)))
    d = ImageDraw.Draw(ov)
    font = _font(28)
    for label, (x1, y1, x2, y2) in boxes.items():
        b = [round(v * f) for v in (x1, y1, x2, y2)]
        d.rectangle(b, outline=(220, 0, 0), width=4)
        d.rectangle([b[0], b[1], b[0] + 110, b[1] + 34], fill=(220, 0, 0))
        d.text((b[0] + 6, b[1] + 2), label, fill="white", font=font)
    ov.save(path, quality=80)


def write_captions(scan: Image.Image, boxes: dict[str, tuple], path: Path) -> None:
    strip_h = round(scan.height * CAPTION_FRAC)
    strips = []
    for label, (x1, y1, x2, y2) in boxes.items():
        # a little wider than the image: captions may start left of it
        sx1 = max(0, x1 - (x2 - x1) // 10)
        sx2 = min(scan.width, x2 + (x2 - x1) // 10)
        # start a little above the box: some crops reach past the picture
        # and would cut the caption's top off
        top = max(0, y2 - strip_h // 3)
        strip = scan.crop((sx1, top, sx2, min(scan.height, y2 + strip_h))).convert("RGB")
        if strip.width > 1400:
            strip = strip.resize((1400, round(strip.height * 1400 / strip.width)))
        strips.append((label, strip))
    if not strips:
        return
    label_w = 130
    W = label_w + max(s.width for _, s in strips)
    H = sum(s.height + 6 for _, s in strips)
    sheet = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(sheet)
    font = _font(26)
    y = 0
    for label, s in strips:
        d.text((6, y + s.height // 2 - 13), label, fill=(220, 0, 0), font=font)
        sheet.paste(s, (label_w, y))
        y += s.height + 6
        d.line([(0, y - 3), (W, y - 3)], fill=(200, 200, 200), width=1)
    sheet.save(path)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("article", type=Path)
    parser.add_argument("--refresh", action="store_true", help="re-download images")
    args = parser.parse_args()

    _tpl, fields, body = parse_article_file(args.article.read_text(encoding="utf-8"))
    captions = {m.group(1).strip(): m.group(2).split("|")[-1].strip()
                if m.group(2).count("|") > 1 else ""
                for m in _FILE_LINE_RE.finditer(body)}
    if not captions:
        print("no [[File:…]] in this article")
        return

    band = args.article.parent.name
    chunk = int(fields["Chunk"])
    von = int(fields["Originalseitenvon"])
    bis = int(fields.get("Originalseitenbis") or von)
    scans = {(c.name, stem): source_paths(c, stem)["scan"]
             for c, stem, _ in find_pages(band, chunk, von, bis)}

    by_page: dict[tuple[str, str], list[str]] = {}
    for name in captions:
        m = _IMG_NAME_RE.match(name)
        if m:
            by_page.setdefault((m["chunk"], m["page"]), []).append(name)
        else:
            print(f"?? {name}: name does not tell its page")

    files = fetch_images(list(captions), refresh=args.refresh)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for (chunk_name, stem), names in sorted(by_page.items()):
        scan_path = scans.get((chunk_name, stem)) or source_paths(
            REPO_ROOT / "data" / "extracted" / chunk_name, stem)["scan"]
        print(f"\n{chunk_name}/{stem}  scan: "
              f"{scan_path.relative_to(REPO_ROOT) if scan_path else '—'}")
        if not scan_path:
            for n in names:
                print(f"  {n}: no scan")
            continue
        scan = Image.open(scan_path)
        spread = scan.width > scan.height
        boxes = {}
        for n in sorted(names):
            label = n.rsplit("_", 1)[-1].split(".")[0]  # img001
            if files.get(n) is None:
                print(f"  {label}  not on the wiki — cannot locate")
                continue
            score, box = locate(scan, Image.open(files[n]))
            boxes[label] = box
            side = ("L" if (box[0] + box[2]) / 2 < scan.width / 2 else "R") if spread else "-"
            flag = "" if score >= 0.6 else "  LOW MATCH — check the overview"
            cap = captions[n] or "(no caption)"
            print(f"  {label}  page {side}  box {box}  score {score:.2f}{flag}\n"
                  f"          article caption: {cap}")
        base = OUT_DIR / f"{chunk_name}_{stem}"
        write_overview(scan, boxes, base.with_name(base.name + "_overview.jpg"))
        write_captions(scan, boxes, base.with_name(base.name + "_captions.png"))
        print(f"  overview: {base.relative_to(REPO_ROOT)}_overview.jpg")
        print(f"  captions: {base.relative_to(REPO_ROOT)}_captions.png")


if __name__ == "__main__":
    main()
