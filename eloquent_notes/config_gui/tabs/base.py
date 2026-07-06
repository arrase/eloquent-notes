"""Base class for configuration GUI tabs."""

from PyQt6.QtWidgets import QWidget


class ConfigTab(QWidget):
    """Abstract base class for a configuration tab."""

    def load_settings(self, config_data: dict) -> None:
        """Load settings from the configuration dict into the UI."""
        raise NotImplementedError

    def save_settings(self, config_data: dict) -> bool:
        """Save settings from the UI into the configuration dict. Returns True if valid."""
        raise NotImplementedError

    def restore_defaults(self) -> None:
        """Restore default settings in the UI."""
        pass

    def cleanup(self) -> None:
        """Cleanup any background threads or resources."""
        pass
