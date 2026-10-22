import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

# Keep the embedding cache and desktop entries of the user's real session out of reach.
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="eloquent-notes-cache-")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="eloquent-notes-data-")

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
    return app
