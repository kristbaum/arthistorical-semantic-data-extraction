"""Pass 2: Improve formatted articles via LLM.

Reads each article from data/formatted/BandXX/, extracts the article body
(everything after the {{Artikel …}} template), sends it through an LLM for
cleanup, and writes the result (with the original template re-attached) to
data/pass2/BandXX/<lemma>.wiki.

Only articles with an empty |Meta= field are processed (meta articles like
Vorwort, Register, Malerliste need a different treatment).

Improvements applied by the LLM:
  - Remove leftover line breaks from the book's column layout
  - Fix punctuation (spacing, quotation marks, dashes)
  - Expand a predefined set of abbreviations on first occurrence
  - Remove superfluous blank lines (MediaWiki formatting)
  - Format section markers (A1 → A<sub>1</sub>, ALL-CAPS titles → bold)
  - Format the Befund/Maße section as a wikitable
  - Split Quellen und Literatur entries into bullet points

Usage:
    # Single band, dry-run (prints article count, no LLM calls)
    python src/run_pass2.py --input-dir data/formatted --band Band01

    # Process one article (test)
    python src/run_pass2.py \\
        --input-dir data/formatted --band Band01 \\
        --article "Antdorf, Kirnbergkapelle" \\
        --model qwen3:32b-fp16

    # Process all articles
    python src/run_pass2.py \\
        --input-dir data/formatted \\
        --model qwen3:32b-fp16

    # With page limit for test runs
    python src/run_pass2.py \\
        --input-dir data/formatted \\
        --model qwen3:32b-fp16 \\
        --max-articles 10
"""

import argparse
import json
import http.client
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_BASE = REPO_ROOT / "data" / "pass2"

# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------

_FIELD_RE = re.compile(r"^\s*\|(\w+)=(.*)$")


def _parse_article_file(text: str) -> tuple[str, dict[str, str], str]:
    """Split an article file into (template_block, fields, body).

    template_block: the raw text from {{Artikel to }} inclusive (with newlines).
    fields:         dict of field_name → value.
    body:           everything after the closing }}.
    """
    lines = text.splitlines(keepends=True)
    in_tpl = False
    tpl_lines: list[str] = []
    fields: dict[str, str] = {}
    body_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("{{Artikel"):
            in_tpl = True
            tpl_lines.append(line)
        elif s == "}}" and in_tpl:
            tpl_lines.append(line)
            body_start = i + 1
            break
        elif in_tpl:
            tpl_lines.append(line)
            m = _FIELD_RE.match(line)
            if m:
                fields[m.group(1)] = m.group(2).strip()

    template_block = "".join(tpl_lines)
    body = "".join(lines[body_start:])
    return template_block, fields, body


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
Du erhältst den Fließtext eines kunsthistorischen Artikels über barocke \
Deckenmalereien aus dem »Corpus der barocken Deckenmalerei in Deutschland«. \
Der Text ist bereits in MediaWiki-Markup, wurde aber per OCR erfasst und \
enthält noch Artefakte. Verbessere ihn nach den folgenden Regeln.

Gib NUR den verbesserten MediaWiki-Text aus, ohne Erklärungen.

== Regeln ==

=== 1. Zeilenumbrüche bereinigen ===
Entferne überflüssige Zeilenumbrüche, die vom Buchlayout stammen. \
Zusammengehörende Absätze zu durchlaufendem Fließtext zusammenfügen. \
Trennzeichen am Zeilenende (Wort-) mit dem Wort auf der nächsten Zeile \
zusammenführen.

=== 2. Leerzeilen (MediaWiki-Richtlinien) ===
- Maximal EINE Leerzeile zwischen Absätzen.
- Genau EINE Leerzeile vor und nach jeder == Überschrift ==.
- Keine Leerzeilen am Anfang oder Ende des Texts.

=== 3. Zeichensetzung ===
- Fehlende Punkte am Satzende ergänzen.
- Leerzeichen vor Satzzeichen (, . ; : ! ?) entfernen.
- Gedankenstriche vereinheitlichen: – (Halbgeviert).
- Anführungszeichen: »…« für Zitate, ›…‹ für Zitate im Zitat.

=== 4. Befund-Abschnitt: Maße als Tabelle ===
Der Abschnitt == Befund == enthält oft eine »Maße:«-Angabe mit \
Aufzählungen wie:
  A Höhe 8,30 m; 3,60 × 4,90
  B Höhe 8,30 m; 10,10 × 4,90
Formatiere solche Maß-Listen als MediaWiki-Tabelle:
{{| class="wikitable"
|-
! Bereich !! Höhe !! Maße
|-
| A || 8,30 m || 3,60 × 4,90
|-
| B || 8,30 m || 10,10 × 4,90
|}}
Wenn es nur eine einzige Maßangabe gibt, keine Tabelle erstellen. \
Einleitungstext (»Maße:« oder »Maße (lichte Maße):«) als Zeile vor \
der Tabelle belassen. Alle anderen Teile des Befund-Abschnitts \
(Träger, Rahmen, Technik, Erhaltungszustand) NICHT in Tabellen umwandeln.

=== 5. Beschreibung: Abschnittskennungen formatieren ===
Kennungen wie »A1 HIMMELFAHRT CHRISTI Beschreibungstext…« bestehen aus:
- Buchstabe+Zahl → Buchstabe<sub>Zahl</sub> (z. B. A1 → A<sub>1</sub>)
- GROSSBUCHSTABEN-Titel → '''fett''' (z. B. '''HIMMELFAHRT CHRISTI''')
Ergebnis: A<sub>1</sub> '''HIMMELFAHRT CHRISTI''' Beschreibungstext…
Einfache Buchstabenkennungen ohne Zahl (A, B, C, W, …) bleiben ohne \
<sub>. Kennungen wie D<sub>1</sub>–4 (bereits mit sub) nicht doppelt formatieren.

=== 6. Quellen und Literatur: Aufzählungsliste ===
Der Abschnitt == Quellen und Literatur == enthält oft mehrere \
Literaturangaben hintereinander im Fließtext. Trenne jede Quellenangabe \
als einzelnen Aufzählungspunkt (* ) ab. Erkenne Einträge an Autorennamen, \
Titeln und Jahreszahlen. Beispiel:
Vorher:
  Braun-Augsburg, Bd 1, S. 334 f. KDB I IOB (1), S. 698. Thieme-Becker, Bd 22, S. 72.
Nachher:
  * Braun-Augsburg, Bd 1, S. 334 f.
  * KDB I IOB (1), S. 698.
  * Thieme-Becker, Bd 22, S. 72.

=== 7. Bestehendes Markup beibehalten ===
- [[File:…]] Bild-Einbindungen EXAKT unverändert lassen.
- == Überschriften == nicht umbenennen.
- <sub>, <sup>, '''…''' und andere vorhandene Formatierungen beibehalten.
- Keine neuen Inhalte hinzufügen, keinen Sinn verändern.
- OCR-Zeichensalat (sinnlose Zeichen-/Zahlenfolgen) entfernen.

== Artikeltext ==

{article_body}

== Verbesserter Text ==
"""

# LLM communication (mirrors run_pass1.py)
# ---------------------------------------------------------------------------

# No system prompt — Qwen3 thinking mode is on by default.
# Thinking produces better results for the complex formatting judgments in
# pass2 (bibliographic boundary detection, OCR artifact removal, table
# construction) at the cost of more tokens per article.
_SYSTEM = ""

# Generation options recommended by Qwen3 for thinking mode.
_OPTIONS = {"temperature": 0.6, "top_p": 0.95, "top_k": 20}


def post_generate(model: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "system": _SYSTEM,
            "prompt": prompt,
            "stream": True,
            "options": _OPTIONS,
        }
    )
    conn = http.client.HTTPConnection("localhost", 11434, timeout=600)
    conn.request(
        "POST",
        "/api/generate",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    if resp.status != 200:
        data = resp.read().decode("utf-8", errors="replace")
        conn.close()
        raise RuntimeError(f"Ollama returned {resp.status}: {data[:500]}")

    _TIMEOUT_S = 900  # 15 minutes – thinking mode adds reasoning tokens
    tokens: list[str] = []
    deadline = time.monotonic() + _TIMEOUT_S
    for raw_line in resp:
        if time.monotonic() > deadline:
            conn.close()
            raise RuntimeError(f"LLM response exceeded {_TIMEOUT_S}s timeout")
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        r = obj.get("response")
        if isinstance(r, str):
            tokens.append(r)
        if obj.get("done"):
            break
    conn.close()
    return "".join(tokens)


# ---------------------------------------------------------------------------
# Article processing
# ---------------------------------------------------------------------------


def process_article(
    wiki_path: Path,
    output_path: Path,
    model: str,
) -> bool:
    """Process a single formatted article. Returns True on success."""
    text = wiki_path.read_text(encoding="utf-8")
    template_block, fields, body = _parse_article_file(text)

    # Only process non-meta articles
    meta = fields.get("Meta", "")
    if meta:
        return False  # skip silently

    if not body.strip():
        print(f"  [SKIP] {wiki_path.name}: empty body", flush=True)
        return False

    prompt = PROMPT_TEMPLATE.format(
        article_body=body.strip(),
    )

    try:
        result = post_generate(model, prompt)
    except Exception as e:
        print(f"  [ERROR] {wiki_path.name}: {e}", flush=True)
        return False

    result = result.strip()
    if not result:
        print(f"  [WARN] {wiki_path.name}: empty LLM response", flush=True)
        return False

    # Re-attach template + improved body
    final = template_block.rstrip("\n") + "\n\n" + result + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final, encoding="utf-8")
    return True


def process_band(
    input_dir: Path,
    band_prefix: str,
    model: str,
    *,
    article_filter: str | None = None,
    remaining: int | None = None,
) -> tuple[int, int, int]:
    """Process all articles in a band. Returns (ok, skipped, failed)."""
    band_dir = input_dir / band_prefix
    out_band = OUTPUT_BASE / band_prefix

    if not band_dir.is_dir():
        print(f"[SKIP] {band_prefix}: not found", flush=True)
        return 0, 0, 0

    wiki_files = sorted(band_dir.glob("*.wiki"))
    if article_filter:
        wiki_files = [
            f for f in wiki_files
            if f.stem == article_filter
        ]
    if remaining is not None:
        wiki_files = wiki_files[:remaining]

    ok, skipped, failed = 0, 0, 0
    for wiki_path in wiki_files:
        out_path = out_band / wiki_path.name

        # Skip if already processed
        if out_path.exists():
            print(f"  [SKIP] {out_path.relative_to(REPO_ROOT)} exists", flush=True)
            ok += 1
            continue

        # Pre-check: is it a meta article?
        text = wiki_path.read_text(encoding="utf-8")
        _, fields, body = _parse_article_file(text)
        if fields.get("Meta", ""):
            skipped += 1
            continue

        if not model:
            # Dry-run: just count
            print(f"  [DRY-RUN] would process {band_prefix}/{wiki_path.name}", flush=True)
            ok += 1
            continue

        print(f"  Processing {wiki_path.name}...", flush=True)
        if process_article(wiki_path, out_path, model):
            ok += 1
            print(f"  [OK] {wiki_path.name}", flush=True)
        else:
            failed += 1

    return ok, skipped, failed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Pass 2: Improve formatted articles")
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Root formatted directory (data/formatted)",
    )
    parser.add_argument(
        "--band",
        metavar="BAND",
        help="Process only this band, e.g. Band01",
    )
    parser.add_argument(
        "--article",
        metavar="LEMMA",
        help="Process only this article (stem without .wiki). "
        "Requires --band.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Ollama model name (empty = dry-run, no LLM calls)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N articles (useful for test runs).",
    )
    args = parser.parse_args()

    if args.article and not args.band:
        parser.error("--article requires --band")

    input_dir: Path = args.input_dir

    if args.band:
        band_prefixes = [args.band]
    else:
        band_prefixes = sorted(
            p.name for p in input_dir.iterdir() if p.is_dir()
        )

    remaining = args.max_articles
    total_ok, total_skipped, total_failed = 0, 0, 0

    for bp in band_prefixes:
        if remaining is not None and remaining <= 0:
            break
        print(f"[BAND] {bp}", flush=True)
        ok, skipped, failed = process_band(
            input_dir,
            bp,
            args.model,
            article_filter=args.article,
            remaining=remaining,
        )
        total_ok += ok
        total_skipped += skipped
        total_failed += failed
        if remaining is not None:
            remaining -= ok + failed

    mode = "Processed" if args.model else "Would process"
    print(
        f"\n[DONE] {mode} {total_ok + total_failed} articles "
        f"({total_ok} ok, {total_failed} failed, {total_skipped} meta-skipped) "
        f"across {len(band_prefixes)} band(s).",
        flush=True,
    )
    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
