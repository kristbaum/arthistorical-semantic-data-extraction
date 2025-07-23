# LRZ AI System Usage Guide for LLM Text Processing

This guide provides step-by-step instructions for running large language models (LLMs) on the LRZ AI systems to process and format large volumes of text, specifically for arthistorical semantic data extraction.

## Prerequisites

- Valid LRZ account with access to AI systems
- SSH access to LRZ login nodes
- Basic familiarity with SLURM workload manager

## Quick Start Guide

⚠️ **Important**: LRZ resources are **not** automatically released. Always remember to exit your allocations when done to avoid unnecessary charges. See [Resource Management](#resource-management) section below.

### 1. Connect and Allocate Resources

After logging into the LRZ system, allocate GPU resources for your work:

```bash
# Allocate a single GPU on V100 partition
salloc -p lrz-v100x2 --gres=gpu:1

# For larger models, you might need more GPUs
# salloc -p lrz-dgx-1-v100x8 --gres=gpu:2
```

### 2. Start Interactive Session

Launch an interactive session on the allocated compute node:

```bash
srun --pty bash
```

### 3. Set Up Container Environment

The LRZ system uses Enroot containers. Choose from these options:

```bash
# Import PyTorch container from NVIDIA NGC
enroot import docker://nvcr.io#nvidia/pytorch:23.12-py3

# Create container
enroot create --name llm-workspace pytorch:23.12-py3.sqsh

# Start container with mounted data directory
enroot start --mount /your/data/path:/workspace/data llm-workspace
```

### 4. Install LLM Framework

Inside the container, install your preferred LLM framework:

#### For Ollama (Recommended for local models)

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service in background
ollama serve &

# First, pull Mistral for text formatting and error correction
ollama pull mistral:7b
```

#### For Transformers (Hugging Face)

```bash
pip install transformers torch accelerate
```

### 5. Test Mistral Setup

Create a simple test script to verify Mistral is working for text formatting:

```bash
cat > test_mistral.py << 'EOF'
#!/usr/bin/env python3
import requests
import json

def test_ollama_connection():
    """Test if Ollama is running and can process text"""
    try:
        # Test connection to Ollama
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            print("✓ Ollama is running")
            models = response.json().get('models', [])
            print(f"Available models: {[m['name'] for m in models]}")
            return True
        else:
            print("✗ Ollama not responding")
            return False
    except Exception as e:
        print(f"✗ Error connecting to Ollama: {e}")
        return False

def format_and_clean_text(text, model="mistral:7b"):
    """Test function to format and clean art historical text using Mistral"""
    
    prompt = f"""
    Please clean and format the following art historical text. Fix any grammar errors, 
    standardize terminology, and improve readability while preserving all factual 
    information and historical context. Maintain any foreign language terms that 
    are standard in art history.
    
    Text to clean and format:
    {text}
    
    Cleaned text:
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for consistent formatting
                    "top_p": 0.9
                }
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['response']
        else:
            return f"Error: {response.status_code}"
            
    except Exception as e:
        return f"Error: {e}"

# Test the setup
if __name__ == "__main__":
    print("Testing Mistral setup on LRZ...")
    
    if test_ollama_connection():
        # Sample messy art historical text that needs formatting
        sample_text = """
        vincent van gogh painted the starry night in 1889 while he was patient 
        at saint-paul-de-mausole asylum in saint rémy de provence france this 
        post impressionist masterpiece depicts swirling night sky over village 
        combining observation and imagination painting showcases van goghs 
        distinctive style with bold brushstrokes vibrant colors
        """
        
        print("\nOriginal text:")
        print(sample_text)
        print("\nCleaning and formatting text...")
        result = format_and_clean_text(sample_text)
        print("\nFormatted output:")
        print(result)
    else:
        print("Please start Ollama first: ollama serve &")
EOF

# Make it executable and run
chmod +x test_mistral.py
python test_mistral.py
```

### 6. Set Up DeepSeek for Structured Extraction

Once Mistral is working, add the DeepSeek model for structured data extraction:

```bash
# Pull DeepSeek Coder model for structured extraction
ollama pull deepseek-coder:6.7b

# Verify both models are available
ollama list
```

### 7. Test Complete Pipeline

Create a comprehensive test that uses both models:

```bash
cat > test_pipeline.py << 'EOF'
#!/usr/bin/env python3
import requests
import json

def clean_text_with_mistral(text):
    """Clean and format text using Mistral"""
    prompt = f"""
    Clean and format this art historical text. Fix grammar, standardize terminology, 
    and improve readability while preserving all factual information:
    
    {text}
    
    Cleaned text:
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral:7b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3}
            }
        )
        if response.status_code == 200:
            return response.json()['response'].strip()
        return text  # Fallback to original if cleaning fails
    except:
        return text

def extract_triplets_with_deepseek(text):
    """Extract semantic triplets using DeepSeek"""
    prompt = f"""
    Extract semantic triplets from this art historical text. Return JSON format:
    [["Subject", "Predicate", "Object"], ["Subject", "Predicate", "Object"]]
    
    Focus on relationships between artists, artworks, dates, styles, and locations.
    
    Text: {text}
    
    JSON:
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "deepseek-coder:6.7b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1}
            }
        )
        if response.status_code == 200:
            result = response.json()['response']
            # Try to parse JSON from response
            start = result.find('[')
            end = result.rfind(']') + 1
            if start != -1 and end != 0:
                return json.loads(result[start:end])
        return []
    except Exception as e:
        return f"Error: {e}"

# Test complete pipeline
if __name__ == "__main__":
    raw_text = """
    pablo picasso painted les demoiselles davignon in 1907 this work considered 
    seminal piece in development of cubism showing influence of african mask art 
    painting depicts five nude female figures with fragmented geometric forms
    """
    
    print("🎨 Testing Complete Pipeline")
    print("=" * 50)
    print(f"Original text: {raw_text}")
    
    # Stage 1: Clean with Mistral
    print("\n📝 Stage 1: Cleaning text with Mistral...")
    cleaned_text = clean_text_with_mistral(raw_text)
    print(f"Cleaned text: {cleaned_text}")
    
    # Stage 2: Extract with DeepSeek
    print("\n🔍 Stage 2: Extracting triplets with DeepSeek...")
    triplets = extract_triplets_with_deepseek(cleaned_text)
    print("Extracted triplets:")
    for i, triplet in enumerate(triplets, 1):
        if isinstance(triplet, list) and len(triplet) == 3:
            print(f"  {i}. [{triplet[0]}] → [{triplet[1]}] → [{triplet[2]}]")
EOF

# Run the complete pipeline test
python test_pipeline.py

# Clean up and exit when done
echo "🔧 Work completed. Remember to exit your allocation:"
echo "1. Type 'exit' to leave the container"
echo "2. Type 'exit' again to leave the interactive session"
echo "3. Type 'exit' one more time to release the allocation"
```

## Batch Job Example

For processing larger volumes of text, use batch jobs:

```bash
cat > process_texts.sbatch << 'EOF'
#!/bin/bash
#SBATCH -p lrz-v100x2
#SBATCH --gres=gpu:1
#SBATCH -o llm_processing.out
#SBATCH -e llm_processing.err
#SBATCH --container-image=nvcr.io#nvidia/pytorch:23.12-py3
#SBATCH --container-mounts=/your/data/path:/workspace/data

# Start Ollama service
ollama serve &
sleep 10

# Pull both models if not already available
ollama pull mistral:7b
ollama pull deepseek-coder:6.7b

# Run your text processing script
python /workspace/data/process_arthistory_texts.py
EOF

# Submit the job
sbatch process_texts.sbatch
```

## Model Recommendations

For art historical text processing:

| Model | Size | Primary Use Case | Strengths |
|-------|------|------------------|-----------|
| `mistral:7b` | 7B | **Text formatting & error correction** | Multilingual, fast, preserves meaning |
| `deepseek-coder:6.7b` | 6.7B | **Structured data extraction** | High accuracy, consistent JSON output |
| `llama2:7b` | 7B | General text analysis | Good balance, reliable |
| `codellama:7b` | 7B | Alternative structured extraction | Code-focused, consistent formatting |

### Usage Recommendations

- **Pipeline approach**: Use `mistral:7b` first for text cleanup, then `deepseek-coder:6.7b` for extraction
- **Single-pass workflow**: Use `deepseek-coder:6.7b` if you need both correction and extraction in one step
- **Multilingual texts**: Always prefer `mistral:7b` for texts with mixed languages

## Performance Tips

1. **Batch Processing**: Process multiple texts in batches for efficiency
2. **Model Size**: Start with smaller models (7B) and scale up if needed
3. **Container Persistence**: Use `enroot export` to save configured containers
4. **Resource Management**: Always release allocated resources when done to avoid charges

## Resource Management

**Important**: On LRZ systems, allocated resources are **not** automatically released. You must manually deallocate them when finished to avoid unnecessary charges.

### During Interactive Sessions

```bash
# When you're done with your work session:
exit  # Exit the interactive session (srun)
exit  # Exit the allocation (salloc)

# Or use scancel to cancel your allocation
scancel $SLURM_JOB_ID
```

### Check Your Active Allocations

```bash
# Check your running jobs and allocations
squeue -u $USER

# Check detailed information about your allocations
scontrol show job $SLURM_JOB_ID
```

### Best Practices for Resource Management

```bash
# 1. Set time limits when allocating resources
salloc -p lrz-v100x2 --gres=gpu:1 --time=02:00:00  # 2-hour limit

# 2. Always clean up when done
# Exit containers first
exit  # from container
exit  # from interactive session
exit  # from allocation

# 3. For long sessions, monitor your time
squeue -u $USER  # Check remaining time
```

### Save Your Work Before Exiting

```bash
# Save custom containers for reuse
enroot export --output my_custom_llm_container.sqsh llm-workspace

# Save your data and scripts to persistent storage
cp -r /workspace/results /your/persistent/path/
```

## Troubleshooting

### Common Issues

1. **GPU not detected**: Ensure `--gres=gpu:1` is specified in allocation
2. **Ollama connection failed**: Check if service is running: `pgrep ollama`
3. **Out of memory**: Try smaller models or reduce batch size
4. **Container issues**: Verify NVIDIA NGC credentials are set up correctly

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

## Next Steps

1. Adapt the example scripts to your specific text processing needs
2. Implement batch processing for large document collections
3. Set up automated pipelines using SLURM job arrays
4. Consider fine-tuning models for domain-specific art historical terminology

For more advanced configurations and custom container creation, refer to the complete LRZ documentation in `LRZDocs.txt`.
