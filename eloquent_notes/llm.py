import base64
import json
import sys
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

def send_audio_to_ollama(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, audio_bytes, keep_alive="5m", max_retries=3):
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    num_ctx = context_length or get_model_max_context(ollama_url, model)
    
    max_retries = max(0, int(max_retries))
    
    options = {"temperature": 0.0}
    if num_ctx:
        options["num_ctx"] = num_ctx
        
    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": user_prompt,
            "images": [audio_base64]
        }
    ]
    
    last_error = None
    for attempt in range(max_retries + 1):
        payload = {
            "model": model,
            "messages": messages,
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
        
        try:
            if attempt > 0:
                print(f"Retrying audio processing with Ollama (attempt {attempt}/{max_retries})...", file=sys.stderr)
                
            response = requests.post(f"{ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            
            content = response.json()["message"]["content"]
            
            try:
                result = json.loads(content)
                if isinstance(result, dict) and "empty" in result and "text" in result:
                    return result
                else:
                    raise ValueError("JSON response is missing required keys 'empty' or 'text'")
            except (json.JSONDecodeError, TypeError, ValueError) as json_err:
                print(f"Invalid JSON output on attempt {attempt}: {content}. Error: {json_err}", file=sys.stderr)
                if attempt < max_retries:
                    messages.append({
                        "role": "assistant",
                        "content": content
                    })
                    messages.append({
                        "role": "user",
                        "content": retry_prompt
                    })
                    last_error = json_err
                    continue
                else:
                    raise json_err
                    
        except requests.RequestException as req_err:
            print(f"Ollama request error on attempt {attempt}: {req_err}", file=sys.stderr)
            last_error = req_err
            if attempt >= max_retries:
                raise req_err
                
    if last_error:
        raise last_error
    else:
        raise ValueError("Unknown error during Ollama processing")
