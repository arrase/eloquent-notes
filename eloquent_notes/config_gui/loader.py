"""Background workers for Ollama model loading."""

from PyQt6.QtCore import QThread, pyqtSignal
import requests


class OllamaModelLoader(QThread):
    """Background thread to query Ollama model names asynchronously."""

    models_fetched = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.is_cancelled = False

    def run(self):
        """Fetch model names from Ollama API."""
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=2.0)
            r.raise_for_status()
            if self.is_cancelled:
                return
            data = r.json()
            all_models = [m["name"] for m in data.get("models", [])]
            audio_models = []
            for name in all_models:
                if self.is_cancelled:
                    return
                try:
                    show_r = requests.post(
                        f"{self.url}/api/show",
                        json={"name": name},
                        timeout=2.0
                    )
                    if show_r.status_code == 200:
                        show_data = show_r.json()
                        caps = show_data.get("capabilities", [])
                        if "audio" in caps:
                            audio_models.append(name)
                except Exception:
                    pass
            if self.is_cancelled:
                return
            self.models_fetched.emit(audio_models)
        except Exception as e:
            if not self.is_cancelled:
                self.error_occurred.emit(str(e))
