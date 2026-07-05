"""LLM interaction module for Ollama API.

Handles audio transcription requests to the Ollama API with structured
JSON output, including retry logic for malformed responses.
"""

import base64
import json
import logging

import requests

logger = logging.getLogger("eloquent_notes.llm")


def preload_model(ollama_url, model, context_length, keep_alive="5m", timeout=180):
    """Send an empty request to Ollama to preload model weights into VRAM.

    This reduces cold start time when the user stops recording and
    triggers generation.
    """
    response = requests.post(
        f"{ollama_url}/api/chat",
        json={
            "model": model,
            "messages": [],
            "keep_alive": keep_alive,
            "options": {"temperature": 0.0, "num_ctx": context_length},
        },
        timeout=timeout,
    )
    response.raise_for_status()


def _execute_ollama_json_request(
    ollama_url, model, messages, format_schema, required_keys,
    retry_prompt, context_length, keep_alive, max_retries, timeout,
    task_name,
):
    """Execute an Ollama chat request expecting structured JSON output.

    Retries up to max_retries times if the response is not valid JSON
    or is missing required keys.
    """
    options = {"temperature": 0.0, "num_ctx": context_length}

    for attempt in range(max_retries + 1):
        payload = {
            "model": model,
            "messages": messages,
            "format": format_schema,
            "options": options,
            "keep_alive": keep_alive,
            "stream": False,
        }

        if attempt > 0:
            logger.warning(
                "Retrying %s with Ollama (attempt %d/%d)...",
                task_name, attempt, max_retries,
            )

        response = requests.post(
            f"{ollama_url}/api/chat", json=payload, timeout=timeout,
        )
        response.raise_for_status()

        content = response.json()["message"]["content"]

        try:
            result = json.loads(content)
            if not isinstance(result, dict) or not all(
                k in result for k in required_keys
            ):
                raise ValueError(
                    f"JSON response missing required keys: {required_keys}"
                )
            return result
        except (json.JSONDecodeError, TypeError, ValueError) as json_err:
            logger.error(
                "Invalid JSON output on attempt %d for %s: %s. Error: %s",
                attempt, task_name, content, json_err,
            )
            if attempt >= max_retries:
                raise json_err
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": retry_prompt})


def send_audio_to_ollama(
    ollama_url, model, system_prompt, user_prompt, retry_prompt,
    context_length, audio_bytes, keep_alive="5m", max_retries=3,
    timeout=300,
):
    """Transcribe and process audio through Ollama, returning structured JSON.

    Returns a dict with keys: 'empty' (bool), 'text' (str), 'tags' (list).
    """
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt, "images": [audio_base64]},
    ]
    format_schema = {
        "type": "object",
        "properties": {
            "empty": {
                "type": "boolean",
                "description": (
                    "True if the audio contains only silence, background"
                    " noise, or no spoken words; False otherwise."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "Cleaned, enriched Obsidian Markdown text if audio"
                    " is not empty; empty string otherwise."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "An array of 2 to 5 relevant tags if audio is not"
                    " empty; empty array otherwise."
                ),
            },
        },
        "required": ["empty", "text", "tags"],
    }

    return _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages,
        format_schema=format_schema, required_keys=["empty", "text", "tags"],
        retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout,
        task_name="audio processing",
    )
