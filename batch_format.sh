#!/bin/bash
#
# SLURM batch script (Pyxis container) to format & correct an OCR'ed art-historical text file
# using Mistral served via Ollama inside an NVIDIA PyTorch container.
#
# Usage:
#   sbatch batch_format_container.sh "/absolute/path/to/repo/data/raw/Band01_chunk001.txt" "/absolute/path/to/repo/data/formatted/Band01_chunk001_formatted.md"
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
#SBATCH --container-image=/dss/dsshome1/02/di97hiw/nvidia+pytorch+23.12-py3.sqsh
#SBATCH --container-mounts=/dss/dsshome1/02/di97hiw/arthistorical-semantic-data-extraction:/workspace


set -euo pipefail

RAW_FILE=${1:-${RAW_FILE:-""}}
OUT_FILE=${2:-${OUT_FILE:-""}}
MODEL="mistral:7b"
TEMP="0.3"

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

##################################################
# 1. Install & start Ollama inside container
##################################################

if ! command -v ollama >/dev/null 2>&1; then
  echo "[INFO] Installing Ollama..." >&2
  curl -fsSL https://ollama.ai/install.sh | sh
fi

echo "[INFO] Launching Ollama service..." >&2
ollama serve &
OLLAMA_PID=$!
sleep 8

##################################################
# 2. Pull model if needed
##################################################

if ! ollama list | grep -q "^$MODEL"; then
  echo "[INFO] Pulling model $MODEL..." >&2
  ollama pull "$MODEL" || {
    echo "[ERROR] Failed to pull model $MODEL" >&2; kill $OLLAMA_PID || true; exit 4;
  }
fi

##################################################
# 3. Read input & build JSON prompt
##################################################

FILE_CONTENT=$(sed 's/"/\\"/g' "$RAW_FILE")
PROMPT="Clean and format this scanned German art historical text about baroque ceiling paintings. Fix line breaks, obvious OCR errors and remove random, wrongly scanned headlines, text from maps or artwork, or image captions. Export as Markdown; use bold for parts before ':' when they denote labels. Do not add new content.\n\nText to clean and format:\n$FILE_CONTENT\n\nCleaned text:"

JSON_PAYLOAD=$(cat <<EOF
{
  "model": "$MODEL",
  "prompt": "$PROMPT",
  "stream": false,
  "options": {"temperature": $TEMP}
}
EOF
)

##################################################
# 4. Call Ollama API
##################################################

echo "[INFO] Sending prompt to model..." >&2
RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate -d "$JSON_PAYLOAD" || true)

if [[ -z "$RESPONSE" ]]; then
  echo "[ERROR] Empty response from model" >&2
  kill $OLLAMA_PID || true
  exit 5
fi

FORMATTED=$(echo "$RESPONSE" | python3 - <<'PY'
import sys, json
data=json.loads(sys.stdin.read())
print(data.get("response",""))
PY
)

if [[ -z "$FORMATTED" ]]; then
  echo "[ERROR] No 'response' field found in model output." >&2
  kill $OLLAMA_PID || true
  exit 6
fi


echo "$FORMATTED" > "$OUT_FILE"
echo "[INFO] Wrote formatted output to $OUT_FILE" >&2

kill $OLLAMA_PID >/dev/null 2>&1 || true
echo "[INFO] Completed at $(date)" >&2
