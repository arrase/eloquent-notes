"""Logging configuration for Eloquent Notes.

Sets up rotating file and console logging under the
XDG_STATE_HOME directory.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def get_log_dir():
    """Return the log directory path following XDG conventions."""
    xdg_state = (
        os.environ.get("XDG_STATE_HOME")
        or os.path.expanduser("~/.local/state")
    )
    return os.path.join(xdg_state, "eloquent-notes")


def setup_logging(log_level_str, max_mb, backup_count):
    """Configure the eloquent_notes logger with console and file handlers."""
    level = getattr(logging, log_level_str.upper(), logging.INFO)

    logger = logging.getLogger("eloquent_notes")
    logger.setLevel(level)

    if logger.handlers:
        return

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s [%(levelname)s] (%(threadName)s)"
            " %(name)s.%(funcName)s:%(lineno)d - %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "app.log")

        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=max_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(
            f"Warning: Could not initialize file logging: {e}",
            file=sys.stderr,
        )
