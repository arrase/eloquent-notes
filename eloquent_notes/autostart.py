"""Autostart desktop entry installer for Linux.

Creates a .desktop file in ~/.config/autostart/ so Eloquent Notes
launches automatically on login.
"""

import os
import shutil
import sys


def install_autostart():
    """Install the autostart desktop entry for Eloquent Notes."""
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file_path = os.path.join(autostart_dir, "eloquent-notes.desktop")

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
    os.makedirs(autostart_dir, exist_ok=True)
    with open(desktop_file_path, "w", encoding="utf-8") as f:
        f.write(desktop_entry_content)
    os.chmod(desktop_file_path, 0o644)
    print(f"Autostart entry created at: {desktop_file_path}")
    print("Eloquent Notes will now start automatically upon login!")
