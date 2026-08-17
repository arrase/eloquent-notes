"""Unit tests for eloquent_notes.main."""

import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QDialog

from eloquent_notes import main


def test_parse_args():
    """Test argument parsing for various CLI command combinations."""
    args = main.parse_args([])
    assert args.command is None
    assert args.toggle is False

    args = main.parse_args(["install-autostart"])
    assert args.command == "install-autostart"
    assert args.toggle is False

    args = main.parse_args(["toggle"])
    assert args.command == "toggle"

    args = main.parse_args(["-t"])
    assert args.toggle is True

    args = main.parse_args(["config"])
    assert args.command == "config"


def test_send_ipc_command_success(monkeypatch):
    """Test send_ipc_command returns True when connection succeeds."""
    mock_socket = MagicMock()
    mock_socket.waitForConnected.return_value = True

    monkeypatch.setattr("eloquent_notes.main.QLocalSocket", lambda: mock_socket)

    result = main.send_ipc_command("test_cmd", timeout_ms=300)
    assert result is True
    mock_socket.connectToServer.assert_called_once_with("eloquent_notes_ipc")
    mock_socket.write.assert_called_once_with(b"test_cmd")
    mock_socket.waitForBytesWritten.assert_called_once_with(300)
    mock_socket.disconnectFromServer.assert_called_once()


def test_send_ipc_command_failure(monkeypatch):
    """Test send_ipc_command returns False when connection fails."""
    mock_socket = MagicMock()
    mock_socket.waitForConnected.return_value = False

    monkeypatch.setattr("eloquent_notes.main.QLocalSocket", lambda: mock_socket)

    result = main.send_ipc_command("test_cmd", timeout_ms=300)
    assert result is False
    mock_socket.write.assert_not_called()


def test_send_ipc_command_exception(monkeypatch):
    """Test send_ipc_command ensures disconnect is called if write raises exception."""
    mock_socket = MagicMock()
    mock_socket.waitForConnected.return_value = True
    mock_socket.write.side_effect = RuntimeError("Write error")

    monkeypatch.setattr("eloquent_notes.main.QLocalSocket", lambda: mock_socket)

    with pytest.raises(RuntimeError, match="Write error"):
        main.send_ipc_command("test_cmd", timeout_ms=300)

    mock_socket.disconnectFromServer.assert_called_once()


def test_run_cli_install_autostart(monkeypatch):
    """Test run_cli with install-autostart command."""
    mock_autostart = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.install_autostart", mock_autostart)

    main.run_cli(["install-autostart"], sys_exit=mock_exit)

    mock_autostart.assert_called_once()
    mock_exit.assert_called_once_with(0)


def test_run_cli_config_accepted(monkeypatch):
    """Test run_cli with config command when configuration dialog is accepted."""
    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
    mock_send_ipc = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.ConfigurationDialog", lambda: mock_dialog)
    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["config"], sys_exit=mock_exit)

    mock_dialog.exec.assert_called_once()
    mock_send_ipc.assert_called_once_with("reload", timeout_ms=200)
    mock_exit.assert_called_once_with(0)


def test_run_cli_config_rejected(monkeypatch):
    """Test run_cli with config command when configuration dialog is rejected."""
    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
    mock_send_ipc = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.ConfigurationDialog", lambda: mock_dialog)
    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["config"], sys_exit=mock_exit)

    mock_dialog.exec.assert_called_once()
    mock_send_ipc.assert_not_called()
    mock_exit.assert_called_once_with(0)


def test_run_cli_daemon_already_running(monkeypatch):
    """Test run_cli notifies running daemon via IPC if daemon is already active."""
    mock_send_ipc = MagicMock(return_value=True)
    mock_launcher = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["-t"], launcher=mock_launcher, sys_exit=mock_exit)

    mock_send_ipc.assert_called_once_with("toggle", timeout_ms=500)
    mock_exit.assert_called_once_with(0)
    mock_launcher.assert_not_called()


def test_run_cli_default_no_args_already_running(monkeypatch):
    """Test run_cli sends notify_running when launched with no args and daemon is running."""
    mock_send_ipc = MagicMock(return_value=True)
    mock_launcher = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli([], launcher=mock_launcher, sys_exit=mock_exit)

    mock_send_ipc.assert_called_once_with("notify_running", timeout_ms=500)
    mock_exit.assert_called_once_with(0)
    mock_launcher.assert_not_called()


def test_run_cli_launch_daemon(monkeypatch):
    """Test run_cli launches daemon process when no instance is running."""
    mock_send_ipc = MagicMock(return_value=False)
    mock_launcher = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["toggle"], launcher=mock_launcher, sys_exit=mock_exit)

    mock_send_ipc.assert_called_once_with("toggle", timeout_ms=500)
    mock_exit.assert_not_called()
    mock_launcher.assert_called_once_with(
        sys.executable,
        [sys.executable, "-m", "eloquent_notes.app", "toggle"]
    )


def test_run_cli_launch_daemon_default_no_args(monkeypatch):
    """Test run_cli launches daemon process without toggle arg when started with no args."""
    mock_send_ipc = MagicMock(return_value=False)
    mock_launcher = MagicMock()
    mock_exit = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli([], launcher=mock_launcher, sys_exit=mock_exit)

    mock_send_ipc.assert_called_once_with("notify_running", timeout_ms=500)
    mock_exit.assert_not_called()
    mock_launcher.assert_called_once_with(
        sys.executable,
        [sys.executable, "-m", "eloquent_notes.app"]
    )


def test_main_function(monkeypatch):
    """Test main entry point calls run_cli."""
    mock_run_cli = MagicMock()
    monkeypatch.setattr("eloquent_notes.main.run_cli", mock_run_cli)

    main.main()
    mock_run_cli.assert_called_once()
