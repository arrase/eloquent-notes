"""Background workers for Ollama model loading."""

from PyQt6.QtCore import QThread, pyqtSignal
import requests


class OllamaModelLoader(QThread):
    """Background thread to query Ollama model names asynchronously."""

    models_fetched = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

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
            raw_models = data.get("models") if isinstance(data, dict) else []
            if not isinstance(raw_models, list):
                raw_models = []

            all_models = [
                m["name"]
                for m in raw_models
                if isinstance(m, dict) and "name" in m
            ]

            audio_models = []
            for name in all_models:
                if self.isInterruptionRequested():
                    return
                try:
                    show_r = requests.post(
                        f"{self.url}/api/show",
                        json={"name": name},
                        timeout=2.0,
                    )
                    if self.isInterruptionRequested():
                        return
                    if show_r.status_code == 200:
                        show_data = show_r.json()
                        if isinstance(show_data, dict):
                            caps = show_data.get("capabilities", [])
                            if isinstance(caps, list) and "audio" in caps:
                                audio_models.append(name)
                except (requests.RequestException, ValueError, AttributeError):
                    pass

            if self.isInterruptionRequested():
                return

            self.models_fetched.emit(audio_models)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))

