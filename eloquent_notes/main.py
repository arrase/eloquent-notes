"""CLI entry point for Eloquent Notes.

Handles single-instance enforcement via IPC, autostart installation,
and toggle-recording commands. If no instance is running, launches
the daemon process via os.execv.
"""

import argparse
import os
import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication

from eloquent_notes import config
from eloquent_notes.autostart import install_autostart
from eloquent_notes.config_gui import ConfigurationDialog


def main():
    """Parse CLI arguments and either send IPC, show config, or launch daemon."""
    parser = argparse.ArgumentParser(
        description=(
            "Eloquent Notes - Linux system tray utility"
            " for offline dictation into Obsidian."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install-autostart", "toggle", "config"],
        metavar="command",
        help=(
            "Command to execute: 'install-autostart', 'toggle',"
            " or 'config' (open configuration GUI)."
        ),
    )
    parser.add_argument(
        "-t", "--toggle",
        action="store_true",
        help="Alias for 'toggle' command.",
    )

    args = parser.parse_args()
    wants_toggle = args.command == "toggle" or args.toggle

    if args.command == "install-autostart":
        install_autostart()
        sys.exit(0)

    if args.command == "config":
        config.init_config_dir()
        app = QApplication(sys.argv)
        dialog = ConfigurationDialog()
        dialog.exec()
        sys.exit(0)

    # QCoreApplication needed for QLocalSocket
    app = QCoreApplication(sys.argv)

    # Check if another instance is already running
    socket = QLocalSocket()
    socket.connectToServer("eloquent_notes_ipc")
    if socket.waitForConnected(500):
        message = "toggle" if wants_toggle else "notify_running"
        socket.write(message.encode())
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        sys.exit(0)

    # Not running — launch the daemon process
    daemon_args = [sys.executable, "-m", "eloquent_notes.app"]
    if wants_toggle:
        daemon_args.append("toggle")

    os.execv(sys.executable, daemon_args)


if __name__ == "__main__":
    main()
