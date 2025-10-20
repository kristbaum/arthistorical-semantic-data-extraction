import requests


def test_ollama_connection():
    """Test if Ollama is running and can process text"""
    try:
        # Test connection to Ollama
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            print("✓ Ollama is running")
            models = response.json().get("models", [])
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
    Clean and format this scanned German art historical text about baroque ceiling paintings. Fix line breaks, obvious OCR errors and remove random, wrongly scanned headlines, text from maps or artwork, or image captions in the text. Export the text as Markdown and use bold text for parts before ":". Don't add any new text, stay close to the original, only format it for online publishing.
    
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
                    "top_p": 0.9,
                },
            },
        )

        if response.status_code == 200:
            result = response.json()
            return result["response"]
        else:
            return f"Error: {response.status_code}"

    except Exception as e:
        return f"Error: {e}"


# Test the setup
if __name__ == "__main__":
    print("Testing Mistral setup on LRZ...")

    if test_ollama_connection():
        # Input messy art historical text that needs formatting
        input_text = """
        
        """

        print("\nOriginal text:")
        print(input_text)
        print("\nCleaning and formatting text...")
        result = format_and_clean_text(input_text)
        print("\nFormatted output:")
        print(result)
    else:
        print("Please start Ollama first: ollama serve &")
