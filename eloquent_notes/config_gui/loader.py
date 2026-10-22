"""Background workers for Ollama model loading."""

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class OllamaModelLoader(QThread):
    """Background thread to query Ollama model names asynchronously.

    Emits the audio-capable models (for dictation) and the embedding models
    (for semantic search) found on the server.
    """

    models_fetched = pyqtSignal(list, list)
    error_occurred = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
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
            if not isinstance(caps, list):
                raise TypeError("Invalid capabilities format from Ollama")
            return caps
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return []

    def run(self) -> None:
        """Fetch model names from Ollama API."""
        if self.isInterruptionRequested():
            return
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()
            if self.isInterruptionRequested():
                return

            all_models = [m["name"] for m in r.json()["models"]]

            audio_models = []
            embedding_models = []
            for name in all_models:
                caps = self._capabilities(self.url, name)
                if self.isInterruptionRequested():
                    return
                if "audio" in caps:
                    audio_models.append(name)
                if "embedding" in caps:
                    embedding_models.append(name)

            if not self.isInterruptionRequested():
                self.models_fetched.emit(audio_models, embedding_models)
        except (requests.RequestException, KeyError, TypeError, ValueError) as e:
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))

