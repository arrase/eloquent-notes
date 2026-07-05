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

from eloquent_notes.autostart import install_autostart


def main():
    """Parse CLI arguments and either send IPC or launch the daemon."""
    parser = argparse.ArgumentParser(
        description=(
            "Eloquent Notes - Linux system tray utility"
            " for offline dictation into Obsidian."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install-autostart", "toggle"],
        metavar="command",
        help=(
            "Command to execute: 'install-autostart' or"
            " 'toggle' (toggle recording)."
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
