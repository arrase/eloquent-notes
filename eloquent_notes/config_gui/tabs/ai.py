"""AI settings tab for configuration."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from eloquent_notes.config import KEEP_ALIVE_RE
from eloquent_notes.config_gui.loader import OllamaModelLoader
from eloquent_notes.i18n import OUTPUT_LANGUAGES, _

VALIDATION_ERROR_TITLE = "Validation Error"
_LABEL_WIDTH = 140


def _form_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setMinimumWidth(_LABEL_WIDTH)
    return label


class AITab(QWidget):
    """AI and Ollama configuration tab."""

    def __init__(self):
        super().__init__()
        self._model_loader = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_ai = QGroupBox(_("Ollama && AI Pipeline Settings"))
        form_layout = QFormLayout(grp_ai)
        form_layout.setSpacing(10)

        self.txt_ollama_url = QLineEdit()
        self.txt_ollama_url.setToolTip(_("URL of your local or remote Ollama server."))
        form_layout.addRow(_form_label(_("Ollama URL:")), self.txt_ollama_url)

        model_widget = QWidget()
        model_layout = QVBoxLayout(model_widget)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(3)

        model_row = QHBoxLayout()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(6)

        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        self.cmb_model.setToolTip(
            _("Name of the Ollama LLM model to run for dictation tasks (e.g. gemma4:e4b-it-qat).")
        )
        self.btn_refresh_models = QPushButton(_("Refresh"))
        self.btn_refresh_models.clicked.connect(self._fetch_models)

        model_row.addWidget(self.cmb_model, 1)
        model_row.addWidget(self.btn_refresh_models)

        self.lbl_model_status = QLabel(_("Ready"))
        self.lbl_model_status.setObjectName("statusHint")

        model_layout.addLayout(model_row)
        model_layout.addWidget(self.lbl_model_status)

        lbl_ai_model = _form_label(_("AI Model (Audio):"))
        lbl_ai_model.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl_ai_model.setContentsMargins(0, 6, 0, 0)
        form_layout.addRow(lbl_ai_model, model_widget)

        context_widget = QWidget()
        context_layout = QHBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(10)

        self.spn_context_length = QSpinBox()
        self.spn_context_length.setRange(512, 262144)
        self.spn_context_length.setSingleStep(1024)
        self.spn_context_length.setToolTip(
            _(
                "Context length in tokens to pass to Ollama. "
                "Larger values allow longer dictations but use more memory."
            )
        )

        self.chk_context_default = QCheckBox(_("Use default context length"))
        self.chk_context_default.setToolTip(
            _(
                "If checked, sets context_length to null (or leaves it unset), "
                "instructing Ollama to use the model's default maximum context length."
            )
        )
        self.chk_context_default.toggled.connect(self._toggle_context_default)

        context_layout.addWidget(self.spn_context_length, 1)
        context_layout.addWidget(self.chk_context_default)
        form_layout.addRow(_form_label(_("Context Length:")), context_widget)

        self.txt_keep_alive = QLineEdit()
        self.txt_keep_alive.setToolTip(
            _("Time to keep model loaded after note generation (e.g., '0' to unload immediately, or '5m').")
        )
        form_layout.addRow(_form_label(_("Keep Alive Time:")), self.txt_keep_alive)

        self.txt_preload_keep_alive = QLineEdit()
        self.txt_preload_keep_alive.setToolTip(
            _("Time to keep model weights loaded in VRAM during recording to minimize latency (e.g., '5m').")
        )
        form_layout.addRow(_form_label(_("Preload Keep Alive:")), self.txt_preload_keep_alive)

        self.spn_max_retries = QSpinBox()
        self.spn_max_retries.setRange(0, 10)
        self.spn_max_retries.setToolTip(_("Number of retry attempts if LLM output fails JSON parsing."))
        form_layout.addRow(_form_label(_("Max Retries:")), self.spn_max_retries)

        self.spn_preload_timeout = QSpinBox()
        self.spn_preload_timeout.setRange(10, 1000)
        self.spn_preload_timeout.setSuffix(_(" sec"))
        form_layout.addRow(_form_label(_("Preload Timeout:")), self.spn_preload_timeout)

        self.spn_request_timeout = QSpinBox()
        self.spn_request_timeout.setRange(10, 1000)
        self.spn_request_timeout.setSuffix(_(" sec"))
        form_layout.addRow(_form_label(_("Request Timeout:")), self.spn_request_timeout)

        self.cmb_language = QComboBox()
        self.cmb_language.setEditable(True)
        self.cmb_language.addItems(OUTPUT_LANGUAGES)
        self.cmb_language.setToolTip(
            _("Target language for rewritten notes, titles, and tags (e.g. English, Spanish).")
        )
        form_layout.addRow(_form_label(_("Output Language:")), self.cmb_language)

        layout.addWidget(grp_ai)

        grp_search = QGroupBox(_("Semantic Search"))
        search_layout = QFormLayout(grp_search)
        search_layout.setSpacing(10)

        self.cmb_embedding_model = QComboBox()
        self.cmb_embedding_model.setEditable(True)
        self.cmb_embedding_model.setToolTip(
            _("Ollama embedding model used to search notes by meaning (e.g. embeddinggemma-2:latest).")
        )
        search_layout.addRow(_form_label(_("Embedding Model:")), self.cmb_embedding_model)

        self.txt_search_keep_alive = QLineEdit()
        self.txt_search_keep_alive.setToolTip(
            _("Time to keep the embedding model loaded after a search (e.g., '5m' or '0').")
        )
        search_layout.addRow(_form_label(_("Keep Alive Time:")), self.txt_search_keep_alive)

        self.spn_min_similarity = QDoubleSpinBox()
        self.spn_min_similarity.setRange(0.0, 1.0)
        self.spn_min_similarity.setSingleStep(0.05)
        self.spn_min_similarity.setToolTip(_("Search results below this cosine similarity are hidden."))
        search_layout.addRow(_form_label(_("Minimum Similarity:")), self.spn_min_similarity)

        layout.addWidget(grp_search)
        layout.addStretch()

    def _toggle_context_default(self, checked):
        self.spn_context_length.setEnabled(not checked)

    def _fetch_models(self):
        url = self.txt_ollama_url.text().strip()
        if not url:
            self._model_loader = None
            self.btn_refresh_models.setEnabled(True)
            self.lbl_model_status.setText(_("Ollama URL is empty."))
            return

        self.lbl_model_status.setText(_("Fetching models..."))
        self.btn_refresh_models.setEnabled(False)

        loader = OllamaModelLoader(url)
        self._model_loader = loader
        loader.models_fetched.connect(self._on_models_fetched)
        loader.error_occurred.connect(self._on_models_fetch_failed)
        loader.start()

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        if combo.findText(value) == -1:
            combo.addItem(value)
        combo.setCurrentText(value)

    @staticmethod
    def _fill_models(combo, models):
        """Replace combo items with models, keeping the current selection."""
        current_text = combo.currentText()
        combo.clear()
        combo.addItems(models)
        if current_text:
            AITab._set_combo_value(combo, current_text)

    def _on_models_fetched(self, audio_models, embedding_models):
        if self._model_loader is None or self.sender() is not self._model_loader:
            return
        self._model_loader = None
        self.btn_refresh_models.setEnabled(True)

        self._fill_models(self.cmb_model, audio_models)
        self._fill_models(self.cmb_embedding_model, embedding_models)

        if not audio_models:
            self.lbl_model_status.setText(_("No audio-capable models found."))
        else:
            self.lbl_model_status.setText(_("Models loaded successfully."))

    def _on_models_fetch_failed(self, error_msg):
        if self._model_loader is None or self.sender() is not self._model_loader:
            return
        self._model_loader = None
        self.btn_refresh_models.setEnabled(True)
        self.lbl_model_status.setText(_("Connection failed: {error}").format(error=error_msg))

    def load_settings(self, config_data: dict) -> None:
        ai_cfg = config_data["ai"]
        self.txt_ollama_url.setText(ai_cfg["ollama_url"])
        self._set_combo_value(self.cmb_model, ai_cfg["model"])

        context_len = ai_cfg["context_length"]
        is_default = context_len is None
        self.chk_context_default.setChecked(is_default)
        self.spn_context_length.setEnabled(not is_default)
        if not is_default:
            self.spn_context_length.setValue(context_len)

        self.txt_keep_alive.setText(ai_cfg["keep_alive"])
        self.txt_preload_keep_alive.setText(ai_cfg["preload_keep_alive"])
        self.spn_max_retries.setValue(ai_cfg["max_retries"])
        self.spn_preload_timeout.setValue(ai_cfg["preload_timeout"])
        self.spn_request_timeout.setValue(ai_cfg["request_timeout"])

        search_cfg = config_data["search"]
        self._set_combo_value(self.cmb_embedding_model, search_cfg["embedding_model"])
        self.txt_search_keep_alive.setText(search_cfg["keep_alive"])
        self.spn_min_similarity.setValue(search_cfg["min_similarity"])

        self._set_combo_value(self.cmb_language, ai_cfg["output_language"])

        self._fetch_models()

    def save_settings(self, config_data: dict) -> bool:
        url = self.txt_ollama_url.text().strip().rstrip("/")
        self.txt_ollama_url.setText(url)

        if not url:
            QMessageBox.warning(self, _(VALIDATION_ERROR_TITLE), _("Ollama URL cannot be empty."))
            return False
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(
                self,
                _(VALIDATION_ERROR_TITLE),
                _("Ollama URL must start with http:// or https://."),
            )
            return False

        model = self.cmb_model.currentText().strip()
        if not model:
            QMessageBox.warning(self, _(VALIDATION_ERROR_TITLE), _("AI Model cannot be empty."))
            return False

        embedding_model = self.cmb_embedding_model.currentText().strip()
        if not embedding_model:
            QMessageBox.warning(self, _(VALIDATION_ERROR_TITLE), _("Embedding Model cannot be empty."))
            return False

        output_lang = self.cmb_language.currentText().strip()
        if not output_lang:
            QMessageBox.warning(self, _(VALIDATION_ERROR_TITLE), _("Output Language cannot be empty."))
            return False

        keep_alive = self.txt_keep_alive.text().strip()
        preload_keep_alive = self.txt_preload_keep_alive.text().strip()
        search_keep_alive = self.txt_search_keep_alive.text().strip()

        for value, error_template in (
            (
                keep_alive,
                _(
                    "Invalid Keep Alive format: '{value}'. "
                    "Must be an integer or duration (e.g., 5m, 10s, 1h, 0, -1)."
                ),
            ),
            (
                preload_keep_alive,
                _(
                    "Invalid Preload Keep Alive format: '{value}'. "
                    "Must be an integer or duration (e.g., 5m, 10s, 1h, 0, -1)."
                ),
            ),
            (
                search_keep_alive,
                _(
                    "Invalid Search Keep Alive format: '{value}'. "
                    "Must be an integer or duration (e.g., 5m, 10s, 1h, 0, -1)."
                ),
            ),
        ):
            if not KEEP_ALIVE_RE.fullmatch(value):
                QMessageBox.warning(
                    self,
                    _(VALIDATION_ERROR_TITLE),
                    error_template.format(value=value),
                )
                return False

        context_len = None if self.chk_context_default.isChecked() else self.spn_context_length.value()

        config_data["ai"].update({
            "ollama_url": url,
            "model": model,
            "output_language": output_lang,
            "context_length": context_len,
            "keep_alive": keep_alive,
            "preload_keep_alive": preload_keep_alive,
            "max_retries": self.spn_max_retries.value(),
            "preload_timeout": self.spn_preload_timeout.value(),
            "request_timeout": self.spn_request_timeout.value(),
        })
        config_data["search"].update({
            "embedding_model": embedding_model,
            "keep_alive": search_keep_alive,
            "min_similarity": round(self.spn_min_similarity.value(), 2),
        })
        return True


