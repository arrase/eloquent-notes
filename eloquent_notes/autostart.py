"""Desktop entry and icon installer for Linux.

Installs the application launcher entry in $XDG_DATA_HOME/applications/,
the application SVG icon in $XDG_DATA_HOME/icons/hicolor/scalable/apps/,
and the optional login autostart entry in $XDG_CONFIG_HOME/autostart/.
"""

import sys
from pathlib import Path

from eloquent_notes.config import atomic_write, get_config_home, get_data_home
from eloquent_notes.i18n import _

APP_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect x="4" y="4" width="56" height="56" rx="14" fill="#2C4C7E"/>
  <rect x="12" y="11" width="26" height="34" rx="4" fill="#FFFFFF"/>
  <circle cx="43" cy="38" r="14" fill="#2C4C7E"/>
  <g stroke="#2C4C7E" stroke-width="2.5" stroke-linecap="round">
    <line x1="17" y1="19" x2="33" y2="19"/>
    <line x1="17" y1="25" x2="31" y2="25"/>
    <line x1="17" y1="31" x2="26" y2="31"/>
  </g>
  <rect x="38" y="26" width="10" height="14" rx="5" fill="#FFFFFF"/>
  <g fill="none" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
    <path d="M 34 37 A 9 6 0 0 0 52 37"/>
    <line x1="43" y1="43" x2="43" y2="49"/>
    <line x1="38" y1="49" x2="48" y2="49"/>
  </g>
</svg>
"""


def get_icon_path() -> str:
    """Return the path of the Eloquent Notes application SVG icon."""
    return str(Path(get_data_home(), "icons", "hicolor", "scalable", "apps", "eloquent-notes.svg"))


def get_desktop_entry_path() -> str:
    """Return the path of the Eloquent Notes application launcher desktop entry."""
    return str(Path(get_data_home(), "applications", "eloquent-notes.desktop"))


def get_autostart_path() -> str:
    """Return the path of the Eloquent Notes autostart desktop entry."""
    return str(Path(get_config_home(), "autostart", "eloquent-notes.desktop"))


def is_autostart_enabled() -> bool:
    """Return True if autostart desktop entry exists."""
    return Path(get_autostart_path()).exists()


def remove_autostart() -> None:
    """Remove the autostart desktop entry if it exists."""
    path = Path(get_autostart_path())
    if path.exists():
        path.unlink()


def install_app_icon() -> str:
    """Install the Eloquent Notes SVG icon into the user hicolor icon theme."""
    icon_path = get_icon_path()
    atomic_write(icon_path, APP_ICON_SVG)
    return icon_path


def _resolve_launcher() -> tuple[str, str]:
    icon_path = install_app_icon()
    exec_path = str(Path(sys.executable).with_name("eloquent-notes"))
    if " " in exec_path:
        exec_path = f'"{exec_path}"'
    return icon_path, exec_path


def _write_desktop_entry(path: str, exec_cmd: str, icon_path: str, *extra_lines: str) -> str:
    comment = _("Voice dictations turned into organized notes")
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Exec={exec_cmd}",
        "Name=Eloquent Notes",
        f"Comment={comment}",
        f"Icon={icon_path}",
        "Terminal=false",
        "Categories=Utility;",
        "StartupNotify=false",
        "StartupWMClass=eloquent-notes",
        *extra_lines,
    ]
    atomic_write(path, "\n".join(lines) + "\n")
    Path(path).chmod(0o600)
    return path


def install_desktop_entry() -> str:
    """Install the application launcher desktop entry for Eloquent Notes.

    Returns:
        str: Path to the installed desktop entry file.
    """
    icon_path, exec_path = _resolve_launcher()
    return _write_desktop_entry(get_desktop_entry_path(), f"{exec_path} open", icon_path)


def install_autostart() -> str:
    """Install the autostart desktop entry for Eloquent Notes.

    Returns:
        str: Path to the installed desktop entry file.
    """
    icon_path, exec_path = _resolve_launcher()
    _write_desktop_entry(get_desktop_entry_path(), f"{exec_path} open", icon_path)
    return _write_desktop_entry(
        get_autostart_path(),
        exec_path,
        icon_path,
        "Hidden=false",
        "NoDisplay=false",
        "X-GNOME-Autostart-enabled=true",
    )
