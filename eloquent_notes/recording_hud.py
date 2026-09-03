"""Floating recording HUD overlay widget for Eloquent Notes.

Displays a modern, non-intrusive floating pill indicator with live countdown,
visual recording status, and progress bar during audio dictation.
"""

from __future__ import annotations

import math
from typing import ClassVar

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

_BG_COLOR = QColor(24, 24, 27, 240)
_BORDER_PEN = QPen(QColor(255, 255, 255, 38), 1.0)
_TIMER_LABEL_QSS = "color: {}; font-size: 12px; font-weight: bold; font-family: monospace;"
_PROGRESS_BAR_QSS = (
    "QProgressBar {{ background-color: rgba(255, 255, 255, 0.15); border: none; border-radius: 1px; }}"
    "QProgressBar::chunk {{ background-color: {}; border-radius: 1px; }}"
)


def _format_time(seconds: float) -> str:
    secs = max(0, int(seconds))
    return f"{secs // 60:02d}:{secs % 60:02d}"


class RecordingHUD(QWidget):
    """Minimalist floating recording indicator and countdown HUD."""

    clicked = pyqtSignal()

    # Urgency tiers: (timer label color, progress chunk color).
    _TIERS: ClassVar[dict[str, tuple[str, str]]] = {
        "normal": ("#FFFFFF", "#E5E7EB"),
        "warning": ("#F59E0B", "#F59E0B"),
        "critical": ("#EF4444", "#EF4444"),
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._style_tier = None
        self._init_window()
        self._init_ui()

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Recording in progress — click to stop and process note")
        self.setFixedSize(260, 52)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(5)

        # Header row: Dot + Status + Spacer + Timer
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_dot = QLabel("●")
        self.lbl_dot.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
        self.lbl_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(self.lbl_dot)

        self.lbl_status = QLabel("Recording Note...")
        self.lbl_status.setStyleSheet("color: #F3F4F6; font-size: 12px; font-weight: 600;")
        self.lbl_status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(self.lbl_status)

        header_layout.addStretch()

        self.lbl_timer = QLabel("00:30")
        self.lbl_timer.setStyleSheet(_TIMER_LABEL_QSS.format("#FFFFFF"))
        self.lbl_timer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header_layout.addWidget(self.lbl_timer)

        layout.addLayout(header_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(_PROGRESS_BAR_QSS.format("#E5E7EB"))
        self.progress_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.progress_bar)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render antialiased dark rounded pill background and subtle border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(_BG_COLOR)
        painter.setPen(_BORDER_PEN)
        rect = QRectF(1.0, 1.0, float(self.width() - 2), float(self.height() - 2))
        painter.drawRoundedRect(rect, 16.0, 16.0)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def reposition(self) -> None:
        """Position the HUD centered at the top of the primary screen."""
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + 40
            self.move(x, y)

    def _apply_tier(self, tier: str) -> None:
        """Apply timer/progress styles for an urgency tier (skip if unchanged)."""
        if tier == self._style_tier:
            return
        self._style_tier = tier
        timer_color, chunk_color = self._TIERS[tier]
        self.lbl_timer.setStyleSheet(_TIMER_LABEL_QSS.format(timer_color))
        self.progress_bar.setStyleSheet(_PROGRESS_BAR_QSS.format(chunk_color))

    def show_recording(self, total_duration: float) -> None:
        """Show HUD configured for recording with total duration in seconds."""
        self.progress_bar.setValue(0)
        self._style_tier = None
        self._apply_tier("normal")
        self.lbl_timer.setText(_format_time(total_duration) if total_duration > 0 else "00:00")
        self.reposition()
        self.show()
        self.raise_()
        self.update()

    def update_progress(
        self,
        elapsed_seconds: float,
        remaining_seconds: float,
        total_duration: float,
    ) -> None:
        """Update countdown timer, color state, and progress bar."""
        if total_duration > 0:
            fraction = min(1.0, max(0.0, elapsed_seconds / total_duration))
            self.progress_bar.setValue(int(fraction * 1000))
            secs_left = max(0, math.ceil(remaining_seconds))
            self.lbl_timer.setText(_format_time(secs_left))

            if remaining_seconds <= 5.0:
                self._apply_tier("critical")
            elif remaining_seconds <= 10.0:
                self._apply_tier("warning")
            else:
                self._apply_tier("normal")
        else:
            self.lbl_timer.setText(_format_time(elapsed_seconds))
            self.progress_bar.setValue(0)

    def hide_hud(self) -> None:
        """Hide and reset HUD display."""
        self.hide()
