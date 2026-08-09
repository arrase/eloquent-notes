"""Unit tests for OllamaModelLoader background thread worker."""

from unittest.mock import MagicMock, patch
import requests

from eloquent_notes.config_gui.loader import OllamaModelLoader


def test_ollama_loader_success(qapp):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(models_signal_data.append)

    mock_tags_response = MagicMock()
    mock_tags_response.status_code = 200
    mock_tags_response.json.return_value = {
        "models": [{"name": "audio-model"}, {"name": "text-model"}]
    }

    mock_show_audio = MagicMock()
    mock_show_audio.status_code = 200
    mock_show_audio.json.return_value = {"capabilities": ["audio", "completion"]}

    mock_show_text = MagicMock()
    mock_show_text.status_code = 200
    mock_show_text.json.return_value = {"capabilities": ["completion"]}

    def mock_post(url, json, timeout):
        if json.get("name") == "audio-model":
            return mock_show_audio
        return mock_show_text

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [["audio-model"]]


def test_ollama_loader_get_failure(qapp):
    loader = OllamaModelLoader("http://localhost:11434")

    error_signal_data = []
    loader.error_occurred.connect(error_signal_data.append)

    with patch(
        "requests.get", side_effect=requests.RequestException("Connection refused")
    ):
        loader.run()

    assert len(error_signal_data) == 1
    assert "Connection refused" in error_signal_data[0]


def test_ollama_loader_interruption_at_start(qapp, monkeypatch):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    error_signal_data = []
    loader.models_fetched.connect(models_signal_data.append)
    loader.error_occurred.connect(error_signal_data.append)

    monkeypatch.setattr(loader, "isInterruptionRequested", lambda: True)

    with patch("requests.get") as mock_get:
        loader.run()
        mock_get.assert_not_called()

    assert models_signal_data == []
    assert error_signal_data == []


def test_ollama_loader_interruption_during_show(qapp, monkeypatch):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(models_signal_data.append)

    mock_tags_response = MagicMock()
    mock_tags_response.status_code = 200
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
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"capabilities": ["audio"]}
        return mock_resp

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == []


def test_ollama_loader_show_exception_resilience(qapp):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(models_signal_data.append)

    mock_tags_response = MagicMock()
    mock_tags_response.status_code = 200
    mock_tags_response.json.return_value = {
        "models": [{"name": "failing-model"}, {"name": "audio-model"}]
    }

    mock_show_audio = MagicMock()
    mock_show_audio.status_code = 200
    mock_show_audio.json.return_value = {"capabilities": ["audio"]}

    def mock_post(url, json, timeout):
        if json.get("name") == "failing-model":
            raise requests.RequestException("Timeout on show")
        return mock_show_audio

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [["audio-model"]]


def test_ollama_loader_invalid_json_body_resilience(qapp):
    loader = OllamaModelLoader("http://localhost:11434")

    models_signal_data = []
    loader.models_fetched.connect(models_signal_data.append)

    mock_tags_response = MagicMock()
    mock_tags_response.status_code = 200
    mock_tags_response.json.return_value = {
        "models": [{"name": "bad-json-model"}, {"name": "non-dict-model"}, {"name": "audio-model"}]
    }

    mock_show_bad_json = MagicMock()
    mock_show_bad_json.status_code = 200
    mock_show_bad_json.json.side_effect = ValueError("Invalid JSON")

    mock_show_non_dict = MagicMock()
    mock_show_non_dict.status_code = 200
    mock_show_non_dict.json.return_value = ["not", "a", "dict"]

    mock_show_audio = MagicMock()
    mock_show_audio.status_code = 200
    mock_show_audio.json.return_value = {"capabilities": ["audio"]}

    def mock_post(url, json, timeout):
        name = json.get("name")
        if name == "bad-json-model":
            return mock_show_bad_json
        if name == "non-dict-model":
            return mock_show_non_dict
        return mock_show_audio

    with patch("requests.get", return_value=mock_tags_response), patch(
        "requests.post", side_effect=mock_post
    ):
        loader.run()

    assert models_signal_data == [["audio-model"]]

