import os
import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

if "sounddevice" not in sys.modules:
    sd_mock = MagicMock()
    sd_mock.CallbackFlags = MagicMock()
    sys.modules["sounddevice"] = sd_mock


@pytest.fixture(scope="session")
def qapp():
    """Fixture to ensure a QApplication instance exists for Qt widget testing."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
