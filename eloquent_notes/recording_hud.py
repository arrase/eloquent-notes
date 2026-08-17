"""Floating recording HUD overlay widget for Eloquent Notes.

Displays a modern, non-intrusive floating pill indicator with live countdown,
visual recording status, and progress bar during audio dictation.
"""

import math

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class RecordingHUD(QWidget):
    """Minimalist floating recording indicator and countdown HUD."""

    clicked = pyqtSignal()

    _TIMER_LABEL_QSS = "color: {}; font-size: 12px; font-weight: bold; font-family: monospace;"

    def _progress_bar_qss(self, chunk_color: str) -> str:
        return f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color};
                border-radius: 1px;
            }}
            """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._total_duration = 30.0
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
        header_layout.addWidget(self.lbl_dot)

        self.lbl_status = QLabel("Recording Note...")
        self.lbl_status.setStyleSheet("color: #F3F4F6; font-size: 12px; font-weight: 600;")
        header_layout.addWidget(self.lbl_status)

        header_layout.addStretch()

        self.lbl_timer = QLabel("00:30")
        self.lbl_timer.setStyleSheet(self._TIMER_LABEL_QSS.format("#FFFFFF"))
        header_layout.addWidget(self.lbl_timer)

        layout.addLayout(header_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self._progress_bar_qss("#E5E7EB"))
        layout.addWidget(self.progress_bar)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Render antialiased dark rounded pill background and subtle border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(24, 24, 27, 240))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
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

    def show_recording(self, total_duration: float) -> None:
        """Show HUD configured for recording with total duration in seconds."""
        self._total_duration = total_duration
        self.lbl_dot.setText("●")
        self.lbl_dot.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
        self.lbl_status.setText("Recording Note...")
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self._progress_bar_qss("#E5E7EB"))

        if total_duration > 0:
            secs = int(total_duration)
            self.lbl_timer.setText(f"{secs // 60:02d}:{secs % 60:02d}")
        else:
            self.lbl_timer.setText("00:00")

        self.lbl_timer.setStyleSheet(self._TIMER_LABEL_QSS.format("#FFFFFF"))
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

            secs_left = max(0, int(math.ceil(remaining_seconds)))
            self.lbl_timer.setText(f"{secs_left // 60:02d}:{secs_left % 60:02d}")

            if remaining_seconds <= 5.0:
                timer_color = "#EF4444"
                chunk_color = "#EF4444"
            elif remaining_seconds <= 10.0:
                timer_color = "#F59E0B"
                chunk_color = "#F59E0B"
            else:
                timer_color = "#FFFFFF"
                chunk_color = "#E5E7EB"

            self.lbl_timer.setStyleSheet(self._TIMER_LABEL_QSS.format(timer_color))
            self.progress_bar.setStyleSheet(self._progress_bar_qss(chunk_color))
        else:
            secs = int(elapsed_seconds)
            self.lbl_timer.setText(f"{secs // 60:02d}:{secs % 60:02d}")
            self.progress_bar.setValue(0)

    def show_processing(self) -> None:
        """Update HUD state to indicate processing."""
        self.lbl_dot.setText("⏳")
        self.lbl_dot.setStyleSheet("color: #F59E0B; font-size: 12px;")
        self.lbl_status.setText("Processing Note...")
        self.lbl_timer.setText("LLM")
        self.lbl_timer.setStyleSheet(self._TIMER_LABEL_QSS.format("#F59E0B"))
        self.progress_bar.setValue(1000)
        self.progress_bar.setStyleSheet(self._progress_bar_qss("#F59E0B"))
        self.update()

    def hide_hud(self) -> None:
        """Hide and reset HUD display."""
        self.hide()
