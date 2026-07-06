"""AI settings tab for configuration."""

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes.config_gui.loader import OllamaModelLoader
from eloquent_notes.config_gui.tabs.base import ConfigTab


class AITab(ConfigTab):
    """AI and Ollama configuration tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model_loader = None
        self._running_loaders = set()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_ai = QGroupBox("Ollama & AI Pipeline Settings")
        form_layout = QFormLayout(grp_ai)
        form_layout.setSpacing(10)

        self.txt_ollama_url = QLineEdit()
        self.txt_ollama_url.setToolTip("URL of your local or remote Ollama server.")
        form_layout.addRow(QLabel("Ollama URL:"), self.txt_ollama_url)

        model_widget = QWidget()
        model_layout = QVBoxLayout(model_widget)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(3)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)

        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        self.cmb_model.setToolTip(
            "Name of the Ollama LLM model to run for dictation tasks (e.g. gemma4:12b-it-qat)."
        )
        self.btn_refresh_models = QPushButton("Refresh")
        self.btn_refresh_models.clicked.connect(self._fetch_models)

        model_row.addWidget(self.cmb_model)
        model_row.addWidget(self.btn_refresh_models)

        self.lbl_model_status = QLabel("Ready")
        self.lbl_model_status.setStyleSheet("color: #7f849c; font-size: 11px;")

        model_layout.addLayout(model_row)
        model_layout.addWidget(self.lbl_model_status)
        form_layout.addRow(QLabel("AI Model (Audio):"), model_widget)

        context_widget = QWidget()
        context_layout = QHBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(10)

        self.spn_context_length = QSpinBox()
        self.spn_context_length.setRange(512, 262144)
        self.spn_context_length.setSingleStep(1024)
        self.spn_context_length.setValue(10000)
        self.spn_context_length.setToolTip(
            "Context length in tokens to pass to Ollama. "
            "Larger values allow more vault context but use more memory."
        )

        self.chk_context_default = QCheckBox("Use default context length")
        self.chk_context_default.setToolTip(
            "If checked, sets context_length to null (or leaves it unset), "
            "instructing Ollama to use the model's default maximum context length."
        )
        self.chk_context_default.toggled.connect(self._toggle_context_default)

        context_layout.addWidget(self.spn_context_length)
        context_layout.addWidget(self.chk_context_default)
        form_layout.addRow(QLabel("Context Length:"), context_widget)

        self.txt_keep_alive = QLineEdit()
        self.txt_keep_alive.setToolTip(
            "Time to keep model loaded after note generation (e.g., '0' to unload immediately, or '5m')."
        )
        form_layout.addRow(QLabel("Keep Alive Time:"), self.txt_keep_alive)

        self.txt_preload_keep_alive = QLineEdit()
        self.txt_preload_keep_alive.setToolTip(
            "Time to keep model weights loaded in VRAM during recording to minimize latency (e.g., '5m')."
        )
        form_layout.addRow(QLabel("Preload Keep Alive:"), self.txt_preload_keep_alive)

        self.spn_max_retries = QSpinBox()
        self.spn_max_retries.setRange(0, 10)
        self.spn_max_retries.setToolTip("Number of retry attempts if LLM output fails JSON parsing.")
        form_layout.addRow(QLabel("Max Retries:"), self.spn_max_retries)

        self.spn_preload_timeout = QSpinBox()
        self.spn_preload_timeout.setRange(10, 1000)
        self.spn_preload_timeout.setSuffix(" sec")
        form_layout.addRow(QLabel("Preload Timeout:"), self.spn_preload_timeout)

        self.spn_request_timeout = QSpinBox()
        self.spn_request_timeout.setRange(10, 1000)
        self.spn_request_timeout.setSuffix(" sec")
        form_layout.addRow(QLabel("Request Timeout:"), self.spn_request_timeout)

        layout.addWidget(grp_ai)
        layout.addStretch()

    def _toggle_context_default(self, checked):
        self.spn_context_length.setEnabled(not checked)

    def _fetch_models(self):
        url = self.txt_ollama_url.text().strip()
        if not url:
            self.lbl_model_status.setText("Ollama URL is empty.")
            return

        self.lbl_model_status.setText("Fetching audio models...")
        self.lbl_model_status.setStyleSheet("color: #7f849c; font-size: 11px;")
        self.btn_refresh_models.setEnabled(False)

        if self._model_loader is not None and self._model_loader.isRunning():
            self._model_loader.is_cancelled = True

        loader = OllamaModelLoader(url, QCoreApplication.instance())
        self._model_loader = loader
        self._running_loaders.add(loader)

        loader.finished.connect(self._on_loader_finished)
        loader.models_fetched.connect(self._on_models_fetched)
        loader.error_occurred.connect(self._on_models_fetch_failed)
        loader.finished.connect(loader.deleteLater)
        loader.start()

    def _on_loader_finished(self):
        loader = self.sender()
        if loader:
            self._running_loaders.discard(loader)
        if loader is self._model_loader:
            self._model_loader = None
            self.btn_refresh_models.setEnabled(True)

    def _on_models_fetched(self, models):
        if self.sender() is not self._model_loader:
            return

        current_text = self.cmb_model.currentText()
        self.cmb_model.clear()

        if not models:
            self.lbl_model_status.setText("No audio-capable models found.")
            self.lbl_model_status.setStyleSheet("color: #f38ba8; font-size: 11px;")
            if current_text:
                self.cmb_model.addItem(current_text)
                self.cmb_model.setCurrentText(current_text)
            return

        self.cmb_model.addItems(models)
        if current_text in models:
            self.cmb_model.setCurrentText(current_text)
        elif current_text:
            self.cmb_model.addItem(current_text)
            self.cmb_model.setCurrentText(current_text)

        self.lbl_model_status.setText("Audio models loaded successfully.")
        self.lbl_model_status.setStyleSheet("color: #a6e3a1; font-size: 11px;")

    def _on_models_fetch_failed(self, error_msg):
        if self.sender() is not self._model_loader:
            return
        self.lbl_model_status.setText(f"Connection failed: {error_msg}")
        self.lbl_model_status.setStyleSheet("color: #f38ba8; font-size: 11px;")

    def cleanup(self):
        """Asynchronously cancel active loaders without blocking the GUI thread."""
        for loader in list(self._running_loaders):
            loader.is_cancelled = True
            try:
                loader.finished.disconnect(self._on_loader_finished)
                loader.models_fetched.disconnect(self._on_models_fetched)
                loader.error_occurred.disconnect(self._on_models_fetch_failed)
            except TypeError:
                pass
        self._running_loaders.clear()
        self._model_loader = None

    def load_settings(self, config_data: dict) -> None:
        ai_cfg = config_data["ai"]
        self.txt_ollama_url.setText(ai_cfg["ollama_url"])

        curr_model = ai_cfg["model"]
        if self.cmb_model.findText(curr_model) == -1:
            self.cmb_model.addItem(curr_model)
        self.cmb_model.setCurrentText(curr_model)

        context_len = ai_cfg["context_length"]
        if context_len is None:
            self.chk_context_default.setChecked(True)
            self.spn_context_length.setEnabled(False)
            self.spn_context_length.setValue(10000)
        else:
            self.chk_context_default.setChecked(False)
            self.spn_context_length.setEnabled(True)
            self.spn_context_length.setValue(context_len)

        self.txt_keep_alive.setText(str(ai_cfg["keep_alive"]))
        self.txt_preload_keep_alive.setText(str(ai_cfg["preload_keep_alive"]))
        self.spn_max_retries.setValue(ai_cfg["max_retries"])
        self.spn_preload_timeout.setValue(ai_cfg["preload_timeout"])
        self.spn_request_timeout.setValue(ai_cfg["request_timeout"])

        # Trigger an initial fetch
        self._fetch_models()

    def save_settings(self, config_data: dict) -> bool:
        context_len = None if self.chk_context_default.isChecked() else self.spn_context_length.value()

        config_data["ai"].update({
            "ollama_url": self.txt_ollama_url.text().strip(),
            "model": self.cmb_model.currentText().strip(),
            "context_length": context_len,
            "keep_alive": self.txt_keep_alive.text().strip(),
            "preload_keep_alive": self.txt_preload_keep_alive.text().strip(),
            "max_retries": self.spn_max_retries.value(),
            "preload_timeout": self.spn_preload_timeout.value(),
            "request_timeout": self.spn_request_timeout.value(),
        })
        return True
