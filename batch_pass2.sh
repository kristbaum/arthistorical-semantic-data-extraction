#!/bin/bash
#SBATCH -p lrz-hgx-h100-94x4
#SBATCH --gres=gpu:1
#SBATCH --time=00:30:00
#SBATCH -o logs/log_%j.out
#SBATCH -e logs/log_%j.err
#SBATCH --container-remap-root

set -euo pipefail
cd /workspace

MODEL=qwen3:32b-fp16

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

python3 src/run_pass2.py \
  --input-dir data/formatted \
  --model "$MODEL"

echo "[INFO] Done $(date)"
