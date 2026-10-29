"""Unit tests for RecordingHUD."""

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from eloquent_notes.recording_hud import RecordingHUD


def test_recording_hud_initialization(qapp):
    """Test that RecordingHUD initializes with proper flags, layout, and defaults."""
    hud = RecordingHUD()
    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:00"
    assert hud.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_recording_hud_show_recording(qapp):
    """Test show_recording resets timer and shows the widget."""
    hud = RecordingHUD()
    hud.update_timer(45.0)
    assert hud.lbl_timer.text() == "00:45"

    hud.show_recording()
    qapp.processEvents()

    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:00"
    assert hud.isVisible()
    hud.hide()
    assert not hud.isVisible()


def test_recording_hud_update_timer(qapp):
    """Test update_timer formats elapsed seconds and keeps styling intact."""
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


def test_recording_hud_mouse_click_emits_signal(qapp):
    """Test that left clicking the HUD widget emits the clicked signal."""
    hud = RecordingHUD()
    mock_slot = MagicMock()
    hud.clicked.connect(mock_slot)

    # Left click triggers signal
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20.0, 20.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    hud.mousePressEvent(event)
    mock_slot.assert_called_once()

    # Right click does not trigger signal
    right_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20.0, 20.0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    hud.mousePressEvent(right_event)
    assert mock_slot.call_count == 1
    hud.hide()
