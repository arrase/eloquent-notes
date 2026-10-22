import atexit
import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

# Keep the user's real XDG directories out of reach and clean up /tmp on exit.
for _xdg_var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
    _xdg_tmp = tempfile.mkdtemp(prefix=f"eloquent-notes-{_xdg_var.lower()}-")
    os.environ[_xdg_var] = _xdg_tmp
    atexit.register(shutil.rmtree, _xdg_tmp, ignore_errors=True)

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
