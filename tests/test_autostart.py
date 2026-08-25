"""Unit tests for eloquent_notes.autostart."""

import os
import stat
from pathlib import Path

from eloquent_notes import autostart


def test_get_autostart_path_honors_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    expected = os.path.join(str(tmp_path), "autostart", "eloquent-notes.desktop")
    assert autostart.get_autostart_path() == expected


def test_get_autostart_path_default(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = os.path.join(
        os.path.expanduser("~/.config"), "autostart", "eloquent-notes.desktop"
    )
    assert autostart.get_autostart_path() == expected


def test_install_autostart(tmp_path, monkeypatch):
    """Test install_autostart creates the desktop entry with safe defaults."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    filepath = autostart.install_autostart()

    expected_path = os.path.join(str(tmp_path), "autostart", "eloquent-notes.desktop")
    assert filepath == expected_path
    assert os.path.exists(filepath)

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=eloquent-notes" in content
    assert "Name=Eloquent Notes" in content

    st_mode = os.stat(filepath).st_mode
    assert stat.S_IMODE(st_mode) == 0o644


def test_install_autostart_with_found_executable(tmp_path, monkeypatch):
    """Test install_autostart uses the absolute executable path found in PATH."""
    mock_bin = "/usr/local/bin/eloquent-notes"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda cmd: mock_bin)

    filepath = autostart.install_autostart()

    content = Path(filepath).read_text(encoding="utf-8")
    assert f"Exec={mock_bin}" in content
