"""Eloquent Notes package."""

from importlib.metadata import PackageNotFoundError, version

IPC_SERVER_NAME = "eloquent_notes_ipc"

try:
    __version__ = version("eloquent-notes")
except PackageNotFoundError:
    # Running from a source checkout that was never installed.
    __version__ = "0.0.0+unknown"
