# Corpus Modernization

## Motivation

The printed versions of the "Corpus der barocken Deckenmalerei in Deutschland" exist in 15 books (14 volumes and one index). They were published from 1976 to 2010 and cover all areas of upper Bavaria. Only a few number of books was printed at the time, and they are not readily available.
The goal of this work is to update the contents of the original CbDD to fit the modern digital format of the [deckenmalerei.eu](https://www.deckenmalerei.eu) database.

* Band 1: Die Landkreise Landsberg am Lech, Starnberg, Weilheim-Schongau. Hirmer, München 1976, ISBN 978-3-7991-5737-7 (dnb.de).
* Band 2: Die Landkreise Bad Tölz-Wolfratshausen, Garmisch-Partenkirchen, Miesbach. Hirmer, München 1981, ISBN 978-3-7991-5834-3 (dnb.de).
* Band 3: Teil 1: Stadt und Landkreis München. Sakralbauten. Hirmer, München 1987, ISBN 978-3-7991-6111-4 (dnb.de).
* Band 3: Teil 2: Stadt und Landkreis München. Profanbauten. Hirmer, München 1989, ISBN 978-3-7991-6358-3 (dnb.de).
* Band 4: Landkreis Fürstenfeldbruck. Hirmer, München 1995, ISBN 978-3-7774-6310-0 (dnb.de).
* Band 5: Landkreis Dachau. Hirmer, München 1996, ISBN 978-3-7774-6320-9 (dnb.de).
* Band 6: Stadt und Landkreis Freising. Hirmer, München 1998, ISBN 978-3-7774-7590-5 (dnb.de).
* Band 7: Landkreis Erding. Hirmer, München 2001, ISBN 978-3-7774-7830-2 (dnb.de).
* Band 8: Landkreis Mühldorf am Inn. Hirmer, München 2002, ISBN 978-3-7774-9430-2 (dnb.de).
* Band 9: Landkreis Altötting. Hirmer, München 2003, ISBN 978-3-7774-9690-0 (dnb.de).
* Band 10: Landkreis Neuburg-Schrobenhausen. Hirmer, München 2005, ISBN 978-3-7774-2365-4 (dnb.de).
* Band 11: Landkreis Traunstein. Hirmer, München 2005, ISBN 978-3-7774-2695-2 (dnb.de).
* Band 12: Teil 1: Stadt und Landkreis Rosenheim. Hirmer, München 2006, ISBN 978-3-7774-3355-4 (dnb.de).
* Band 12: Teil 2: Stadt und Landkreis Rosenheim. Hirmer, München 2006, ISBN 978-3-7774-3355-4 (dnb.de).
* Band 13: Landkreis Eichstätt. Hirmer, München 2008, ISBN 978-3-7774-4475-8 (dnb.de).
* Band 14: Landkreis Ingolstadt; Landkreis Pfaffenhofen. Hirmer, München 2010, ISBN 978-3-7774-3001-0 (dnb.de).
* Gesamtindex: Freistaat Bayern, Regierungsbezirk Oberbayern. Hirmer, München 2010, ISBN 978-3-7774-3001-0 (dnb.de).

## Process

* [x] Scanning of the complete Corpus (15 books, 6516 Pages, 12.37 GB)

### Text processing

* [x] Spliting into smaller sizes for processing on the transcribus scanning platform
* [x] Hand-checking 100 pages for ground truth
* [x] Training a custon text recognition model (6.5h on transcribus.org)
* [x] Running all pages through model (34.5h)
* [x] Running an additional layout and text recognition model ([surya](https://github.com/VikParuchuri/surya), 2025) on smallscale hardware (GTX 1660)
* [x] Parse and transform the layouted ocr results into [MediaWiki markup language](https://www.mediawiki.org/wiki/Help:Formatting)
* [ ] Adding hidden links to relevant part of pdf on every page
* [ ] Merge both ocr results with larger LLM model (Mistral-7B) on LRZ AI hardware to improve results and fix layout ordering errors from transcribus ocr (Pass 1)
* [ ] Improve spelling mistakes and remove indices and other non article text (Pass 1)
* [ ] Expand abbreviations, based on the glossar (Abkürzungen: allgemein, biblische Schriften, bibliographische, Editions- und Zitierhinweise), of each volume (Pass 1)
* [ ] Identify and split results into building based articles using Mistral on LRZ AI (Pass 2)
* [ ] Standardize article formatting with sections:
  * Patrozinium
  * Zum Bauwerk
  * Auftraggeber
  * Autor und Entstehungszeit
  * Befund
  * Beschreibung und Ikonographie
  * Literatur
  * Photographische Dokumentation
  * Planskizzen
  * Anhang
* [ ] Improve article formatting by adding citation box at the top, that reference the correct volume (and page number?) with a template
Match
* [ ] Match articles to stub articles in deckenmalerei.eu database to get identifiers and correct lemma
* [ ] Upload articles into MediaWiki
* [ ] Fix remaning errors on MediaWiki to track changes

### Image processing

* [x] Extracting images and caption from the surya detected layout with script
* [x] Match captions to images based on proximity
* [x] Add links to images with captions to parsed MediaWiki markup results
* [ ] Identify and document errors in image recognition manually (GWAP?)
* [ ] Upload images into MediaWiki
