#!/bin/bash
#SBATCH -p lrz-v100x2
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH -o logs/log_%j.out
#SBATCH -e logs/log_%j.err
#SBATCH --container-remap-root
#SBATCH --container-image=/dss/dsshome1/02/USERNAME_HERE/nvidia+pytorch+23.12-py3.sqsh
#SBATCH --container-mounts=/dss/dsshome1/02/USERNAME_HERE/arthistorical-semantic-data-extraction:/workspace

set -euo pipefail
cd /workspace

MODEL=qwen3:14b
# Non-thinking mode: add /no_think to the system prompt in run_pass1.py for faster, deterministic output.
# Recommended Ollama options for non-thinking mode: temperature=0.7, top_p=0.8, top_k=20

echo "[INFO] Host=$(hostname) Start=$(date)"

# Install and start Ollama
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.ai/install.sh | sh
fi
ollama serve &
for i in {1..60}; do
  curl -s -o /dev/null http://localhost:11434/api/tags && break
  [ "$i" -eq 60 ] && { echo "[ERROR] Ollama timeout"; exit 7; }
  sleep 1
done
ollama pull "$MODEL"

# TEST RUN — process first 20 pages of Band01_chunk001 to verify quality before full run
python3 src/run_pass1.py \
  --input-dir data/extracted/Band01_chunk001 \
  --output-dir data/pass1/Band01_chunk001 \
  --model "$MODEL" \
  --max-pages 20

# FULL RUN — uncomment once test results are verified
# python3 src/run_pass1.py \
#   --input-dir data/extracted \
#   --output-dir data/pass1 \
#   --model "$MODEL"

echo "[INFO] Done $(date)"