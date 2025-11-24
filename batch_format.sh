#!/bin/bash
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
MODEL=${MODEL:-mistral:7b}

if [[ -z "$RAW_FILE" || -z "$OUT_FILE" ]]; then
  echo "[ERROR] args: RAW_FILE OUT_FILE" >&2
  exit 2
fi
if [[ ! -f "$RAW_FILE" ]]; then
  echo "[ERROR] missing input $RAW_FILE" >&2
  exit 3
fi
mkdir -p "$(dirname "$OUT_FILE")"

echo "[INFO] Host=$(hostname) Start=$(date)"
echo "[INFO] Model=$MODEL"

if ! command -v ollama >/dev/null 2>&1; then
  echo "[INFO] Installing Ollama..."
  curl -fsSL https://ollama.ai/install.sh | sh
fi

echo "[INFO] Starting Ollama..."
ollama serve &
OLLAMA_PID=$!
cleanup() {
  if [[ -n "${OLLAMA_PID:-}" ]] && kill -0 "$OLLAMA_PID" 2>/dev/null; then
    kill "$OLLAMA_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[INFO] Waiting for API..."
for i in {1..40}; do
  if curl -s -o /dev/null http://localhost:11434/api/tags; then
    echo "[INFO] Ready in ${i}s"
    break
  fi
  if [[ $i -eq 40 ]]; then
    echo "[ERROR] Ollama not ready"
    exit 7
  fi
  sleep 1
done

if ! ollama list | grep -q "^$MODEL"; then
  echo "[INFO] Pulling $MODEL..."
  ollama pull "$MODEL"
fi

python3 /workspace/format_chunks.py \
  --input "$RAW_FILE" \
  --output "$OUT_FILE" \
  --model "$MODEL"

echo "[INFO] Done $(date)"