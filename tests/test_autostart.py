"""Unit tests for eloquent_notes.autostart."""

import stat
from pathlib import Path

import pytest

from eloquent_notes import autostart


def test_get_autostart_path_honors_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    expected = str(tmp_path / "autostart" / "eloquent-notes.desktop")
    assert autostart.get_autostart_path() == expected


def test_get_autostart_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    expected = str(Path("~/.config").expanduser() / "autostart" / "eloquent-notes.desktop")
    assert autostart.get_autostart_path() == expected


def test_get_desktop_and_icon_paths_honor_xdg_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert autostart.get_desktop_entry_path() == str(tmp_path / "applications" / "eloquent-notes.desktop")
    assert autostart.get_icon_path() == str(tmp_path / "icons" / "hicolor" / "scalable" / "apps" / "eloquent-notes.svg")


def test_get_desktop_and_icon_paths_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    default_data = Path("~/.local/share").expanduser()
    assert autostart.get_desktop_entry_path() == str(default_data / "applications" / "eloquent-notes.desktop")
    assert autostart.get_icon_path() == str(
        default_data / "icons" / "hicolor" / "scalable" / "apps" / "eloquent-notes.svg"
    )


def test_install_app_icon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    icon_path = autostart.install_app_icon()
    assert icon_path == autostart.get_icon_path()
    assert Path(icon_path).read_text(encoding="utf-8") == autostart.APP_ICON_SVG


def test_install_desktop_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test install_desktop_entry writes the SVG icon and application launcher entry."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.executable", "/usr/local/bin/python3")

    filepath = autostart.install_desktop_entry()
    icon_path = autostart.get_icon_path()

    assert filepath == autostart.get_desktop_entry_path()
    assert Path(filepath).exists()
    assert Path(icon_path).exists()
    assert Path(icon_path).read_text(encoding="utf-8") == autostart.APP_ICON_SVG

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=/usr/local/bin/eloquent-notes open\n" in content
    assert f"Icon={icon_path}\n" in content
    assert "StartupWMClass=eloquent-notes\n" in content
    assert "StartupNotify=false\n" in content
    assert "X-GNOME-Autostart-enabled" not in content
    assert stat.S_IMODE(Path(filepath).stat().st_mode) == 0o600


def test_install_autostart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test install_autostart creates the desktop entry using the current environment binary."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("sys.executable", "/usr/local/bin/python3")

    filepath = autostart.install_autostart()

    expected_path = str(tmp_path / "config" / "autostart" / "eloquent-notes.desktop")
    assert filepath == expected_path
    assert Path(filepath).exists()
    assert Path(autostart.get_desktop_entry_path()).exists()

    content = Path(filepath).read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=/usr/local/bin/eloquent-notes\n" in content
    assert "Name=Eloquent Notes" in content
    assert f"Icon={autostart.get_icon_path()}" in content
    assert "X-GNOME-Autostart-enabled=true\n" in content

    st_mode = Path(filepath).stat().st_mode
    assert stat.S_IMODE(st_mode) == 0o600


def test_install_entries_quote_path_with_spaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test desktop and autostart entries quote executable paths containing spaces."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("sys.executable", "/opt/My Apps/bin/python3")

    autostart_path = autostart.install_autostart()
    desktop_path = autostart.get_desktop_entry_path()

    assert 'Exec="/opt/My Apps/bin/eloquent-notes"\n' in Path(autostart_path).read_text(encoding="utf-8")
    assert 'Exec="/opt/My Apps/bin/eloquent-notes" open\n' in Path(desktop_path).read_text(encoding="utf-8")


def test_is_autostart_enabled_and_remove(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test checking autostart status and removing the desktop entry."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    assert not autostart.is_autostart_enabled()
    filepath = autostart.install_autostart()
    assert autostart.is_autostart_enabled()

    autostart.remove_autostart()
    assert not autostart.is_autostart_enabled()
    assert not Path(filepath).exists()
