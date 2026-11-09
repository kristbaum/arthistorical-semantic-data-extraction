#!/usr/bin/env python3
"""Check that every quote in claims.tsv (or any table with lemma + quote columns) is faithfully copied from its article.

The article's wikitext is reduced to plain text ({{Abk|x}} -> x, file links ->
their caption, <sub>/<sup>, bold/italics and headings removed, table rows
joined with " – ", whitespace collapsed). A quote may skip text with "[…]";
each segment between gaps must occur verbatim in the plain text, in order.
Trailing punctuation of a segment is ignored (it's often added when cutting).

Usage: check_quotes.py --articles data/cleaned-with-skill-v2/Band01 data/wikidata/Band01/claims.tsv
Exit code 1 if any quote fails.
"""
import argparse, csv, re, sys
from pathlib import Path

def plain(wiki: str) -> str:
    t = re.sub(r"\{\{Artikel.*?\n\}\}", "", wiki, flags=re.S)
    t = re.sub(r"\{\{Abk\|([^}|]*)(?:\|([^}|]*))?\}\}", lambda m: m.group(2) or m.group(1), t)
    t = re.sub(r"\{\{Entität\|(?:1=)?([^{}]*?)(?:\|(?:rolle|titel|bild|qid|id)=[^|{}]*)*\}\}", r"\1", t)
    t = re.sub(r"\[\[File:[^\]]*\]\]", "", t)  # embedded images (thumbs)
    t = re.sub(r"\[\[:File:[^|\]]*\|([^\]]*)\]\]", r"\1", t)  # links to images
    t = re.sub(r"<gallery.*?</gallery>", "", t, flags=re.S)
    t = re.sub(r"</?su[bp]>", "", t)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"^=+\s*(.*?)\s*=+$", r"\1", t, flags=re.M)
    # tables: one line per row, cells joined by " – "
    t = re.sub(r"^\{\|.*$|^\|\}$|^\|-$", "", t, flags=re.M)
    t = re.sub(r"^[!|]\s*(.*)$", lambda m: re.sub(r"\s*(\|\||!!)\s*", " – ", m.group(1)), t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()

def check(quote: str, text: str) -> str | None:
    pos = 0
    for seg in (s.strip() for s in re.split(r"\s*\[…\]\s*", quote)):
        seg = seg.rstrip(".,;:")
        if not seg:
            continue
        i = text.find(seg, pos)
        if i < 0:
            return seg if text.find(seg) < 0 else f"(out of order) {seg}"
        pos = i + len(seg)
    return None

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--articles", required=True, help="folder with <Lemma>.wiki")
    ap.add_argument("context")
    a = ap.parse_args()
    cache, bad, n = {}, 0, 0
    seen = set()
    for r in csv.DictReader(open(a.context, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
        key = (r["lemma"], r["quote"])
        if key in seen:
            continue
        seen.add(key); n += 1
        if r["lemma"] not in cache:
            cache[r["lemma"]] = plain((Path(a.articles) / f"{r['lemma']}.wiki").read_text(encoding="utf-8"))
        miss = check(r["quote"], cache[r["lemma"]])
        if miss:
            bad += 1
            print(f"FAIL {r['lemma']}: not found: »{miss}«")
    print(f"{n - bad}/{n} distinct quotes verbatim")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
