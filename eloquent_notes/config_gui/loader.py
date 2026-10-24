"""Background worker for Ollama model loading."""

import threading

import requests
from PyQt6.QtCore import QObject, pyqtSignal


class OllamaModelLoader(QObject):
    """Background worker to query Ollama model names asynchronously.

    Emits the audio-capable models (for dictation) and the embedding models
    (for semantic search) found on the server.
    """

    models_fetched = pyqtSignal(list, list)
    error_occurred = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url.rstrip("/")

    @staticmethod
    def _capabilities(base_url: str, name: str) -> list[str]:
        """Return the capabilities Ollama reports for the given model."""
        try:
            show_r = requests.post(
                f"{base_url}/api/show",
                json={"name": name},
                timeout=5,
            )
            show_r.raise_for_status()
            caps = show_r.json()["capabilities"]
            return caps if isinstance(caps, list) else []
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return []

    def start(self) -> None:
        """Start fetching model names on a background daemon thread."""
        threading.Thread(target=self.run, daemon=True).start()

    def run(self) -> None:
        """Fetch model names from Ollama API."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()

            all_models = [m["name"] for m in r.json()["models"]]

            audio_models = []
            embedding_models = []
            for name in all_models:
                caps = self._capabilities(self.url, name)
                if "audio" in caps:
                    audio_models.append(name)
                if "embedding" in caps:
                    embedding_models.append(name)

            self.models_fetched.emit(audio_models, embedding_models)
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            self.error_occurred.emit(str(e))


