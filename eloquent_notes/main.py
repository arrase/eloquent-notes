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
from PyQt6.QtWidgets import QApplication, QDialog

from eloquent_notes import config
from eloquent_notes.autostart import install_autostart
from eloquent_notes.config_gui import ConfigurationDialog


def create_arg_parser():
    """Create and return the CLI argument parser."""
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
    return parser


def parse_args(cli_args=None):
    """Parse command line arguments."""
    parser = create_arg_parser()
    return parser.parse_args(cli_args)


def send_ipc_command(command, timeout_ms=500):
    """Send a command string to the running daemon via local socket IPC.

    Returns:
        bool: True if connection and write succeeded, False otherwise.
    """
    socket = QLocalSocket()
    socket.connectToServer("eloquent_notes_ipc")
    if socket.waitForConnected(timeout_ms):
        try:
            socket.write(command.encode("utf-8"))
            socket.waitForBytesWritten(timeout_ms)
            return True
        finally:
            socket.disconnectFromServer()
    return False


def run_cli(cli_args=None, launcher=os.execv, sys_exit=sys.exit):
    """Execute CLI logic based on provided arguments."""
    args = parse_args(cli_args)
    wants_toggle = args.command == "toggle" or args.toggle

    if args.command == "install-autostart":
        install_autostart()
        sys_exit(0)
        return

    if args.command == "config":
        config.init_config_dir()
        app = QApplication.instance() or QApplication(sys.argv)
        dialog = ConfigurationDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            send_ipc_command("reload", timeout_ms=200)
        sys_exit(0)
        return

    if not QCoreApplication.instance():
        _app = QCoreApplication(sys.argv)

    message = "toggle" if wants_toggle else "notify_running"
    if send_ipc_command(message, timeout_ms=500):
        sys_exit(0)
        return

    daemon_args = [sys.executable, "-m", "eloquent_notes.app"]
    if wants_toggle:
        daemon_args.append("toggle")

    launcher(sys.executable, daemon_args)


def main():
    """Main entry point for the CLI application."""
    run_cli()


if __name__ == "__main__":
    main()
