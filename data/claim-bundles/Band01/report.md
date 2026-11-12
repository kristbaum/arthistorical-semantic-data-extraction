# Band01: extraction report (claim bundle `cbdd-band01`, version 2)

Source: `data/cleaned-with-skill-v2/Band01` (8 articles). Built with
`make_bundle.py`, then `claim-bundle candidates` (label search for the six
people without candidates), `verify`, `route --policy references/policy.json`,
`anchors`; `check` passes (0 errors, 1 warning: Perfall has no claim, kept
for the `{{Entität}}` link).

92 entities (24 match, 60 create, 8 reconcile), 631 claims:
direct 377 · game 206 · curator 48. 17 claims are already on Wikidata
(`statement_id`): their batch lines only add the reference.
Games: motiv 89 · iconclass 43 · datierung-sicherheit 21 · zustand 18 ·
stichprobe 16 · urheber-sicherheit 9 · urheber 6 · datierung 4, plus the
reconciliation game for Haid (3 candidates). All 206 game claims are playable
now (games without actions); 122 claims wait for items to be created.

Compared with the version 1 bundle of 2026-11-11: curator 95 → 48 (hedged
attributions and dates became certainty games), skip 11 → 0 (references are
added instead), playable game prompts 33 → 206.

## Per article

**Adelshausen**: building Q41254096 (CbDD P10626, monument item dated 1677).
Anwander Q1692498 (1750–1800). Two rooms (Gemeinderaum, Altarraum), 8
paintings. Attribution "zuschreiben" and date "zeitliche Nähe zu 1795" → certainty
games (urheber-sicherheit, datierung-sicherheit). A1–4 as Vier Letzte Dinge is
hedged (vermutlich/wohl) → P921 and three Iconclass claims to the curator.
Not an entity: the cycle template `cfp5aj5w` (A1–4).

**Asch**: building Q40873464. Two rooms. Author unknown → `P170 somevalue`;
date "1720 … wohl gleichzeitig mit dem Stuck" → presumably, curator.
Einßlin and Boodman: no items → reconcile, curator.

**Beuerbach**: building Q41254110 (Rundbau 1686 / Anbau 1824 match). No
rooms (one space). Date "7./8. Jahrzehnt des 18. Jh." → century precision
with 1760–1780 bounds, curator. W1–4 created although the article says no
baroque substance remains; a curator may drop them. Not an entity: cycle
template `euiti377`.

**Beuern**: Engelsturz exists (Q142089560, batch 66344): 5 statements
already on it → `statement_id`, the batch only adds the reference. Schöpf attribution kept as the authors' argument
(curator), plus the rejected attribution to J. N. von Schöpf for a
deprecated statement (curator). J. N. von Schöpf (Q1695668, dates differ)
and Haid (4 candidates). `verify` excluded Johann Nepomuk Schöpf's only candidate
(Wikidata birth year 1733 vs. 1735 in the article) → curator; for Haid it
excluded Johann Jakob Haid (1670–1730), three candidates go to the game.
Mauser, Bayerlacher → curator (label search: no hit).
LHs template `pt1aoalg` not an entity (single room).

**Bischofsried**: building Q41253998, Wolcker Q1693998 (attribution
"einzureihen" → certainty game), Karg Q94819127 (GND, CbDD ID).

**Denklingen**: building Q1586238. Three rooms. Hueber Q1694998 signed B
(1767) → urheber/datierung games; C attributed through the comparison
sentence. Kleinhans Q1449663 (inscription says "Johannes Kleinhans aus
Tirol"), Finsterwalder Q1657439 as P767 + role stuccoist (curator). Joseph
Schmid: the label search found 10 namesakes; three were excluded by dates,
a composer without dates removed by hand → curator. Not entities: cycle
templates `q3jxghd5`, `ksunmiyz`.

**Dienhausen**: building Q41253199. Abbot Dierling: no item → curator.
AR template `og9w621s` not an entity (single room).

**Dießen**: no CbDD building; Q1254306 by place, dedication and its existing
fresco items. **B = Q127502516, C = Q104218325, D = Q106548750 already
exist**; only A is created. Statements already on them get `statement_id`. Hedged
saints in D (Hedwig, Elisabeth von Portugal: "wohl") → curator.

## Open questions

- Q106548750's description places D in the Altarraum; the article puts it
  over the crossing.
- `apply_qids.py` needs the state file of the claim-bundle run (QIDs of
  created and reconciled items) before it can write the articles.
