"""Unit tests for eloquent_notes.autostart."""

import os
from pathlib import Path
import stat

from eloquent_notes import autostart


def test_install_autostart_default(tmp_path, monkeypatch):
    """Test install_autostart creates desktop entry when executable is not found in PATH."""
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    filepath = autostart.install_autostart()

    expected_path = os.path.join(str(tmp_path), ".config", "autostart", "eloquent-notes.desktop")
    assert os.path.exists(filepath)
    assert filepath == expected_path

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=eloquent-notes" in content
    assert "Name=Eloquent Notes" in content

    # Check file permissions (should end with 644)
    st_mode = os.stat(filepath).st_mode
    assert stat.S_IMODE(st_mode) == 0o644


def test_install_autostart_with_found_executable(tmp_path, monkeypatch):
    """Test install_autostart uses absolute executable path when found in PATH."""
    mock_bin = "/usr/local/bin/eloquent-notes"

    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.setattr("shutil.which", lambda cmd: mock_bin)

    filepath = autostart.install_autostart()

    content = Path(filepath).read_text(encoding="utf-8")
    assert f"Exec={mock_bin}" in content
