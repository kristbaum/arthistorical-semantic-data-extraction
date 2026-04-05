#!/usr/bin/env python3
"""List all files uploaded to the MediaWiki instance and write them to a CSV."""

import csv
from pathlib import Path
import pywikibot

WIKI_URL = "https://badwcbd-lab.srv.mwn.de/api.php"
OUTPUT = Path("files.csv")

site = pywikibot.Site(url=WIKI_URL)

rows = []
for filepage in site.allimages():
    page_url = filepage.full_url()
    file_url = filepage.get_file_url()
    rows.append((page_url, file_url))

with OUTPUT.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["image1_description_link", "image1_url"])
    writer.writerows(rows)

print(f"Wrote {len(rows)} entries to {OUTPUT}")
