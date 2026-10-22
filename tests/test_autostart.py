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


def test_get_desktop_and_icon_paths_honor_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert autostart.get_desktop_entry_path() == os.path.join(
        str(tmp_path), "applications", "eloquent-notes.desktop"
    )
    assert autostart.get_icon_path() == os.path.join(
        str(tmp_path), "icons", "hicolor", "scalable", "apps", "eloquent-notes.svg"
    )


def test_get_desktop_and_icon_paths_default(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    default_data = os.path.expanduser("~/.local/share")
    assert autostart.get_desktop_entry_path() == os.path.join(
        default_data, "applications", "eloquent-notes.desktop"
    )
    assert autostart.get_icon_path() == os.path.join(
        default_data, "icons", "hicolor", "scalable", "apps", "eloquent-notes.svg"
    )


def test_install_app_icon(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    icon_path = autostart.install_app_icon()
    assert icon_path == autostart.get_icon_path()
    assert Path(icon_path).read_text(encoding="utf-8") == autostart.APP_ICON_SVG


def test_install_desktop_entry(tmp_path, monkeypatch):
    """Test install_desktop_entry writes the SVG icon and application launcher entry."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/eloquent-notes")

    filepath = autostart.install_desktop_entry()
    icon_path = autostart.get_icon_path()

    assert filepath == autostart.get_desktop_entry_path()
    assert os.path.exists(filepath)
    assert os.path.exists(icon_path)
    assert Path(icon_path).read_text(encoding="utf-8") == autostart.APP_ICON_SVG

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=/usr/local/bin/eloquent-notes open\n" in content
    assert f"Icon={icon_path}\n" in content
    assert "StartupWMClass=eloquent-notes\n" in content
    assert "StartupNotify=false\n" in content
    assert stat.S_IMODE(os.stat(filepath).st_mode) == 0o600


def test_install_autostart(tmp_path, monkeypatch):
    """Test install_autostart creates the desktop entry with safe defaults."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("shutil.which", lambda cmd: None)

    filepath = autostart.install_autostart()

    expected_path = os.path.join(str(tmp_path / "config"), "autostart", "eloquent-notes.desktop")
    assert filepath == expected_path
    assert os.path.exists(filepath)
    assert os.path.exists(autostart.get_desktop_entry_path())

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=eloquent-notes\n" in content
    assert "Name=Eloquent Notes" in content
    assert f"Icon={autostart.get_icon_path()}" in content

    st_mode = os.stat(filepath).st_mode
    assert stat.S_IMODE(st_mode) == 0o600


def test_install_autostart_with_found_executable(tmp_path, monkeypatch):
    """Test install_autostart uses the absolute executable path found in PATH."""
    mock_bin = "/usr/local/bin/eloquent-notes"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("shutil.which", lambda cmd: mock_bin)

    filepath = autostart.install_autostart()

    content = Path(filepath).read_text(encoding="utf-8")
    assert f"Exec={mock_bin}\n" in content


def test_install_entries_quote_path_with_spaces(tmp_path, monkeypatch):
    """Test desktop and autostart entries quote executable paths containing spaces."""
    mock_bin = "/opt/My Apps/eloquent-notes"

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("shutil.which", lambda cmd: mock_bin)

    autostart_path = autostart.install_autostart()
    desktop_path = autostart.get_desktop_entry_path()

    assert f'Exec="{mock_bin}"\n' in Path(autostart_path).read_text(encoding="utf-8")
    assert f'Exec="{mock_bin}" open\n' in Path(desktop_path).read_text(encoding="utf-8")


def test_is_autostart_enabled_and_remove(tmp_path, monkeypatch):
    """Test checking autostart status and removing the desktop entry."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert not autostart.is_autostart_enabled()
    filepath = autostart.install_autostart()
    assert autostart.is_autostart_enabled()

    autostart.remove_autostart()
    assert not autostart.is_autostart_enabled()
    assert not os.path.exists(filepath)
