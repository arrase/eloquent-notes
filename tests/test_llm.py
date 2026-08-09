"""Unit tests for eloquent_notes.llm module."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from eloquent_notes import llm


def test_strip_code_fences_plain_json():
    text = '{"key": "value"}'
    assert llm._strip_code_fences(text) == '{"key": "value"}'


def test_strip_code_fences_standard_fence():
    text = "```json\n{\"key\": \"value\"}\n```"
    assert llm._strip_code_fences(text) == '{"key": "value"}'


def test_strip_code_fences_no_lang_fence():
    text = "```\n{\"key\": \"value\"}\n```"
    assert llm._strip_code_fences(text) == '{"key": "value"}'


def test_strip_code_fences_surrounding_text():
    text = (
        "Here is the requested JSON output:\n"
        "```json\n"
        "{\"empty\": false, \"transcription\": \"Hello world\"}\n"
        "```\n"
        "Hope this helps!"
    )
    assert (
        llm._strip_code_fences(text)
        == '{"empty": false, "transcription": "Hello world"}'
    )


def test_strip_code_fences_inline_fence():
    text = '```json{"empty": true}```'
    assert llm._strip_code_fences(text) == '{"empty": true}'


@patch("eloquent_notes.llm.requests.post")
def test_preload_model(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    llm.preload_model("http://localhost:11434", "gemma", 4096)

    mock_post.assert_called_once_with(
        "http://localhost:11434/api/chat",
        json={
            "model": "gemma",
            "messages": [],
            "keep_alive": "5m",
            "options": {"temperature": 0.0, "num_ctx": 4096},
        },
        timeout=180,
    )


@patch("eloquent_notes.llm.requests.post")
def test_execute_ollama_json_request_success_first_try(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "message": {"content": '{"result": "ok"}'}
    }
    mock_post.return_value = mock_response

    messages = [{"role": "user", "content": "hi"}]
    res = llm._execute_ollama_json_request(
        ollama_url="http://localhost:11434",
        model="gemma",
        messages=messages,
        format_schema={},
        required_keys=["result"],
        retry_prompt="retry",
        context_length=2048,
        keep_alive="5m",
        max_retries=2,
        timeout=30,
        task_name="test task",
    )

    assert res == {"result": "ok"}
    assert len(messages) == 1  # Verify original list unchanged


@patch("eloquent_notes.llm.requests.post")
def test_execute_ollama_json_request_retry_and_immutability(mock_post):
    # First response invalid JSON, second valid JSON
    resp1 = MagicMock()
    resp1.raise_for_status.return_value = None
    resp1.json.return_value = {"message": {"content": "Not JSON at all"}}

    resp2 = MagicMock()
    resp2.raise_for_status.return_value = None
    resp2.json.return_value = {"message": {"content": '{"result": "success"}'}}

    mock_post.side_effect = [resp1, resp2]

    original_messages = [{"role": "user", "content": "hello"}]
    messages_copy = list(original_messages)

    res = llm._execute_ollama_json_request(
        ollama_url="http://localhost:11434",
        model="gemma",
        messages=messages_copy,
        format_schema={},
        required_keys=["result"],
        retry_prompt="Please fix JSON",
        context_length=2048,
        keep_alive="5m",
        max_retries=2,
        timeout=30,
        task_name="retry test",
    )

    assert res == {"result": "success"}
    # Check that input list passed to function was NOT mutated
    assert messages_copy == original_messages
    assert mock_post.call_count == 2


@patch("eloquent_notes.llm.requests.post")
def test_execute_ollama_json_request_missing_required_key(mock_post):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"message": {"content": '{"wrong_key": "val"}'}}
    mock_post.return_value = mock_resp

    messages = [{"role": "user", "content": "test"}]
    with pytest.raises(ValueError, match="missing required keys"):
        llm._execute_ollama_json_request(
            ollama_url="http://localhost:11434",
            model="gemma",
            messages=messages,
            format_schema={},
            required_keys=["expected_key"],
            retry_prompt="retry",
            context_length=2048,
            keep_alive="5m",
            max_retries=1,
            timeout=30,
            task_name="missing key test",
        )


@patch("eloquent_notes.llm.requests.post")
def test_execute_ollama_json_request_malformed_response_structure(mock_post):
    mock_resp1 = MagicMock()
    mock_resp1.raise_for_status.return_value = None
    mock_resp1.json.return_value = {"error": "unexpected format"}
    mock_resp1.text = '{"error": "unexpected format"}'

    mock_resp2 = MagicMock()
    mock_resp2.raise_for_status.return_value = None
    mock_resp2.json.return_value = {"message": {"content": '{"result": "ok"}'}}

    mock_post.side_effect = [mock_resp1, mock_resp2]

    res = llm._execute_ollama_json_request(
        ollama_url="http://localhost:11434",
        model="gemma",
        messages=[{"role": "user", "content": "hi"}],
        format_schema={},
        required_keys=["result"],
        retry_prompt="retry",
        context_length=2048,
        keep_alive="5m",
        max_retries=1,
        timeout=30,
        task_name="malformed response test",
    )

    assert res == {"result": "ok"}
    assert mock_post.call_count == 2


@patch("eloquent_notes.llm._execute_ollama_json_request")
def test_transcribe_audio(mock_exec):
    mock_exec.return_value = {"empty": False, "transcription": "Test speech"}
    audio_bytes = b"fake wav data"

    res = llm.transcribe_audio(
        ollama_url="http://localhost:11434",
        model="gemma",
        system_prompt="sys",
        user_prompt="usr",
        retry_prompt="retry",
        context_length=2048,
        audio_bytes=audio_bytes,
    )

    assert res == {"empty": False, "transcription": "Test speech"}
    mock_exec.assert_called_once()


@patch("eloquent_notes.llm._execute_ollama_json_request")
def test_rewrite_transcription(mock_exec):
    mock_exec.return_value = {"title": "Title", "content": "Content"}

    res = llm.rewrite_transcription(
        ollama_url="http://localhost:11434",
        model="gemma",
        system_prompt="sys",
        user_prompt="usr",
        retry_prompt="retry",
        context_length=2048,
    )

    assert res == {"title": "Title", "content": "Content"}
    mock_exec.assert_called_once()


@patch("eloquent_notes.llm._execute_ollama_json_request")
def test_classify_transcription(mock_exec):
    mock_exec.return_value = {
        "type": "idea",
        "wikilinks": ["Link1"],
        "tags": ["tag1"],
    }

    res = llm.classify_transcription(
        ollama_url="http://localhost:11434",
        model="gemma",
        system_prompt="sys",
        user_prompt="usr",
        retry_prompt="retry",
        context_length=2048,
    )

    assert res == {
        "type": "idea",
        "wikilinks": ["Link1"],
        "tags": ["tag1"],
    }
    mock_exec.assert_called_once()
