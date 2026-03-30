"""Pass 1: Merge Surya wiki + Transkribus OCR via LLM.

Pairs each p*.wiki file with its matching Transkribus text file,
sends both to the LLM using the prompt from prompt_pass1.py,
and writes the cleaned MediaWiki output.

Usage:
    # Process a single chunk (test, 20 pages max)
    python src/run_pass1.py \
        --input-dir data/extracted/Band01_chunk001 \
        --model qwen3:32b-fp16 \
        --max-pages 20
    # Output: data/extracted/Band01_chunk001/pass1/p001.wiki ...

    # Process specific pages
    python src/run_pass1.py \
        --input-dir data/extracted/Band01_chunk001 \
        --model qwen3:32b-fp16 \
        --pages p003 p004 p005

    # Process all chunks
    python src/run_pass1.py \
        --input-dir data/extracted \
        --model qwen3:32b-fp16
    # Output: data/extracted/Band*/pass1/p*.wiki
"""

import argparse
import json
import http.client
import re
import sys
import time
from pathlib import Path

PROMPT_TEMPLATE = """\
Du erhältst zwei OCR-Versionen derselben Doppelseite eines kunsthistorischen \
Fachbuches über barocke Deckenmalereien in Deutschland. Die Surya-Version hat \
bereits MediaWiki-Markup-Struktur, die Transkribus-Version ist Reintext.
Erstelle daraus eine einzige, bereinigte Textfassung in MediaWiki-Markup.

Grundregeln:
- Surya-Version ist die Basis: behalte ihr Markup, ihre Abschnittsstruktur \
(== Überschrift ==, ''' txt ''', <sub>, <sup>, <!-- txt -->) und Reihenfolge vollständig bei.
- Transkribus nur zur Korrektur einzelner unlesbarer oder offensichtlich falscher Stellen heranziehen.

Textbereinigung:
- Korrigiere OCR-Fehler (falsch erkannte Zeichen, Satzzeichen, zusammengerutschte \
oder getrennten Wörter wie „Stichkap pen" → „Stichkappen").
- <br>-Tags entfernen: bei Silbentrennung Wort zusammenführen \
(„ge-<br>bildet" → „gebildet"), sonst Zeilenumbruch durch Leerzeichen oder \n ersetzen.
- Scanfragmente entfernen: Kopf-/Fußzeilen, Seitenzahlen, Bildunterschriften, \
Zeichensalat (z. B. „D 110110 3,0 ) FR OSEXISO").

Zitate:
- Im Surya-Text sind erkannte Zitate bereits als {{ZITAT|NNN}} vormarkiert – \
diese Platzhalter EXAKT unverändert übernehmen, Inhalt niemals anpassen.
- Weitere (nicht vormarkierte) Zitate mit »« umschließen.
- Zitate über ca. 40 Wörter zusätzlich mit <blockquote>…</blockquote> umrahmen.

Sonstiges:
- Keine neuen Inhalte hinzufügen, Sinn nicht verändern.
- Abkürzungen (z. B. „ABA", „Pf 86", „DI", „NK 35") unverändert lassen.
- Nur den bereinigten MediaWiki-Text ausgeben, ohne Erläuterungen.

Surya-OCR:
{surya_text}

Transkribus-OCR:
{transkribus_text}

Bereinigter Text:"""


def find_transkribus_match(add_txt_dir: Path, page_stem: str) -> Path | None:
    """Find the Transkribus txt file matching a page stem like 'p003'."""
    for txt_file in sorted(add_txt_dir.glob("*.txt")):
        # Naming pattern: 0003_p003.txt or similar containing the page stem
        if page_stem in txt_file.stem:
            return txt_file
    return None


_QUOTE_RE = re.compile(r"»[^»«]*«", re.DOTALL)


def _extract_quotes(text: str) -> tuple[str, list[str]]:
    """Replace »…« spans with {{ZITAT|NNN}} placeholders to shield them from the LLM.

    Returns (modified_text, list_of_original_spans_in_order).
    """
    originals: list[str] = []

    def _sub(m: re.Match) -> str:
        idx = len(originals)
        originals.append(m.group(0))
        return "{{ZITAT|" + f"{idx:03d}" + "}}"

    return _QUOTE_RE.sub(_sub, text), originals


def _restore_quotes(text: str, originals: list[str]) -> str:
    """Replace {{ZITAT|NNN}} placeholders back with the original »…« spans."""
    for idx, original in enumerate(originals):
        text = text.replace("{{ZITAT|" + f"{idx:03d}" + "}}", original)
    return text


# System prompt for Qwen3 non-thinking mode.
# /no_think disables the <think>...</think> reasoning block for faster, lower-token output.
_SYSTEM_NO_THINK = "/no_think"

# Generation options tuned for Qwen3 non-thinking mode.
_OPTIONS_NO_THINK = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}


def post_generate(model: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "system": _SYSTEM_NO_THINK,
            "prompt": prompt,
            "stream": True,
            "options": _OPTIONS_NO_THINK,
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

    _TIMEOUT_S = 300  # 5 minutes total wall-clock limit
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


def process_page(
    wiki_file: Path, add_txt_dir: Path, output_file: Path, model: str
) -> bool:
    """Process a single page. Returns True on success."""
    page_stem = wiki_file.stem  # e.g. "p003"

    surya_text = wiki_file.read_text(encoding="utf-8", errors="replace")
    if not surya_text.strip():
        print(f"  [SKIP] {wiki_file.name}: empty surya file", flush=True)
        return False

    # Shield »…« spans from LLM edits by replacing them with opaque placeholders.
    # The LLM receives {{ZITAT|NNN}} and must not touch them; we restore afterwards.
    surya_shielded, quote_originals = _extract_quotes(surya_text)
    if quote_originals:
        print(
            f"  [INFO] Shielded {len(quote_originals)} quote(s) in {wiki_file.name}",
            flush=True,
        )

    transkribus_file = find_transkribus_match(add_txt_dir, page_stem)
    transkribus_text = ""
    if transkribus_file:
        transkribus_text = transkribus_file.read_text(
            encoding="utf-8", errors="replace"
        )
    else:
        print(f"  [WARN] No Transkribus match for {page_stem}", flush=True)

    prompt = PROMPT_TEMPLATE.format(
        surya_text=surya_shielded, transkribus_text=transkribus_text
    )

    try:
        result = post_generate(model, prompt)
    except Exception as e:
        print(f"  [ERROR] {wiki_file.name}: {e}", flush=True)
        return False

    result = result.strip()
    if not result:
        print(f"  [WARN] {wiki_file.name}: empty LLM response", flush=True)
        return False

    result = _restore_quotes(result, quote_originals)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(result + "\n", encoding="utf-8")
    return True


def process_chunk(
    chunk_dir: Path,
    model: str,
    pass_name: str = "pass1",
    page_filter: set[str] | None = None,
    remaining: int | None = None,
) -> tuple[int, int]:
    """Process all pages in a single chunk directory. Returns (ok, failed).

    Output is written to chunk_dir/pass_name/. remaining limits total pages.
    """
    wiki_dir = chunk_dir / "wiki"
    add_txt_dir = chunk_dir / "add_txt"
    output_dir = chunk_dir / pass_name

    if not wiki_dir.is_dir():
        print(f"[SKIP] No wiki/ in {chunk_dir.name}", flush=True)
        return 0, 0

    wiki_files = sorted(wiki_dir.glob("p*.wiki"))
    if page_filter:
        wiki_files = [f for f in wiki_files if f.stem in page_filter]
    if remaining is not None:
        wiki_files = wiki_files[:remaining]

    if not wiki_files:
        return 0, 0

    ok, failed = 0, 0
    for wiki_file in wiki_files:
        out_file = output_dir / wiki_file.name
        if out_file.exists():
            print(f"  [SKIP] {out_file} already exists", flush=True)
            ok += 1
            continue

        print(f"  Processing {wiki_file.name}...", flush=True)
        if process_page(wiki_file, add_txt_dir, out_file, model):
            ok += 1
            print(f"  [OK] {wiki_file.name}", flush=True)
        else:
            failed += 1

    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Pass 1: Merge Surya + Transkribus")
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Single chunk dir (e.g. data/extracted/Band01_chunk001) "
        "or parent dir (data/extracted) to process all chunks",
    )
    parser.add_argument(
        "--pass-name",
        default="pass1",
        help="Subdirectory name written inside each chunk dir (default: pass1)",
    )
    parser.add_argument("--model", default="qwen3:32b-fp16")
    parser.add_argument(
        "--pages",
        nargs="*",
        help="Process only these pages (e.g. p003 p004). "
        "Only works with a single chunk input dir.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Stop after processing N pages in total (useful for test runs).",
    )
    args = parser.parse_args()

    page_filter = set(args.pages) if args.pages else None
    remaining = args.max_pages  # None means unlimited

    # Determine if input is a single chunk or a parent directory
    if (args.input_dir / "wiki").is_dir():
        # Single chunk
        chunks = [args.input_dir]
    else:
        # Parent directory — find all chunk subdirectories
        chunks = [
            chunk_dir
            for chunk_dir in sorted(args.input_dir.iterdir())
            if chunk_dir.is_dir() and (chunk_dir / "wiki").is_dir()
        ]

    total_ok, total_failed = 0, 0
    for chunk_dir in chunks:
        if remaining is not None and remaining <= 0:
            break
        print(f"[CHUNK] {chunk_dir.name}  -> {chunk_dir / args.pass_name}", flush=True)
        ok, failed = process_chunk(
            chunk_dir, args.model, args.pass_name, page_filter, remaining
        )
        total_ok += ok
        total_failed += failed
        if remaining is not None:
            remaining -= ok + failed

    print(
        f"\n[DONE] Processed {total_ok + total_failed} pages: "
        f"{total_ok} ok, {total_failed} failed",
        flush=True,
    )
    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
