import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import pytest

from eloquent_notes import logging_utils


def test_parse_log_level_valid() -> None:
    assert set(logging_utils.LOG_LEVELS) == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    assert logging_utils.parse_log_level("debug") == logging.DEBUG
    assert logging_utils.parse_log_level("INFO") == logging.INFO
    assert logging_utils.parse_log_level("Warning") == logging.WARNING


def test_parse_log_level_invalid_fails_fast() -> None:
    with pytest.raises(ValueError, match="Invalid log level"):
        logging_utils.parse_log_level("NOT_A_LEVEL")


def test_get_log_dir_custom_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_log_dir when XDG_STATE_HOME environment variable is set."""
    custom_state = str(tmp_path / "custom_state")
    monkeypatch.setenv("XDG_STATE_HOME", custom_state)

    log_dir = logging_utils.get_log_dir()
    assert log_dir == str(Path(custom_state, "eloquent-notes"))


def test_get_log_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_log_dir when XDG_STATE_HOME environment variable is unset."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    log_dir = logging_utils.get_log_dir()
    expected = str(Path("~/.local/state/eloquent-notes").expanduser())
    assert log_dir == expected


def test_setup_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test setup_logging configures console and file handlers correctly."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    # Reset logger state before test
    logger = logging.getLogger("eloquent_notes")
    logger.handlers.clear()

    returned_logger = logging_utils.setup_logging("DEBUG", max_mb=5, backup_count=3)
    assert returned_logger is logger
    assert logger.level == logging.DEBUG

    handlers = logger.handlers
    assert len(handlers) == 2

    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in handlers)
    has_file = any(isinstance(h, RotatingFileHandler) for h in handlers)

    assert has_stream
    assert has_file

    file_handler = next(h for h in handlers if isinstance(h, RotatingFileHandler))
    assert file_handler.maxBytes == 5 * 1024 * 1024
    assert file_handler.backupCount == 3

    # Test calling setup_logging again to reconfigure existing logger
    reconfigured_logger = logging_utils.setup_logging("WARNING", max_mb=10, backup_count=5)
    assert reconfigured_logger is logger
    assert logger.level == logging.WARNING
    assert file_handler.maxBytes == 10 * 1024 * 1024
    assert file_handler.backupCount == 5


def test_setup_logging_file_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test setup_logging fails fast and leaves handlers empty when file logging fails."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    logger = logging.getLogger("eloquent_notes")
    logger.handlers.clear()

    def fail_file_handler(*_args: Any, **_kwargs: Any) -> RotatingFileHandler:
        raise PermissionError("Access denied")

    monkeypatch.setattr(logging_utils, "RotatingFileHandler", fail_file_handler)

    with pytest.raises(PermissionError, match="Access denied"):
        logging_utils.setup_logging("INFO", max_mb=1, backup_count=1)

    assert logger.handlers == []


def test_get_log_file_path() -> None:
    """Test get_log_file_path returns app.log under the log directory."""
    path = logging_utils.get_log_file_path()
    assert path.endswith("app.log")
    assert "eloquent-notes" in path
