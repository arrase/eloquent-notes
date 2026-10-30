"""Unit tests for eloquent_notes.main."""

import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QDialog

from eloquent_notes import __version__, main


def test_version_flag_prints_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    """The --version flag reports the installed distribution version."""
    with pytest.raises(SystemExit) as exc_info:
        main.parse_args(["--version"])

    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_parse_args() -> None:
    """Test argument parsing for various CLI command combinations."""
    args = main.parse_args([])
    assert args.command is None
    assert args.toggle is False

    args = main.parse_args(["install-autostart"])
    assert args.command == "install-autostart"
    assert args.toggle is False

    args = main.parse_args(["toggle"])
    assert args.command == "toggle"

    args = main.parse_args(["open"])
    assert args.command == "open"

    args = main.parse_args(["-t"])
    assert args.toggle is True

    args = main.parse_args(["config"])
    assert args.command == "config"


def test_send_ipc_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_send_ipc_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test send_ipc_command returns False when connection fails."""
    mock_socket = MagicMock()
    mock_socket.waitForConnected.return_value = False

    monkeypatch.setattr("eloquent_notes.main.QLocalSocket", lambda: mock_socket)

    result = main.send_ipc_command("test_cmd", timeout_ms=300)
    assert result is False
    mock_socket.write.assert_not_called()


def test_send_ipc_command_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test send_ipc_command ensures disconnect is called if write raises exception."""
    mock_socket = MagicMock()
    mock_socket.waitForConnected.return_value = True
    mock_socket.write.side_effect = RuntimeError("Write error")

    monkeypatch.setattr("eloquent_notes.main.QLocalSocket", lambda: mock_socket)

    with pytest.raises(RuntimeError, match="Write error"):
        main.send_ipc_command("test_cmd", timeout_ms=300)

    mock_socket.disconnectFromServer.assert_called_once()


def test_run_cli_install_autostart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_cli with install-autostart command."""
    mock_autostart = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.install_autostart", mock_autostart)

    main.run_cli(["install-autostart"])

    mock_autostart.assert_called_once()


def test_run_cli_config_accepted(monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
    """Test run_cli with config command when configuration dialog is accepted."""
    del qapp
    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
    mock_send_ipc = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.ConfigurationDialog", lambda: mock_dialog)
    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["config"])

    mock_dialog.exec.assert_called_once()
    mock_send_ipc.assert_called_once_with("reload", timeout_ms=200)


def test_run_cli_config_rejected(monkeypatch: pytest.MonkeyPatch, qapp: QApplication) -> None:
    """Test run_cli with config command when configuration dialog is rejected."""
    del qapp
    mock_dialog = MagicMock()
    mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
    mock_send_ipc = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.ConfigurationDialog", lambda: mock_dialog)
    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["config"])

    mock_dialog.exec.assert_called_once()
    mock_send_ipc.assert_not_called()


def test_run_cli_daemon_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_cli notifies running daemon via IPC if daemon is already active."""
    created_apps = []

    def fake_core_app(_argv: list[str]) -> MagicMock:
        app = MagicMock()
        created_apps.append(app)
        return app

    mock_core_app_cls = MagicMock(side_effect=fake_core_app)
    mock_core_app_cls.instance.return_value = None

    def check_app_alive(_cmd: str) -> bool:
        assert len(created_apps) == 1
        assert sys.getrefcount(created_apps[0]) > 2
        return True

    mock_send_ipc = MagicMock(side_effect=check_app_alive)
    mock_launcher = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.QCoreApplication", mock_core_app_cls)
    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["-t"], launcher=mock_launcher)

    mock_send_ipc.assert_called_once_with("toggle")
    mock_launcher.assert_not_called()


def test_run_cli_default_no_args_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_cli asks the running daemon to open the notes window when launched with no args."""
    mock_send_ipc = MagicMock(return_value=True)
    mock_launcher = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli([], launcher=mock_launcher)

    mock_send_ipc.assert_called_once_with("open")
    mock_launcher.assert_not_called()


def test_run_cli_launch_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_cli launches daemon process when no instance is running."""
    mock_send_ipc = MagicMock(return_value=False)
    mock_launcher = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["toggle"], launcher=mock_launcher)

    mock_send_ipc.assert_called_once_with("toggle")
    mock_launcher.assert_called_once_with(sys.executable, [sys.executable, "-m", "eloquent_notes.app", "toggle"])


def test_run_cli_launch_daemon_default_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_cli launches daemon process without toggle arg when started with no args."""
    mock_send_ipc = MagicMock(return_value=False)
    mock_launcher = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli([], launcher=mock_launcher)

    mock_send_ipc.assert_called_once_with("open")
    mock_launcher.assert_called_once_with(sys.executable, [sys.executable, "-m", "eloquent_notes.app"])


def test_main_function(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main entry point calls run_cli."""
    mock_run_cli = MagicMock()
    monkeypatch.setattr("eloquent_notes.main.run_cli", mock_run_cli)

    main.main()
    mock_run_cli.assert_called_once()


def test_run_cli_open_launches_daemon_with_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 'open' starts the daemon with the notes window when no instance is running."""
    mock_send_ipc = MagicMock(return_value=False)
    mock_launcher = MagicMock()

    monkeypatch.setattr("eloquent_notes.main.send_ipc_command", mock_send_ipc)

    main.run_cli(["open"], launcher=mock_launcher)

    mock_send_ipc.assert_called_once_with("open")
    mock_launcher.assert_called_once_with(sys.executable, [sys.executable, "-m", "eloquent_notes.app", "open"])
