"""Eloquent Notes package."""

import os
from importlib.metadata import version
from pathlib import Path

__version__ = version("eloquent-notes")

IDLE = "IDLE"
RECORDING = "RECORDING"
PROCESSING = "PROCESSING"


def get_ipc_server_name() -> str:
    """Return the per-user local IPC socket path or name."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return str(Path(runtime_dir, "eloquent_notes_ipc"))
    return f"eloquent_notes_ipc_{os.getuid()}"
