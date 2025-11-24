#!/bin/bash
#
# SLURM batch script (Pyxis container) to format & correct an OCR'ed text
# Using Mistral served via Ollama inside an NVIDIA PyTorch container.
#
# Usage:
#   sbatch batch_format.sh "/workspace/data/raw/Band01_chunk001_full.txt" "/workspace/data/formatted/Band01_chunk001_formatted.md"
#
# Monitor:
#   tail -f log_<jobid>.out
# Cancel:
#   scancel <jobid>
#
# ---------------- Slurm Preamble ----------------
#SBATCH -p lrz-v100x2
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH -o logs/log_%j.out
#SBATCH -e logs/log_%j.err
#SBATCH --container-remap-root
#SBATCH --container-image=/dss/dsshome1/02/di97hiw/nvidia+pytorch+23.12-py3.sqsh
#SBATCH --container-mounts=/dss/dsshome1/02/di97hiw/arthistorical-semantic-data-extraction:/workspace

set -euo pipefail

RAW_FILE=${1:-${RAW_FILE:-""}}
OUT_FILE=${2:-${OUT_FILE:-""}}
MODEL="mistral:7b"
TEMP="0.3"
MAX_RETRIES=${MAX_RETRIES:-60}
RETRY_DELAY=${RETRY_DELAY:-5}

if [[ -z "$RAW_FILE" || -z "$OUT_FILE" ]]; then
  echo "[ERROR] RAW_FILE and OUT_FILE must be provided (args or env)." >&2
  exit 2
fi
if [[ ! -f "$RAW_FILE" ]]; then
  echo "[ERROR] Input file not found: $RAW_FILE" >&2
  exit 3
fi
mkdir -p "$(dirname "$OUT_FILE")"

echo "[INFO] (Container) Start on $(hostname) at $(date)" >&2
echo "[INFO] Input: $RAW_FILE" >&2
echo "[INFO] Output: $OUT_FILE" >&2

if ! command -v ollama >/dev/null 2>&1; then
  echo "[INFO] Installing Ollama..." >&2
  curl -fsSL https://ollama.ai/install.sh | sh
fi

echo "[INFO] Launching Ollama service..." >&2
ollama serve &
OLLAMA_PID=$!
cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[INFO] Waiting for Ollama readiness..." >&2
READY=0
for i in {1..30}; do
  if curl -s -o /dev/null http://localhost:11434/api/tags; then
    echo "[INFO] Ollama ready after ${i}s" >&2
    READY=1
    break
  fi
  sleep 1
done
if [[ $READY -ne 1 ]]; then
  echo "[ERROR] Ollama did not become ready within timeout." >&2
  exit 7
fi

# Pull model if needed
if ! ollama list | grep -q "^$MODEL"; then
  echo "[INFO] Pulling model $MODEL..." >&2
  ollama pull "$MODEL" || {
    echo "[ERROR] Failed to pull model $MODEL" >&2; kill $OLLAMA_PID || true; exit 4;
  }
fi

# Build raw prompt
PROMPT_HEADER=$(cat <<'EOT'
Clean and format this scanned German art historical text about baroque ceiling paintings. Fix line breaks, obvious OCR errors and remove random, wrongly scanned headlines, text from maps or artwork, or image captions. Export as Markdown; use bold for parts before ':' when they denote labels. Do not add new content.

Text to clean and format:
EOT
)

FILE_CONTENT=$(cat "$RAW_FILE")
PROMPT="${PROMPT_HEADER}${FILE_CONTENT}

Cleaned text:"

# Escape via python json.dumps to ensure valid JSON string
PROMPT_ESC=$(python3 - <<'PY'
import json,sys
prompt=sys.stdin.read()
print(json.dumps(prompt))
PY
<<<"$PROMPT")

JSON_PAYLOAD='{"model":"'$MODEL'","prompt":'$PROMPT_ESC',"stream":false,"options":{"temperature":'$TEMP'}}'

echo "[INFO] Sending prompt to model..." >&2
HTTP_CODE=$(curl -s -o "$RESP_FILE" -w '%{http_code}' -H 'Content-Type: application/json' -X POST http://localhost:11434/api/generate -d "$JSON_PAYLOAD" || echo 000)


echo "$FORMATTED" > "$OUT_FILE"
echo "[INFO] Wrote formatted output to $OUT_FILE" >&2
echo "[INFO] Completed at $(date)" >&2
