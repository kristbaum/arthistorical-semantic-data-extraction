# LRZ AI System — OCR Post-Processing Guide

Guide for running LLM-based OCR merging and cleanup on the LRZ AI Systems using Ollama + Qwen3.

## Paths

| What             | Path                                              |
| ---------------- | ------------------------------------------------- |
| Home directory   | `/dss/dsshome1/02/USERNAME_HERE`                  |
| Project repo     | `~/arthistorical-semantic-data-extraction`        |
| Container image  | `~/nvidia+pytorch+23.12-py3.sqsh`                 |
| Surya wiki files | `data/extracted/Band*/wiki/p*.wiki` (~3000 files) |
| Transkribus text | `data/extracted/Band*/add_txt/0*_p*.txt`          |
| Pass 1 output    | `data/pass1/Band*/p*.wiki`                        |
| Pass 2 output    | `data/pass2/Band*/p*.wiki`                        |
| Pass 3 output    | `data/pass3/Band*/`                               |

## 1. Quick Test (Interactive Session)

### 1.1 Allocate a GPU and start a container

```bash
ssh USERNAME_HERE@login.ai.lrz.de
cd ~/arthistorical-semantic-data-extraction

# Allocate one V100 GPU for 2 hours
salloc -p lrz-v100x2 --gres=gpu:1 --time=02:00:00
salloc -p lrz-hgx-h100-94x4 --gres=gpu:1 --time=24:00:00

# Start interactive shell inside the container
srun --pty \
  --container-remap-root \
  --container-image=$HOME/nvidia+pytorch+23.12-py3.sqsh \
  --container-mounts=$HOME/arthistorical-semantic-data-extraction:/workspace \
  bash
```

### 1.2 Install Ollama and pull model

```bash
# Inside the container
cd /workspace

# Install Ollama
apt-get update
apt-get install -y zstd
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama in background
ollama serve &

# Wait for API readiness
until curl -s http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 1; done

# Pull model — Qwen3:32b-fp16 (66 GB) fits comfortably on a single H100 (94 GB VRAM)
# Non-thinking mode is used for efficiency (append /no_think to system prompt in run_pass1.py)
ollama pull qwen3:32b-fp16
```

### 1.3 Test Pass 1 on a few pages

```bash
# Run on 3 sample pages to verify quality
# Output goes to data/extracted/Band01_chunk001/pass1/p*.wiki
python3 src/run_pass1.py \
  --input-dir data/extracted/Band01_chunk001 \
  --model qwen3:32b-fp16 \
  --pages p013 p014 p015

# Inspect the results
cat data/extracted/Band01_chunk001/pass1/p003.wiki
```

Compare the output against the originals:

```bash
diff data/extracted/Band01_chunk001/wiki/p003.wiki data/extracted/Band01_chunk001/pass1/p013.wiki
```

### 1.4 Save test results for local review via rsync

From your **local machine**:

```bash
# From local machine — syncs pass1/ outputs back into the local extracted chunk dirs
rsync -avz --include='*/' --include='pass1/' --include='pass1/*.wiki' --exclude='*' \
  USERNAMEHERE@login.ai.lrz.de:~/arthistorical-semantic-data-extraction/data/extracted/ \
  data/extracted/
```

## 2. Full Pass 1 — Merge Surya + Transkribus OCR

Pass 1 pairs each Surya `.wiki` file with its corresponding Transkribus `.txt` file and sends both to the LLM. The Surya version is the structural base; Transkribus fills in gaps where Surya OCR failed. Output is cleaned MediaWiki markup.

```bash
sbatch batch_pass1.sh
```

The script processes all ~3000 pages across all Band chunks. Monitor progress:

```bash
# Check job status
squeue -u $USER

# Follow logs
tail -f logs/log_$(squeue -u $USER -h -o %i | head -1).out
```

## 3. Pass 2 — Expand Abbreviations

Pass 2 takes the cleaned Pass 1 output and expands domain-specific abbreviations using the glossary from each volume.

```bash
sbatch batch_pass2.sh
```

Uses the same container setup. The prompt instructs the LLM to expand abbreviations (ABA, Pf, DI, NK, B. V.-F, etc.) based on the volume-specific glossary while preserving all other text.

## 4. Pass 3 — Split into Articles

Pass 3 splits the continuous page text into individual building-based articles and standardizes their structure with sections:

- Patrozinium
- Zum Bauwerk
- Auftraggeber
- Autor und Entstehungszeit
- Befund
- Beschreibung und Ikonographie
- Literatur
- Photographische Dokumentation
- Planskizzen
- Anhang

```bash
sbatch batch_pass3.sh
```

## 5. Sync Results

After each pass completes, sync results to your local machine:

```bash
# From local machine — syncs all pass*/  subdirs within each chunk back into data/extracted/
rsync -avz --include='*/' --include='pass*/' --include='pass*/*.wiki' --exclude='*' \
  USERNAMEHERE@login.ai.lrz.de:~/arthistorical-semantic-data-extraction/data/extracted/ \
  data/extracted/
```

## 6. Debug Commands

```bash
# Check GPU status and VRAM usage
nvidia-smi

# Check active jobs
squeue -u $USER

# Cancel a job
scancel <job_id>

# Check Ollama model list (inside container)
ollama list

# Test Ollama is responding (inside container)
curl http://localhost:11434/api/tags

# View job output after completion
sacct -j <job_id> --format=JobID,State,Elapsed,MaxRSS

# Check available partitions
sinfo
```

## 7. Model Choice

| Model            | VRAM   | Speed | Partition                           | Thinking |
| ---------------- | ------ | ----- | ----------------------------------- | -------- |
| `qwen3:14b`      | ~10 GB | Fast  | `lrz-v100x2` (1× V100 16 GB)        | optional |
| `qwen3:32b-q8_0` | ~35 GB | Good  | `lrz-hgx-a100-80x4` (1× A100 80 GB) | optional |
| `qwen3:32b-fp16` | ~66 GB | Good  | `lrz-hgx-h100-94x4` (1× H100 94 GB) | optional |

For production runs, `qwen3:32b-fp16` on H100 is the recommended choice — full precision, ~27 GB headroom. Fall back to `qwen3:32b-q8_0` on A100 or `qwen3:14b` on V100 if H100 nodes are unavailable.

**Non-thinking mode** (recommended for OCR cleanup tasks): append `/no_think` to the system prompt sent to Ollama. This disables the `<think>...</think>` reasoning block, reducing token usage and latency. Equivalent Ollama generation options: `temperature=0.7`, `top_p=0.8`, `top_k=20`.

When using a different partition, update the `#SBATCH -p` and `--gres` lines in the batch scripts accordingly.
