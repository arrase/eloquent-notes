"""Unit tests for OllamaModelLoader background thread worker."""

from unittest.mock import MagicMock, patch

import requests

from eloquent_notes.config_gui.loader import OllamaModelLoader


def test_ollama_loader_success():
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))

    mock_tags_response = MagicMock()
    mock_tags_response.json.return_value = {
        "models": [{"name": "audio-model"}, {"name": "text-model"}, {"name": "embed-model"}]
    }

    mock_show_audio = MagicMock()
    mock_show_audio.json.return_value = {"capabilities": ["audio", "completion"]}

    mock_show_text = MagicMock()
    mock_show_text.json.return_value = {"capabilities": ["completion"]}

    mock_show_embed = MagicMock()
    mock_show_embed.json.return_value = {"capabilities": ["embedding"]}

    def mock_post(url, json, timeout):
        return {"audio-model": mock_show_audio, "embed-model": mock_show_embed}.get(json["name"], mock_show_text)

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [(["audio-model"], ["embed-model"])]


def test_ollama_loader_get_failure():
    loader = OllamaModelLoader("http://localhost:11434")

    error_signal_data = []
    loader.error_occurred.connect(error_signal_data.append)

    with patch(
        "requests.get", side_effect=requests.RequestException("Connection refused")
    ):
        loader.run()

    assert len(error_signal_data) == 1
    assert "Connection refused" in error_signal_data[0]


def test_ollama_loader_interruption_at_start(monkeypatch):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    error_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))
    loader.error_occurred.connect(error_signal_data.append)

    monkeypatch.setattr(loader, "isInterruptionRequested", lambda: True)

    with patch("requests.get") as mock_get:
        loader.run()
        mock_get.assert_not_called()

    assert models_signal_data == []
    assert error_signal_data == []


def test_ollama_loader_interruption_during_tags(monkeypatch):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))

    interrupted = False
    monkeypatch.setattr(loader, "isInterruptionRequested", lambda: interrupted)

    def mock_get(url, timeout):
        nonlocal interrupted
        interrupted = True
        return MagicMock()

    with patch("requests.get", side_effect=mock_get), patch("requests.post") as mock_post:
        loader.run()
        mock_post.assert_not_called()

    assert models_signal_data == []


def test_ollama_loader_interruption_during_show(monkeypatch):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))

    mock_tags_response = MagicMock()
    mock_tags_response.json.return_value = {
        "models": [{"name": "model1"}, {"name": "model2"}]
    }

    interrupted = False

    def mock_is_interrupted():
        return interrupted

    monkeypatch.setattr(loader, "isInterruptionRequested", mock_is_interrupted)

    def mock_post(url, json, timeout):
        nonlocal interrupted
        interrupted = True
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"capabilities": ["audio"]}
        return mock_resp

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == []


def test_ollama_loader_show_exception_resilience():
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))

    mock_tags_response = MagicMock()
    mock_tags_response.json.return_value = {
        "models": [{"name": "failing-model"}, {"name": "audio-model"}]
    }

    mock_show_audio = MagicMock()
    mock_show_audio.json.return_value = {"capabilities": ["audio"]}

    def mock_post(url, json, timeout):
        if json["name"] == "failing-model":
            raise requests.RequestException("Timeout on show")
        return mock_show_audio

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [(["audio-model"], [])]


def test_ollama_loader_invalid_json_body_resilience():
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(lambda audio, embedding: models_signal_data.append((audio, embedding)))

    mock_tags_response = MagicMock()
    mock_tags_response.json.return_value = {
        "models": [
            {"name": "bad-json-model"},
            {"name": "non-dict-model"},
            {"name": "non-list-caps-model"},
            {"name": "audio-model"},
        ]
    }

    mock_show_bad_json = MagicMock()
    mock_show_bad_json.json.side_effect = ValueError("Invalid JSON")

    mock_show_non_dict = MagicMock()
    mock_show_non_dict.json.return_value = ["not", "a", "dict"]

    mock_show_non_list_caps = MagicMock()
    mock_show_non_list_caps.json.return_value = {"capabilities": "not-a-list"}

    mock_show_audio = MagicMock()
    mock_show_audio.json.return_value = {"capabilities": ["audio"]}

    def mock_post(url, json, timeout):
        name = json["name"]
        if name == "bad-json-model":
            return mock_show_bad_json
        if name == "non-dict-model":
            return mock_show_non_dict
        if name == "non-list-caps-model":
            return mock_show_non_list_caps
        return mock_show_audio

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [(["audio-model"], [])]


def test_ollama_loader_invalid_tags_payload_emits_error():
    loader = OllamaModelLoader("http://localhost:11434/")
    assert loader.url == "http://localhost:11434"

    errors = []
    loader.error_occurred.connect(errors.append)

    for bad_payload in (["not", "dict"], {"models": "not-list"}, {"models": ["not-dict"]}, {}):
        mock_resp = MagicMock()
        mock_resp.json.return_value = bad_payload
        with patch("requests.get", return_value=mock_resp):
            loader.run()

    assert len(errors) == 4
