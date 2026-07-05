"""LLM interaction module for Ollama API.

Implements a three-phase pipeline for audio-to-note conversion:
  Phase 1 (transcription): Multimodal audio → clean text.
  Phase 2 (rewriting): Text → rewritten note prose and title.
  Phase 3 (classification): Text → metadata (note type, wikilinks, tags).

Includes retry logic for malformed JSON responses.
"""

import base64
import json
import logging
import re

import requests

logger = logging.getLogger("eloquent_notes.llm")

_CODE_FENCE_RE = re.compile(r"^```\w*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def _strip_code_fences(text):
    """Remove markdown code fences (```json ... ```) if present."""
    match = _CODE_FENCE_RE.match(text.strip())
    return match.group(1) if match else text


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
        content = _strip_code_fences(content)

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
            full_retry = (
                f"{retry_prompt}\n\n"
                f"Expected fields: {', '.join(required_keys)}."
            )
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": full_retry})


def transcribe_audio(
    ollama_url, model, system_prompt, user_prompt, retry_prompt,
    context_length, audio_bytes, keep_alive="5m", max_retries=3,
    timeout=300,
):
    """Transcribe audio through Ollama (Phase 1).

    Returns a dict with keys: 'empty' (bool) and 'transcription' (str).
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
            "transcription": {
                "type": "string",
                "description": (
                    "Clean transcription of the spoken words, or empty"
                    " string if audio is empty."
                ),
            },
        },
        "required": ["empty", "transcription"],
    }

    return _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages,
        format_schema=format_schema,
        required_keys=["empty", "transcription"],
        retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout,
        task_name="audio transcription",
    )


def rewrite_transcription(
    ollama_url, model, system_prompt, user_prompt, retry_prompt,
    context_length, keep_alive="5m", max_retries=3, timeout=300,
):
    """Rewrite a transcription into a structured clean note (Phase 2).

    Returns a dict with keys: 'title' and 'content'.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    format_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "Concise title (max 8 words) capturing the main topic."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Clean, direct note prose. Basic formatting allowed."
                ),
            },
        },
        "required": ["title", "content"],
    }

    return _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages,
        format_schema=format_schema,
        required_keys=["title", "content"],
        retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout,
        task_name="note rewriting",
    )


def classify_transcription(
    ollama_url, model, system_prompt, user_prompt, retry_prompt,
    context_length, keep_alive="0", max_retries=3, timeout=300,
):
    """Classify and extract metadata from the transcription (Phase 3).

    Returns a dict with keys: 'type', 'wikilinks', and 'tags'.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    format_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "task", "idea", "note", "reminder",
                    "question", "decision",
                ],
                "description": "Classification of the note content.",
            },
            "wikilinks": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Key concepts, tools, or proper nouns that deserve"
                    " linked notes."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2 to 5 relevant tags, lowercase, in English.",
            },
        },
        "required": ["type", "wikilinks", "tags"],
    }

    return _execute_ollama_json_request(
        ollama_url=ollama_url, model=model, messages=messages,
        format_schema=format_schema,
        required_keys=["type", "wikilinks", "tags"],
        retry_prompt=retry_prompt, context_length=context_length,
        keep_alive=keep_alive, max_retries=max_retries, timeout=timeout,
        task_name="note classification",
    )
