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
    
    content = response.json()["message"]["content"]
    return json.loads(content)
