"""Unit tests for RecordingHUD."""

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from eloquent_notes.recording_hud import RecordingHUD


def test_recording_hud_initialization(qapp: QApplication) -> None:
    """Test that RecordingHUD initializes with proper flags, layout, and defaults."""
    del qapp
    hud = RecordingHUD()
    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:00"
    assert hud.waveform._levels == [0.0] * 10
    assert hud.btn_cancel.text() == "✕"
    assert hud.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_recording_hud_show_recording(qapp: QApplication) -> None:
    """Test show_recording resets timer and waveform and shows the widget."""
    hud = RecordingHUD()
    hud.update_timer(45.0)
    hud.update_level(0.5)
    assert hud.lbl_timer.text() == "00:45"
    assert hud.waveform._levels[-1] == 1.0

    hud.show_recording()
    qapp.processEvents()

    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:00"
    assert hud.waveform._levels == [0.0] * 10
    assert hud.isVisible()
    hud.hide()
    assert not hud.isVisible()


def test_recording_hud_update_level(qapp: QApplication) -> None:
    """Test update_level pushes normalized clamped values into the waveform."""
    hud = RecordingHUD()
    hud.show_recording()

    hud.update_level(0.05)
    assert hud.waveform._levels[-1] == 0.4
    assert len(hud.waveform._levels) == 10

    hud.update_level(0.5)
    assert hud.waveform._levels[-2:] == [0.4, 1.0]
    qapp.processEvents()
    hud.hide()


def test_recording_hud_update_timer(qapp: QApplication) -> None:
    """Test update_timer formats elapsed seconds and keeps styling intact."""
    del qapp
    hud = RecordingHUD()
    hud.show_recording()

    hud.update_timer(10.0)
    assert hud.lbl_timer.text() == "00:10"
    assert "#FFFFFF" in hud.lbl_timer.styleSheet()
    assert "#EF4444" in hud.lbl_dot.styleSheet()

    hud.update_timer(65.8)
    assert hud.lbl_timer.text() == "01:05"

    hud.update_timer(-3.0)
    assert hud.lbl_timer.text() == "00:00"

    hud.hide()


def test_recording_hud_mouse_click_and_cancel_signals(qapp: QApplication) -> None:
    """Test left-click emits clicked, right-click and cancel button emit cancelled."""
    del qapp
    hud = RecordingHUD()
    mock_clicked = MagicMock()
    mock_cancelled = MagicMock()
    hud.clicked.connect(mock_clicked)
    hud.cancelled.connect(mock_cancelled)

    # Left click triggers clicked signal
    left_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20.0, 20.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    hud.mousePressEvent(left_event)
    mock_clicked.assert_called_once()
    mock_cancelled.assert_not_called()

    # Right click triggers cancelled signal without triggering clicked
    right_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20.0, 20.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    hud.mousePressEvent(right_event)
    assert mock_clicked.call_count == 1
    mock_cancelled.assert_called_once()

    # Cancel button click triggers cancelled signal
    hud.btn_cancel.click()
    assert mock_clicked.call_count == 1
    assert mock_cancelled.call_count == 2
    hud.hide()
