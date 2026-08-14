from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
import pytest

from eloquent_notes.recording_hud import RecordingHUD


def test_recording_hud_initialization(qapp):
    """Test that RecordingHUD initializes with proper flags, layout, and defaults."""
    hud = RecordingHUD()
    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:30"
    assert hud.progress_bar.value() == 0
    assert hud.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_recording_hud_show_recording(qapp):
    """Test show_recording resets timer and labels correctly."""
    hud = RecordingHUD()
    hud.show_recording(45.0)

    assert hud.lbl_status.text() == "Recording Note..."
    assert hud.lbl_timer.text() == "00:45"
    assert hud.progress_bar.value() == 0
    assert hud.isVisible()
    hud.hide_hud()


def test_recording_hud_show_recording_zero_duration(qapp):
    """Test show_recording handles indefinite (0s) duration."""
    hud = RecordingHUD()
    hud.show_recording(0.0)

    assert hud.lbl_timer.text() == "00:00"
    assert hud.progress_bar.value() == 0
    hud.hide_hud()


def test_recording_hud_update_progress(qapp):
    """Test update_progress updates progress value, timer label, and color schemes."""
    hud = RecordingHUD()
    hud.show_recording(30.0)

    # Normal state (> 10s left)
    hud.update_progress(10.0, 20.0, 30.0)
    assert hud.lbl_timer.text() == "00:20"
    assert hud.progress_bar.value() == int((10.0 / 30.0) * 1000)
    assert "#FFFFFF" in hud.lbl_timer.styleSheet()
    assert "#E5E7EB" in hud.progress_bar.styleSheet()
    assert "#EF4444" in hud.lbl_dot.styleSheet()

    # Warning state (<= 10s left)
    hud.update_progress(22.0, 8.0, 30.0)
    assert hud.lbl_timer.text() == "00:08"
    assert "#F59E0B" in hud.lbl_timer.styleSheet()
    assert "#F59E0B" in hud.progress_bar.styleSheet()
    assert "#EF4444" in hud.lbl_dot.styleSheet()

    # Critical alert state (<= 5s left)
    hud.update_progress(27.0, 3.0, 30.0)
    assert hud.lbl_timer.text() == "00:03"
    assert "#EF4444" in hud.lbl_timer.styleSheet()
    assert "#EF4444" in hud.progress_bar.styleSheet()
    assert "#EF4444" in hud.lbl_dot.styleSheet()

    hud.hide_hud()


def test_recording_hud_update_progress_zero_duration(qapp):
    """Test update_progress with indefinite duration (total_duration = 0)."""
    hud = RecordingHUD()
    hud.show_recording(0.0)

    hud.update_progress(15.0, 0.0, 0.0)
    assert hud.lbl_timer.text() == "00:15"
    assert hud.progress_bar.value() == 0
    hud.hide_hud()


def test_recording_hud_show_processing(qapp):
    """Test show_processing updates UI state before auto-hiding."""
    hud = RecordingHUD()
    hud.show_recording(30.0)
    hud.show_processing()

    assert hud.lbl_status.text() == "Processing Note..."
    assert hud.lbl_timer.text() == "LLM"
    assert hud.lbl_dot.text() == "⏳"
    assert hud.progress_bar.value() == 1000
    hud.hide_hud()


def test_recording_hud_mouse_click_emits_signal(qapp):
    """Test that clicking the HUD widget emits the clicked signal."""
    hud = RecordingHUD()
    mock_slot = MagicMock()
    hud.clicked.connect(mock_slot)

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(20.0, 20.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    hud.mousePressEvent(event)
    mock_slot.assert_called_once()
    hud.hide_hud()
