import argparse, json, re, http.client
from pathlib import Path

PROMPT_HEADER = """Clean and format this scanned German art historical text about baroque ceiling paintings.
Tasks:
- Fix broken line wraps and paragraphs.
- Correct obvious OCR mistakes.
- Remove stray map legends, page headers/footers, random image captions or wrongly scanned headlines.
- Preserve valid section headings.
- Output Markdown; before ':' when it denotes a label make it bold (**Label:**).
- Do NOT invent missing content.

Text to clean and format:
"""
PROMPT_SUFFIX = "\n\nCleaned text:\n"


def chunk_paragraphs(text: str, limit: int):
    paras = re.split(r"\n\s*\n", text)
    chunks = []
    cur, length = [], 0
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


def post_generate(model: str, prompt: str):
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


def parse_ndjson(data: str):
    out = []
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
    # fallback single JSON
    try:
        obj = json.loads(data)
        if isinstance(obj, dict) and isinstance(obj.get("response"), str):
            return obj["response"]
    except Exception:
        pass
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    chunks = chunk_paragraphs(raw, 18000)
    print(f"[INFO] Total chunks: {len(chunks)}", flush=True)

    # Truncate output file
    Path(args.output).write_text("", encoding="utf-8")

    for idx, chunk in enumerate(chunks, 1):
        prompt = f"{PROMPT_HEADER}{chunk}{PROMPT_SUFFIX}"
        print(f"[INFO] Chunk {idx}/{len(chunks)} chars={len(chunk)}", flush=True)
        status, data = post_generate(args.model, prompt)
        if status != 200 or not data.strip():
            print(
                f"[WARN] Chunk {idx} status={status} empty response; writing placeholder",
                flush=True,
            )
            cleaned = ""  # or keep empty
        else:
            cleaned = parse_ndjson(data).strip()
        with open(args.output, "a", encoding="utf-8") as f:
            if cleaned:
                f.write(cleaned)
            f.write("\n\n")

    # Collapse excessive blank lines
    final = Path(args.output).read_text(encoding="utf-8")
    final = re.sub(r"\n{3,}", "\n\n", final).strip() + "\n"
    Path(args.output).write_text(final, encoding="utf-8")
    print(f"[INFO] Wrote {args.output} total_chars={len(final)}", flush=True)


if __name__ == "__main__":
    main()
