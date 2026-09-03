"""System tray status icons rendered dynamically with QPainter."""

import functools

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

COLOR_RED = QColor(220, 38, 38)
COLOR_ORANGE = QColor(217, 119, 6)
COLOR_GRAY = QColor(75, 85, 99)
COLOR_WHITE = QColor(255, 255, 255)


STATE_COLORS = {
    "red": COLOR_RED,
    "orange": COLOR_ORANGE,
    "gray": COLOR_GRAY,
}

_PEN_WHITE_3 = QPen(COLOR_WHITE, 3.0)
_HOURGLASS_TOP = QPolygonF([
    QPointF(24.0, 20.0), QPointF(40.0, 20.0), QPointF(32.0, 32.0),
])
_HOURGLASS_BOTTOM = QPolygonF([
    QPointF(24.0, 44.0), QPointF(32.0, 32.0), QPointF(40.0, 44.0),
])


def create_icon_pixmap(color: str) -> QPixmap:
    """Render a 64x64 status icon: colored circle with a white glyph."""
    if color not in STATE_COLORS:
        raise ValueError(f"Unknown icon status color: {color!r}")

    circle_color = STATE_COLORS[color]

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(circle_color)
    painter.drawEllipse(QRectF(4.0, 4.0, 56.0, 56.0))

    painter.setBrush(COLOR_WHITE)
    if color == "red":
        painter.drawEllipse(QRectF(22.0, 22.0, 20.0, 20.0))
    elif color == "orange":
        painter.drawPolygon(_HOURGLASS_TOP)
        painter.drawPolygon(_HOURGLASS_BOTTOM)
    elif color == "gray":
        # Microphone: capsule, cradle arc, stem and base.
        painter.drawRoundedRect(QRectF(26.0, 18.0, 12.0, 16.0), 6.0, 6.0)
        painter.setPen(_PEN_WHITE_3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(20.0, 24.0, 24.0, 14.0), 180 * 16, 180 * 16)
        painter.drawLine(QPointF(32.0, 38.0), QPointF(32.0, 46.0))
        painter.drawLine(QPointF(22.0, 46.0), QPointF(42.0, 46.0))

    painter.end()
    return pixmap


@functools.lru_cache(maxsize=4)
def get_qicon(color: str) -> QIcon:
    """Return the cached QIcon for the given state color."""
    return QIcon(create_icon_pixmap(color))
