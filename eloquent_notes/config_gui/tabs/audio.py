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
    QWidget,
)

from eloquent_notes.i18n import _


class AudioTab(QWidget):
    """Audio configuration tab."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        grp_audio = QGroupBox(_("Audio Capture Settings"))
        form_layout = QFormLayout(grp_audio)
        form_layout.setSpacing(10)

        self.cmb_channels = QComboBox()
        self.cmb_channels.addItems([_("Mono (1 channel)"), _("Stereo (2 channels)")])
        self.cmb_channels.setToolTip(_("Number of audio input channels."))
        form_layout.addRow(QLabel(_("Audio Channels:")), self.cmb_channels)

        self.chk_recording_hud_enabled = QCheckBox(_("Show floating countdown HUD overlay during recording"))
        self.chk_recording_hud_enabled.setToolTip(
            _("Displays a sleek floating pill overlay with live countdown timer and progress bar while dictating.")
        )
        form_layout.addRow(self.chk_recording_hud_enabled)

        self.chk_beep_enabled = QCheckBox(_("Play beep on recording start and stop"))
        self.chk_beep_enabled.setToolTip(_("Audible feedback beeps when starting/stopping recording."))
        self.chk_beep_enabled.toggled.connect(self._toggle_beep_controls)
        form_layout.addRow(self.chk_beep_enabled)

        self.spn_beep_freq = QSpinBox()
        self.spn_beep_freq.setRange(100, 5000)
        self.spn_beep_freq.setSuffix(_(" Hz"))
        form_layout.addRow(QLabel(_("Beep Frequency:")), self.spn_beep_freq)

        self.spn_beep_duration = QDoubleSpinBox()
        self.spn_beep_duration.setRange(0.01, 2.0)
        self.spn_beep_duration.setSingleStep(0.05)
        self.spn_beep_duration.setDecimals(2)
        self.spn_beep_duration.setSuffix(_(" sec"))
        form_layout.addRow(QLabel(_("Beep Duration:")), self.spn_beep_duration)

        layout.addWidget(grp_audio)
        layout.addStretch()

    def _toggle_beep_controls(self, checked: bool) -> None:
        self.spn_beep_freq.setEnabled(checked)
        self.spn_beep_duration.setEnabled(checked)

    def load_settings(self, config_data: dict) -> None:
        audio_cfg = config_data["audio"]
        self.cmb_channels.setCurrentIndex(0 if audio_cfg["channels"] == 1 else 1)
        self.chk_recording_hud_enabled.setChecked(audio_cfg["recording_hud_enabled"])
        beep_enabled = audio_cfg["beep_enabled"]
        self.chk_beep_enabled.setChecked(beep_enabled)
        self._toggle_beep_controls(beep_enabled)
        self.spn_beep_freq.setValue(audio_cfg["beep_frequency"])
        self.spn_beep_duration.setValue(audio_cfg["beep_duration"])

    def save_settings(self, config_data: dict) -> bool:
        config_data["audio"].update(
            {
                "channels": 1 if self.cmb_channels.currentIndex() == 0 else 2,
                "recording_hud_enabled": self.chk_recording_hud_enabled.isChecked(),
                "beep_enabled": self.chk_beep_enabled.isChecked(),
                "beep_frequency": self.spn_beep_freq.value(),
                "beep_duration": round(self.spn_beep_duration.value(), 2),
            }
        )
        return True
