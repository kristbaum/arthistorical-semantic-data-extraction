# Band01: extraction report

Source: `data/cleaned-with-skill-v2/Band01` (8 articles, CbDD vol. 1 = Q118117102).
Built with `build.py`; counts in `build-report.md`, every statement in `claims.tsv`.

| Route | Text-backed statements | File |
|---|---|---|
| direct | 143 (+201 structural) | `create.qs`, `direct.qs` |
| audit sample (10 %, ≥ 1 per article) | 20 | game *Stichprobe Corpus* (no action) |
| game | 111 prompts | `games/*.json` + `.csv` |
| follows a game decision | 26 | `followers.tsv` → `apply_results.py` → `followers.qs` |
| curator | 21 | `curator.qs` |

New items: 45 ceiling paintings, 4 wall paintings, 9 rooms. Existing painting
items reused: Dießen B = Q127502516, D = Q106548750.

## Per article

| Article | Building | Evidence | direct / audit / game / follows / curator |
|---|---|---|---|
| Adelshausen (Weil), Kapelle St. Martin | Q41254096 | CbDD link, lemma alias, P131 Weil, "bezeichnet 1677" | 25 / 2 / 13 / 15 / 9 |
| Asch, Pfarrkirche St. Johannes Baptist | Q40873464 | CbDD link, lemma alias, P131 Fuchstal | 34 / 1 / 23 / 3 / 1 |
| Beuerbach (Weil), Kapelle im Holz Maria Eich | Q41254110 | CbDD link, lemma alias, P131 Weil | 5 / 2 / 12 / 4 / 1 |
| Beuern, Pfarrkirche St. Michael | Q41254590 | CbDD link, P131 Greifenberg | 4 / 1 / 6 / 0 / 1 |
| Bischofsried, Maria-Schnee-Kapelle | Q41253998 | CbDD link, P131 Dießen, class chapel | 2 / 1 / 4 / 0 / 1 |
| Denklingen, Pfarrkirche St. Michael | Q1586238 | CbDD link, lemma alias, P131 Denklingen | 41 / 10 / 32 / 2 / 3 |
| Dienhausen, Kapelle St. Magnus | Q41253199 | CbDD link, lemma alias, P131 Denklingen | 4 / 1 / 3 / 0 / 1 |
| Dießen, ehem. Augustiner-Chorherrenstiftskirche | Q1254306 | lemma aliases, P84 Johann Michael Fischer, P131 Dießen (no CbDD match) | 28 / 2 / 18 / 2 / 4 |

## People

| Person | QID | Fit |
|---|---|---|
| Johann Baptist Anwander | Q1692498 | 1750–1800; frescoes c. 1795 (not CbDD's "Johann", †1770) |
| Johann Adam Schöpf | Q835326 | 1702–1772; the article argues for him over his son Johann Nepomuk (Q1695668) |
| Johann Georg Wolcker | Q1693998 | 1700–1766; c. 1730 |
| Johann Joseph Anton Huber | Q1694998 | 1737–1815, later academy director; signed 1767 |
| Johann Georg Bergmüller | Q551709 | 1688–1762; signed 1736 (already on the two existing fresco items) |
| Joseph Schmuzer | Q1707978 | 1683–1752; Asch 1720, Beuern 1724–25 |
| Franz Xaver Kleinhans | Q1449663 | 1699–1776; Denklingen 1765/66 (already P84 on the item) |
| Johann Michael Fischer | Q72959 | 1692–1766; Dießen (already P84 on the item) |
| Herkulan Karg | Q94819127 | provost of Dießen; item has no dates (see conflicts) |
| Joseph Ignaz Philipp von Hessen-Darmstadt | Q1707293 | prince-bishop of Augsburg 1740–68 |

## Skipped, with reason

- Benediktus / Jakob Fichtell (Adelshausen): names on the 1677 gable, no role.
- Pfarrer Bayerlacher (Beuern, paid for the frescoes) and Abt Dominicus Dierling (Dienhausen): no Wikidata item; not enough for a new one.
- Beuerbach W1–W4: the article says no baroque substance is left.
- Stuccoists (Schmuzer, Finsterwalder): need P767 + P3831 on rooms; left for a later pass.
- "Autor unbekannt" (Asch, Beuerbach, Dienhausen): no `P170 somevalue` written.
- Restorations (dated) and "Übermalung": no fitting P5816 value.
- Iconclass for local legends (Dießen A–C, Bischofsried) and for "Vermählung Mariens mit der Taube des Geistes": no notation.
- Rathard (Dießen) and the Holy Spirit (Asch A): no fitting item.

## Curator queue (21)

- 2 × P170 for Adelshausen W1/W2: the passage contains no attribution.
- 3 × P1257 for Adelshausen A2–A4: hedged passages (*offenbar*, *(?)*, *wohl*).
- 4 × P921 "Vier letzte Dinge" (Adelshausen A1–A4, *vermutlich*): no game.
- P84 Joseph Schmuzer (Asch, Beuern); P88 commissioners (Bischofsried, Denklingen ×3, Dießen ×4).
- Date ranges: Beuerbach A (1760–80), Dienhausen ("kurz nach 1733").

## Conflicts and notes

- Herkulan Karg's term is printed as 1728–55 (Bischofsried) and 1728–1766 (Dießen); the Wikidata item has neither.
- The deckenmalerei-lab text still carries OCR errors, e.g. "Fresken von 1695" (Adelshausen) where the cleaned text and the scan say 1795. Lab links anchor on the shared words; 7 passages have no common run of ≥ 3 words and link to the page only.
- Beuern is "Pfarrkirche" in the corpus, "Filialkirche" on Wikidata (P31 left unchanged).
- Dießen D: Wikidata describes it as "im Altarraum"; the corpus says "über der Vierung". A new room item "Vierung" was created for it.

## Run order

1. `create.qs` in QuickStatements.
2. `placeholders.py lookup --map placeholders.tsv --apply`.
3. Rerun `build.py` (placeholders become QIDs in `direct.qs` and the game CSVs).
4. `direct.qs`; review `curator.qs`.
5. Create the games, upload CSVs; after play, `apply_results.py` with the exports → `followers.qs`.
