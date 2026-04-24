# Corpus Modernization

## Motivation

The printed versions of the "Corpus der barocken Deckenmalerei in Deutschland" exist in 15 books (14 volumes and one index).
They were published from 1976 to 2010 and cover all areas of upper Bavaria. Only a small number of books were printed at the time, and they are not readily available.
The goal of this work is to update the contents of the original CbDD to fit the modern digital format of the [deckenmalerei.eu](https://www.deckenmalerei.eu) database.

- Band 1: Die Landkreise Landsberg am Lech, Starnberg, Weilheim-Schongau. Hirmer, München 1976, ISBN 978-3-7991-5737-7 (dnb.de).
- Band 2: Die Landkreise Bad Tölz-Wolfratshausen, Garmisch-Partenkirchen, Miesbach. Hirmer, München 1981, ISBN 978-3-7991-5834-3 (dnb.de).
- Band 3: Teil 1: Stadt und Landkreis München. Sakralbauten. Hirmer, München 1987, ISBN 978-3-7991-6111-4 (dnb.de).
- Band 3: Teil 2: Stadt und Landkreis München. Profanbauten. Hirmer, München 1989, ISBN 978-3-7991-6358-3 (dnb.de).
- Band 4: Landkreis Fürstenfeldbruck. Hirmer, München 1995, ISBN 978-3-7774-6310-0 (dnb.de).
- Band 5: Landkreis Dachau. Hirmer, München 1996, ISBN 978-3-7774-6320-9 (dnb.de).
- Band 6: Stadt und Landkreis Freising. Hirmer, München 1998, ISBN 978-3-7774-7590-5 (dnb.de).
- Band 7: Landkreis Erding. Hirmer, München 2001, ISBN 978-3-7774-7830-2 (dnb.de).
- Band 8: Landkreis Mühldorf am Inn. Hirmer, München 2002, ISBN 978-3-7774-9430-2 (dnb.de).
- Band 9: Landkreis Altötting. Hirmer, München 2003, ISBN 978-3-7774-9690-0 (dnb.de).
- Band 10: Landkreis Neuburg-Schrobenhausen. Hirmer, München 2005, ISBN 978-3-7774-2365-4 (dnb.de).
- Band 11: Landkreis Traunstein. Hirmer, München 2005, ISBN 978-3-7774-2695-2 (dnb.de).
- Band 12: Teil 1: Stadt und Landkreis Rosenheim. Hirmer, München 2006, ISBN 978-3-7774-3355-4 (dnb.de).
- Band 12: Teil 2: Stadt und Landkreis Rosenheim. Hirmer, München 2006, ISBN 978-3-7774-3355-4 (dnb.de).
- Band 13: Landkreis Eichstätt. Hirmer, München 2008, ISBN 978-3-7774-4475-8 (dnb.de).
- Band 14: Landkreis Ingolstadt; Landkreis Pfaffenhofen. Hirmer, München 2010, ISBN 978-3-7774-3001-0 (dnb.de).
- Gesamtindex: Freistaat Bayern, Regierungsbezirk Oberbayern. Hirmer, München 2010, ISBN 978-3-7774-3001-0 (dnb.de).

## Process

- [x] Scanning of the complete Corpus (15 books, 6516 Pages, 12.37 GB)
- [x] Splitting into smaller sizes for processing on the Transkribus scanning platform
- [x] Spliting into double page images ([src](src/pdf_to_images.py))

### Text processing

- [x] Hand-checking 100 pages for ground truth
- [x] Training a custom text recognition model (6.5h on transcribus.org)
- [x] Running all pages through model (34.5h)
- [x] Running an additional layout and text recognition model ([surya](https://github.com/VikParuchuri/surya), 2025) on small-scale hardware (GTX 1660) ([src](src/surya_pipeline.py))
- [x] Parse and transform the laid-out OCR results into [MediaWiki markup language](https://www.mediawiki.org/wiki/Help:Formatting) ([src](src/surya_mediawiki.py)) Result: 3,127 files, 2,347,256 words, 16,934,886 characters
- [x] Join lines and remove line breaks and dashes ([src](src/surya_mediawiki.py))
- [x] Adding hidden links to relevant part of the PDFs on dropbox on every page ([src](src/dropbox_links.py))
- [x] Add original page numbers to each page ([src](src/dropbox_links.py))
- [x] Modify formating for improved parsing by LLM (Chapter marks)
- [x] Shield quotations from LLMs by wrapping them in explicit brackets
- [x] Merge both OCR results with larger LLM model (qwen3:32b-fp16) on LRZ AI hardware to improve results and fix layout ordering errors from Transkribus OCR (Pass 1)
- [ ] Improve spelling mistakes and remove indices and other non article text (Pass 1)
- [x] Fix missing metadata and remove remaining OCR footers (Checked 3126 pass1 files, Metadata fixed: 170, Footers cleaned: 511 + 74)
- [x] Split articles, by combining the csv table with the full length text and estimating a separation point by section headers
- [x] Check results by matching the article lemma location with the content of the article (Fix missing scanned page in Band 10, page 14,15)
- [ ] Expand abbreviations, based on the glossary (Abkürzungen: allgemein, biblische Schriften, bibliographische, Editions- und Zitierhinweise), of each volume (Pass 2)
- [ ] Identify and split results into building-based articles using Mistral on LRZ AI (Pass 3)
- [ ] Standardize article formatting with sections:
  - Patrozinium
  - Zum Bauwerk
  - Auftraggeber
  - Autor und Entstehungszeit
  - Befund
  - Beschreibung und Ikonographie
  - Literatur
  - Photographische Dokumentation
  - Planskizzen
  - Anhang
- [ ] Improve article formatting by adding citation box at the top, that references the correct volume (and page number?) with a template
      Match
- [ ] Match articles to stub articles in deckenmalerei.eu database to get identifiers and correct lemma
- [ ] Upload articles into MediaWiki
- [ ] Fix remaining errors on MediaWiki to track changes

### Image processing

- [x] Extracting images and caption from the surya detected layout with script ([src](src/surya_layout.py))
- [x] Match captions to images based on proximity ([src](src/surya_mediawiki.py))
- [x] Add links to images with captions to parsed MediaWiki markup results ([src](src/surya_mediawiki.py))
- [x] Improve extracted images by removing blank space ([src](src/preprocess_images.py))
- [x] Upload the improved images to MediaWiki installation (8959 files)
- [ ] Identify and document errors in image recognition manually (GWAP!)
- [ ] Upload images into MediaWiki

| Metric | Articles | Meta | Total |
| --- | ---: | ---: | ---: |
| Articles (count) | 908 | 86 | 994 |
| Total characters | 14,891,486 | 1,593,255 | 16,484,741 |
| Total words | 2,070,252 | 244,266 | 2,314,518 |
| Total [[File:]]s | 8,598 | 3 | 8,601 |
| Total est. tokens | 3,722,871 | 398,313 | 4,121,185 |
| Avg characters | 16,400 | 18,526 | 16,584 |
| Avg words | 2,280 | 2,840 | 2,328 |
| Avg [[File:]]s | 9.47 | 0.03 | 8.65 |
| Avg est. tokens | 4,100 | 4,632 | 4,146 |
