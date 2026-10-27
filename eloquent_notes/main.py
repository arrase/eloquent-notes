"""CLI entry point for Eloquent Notes.

Handles single-instance communication via a local Unix socket, autostart
installation, and launching the daemon or configuration window.
"""

import argparse
import os
import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication, QDialog

from eloquent_notes import IPC_SERVER_NAME, __version__
from eloquent_notes.autostart import install_autostart
from eloquent_notes.config_gui import ConfigurationDialog
from eloquent_notes.i18n import _


def parse_args(cli_args=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="eloquent-notes",
        description=_(
            "Eloquent Notes - Linux system tray utility that turns offline voice dictations into organized notes."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install-autostart", "toggle", "open", "config"],
        metavar="command",
        help=_(
            "Command to execute: 'install-autostart', 'toggle',"
            " 'open' (show the notes window), or 'config' (open configuration GUI)."
        ),
    )
    parser.add_argument(
        "-t",
        "--toggle",
        action="store_true",
        help=_("Alias for 'toggle' command."),
    )
    return parser.parse_args(cli_args)


def send_ipc_command(command, timeout_ms=500):
    """Send a command string to the running daemon via local socket IPC.

    Returns:
        bool: True if connection and write succeeded, False otherwise.
    """
    socket = QLocalSocket()
    socket.connectToServer(IPC_SERVER_NAME)
    if socket.waitForConnected(timeout_ms):
        try:
            socket.write(command.encode("utf-8"))
            socket.waitForBytesWritten(timeout_ms)
            return True
        finally:
            socket.disconnectFromServer()
    return False


def run_cli(cli_args=None, launcher=os.execv):
    """Execute CLI logic based on provided arguments."""
    args = parse_args(cli_args)
    wants_toggle = args.command == "toggle" or args.toggle

    if args.command == "install-autostart":
        install_autostart()
        return

    if args.command == "config":
        _app = QApplication.instance() or QApplication(sys.argv)
        _app.setApplicationName("eloquent-notes")
        QApplication.setDesktopFileName("eloquent-notes")
        dialog = ConfigurationDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            send_ipc_command("reload", timeout_ms=200)
        return

    _app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    _app.setApplicationName("eloquent-notes")

    message = "toggle" if wants_toggle else "open"
    if send_ipc_command(message):
        return

    daemon_args = [sys.executable, "-m", "eloquent_notes.app"]
    if wants_toggle:
        daemon_args.append("toggle")
    elif args.command == "open":
        daemon_args.append("open")

    launcher(sys.executable, daemon_args)


def main():
    """Main entry point for the CLI application."""
    run_cli()


if __name__ == "__main__":
    main()
