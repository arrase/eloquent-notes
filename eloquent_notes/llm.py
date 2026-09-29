"""Ollama API client for the three-phase dictation pipeline.

Phase 1 (transcription): multimodal audio -> text.
Phase 2 (rewriting): transcription -> clean note prose and title.
Phase 3 (classification): transcription -> type, wikilinks and tags.

Every phase requests structured output through Ollama's ``format`` JSON
schema. If a response still cannot be parsed or lacks required keys
(e.g. an Ollama version that ignores ``format``), the offending answer is
appended to the conversation together with a corrective instruction and
the request is retried up to max_retries times.

Reasoning mode is explicitly disabled on every request. Gemma 4 defaults
to ``thinking: true``, and the reasoning tokens it emits draw from the same
``num_predict`` budget as the answer. Once that budget is exhausted Ollama
returns an empty ``content`` with ``done_reason=length``, which the model
reports as ``empty: true`` — a correctly transcribed dictation is silently
discarded. Disabling reasoning also removes the thinking text Ollama appends
to the assistant turn on retries.

The ``empty`` field of ``TRANSCRIPTION_SCHEMA`` is advisory. Asked to label
silence, the model frequently answers false and invents text instead, so
:mod:`eloquent_notes.audio` decides silence locally before any audio is sent.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import requests

logger = logging.getLogger("eloquent_notes.llm")

DEFAULT_NUM_PREDICT = 2048

# Gemma 4 enables reasoning by default; see the module docstring.
THINK = False

# Field order matters: Ollama emits properties in schema order under
# constrained decoding, so "transcription" must come first for the model to
# commit to the transcript before deciding whether the audio was empty.
TRANSCRIPTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "transcription": {
            "type": "string",
            "description": (
                "Clean transcription of the spoken words in their original"
                " spoken language (never translate), or empty string if audio is empty."
            ),
        },
        "empty": {
            "type": "boolean",
            "description": (
                "True if the audio contains only silence, background"
                " noise, or no spoken words; False otherwise."
            ),
        },
    },
    "required": ["transcription", "empty"],
}

REWRITING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Concise title (max 8 words) in the requested output language.",
        },
        "content": {
            "type": "string",
            "description": "Clean, direct note prose in the requested output language.",
        },
    },
    "required": ["title", "content"],
}

CLASSIFICATION_SCHEMA: dict[str, Any] = {
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
            "description": "2 to 5 relevant tags, lowercase, in the requested output language.",
        },
    },
    "required": ["type", "wikilinks", "tags"],
}


def _chat_url(ollama_url: str) -> str:
    return f"{ollama_url.rstrip('/')}/api/chat"


def preload_model(
    ollama_url: str,
    model: str,
    context_length: int,
    keep_alive: str = "5m",
    timeout: int = 180,
) -> None:
    """Send an empty chat request so Ollama loads the model into VRAM.

    Reduces cold-start latency when the user stops recording and triggers
    the real pipeline.
    """
    response = requests.post(
        _chat_url(ollama_url),
        json={
            "model": model,
            "messages": [],
            "keep_alive": keep_alive,
            "options": {"temperature": 0.0, "num_ctx": context_length},
        },
        timeout=timeout,
    )
    response.raise_for_status()


def _parse_json_response(content: str | None, keys: list[str]) -> dict[str, Any]:
    """Validate an Ollama reply as a JSON object carrying every required key.

    Raises TypeError, ValueError or KeyError on anything malformed so the
    caller can treat every failure mode alike and retry.
    """
    result = json.loads(content)  # type: ignore[arg-type]
    if not isinstance(result, dict):
        raise TypeError(f"expected a JSON object, got {type(result).__name__}")
    missing = [k for k in keys if k not in result]
    if missing:
        raise ValueError(f"missing required keys: {missing}")
    return result


def _execute_ollama_json_request(
    ollama_url: str,
    model: str,
    messages: list[dict[str, Any]],
    format_schema: dict[str, Any],
    retry_prompt: str,
    context_length: int,
    keep_alive: str,
    max_retries: int,
    timeout: int,
    task_name: str,
    required_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Run an Ollama chat request expecting a structured JSON response.

    The input message list is never mutated; retries extend an internal
    copy. Raises the parse error when all attempts are exhausted.
    """
    keys = required_keys if required_keys is not None else format_schema.get("required", [])
    options = {
        "temperature": 0.0,
        "num_ctx": context_length,
        "num_predict": DEFAULT_NUM_PREDICT,
    }
    conversation = list(messages)
    url = _chat_url(ollama_url)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.warning(
                "Retrying %s with Ollama (attempt %d/%d)...",
                task_name, attempt, max_retries,
            )

        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
            "format": format_schema,
            "options": options,
            "keep_alive": keep_alive,
            "stream": False,
            "think": THINK,
        }
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()

        content = None
        try:
            content = response.json()["message"]["content"]
            return _parse_json_response(content, keys)
        except (KeyError, TypeError, ValueError) as err:
            last_error = err
            logger.exception(
                "Invalid JSON output for %s (attempt %d): %r",
                task_name, attempt, content,
            )
            if attempt >= max_retries:
                raise
            conversation.append({
                "role": "assistant",
                "content": content if content is not None else response.text,
            })
            conversation.append({
                "role": "user",
                "content": f"{retry_prompt}\n\nExpected fields: {', '.join(keys)}.",
            })

    # The loop only falls through when max_retries is negative, in which case
    # no request was ever made.
    raise last_error if last_error is not None else ValueError(
        f"No attempt was made for {task_name}: max_retries={max_retries}"
    )


def transcribe_audio(
    ollama_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    retry_prompt: str,
    context_length: int,
    audio_bytes: bytes,
    keep_alive: str = "5m",
    max_retries: int = 3,
    timeout: int = 300,
) -> dict[str, Any]:
    """Transcribe audio through Ollama (Phase 1).

    Returns a dict with keys: 'empty' (bool) and 'transcription' (str).
    """
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt, "images": [audio_base64]},
    ]
    # Constrained decoding follows the schema's property order, so the audio
    # is placed before the instruction text.
    return _execute_ollama_json_request(
        ollama_url=ollama_url,
        model=model,
        messages=messages,
        format_schema=TRANSCRIPTION_SCHEMA,
        retry_prompt=retry_prompt,
        context_length=context_length,
        keep_alive=keep_alive,
        max_retries=max_retries,
        timeout=timeout,
        task_name="audio transcription",
        required_keys=["transcription", "empty"],
    )


def rewrite_transcription(
    ollama_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    retry_prompt: str,
    context_length: int,
    keep_alive: str = "5m",
    max_retries: int = 3,
    timeout: int = 300,
) -> dict[str, Any]:
    """Rewrite a transcription into a structured clean note (Phase 2).

    Returns a dict with keys: 'title' and 'content'.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _execute_ollama_json_request(
        ollama_url=ollama_url,
        model=model,
        messages=messages,
        format_schema=REWRITING_SCHEMA,
        retry_prompt=retry_prompt,
        context_length=context_length,
        keep_alive=keep_alive,
        max_retries=max_retries,
        timeout=timeout,
        task_name="note rewriting",
        required_keys=["title", "content"],
    )


def classify_transcription(
    ollama_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    retry_prompt: str,
    context_length: int,
    keep_alive: str = "0",
    max_retries: int = 3,
    timeout: int = 300,
) -> dict[str, Any]:
    """Classify and extract metadata from the transcription (Phase 3).

    Returns a dict with keys: 'type', 'wikilinks', and 'tags'.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return _execute_ollama_json_request(
        ollama_url=ollama_url,
        model=model,
        messages=messages,
        format_schema=CLASSIFICATION_SCHEMA,
        retry_prompt=retry_prompt,
        context_length=context_length,
        keep_alive=keep_alive,
        max_retries=max_retries,
        timeout=timeout,
        task_name="note classification",
        required_keys=["type", "wikilinks", "tags"],
    )
