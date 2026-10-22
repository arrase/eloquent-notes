"""Desktop entry and icon installer for Linux.

Installs the application launcher entry in $XDG_DATA_HOME/applications/,
the application SVG icon in $XDG_DATA_HOME/icons/hicolor/scalable/apps/,
and the optional login autostart entry in $XDG_CONFIG_HOME/autostart/.
"""

import os
import shutil

from eloquent_notes.config import atomic_write, get_config_home, get_data_home

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


def get_icon_path():
    """Return the path of the Eloquent Notes application SVG icon."""
    return os.path.join(
        get_data_home(), "icons", "hicolor", "scalable", "apps", "eloquent-notes.svg"
    )


def get_desktop_entry_path():
    """Return the path of the Eloquent Notes application launcher desktop entry."""
    return os.path.join(get_data_home(), "applications", "eloquent-notes.desktop")


def get_autostart_path():
    """Return the path of the Eloquent Notes autostart desktop entry."""
    return os.path.join(get_config_home(), "autostart", "eloquent-notes.desktop")


def is_autostart_enabled():
    """Return True if autostart desktop entry exists."""
    return os.path.exists(get_autostart_path())


def remove_autostart():
    """Remove the autostart desktop entry if it exists."""
    path = get_autostart_path()
    if os.path.exists(path):
        os.remove(path)


def install_app_icon():
    """Install the Eloquent Notes SVG icon into the user hicolor icon theme."""
    icon_path = get_icon_path()
    atomic_write(icon_path, APP_ICON_SVG)
    return icon_path


def _write_desktop_file(path, content):
    atomic_write(path, content)
    os.chmod(path, 0o600)
    return path


def _resolve_launcher():
    icon_path = install_app_icon()
    exec_path = shutil.which("eloquent-notes") or "eloquent-notes"
    if " " in exec_path:
        exec_path = f'"{exec_path}"'
    return icon_path, exec_path


def _write_desktop_entry(icon_path, exec_path):
    content = f"""[Desktop Entry]
Type=Application
Exec={exec_path} open
Name=Eloquent Notes
Comment=Voice dictations turned into organized notes
Icon={icon_path}
Terminal=false
Categories=Utility;
StartupNotify=false
StartupWMClass=eloquent-notes
"""
    return _write_desktop_file(get_desktop_entry_path(), content)


def install_desktop_entry():
    """Install the application launcher desktop entry for Eloquent Notes.

    Returns:
        str: Path to the installed desktop entry file.
    """
    icon_path, exec_path = _resolve_launcher()
    return _write_desktop_entry(icon_path, exec_path)


def install_autostart():
    """Install the autostart desktop entry for Eloquent Notes.

    Returns:
        str: Path to the installed desktop entry file.
    """
    icon_path, exec_path = _resolve_launcher()
    _write_desktop_entry(icon_path, exec_path)

    content = f"""[Desktop Entry]
Type=Application
Exec={exec_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Eloquent Notes
Comment=Voice dictations turned into organized notes
Icon={icon_path}
Categories=Utility;
"""
    return _write_desktop_file(get_autostart_path(), content)

