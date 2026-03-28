#!/bin/bash
#SBATCH -p lrz-hgx-h100-94x4
#SBATCH --gres=gpu:1
#SBATCH --time=12:00:00
#SBATCH -o logs/log_%j.out
#SBATCH -e logs/log_%j.err
#SBATCH --container-remap-root

set -euo pipefail
cd /workspace

MODEL=qwen3:32b-fp16
# Non-thinking mode: add /no_think to the system prompt in run_pass1.py for faster, deterministic output.
# Recommended Ollama options for non-thinking mode: temperature=0.7, top_p=0.8, top_k=20

echo "[INFO] Host=$(hostname) Start=$(date)"

# Install and start Ollama
if ! command -v ollama >/dev/null 2>&1; then
  apt-get update
  apt-get install -y zstd pciutils
  curl -fsSL https://ollama.ai/install.sh | sh
fi
ollama serve &
for i in {1..60}; do
  curl -s -o /dev/null http://localhost:11434/api/tags && break
  [ "$i" -eq 60 ] && { echo "[ERROR] Ollama timeout"; exit 7; }
  sleep 1
done
ollama pull "$MODEL"

python3 src/run_pass1.py \
  --input-dir data/extracted \
  --model "$MODEL" \

echo "[INFO] Done $(date)"