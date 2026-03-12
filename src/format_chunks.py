"""Clean and reformat OCR text chunks using a local Ollama LLM.

Configuration is done via the constants below.
When running via batch_format.sh, set INPUT_FILE, OUTPUT_FILE and MODEL
as environment variables before running the script:

    INPUT_FILE=data/raw/Band01_chunk001.txt \
    OUTPUT_FILE=data/formatted/Band01_chunk001_formatted.md \
    MODEL=mistral:7b \
    python src/format_chunks.py
"""

import json
import os
import re
import http.client
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

# Override via environment variables when calling from batch_format.sh
INPUT_FILE = Path(os.environ.get("INPUT_FILE", "data/raw/Band01_chunk001.txt"))
OUTPUT_FILE = Path(
    os.environ.get("OUTPUT_FILE", "data/formatted/Band01_chunk001_formatted.md")
)
MODEL = os.environ.get("MODEL", "mistral:7b")

# Maximum character length per LLM request chunk
CHUNK_LIMIT = 8000

# ──────────────────────────────────────────────────────────────────────────────

PROMPT_HEADER = """Bereinige und formatiere den folgenden eingescannten deutschsprachigen kunsthistorischen Text über barocke Deckenmalereien.
Aufgaben:
- Repariere falsch umbrochene Zeilen und Absätze.
- Korrigiere offensichtliche OCR-Fehler.
- Entferne zufällige Kartenlegenden, Seitenköpfe/-füße, Bildunterschriften oder falsch erkannte Überschriften.
- Erhalte sinnvolle Abschnittsüberschriften.
- Ausgabe als Markdown.
- Füge KEINE neuen Inhalte hinzu.
- Fehler bei hochgestellten und tiefgestellten Nummern und Buchstaben beheben.
- 'x' bei Maßangaben (z.B 6,10 x 10,50) kleinschreiben (nicht 'X').
- Durchmesser- und Durchschnitts-Symbole sowie Kreuzzeichen korrekt wiedergeben, werden im OCR oft falsch erkannt.
- Zitate nicht verändern oder inhaltlich korrigieren.
- Falsch erkannte Zirkumflex-Zeichen nicht als Umlaut behandeln.
- Antworte nur mit dem bereinigten Text.

Zu bereinigender Text:
"""
PROMPT_SUFFIX = "\n\nBereinigter Text:\n"


def chunk_paragraphs(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    paras = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    cur: list[str] = []
    length = 0
    for p in paras:
        plen = len(p) + 2
        if cur and length + plen > limit:
            chunks.append("\n\n".join(cur))
            cur = [p]
            length = plen
        else:
            cur.append(p)
            length += plen
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def post_generate(model: str, prompt: str) -> tuple[int, str]:
    body = json.dumps({"model": model, "prompt": prompt, "stream": True})
    conn = http.client.HTTPConnection("localhost", 11434, timeout=300)
    conn.request(
        "POST", "/api/generate", body=body, headers={"Content-Type": "application/json"}
    )
    resp = conn.getresponse()
    status = resp.status
    data = resp.read().decode("utf-8", errors="replace")
    conn.close()
    return status, data


def parse_ndjson(data: str) -> str:
    out: list[str] = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        r = obj.get("response")
        if isinstance(r, str):
            out.append(r)
        if obj.get("done") is True:
            break
    if out:
        return "".join(out)
    try:
        obj = json.loads(data)
        if isinstance(obj, dict) and isinstance(obj.get("response"), str):
            return obj["response"]
    except Exception:
        pass
    return ""


def main() -> None:
    raw = INPUT_FILE.read_text(encoding="utf-8", errors="replace")
    chunks = chunk_paragraphs(raw)
    print(f"[INFO] Total chunks: {len(chunks)}", flush=True)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("", encoding="utf-8")

    for idx, chunk in enumerate(chunks, 1):
        prompt = f"{PROMPT_HEADER}{chunk}{PROMPT_SUFFIX}"
        print(f"[INFO] Chunk {idx}/{len(chunks)} chars={len(chunk)}", flush=True)
        status, data = post_generate(MODEL, prompt)
        if status != 200 or not data.strip():
            print(
                f"[WARN] Chunk {idx} status={status} empty response; skipping",
                flush=True,
            )
            cleaned = ""
        else:
            cleaned = parse_ndjson(data).strip()
        with OUTPUT_FILE.open("a", encoding="utf-8") as f:
            if cleaned:
                f.write(cleaned)
            f.write("\n\n")

    final = OUTPUT_FILE.read_text(encoding="utf-8")
    final = re.sub(r"\n{3,}", "\n\n", final).strip() + "\n"
    OUTPUT_FILE.write_text(final, encoding="utf-8")
    print(f"[INFO] Wrote {OUTPUT_FILE} total_chars={len(final)}", flush=True)


if __name__ == "__main__":
    main()
