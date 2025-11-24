# LRZ AI System Usage

## Create Container image

```bash
# Allocate a single GPU on V100 partition
salloc -p lrz-v100x2 --gres=gpu:1 --time=02:00:00  # 1-GPU, 2-hour limit

# For larger models, you might need more GPUs
# salloc -p lrz-dgx-1-v100x8 --gres=gpu:2
```

```bash
srun --pty bash
```

```bash
# Import PyTorch container from NVIDIA NGC
enroot import docker://nvcr.io#nvidia/pytorch:23.12-py3

# Create container
enroot create --name llm-workspace pytorch:23.12-py3.sqsh

# Start container with mounted data directory
enroot start --mount /your/data/path:/workspace/data llm-workspace
```

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service in background
ollama serve &

# First, pull Mistral for text formatting and error correction
ollama pull mistral:7b
```

```bash
# Save custom containers for reuse
enroot export --output my_custom_llm_container.sqsh llm-workspace

# Save your data and scripts to persistent storage
cp -r /workspace/results /your/persistent/path/
```

### Debug Commands

```bash
# Check GPU status
nvidia-smi

# Check container status
enroot list

# Monitor system resources
htop

# Check your active allocations
squeue -u $USER
```
