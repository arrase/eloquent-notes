import argparse
import os
import sys
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalSocket
from eloquent_notes.autostart import install_autostart

def main():
    parser = argparse.ArgumentParser(
        description="Eloquent Notes - Linux system tray utility for offline dictation into Obsidian."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install-autostart", "toggle"],
        metavar="command",
        help="Command to execute: 'install-autostart' (install autostart) or 'toggle' (toggle recording)."
    )
    parser.add_argument(
        "-t", "--toggle",
        action="store_true",
        help="Alias for 'toggle' command. Toggle recording on the running instance."
    )
    
    args = parser.parse_args()
    
    if args.command == "install-autostart":
        install_autostart()
        sys.exit(0)
        
    # We must instantiate QCoreApplication to use QLocalSocket
    app = QCoreApplication(sys.argv)
    
    # Check if another instance is already running
    socket = QLocalSocket()
    socket.connectToServer("eloquent_notes_ipc")
    if socket.waitForConnected(500):
        if args.command == "toggle" or args.toggle:
            socket.write(b"toggle")
            socket.waitForBytesWritten(500)
        else:
            socket.write(b"notify_running")
            socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        sys.exit(0)
        
    # Not running, start the application process.
    # We use os.execv to replace the current CLI process with the daemon process.
    # Pass along any command-line arguments to the daemon.
    daemon_args = [sys.executable, "-m", "eloquent_notes.app"]
    if args.command:
        daemon_args.append(args.command)
    if args.toggle:
        daemon_args.append("-t")
        
    os.execv(sys.executable, daemon_args)

if __name__ == "__main__":
    main()
