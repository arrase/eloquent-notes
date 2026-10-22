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

    def _capabilities(self, name: str) -> list:
        """Return the capabilities Ollama reports for the given model."""
        try:
            show_r = requests.post(
                f"{self.url}/api/show",
                json={"name": name},
                timeout=2.0,
            )
            if self.isInterruptionRequested():
                return []
            if show_r.status_code == 200:
                show_data = show_r.json()
                if isinstance(show_data, dict):
                    caps = show_data.get("capabilities", [])
                    if isinstance(caps, list):
                        return caps
        except (requests.RequestException, ValueError):
            pass
        return []

    def run(self) -> None:
        """Fetch model names from Ollama API."""
        if self.isInterruptionRequested():
            return
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=2.0)
            r.raise_for_status()
            if self.isInterruptionRequested():
                return

            data = r.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid response format from Ollama")
            models_list = data.get("models", [])
            if not isinstance(models_list, list) or not all(
                isinstance(m, dict) for m in models_list
            ):
                raise ValueError("Invalid response format from Ollama")
            all_models = [
                m["name"] for m in models_list if isinstance(m.get("name"), str)
            ]

            audio_models = []
            embedding_models = []
            for name in all_models:
                if self.isInterruptionRequested():
                    return
                caps = self._capabilities(name)
                if "audio" in caps:
                    audio_models.append(name)
                if "embedding" in caps:
                    embedding_models.append(name)

            if not self.isInterruptionRequested():
                self.models_fetched.emit(audio_models, embedding_models)
        except (requests.RequestException, ValueError) as e:
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))

