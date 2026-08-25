"""Autostart desktop entry installer for Linux.

Creates a .desktop file in the XDG autostart directory so Eloquent Notes
launches automatically on login.
"""

import os
import shutil

from eloquent_notes.config import get_config_home


def get_autostart_path():
    """Return the path of the Eloquent Notes autostart desktop entry."""
    return os.path.join(get_config_home(), "autostart", "eloquent-notes.desktop")


def install_autostart():
    """Install the autostart desktop entry for Eloquent Notes.

    Returns:
        str: Path to the installed desktop entry file.
    """
    desktop_file_path = get_autostart_path()

    exec_path = shutil.which("eloquent-notes")
    if not exec_path:
        exec_path = "eloquent-notes"

    desktop_entry_content = f"""[Desktop Entry]
Type=Application
Exec={exec_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=Eloquent Notes
Comment=Background dictation utility for Obsidian
Icon=accessories-text-editor
Categories=Utility;
"""
    print("Installing autostart desktop entry...")
    os.makedirs(os.path.dirname(desktop_file_path), exist_ok=True)
    with open(desktop_file_path, "w", encoding="utf-8") as f:
        f.write(desktop_entry_content)
    os.chmod(desktop_file_path, 0o644)
    print(f"Autostart entry created at: {desktop_file_path}")
    print("Eloquent Notes will now start automatically upon login!")
    return desktop_file_path

