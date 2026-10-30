"""Floating recording HUD overlay widget for Eloquent Notes.

Displays a modern, non-intrusive floating pill indicator with live elapsed
time and visual recording status during audio dictation.
"""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from eloquent_notes.i18n import _

_BG_COLOR = QColor(24, 24, 27, 240)
_BORDER_PEN = QPen(QColor(255, 255, 255, 38), 1.0)
_TIMER_LABEL_QSS = "color: #FFFFFF; font-size: 12px; font-weight: bold; font-family: monospace;"


def _format_time(seconds: float) -> str:
    secs = max(0, int(seconds))
    return f"{secs // 60:02d}:{secs % 60:02d}"


class RecordingHUD(QWidget):
    """Minimalist floating recording indicator and elapsed-time HUD."""

    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._init_window()
        self._init_ui()

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, on=True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, on=True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(_("Recording in progress — click to stop and process note"))
        self.setFixedSize(260, 40)

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        self.lbl_dot = QLabel("●")
        self.lbl_dot.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
        self.lbl_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=True)
        layout.addWidget(self.lbl_dot)

        self.lbl_status = QLabel(_("Recording Note..."))
        self.lbl_status.setStyleSheet("color: #F3F4F6; font-size: 12px; font-weight: 600;")
        self.lbl_status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=True)
        layout.addWidget(self.lbl_status)

        layout.addStretch()

        self.lbl_timer = QLabel("00:00")
        self.lbl_timer.setStyleSheet(_TIMER_LABEL_QSS)
        self.lbl_timer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=True)
        layout.addWidget(self.lbl_timer)

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        """Render antialiased dark rounded pill background and subtle border."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(_BG_COLOR)
        painter.setPen(_BORDER_PEN)
        rect = QRectF(1.0, 1.0, float(self.width() - 2), float(self.height() - 2))
        painter.drawRoundedRect(rect, 16.0, 16.0)

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
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

    def show_recording(self) -> None:
        """Show HUD configured for recording with elapsed time reset to zero."""
        self.update_timer(0.0)
        self.reposition()
        self.show()
        self.raise_()
        self.update()

    def update_timer(self, elapsed_seconds: float) -> None:
        """Update the elapsed recording timer display."""
        self.lbl_timer.setText(_format_time(elapsed_seconds))
