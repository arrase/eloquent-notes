"""Ollama API client for the three-phase dictation pipeline.

Phase 1 (transcription): multimodal audio -> text.
Phase 2 (rewriting): transcription -> clean note prose and title.
Phase 3 (classification): transcription -> type, wikilinks and tags.

Every phase requests structured output through Ollama's ``format`` JSON
schema. If a response still cannot be parsed or lacks required keys
(e.g. an Ollama version that ignores ``format``), the offending answer is
appended to the conversation together with a corrective instruction and
the request is retried up to max_retries times.
"""

import base64
import json
import logging

import requests

logger = logging.getLogger("eloquent_notes.llm")


def preload_model(ollama_url, model, context_length, keep_alive="5m", timeout=180):
    """Send an empty chat request so Ollama loads the model into VRAM.

    Reduces cold-start latency when the user stops recording and triggers
    the real pipeline.
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
    """Run an Ollama chat request expecting a structured JSON response.

    The input message list is never mutated; retries extend an internal
    copy. Raises the parse error when all attempts are exhausted.
    """
    options = {"temperature": 0.0, "num_ctx": context_length, "num_predict": 2048}
    conversation = list(messages)

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.warning(
                "Retrying %s with Ollama (attempt %d/%d)...",
                task_name, attempt, max_retries,
            )

        payload = {
            "model": model,
            "messages": conversation,
            "format": format_schema,
            "options": options,
            "keep_alive": keep_alive,
            "stream": False,
        }
        response = requests.post(
            f"{ollama_url}/api/chat", json=payload, timeout=timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            logger.error(
                "Ollama API HTTP error for %s (status %d): %s",
                task_name, response.status_code, response.text,
            )
            raise

        content = None
        try:
            content = response.json()["message"]["content"]
            result = json.loads(content)
            if not isinstance(result, dict) or not all(
                key in result for key in required_keys
            ):
                raise ValueError(f"missing required keys: {required_keys}")
            return result
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
            logger.error(
                "Invalid JSON output for %s (attempt %d): %r (%s)",
                task_name, attempt, content, err,
            )
            if attempt >= max_retries:
                raise
            conversation.append({
                "role": "assistant",
                "content": content if content is not None else response.text,
            })
            conversation.append({
                "role": "user",
                "content": (
                    f"{retry_prompt}\n\n"
                    f"Expected fields: {', '.join(required_keys)}."
                ),
            })


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
                    "Clean transcription of the spoken words in their original"
                    " spoken language (never translate), or empty string if audio is empty."
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
                    "Concise title (max 8 words) in the requested output language."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "Clean, direct note prose in the requested output language."
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
                    "Key concepts, tools, or proper nouns in the requested"
                    " output language that deserve linked notes."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2 to 5 relevant tags, lowercase, in the requested output language."
                ),
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
