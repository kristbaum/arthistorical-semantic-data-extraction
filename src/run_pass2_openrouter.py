"""Pass 2 (OpenRouter variant): same improvements as run_pass2.py, but calls
the OpenRouter API (OpenAI-compatible chat completions) over HTTPS instead of
a local Ollama instance.

Requires the environment variable OPENROUTER_API_KEY to be set.

Prompt, abbreviations, article parsing and output layout are shared with
run_pass2.py.  Only the LLM transport layer differs.

When calling cloud APIs, paying per token rather than per GPU-hour, the
default model is qwen/qwen3-next-80b-a3b-instruct:free (free tier, good for
testing).  Switch to qwen/qwen3-235b-a22b for the best quality production run,
or qwen/qwen3-30b-a3b for an ~8× cheaper alternative.

Usage:
    export OPENROUTER_API_KEY=sk-or-...

    # Dry-run (no API calls, just counts articles)
    python src/run_pass2_openrouter.py --input-dir data/formatted --band Band01

    # Test single article
    python src/run_pass2_openrouter.py \\
        --input-dir data/formatted --band Band01 \\
        --article "Antdorf, Kirnbergkapelle" \\
        --model qwen/qwen3-235b-a22b

    # Process everything
    python src/run_pass2_openrouter.py \\
        --input-dir data/formatted \\
        --model qwen/qwen3-235b-a22b
"""

import argparse
import json
import http.client
import os
import re
import ssl
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared prompt / parsing from the Ollama variant
# ---------------------------------------------------------------------------

from run_pass2 import (
    PROMPT_TEMPLATE,
    _ABBREVIATIONS_BLOCK,
    _parse_article_file,
    REPO_ROOT,
    OUTPUT_BASE,
)

# ---------------------------------------------------------------------------
# OpenRouter transport
# ---------------------------------------------------------------------------

_OR_HOST = "openrouter.ai"
_OR_PATH = "/api/v1/chat/completions"

# Strip <think>…</think> blocks that some model variants stream into content.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

_TIMEOUT_S = 900  # 15 minutes – thinking mode produces many reasoning tokens


def post_generate(model: str, prompt: str) -> str:
    """Call OpenRouter chat completions (streaming) and return the text content."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is not set. "
            "Get a key at https://openrouter.ai/keys"
        )

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    )

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(_OR_HOST, 443, timeout=_TIMEOUT_S, context=ctx)
    conn.request(
        "POST",
        _OR_PATH,
        body=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # Recommended by OpenRouter for attribution / rate-limit tiers
            "HTTP-Referer": "https://deckenmalerei.eu",
            "X-Title": "CbDD Pass 2",
        },
    )

    resp = conn.getresponse()
    if resp.status != 200:
        data = resp.read().decode("utf-8", errors="replace")
        conn.close()
        raise RuntimeError(f"OpenRouter returned HTTP {resp.status}: {data[:500]}")

    tokens: list[str] = []
    deadline = time.monotonic() + _TIMEOUT_S

    for raw_line in resp:
        if time.monotonic() > deadline:
            conn.close()
            raise RuntimeError(f"Response exceeded {_TIMEOUT_S}s timeout")

        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or line.startswith(":"):  # SSE heartbeat / comment
            continue
        if line == "data: [DONE]":
            break
        if not line.startswith("data: "):
            continue

        try:
            obj = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        delta = obj.get("choices", [{}])[0].get("delta", {})
        # reasoning_content holds thinking tokens → ignore
        chunk = delta.get("content") or ""
        if chunk:
            tokens.append(chunk)

    conn.close()

    result = "".join(tokens)
    # Belt-and-suspenders: strip any <think>…</think> that leaked into content
    result = _THINK_RE.sub("", result).strip()
    return result


# ---------------------------------------------------------------------------
# Article processing (same logic as run_pass2.py, calls local post_generate)
# ---------------------------------------------------------------------------


def process_article(wiki_path: Path, output_path: Path, model: str) -> bool:
    """Process a single formatted article. Returns True on success."""
    text = wiki_path.read_text(encoding="utf-8")
    template_block, fields, body = _parse_article_file(text)

    if fields.get("Meta", ""):
        return False  # skip meta articles silently

    if not body.strip():
        print(f"  [SKIP] {wiki_path.name}: empty body", flush=True)
        return False

    prompt = PROMPT_TEMPLATE.format(
        abbreviations_block=_ABBREVIATIONS_BLOCK,
        article_body=body.strip(),
    )

    try:
        result = post_generate(model, prompt)
    except Exception as e:
        print(f"  [ERROR] {wiki_path.name}: {e}", flush=True)
        return False

    if not result:
        print(f"  [WARN] {wiki_path.name}: empty response", flush=True)
        return False

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
        wiki_files = [f for f in wiki_files if f.stem == article_filter]
    if remaining is not None:
        wiki_files = wiki_files[:remaining]

    ok, skipped, failed = 0, 0, 0
    for wiki_path in wiki_files:
        out_path = out_band / wiki_path.name

        if out_path.exists():
            print(f"  [SKIP] {out_path.relative_to(REPO_ROOT)} exists", flush=True)
            ok += 1
            continue

        text = wiki_path.read_text(encoding="utf-8")
        _, fields, _ = _parse_article_file(text)
        if fields.get("Meta", ""):
            skipped += 1
            continue

        if not model:
            print(
                f"  [DRY-RUN] would process {band_prefix}/{wiki_path.name}", flush=True
            )
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
    parser = argparse.ArgumentParser(description="Pass 2 via OpenRouter API")
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Root formatted directory (data/formatted)",
    )
    parser.add_argument(
        "--band", metavar="BAND", help="Process only this band, e.g. Band01"
    )
    parser.add_argument(
        "--article",
        metavar="LEMMA",
        help="Process only this article stem (requires --band)",
    )
    parser.add_argument(
        "--model",
        default="qwen/qwen3.5-35b-a3b",
        help=(
            "OpenRouter model ID (empty string = dry-run, no API calls). "
            "Default: qwen/qwen3-next-80b-a3b-instruct:free (free tier, good for testing). "
            "qwen/qwen3-235b-a22b — best quality; "
            "qwen/qwen3-30b-a3b — ~8× cheaper, still excellent."
        ),
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N articles (useful for cost-controlled test runs).",
    )
    args = parser.parse_args()

    if args.article and not args.band:
        parser.error("--article requires --band")

    band_prefixes = (
        [args.band]
        if args.band
        else sorted(p.name for p in args.input_dir.iterdir() if p.is_dir())
    )

    remaining = args.max_articles
    total_ok, total_skipped, total_failed = 0, 0, 0

    for bp in band_prefixes:
        if remaining is not None and remaining <= 0:
            break
        print(f"[BAND] {bp}", flush=True)
        ok, skipped, failed = process_band(
            args.input_dir,
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
