import base64
import json
import requests

def get_model_max_context(ollama_url, model):
    try:
        response = requests.post(
            f"{ollama_url}/api/show",
            json={"name": model},
            timeout=5
        )
        response.raise_for_status()
        info = response.json().get("model_info", {})
        for k, v in info.items():
            if k.endswith(".context_length"):
                return int(v)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None

def preload_model(ollama_url, model, context_length=None, keep_alive="5m"):
    """
    Sends a request to Ollama to preload the model into memory.
    This reduces the cold start time when the user stops recording and triggers generation.
    """
    try:
        num_ctx = context_length or get_model_max_context(ollama_url, model)
        options = {"temperature": 0.0}
        if num_ctx:
            options["num_ctx"] = num_ctx

        response = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [],
                "keep_alive": keep_alive,
                "options": options
            },
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        raise Exception(f"Failed to preload model: {e}")

def _parse_json(content):
    cleaned = content.strip()
    
    # Strip markdown code block wrapping if present
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
        
    cleaned = cleaned.strip()
    
    # Extract JSON substring by finding matching curly braces
    try:
        start = cleaned.index('{')
        end = cleaned.rindex('}') + 1
        cleaned = cleaned[start:end]
    except ValueError:
        pass
        
    return json.loads(cleaned)

def send_audio_to_ollama(ollama_url, model, system_prompt, user_prompt, context_length, audio_bytes, keep_alive="5m"):
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    num_ctx = context_length or get_model_max_context(ollama_url, model)
    
    options = {"temperature": 0.0}
    if num_ctx:
        options["num_ctx"] = num_ctx
        
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt,
                "images": [audio_base64]
            }
        ],
        "format": {
            "type": "object",
            "properties": {
                "empty": {
                    "type": "boolean",
                    "description": "True if the audio contains only silence, background noise, or no spoken words; False otherwise."
                },
                "text": {
                    "type": "string",
                    "description": "Cleaned, polished, and structured Markdown text if audio is not empty; empty string otherwise."
                }
            },
            "required": ["empty", "text"]
        },
        "options": options,
        "keep_alive": keep_alive,
        "stream": False
    }
    
    response = requests.post(f"{ollama_url}/api/chat", json=payload)
    response.raise_for_status()
    
    response_json = response.json()
    content = response_json["message"]["content"]
    
    try:
        return _parse_json(content)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON from model response. Error: {e}. Raw content: {repr(content)}")
