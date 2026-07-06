"""Audio settings tab for configuration."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from eloquent_notes.config_gui.tabs.base import ConfigTab


class AudioTab(ConfigTab):
    """Audio configuration tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_audio = QGroupBox("Audio Capture Settings")
        form_layout = QFormLayout(grp_audio)
        form_layout.setSpacing(10)

        self.spn_sample_rate = QSpinBox()
        self.spn_sample_rate.setRange(8000, 96000)
        self.spn_sample_rate.setSingleStep(8000)
        self.spn_sample_rate.setSuffix(" Hz")
        self.spn_sample_rate.setToolTip(
            "Sample rate for microphone recording (16000 Hz is recommended for whisper/dictation models)."
        )
        form_layout.addRow(QLabel("Sample Rate:"), self.spn_sample_rate)

        self.cmb_channels = QComboBox()
        self.cmb_channels.addItems(["Mono (1 channel)", "Stereo (2 channels)"])
        self.cmb_channels.setToolTip("Number of audio input channels.")
        form_layout.addRow(QLabel("Audio Channels:"), self.cmb_channels)

        self.chk_beep_enabled = QCheckBox("Play beep on recording start and stop")
        self.chk_beep_enabled.setToolTip("Audible feedback beeps when starting/stopping recording.")
        form_layout.addRow(self.chk_beep_enabled)

        self.spn_beep_freq = QSpinBox()
        self.spn_beep_freq.setRange(100, 5000)
        self.spn_beep_freq.setSuffix(" Hz")
        form_layout.addRow(QLabel("Beep Frequency:"), self.spn_beep_freq)

        self.spn_beep_duration = QDoubleSpinBox()
        self.spn_beep_duration.setRange(0.01, 2.0)
        self.spn_beep_duration.setSingleStep(0.05)
        self.spn_beep_duration.setDecimals(2)
        self.spn_beep_duration.setSuffix(" sec")
        form_layout.addRow(QLabel("Beep Duration:"), self.spn_beep_duration)

        layout.addWidget(grp_audio)
        layout.addStretch()

    def load_settings(self, config_data: dict) -> None:
        audio_cfg = config_data["audio"]
        self.spn_sample_rate.setValue(audio_cfg["sample_rate"])

        channels = audio_cfg["channels"]
        self.cmb_channels.setCurrentIndex(0 if channels == 1 else 1)

        self.chk_beep_enabled.setChecked(audio_cfg["beep_enabled"])
        self.spn_beep_freq.setValue(audio_cfg["beep_frequency"])
        self.spn_beep_duration.setValue(audio_cfg["beep_duration"])

    def save_settings(self, config_data: dict) -> bool:
        config_data["audio"].update({
            "sample_rate": self.spn_sample_rate.value(),
            "channels": 1 if self.cmb_channels.currentIndex() == 0 else 2,
            "beep_enabled": self.chk_beep_enabled.isChecked(),
            "beep_frequency": self.spn_beep_freq.value(),
            "beep_duration": self.spn_beep_duration.value(),
        })
        return True
