import base64
import json
import logging
import sys
import requests

logger = logging.getLogger("eloquent_notes.llm")

def get_model_max_context(ollama_url, model):
    try:
        response = requests.post(f"{ollama_url}/api/show", json={"name": model}, timeout=5)
        response.raise_for_status()
        for k, v in response.json().get("model_info", {}).items():
            if k.endswith(".context_length"):
                return int(v)
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None

def preload_model(ollama_url, model, context_length=None, keep_alive="5m", timeout=180):
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
        timeout=timeout
    )
    response.raise_for_status()

def _execute_ollama_json_request(ollama_url, model, messages, format_schema, required_keys, retry_prompt, context_length, keep_alive, max_retries, timeout, task_name):
    num_ctx = context_length or get_model_max_context(ollama_url, model)
    options = {"temperature": 0.0}
    if num_ctx:
        options["num_ctx"] = num_ctx

    for attempt in range(max_retries + 1):
        payload = {
            "model": model,
            "messages": messages,
            "format": format_schema,
            "options": options,
            "keep_alive": keep_alive,
            "stream": False
        }

        try:
            if attempt > 0:
                logger.warning("Retrying %s with Ollama (attempt %d/%d)...", task_name, attempt, max_retries)

            response = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=timeout)
            response.raise_for_status()

            content = response.json()["message"]["content"]

            try:
                json_str = content.strip()
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = json_str[start_idx:end_idx + 1]

                result = json.loads(json_str)
                if not isinstance(result, dict) or not all(k in result for k in required_keys):
                    raise ValueError(f"JSON response is missing required keys: {required_keys}")

                # Check for array type for tags if required, etc, but basic dictionary key check handles our cases
                return result
            except (json.JSONDecodeError, TypeError, ValueError) as json_err:
                logger.error("Invalid JSON output on attempt %d for %s: %s. Error: %s", attempt, task_name, content, json_err)
                if attempt >= max_retries:
                    raise json_err
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": retry_prompt})

        except requests.RequestException as req_err:
            logger.error("Ollama request error during %s on attempt %d: %s", task_name, attempt, req_err)
            if attempt >= max_retries:
                raise req_err

def send_audio_to_ollama(ollama_url, model, system_prompt, user_prompt, retry_prompt, context_length, audio_bytes, keep_alive="5m", max_retries=3, timeout=300):
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt, "images": [audio_base64]}
    ]
    format_schema = {
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
    }

    return _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages, format_schema=format_schema,
        required_keys=["empty", "text"], retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout, task_name="audio processing"
    )

def enrich_text_with_ollama(ollama_url, model, system_prompt, user_prompt, text, retry_prompt, context_length, keep_alive="5m", max_retries=3, timeout=300):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt.format(text=text)}
    ]
    format_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The enriched Markdown text."
            }
        },
        "required": ["text"]
    }

    result = _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages, format_schema=format_schema,
        required_keys=["text"], retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout, task_name="text enrichment"
    )
    return result["text"]

def extract_tags_with_ollama(ollama_url, model, system_prompt, user_prompt, text, retry_prompt, context_length, keep_alive="5m", max_retries=3, timeout=300):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt.format(text=text)}
    ]
    format_schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "An array of relevant tags."
            }
        },
        "required": ["tags"]
    }

    result = _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages, format_schema=format_schema,
        required_keys=["tags"], retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout, task_name="tag extraction"
    )

    tags = result["tags"]
    if not isinstance(tags, list):
        tags = []
    return tags
