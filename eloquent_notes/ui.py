"""System tray status icons and light/dark theme stylesheets."""

from __future__ import annotations

import functools
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF

COLOR_RED = QColor(220, 38, 38)
COLOR_ORANGE = QColor(217, 119, 6)
COLOR_GRAY = QColor(75, 85, 99)
COLOR_WHITE = QColor(255, 255, 255)


STATE_COLORS = {
    "red": COLOR_RED,
    "orange": COLOR_ORANGE,
    "gray": COLOR_GRAY,
}

_PEN_WHITE_3 = QPen(
    COLOR_WHITE,
    3.0,
    Qt.PenStyle.SolidLine,
    Qt.PenCapStyle.RoundCap,
    Qt.PenJoinStyle.RoundJoin,
)
_HOURGLASS_TOP = QPolygonF([
    QPointF(24.0, 20.0), QPointF(40.0, 20.0), QPointF(32.0, 32.0),
])
_HOURGLASS_BOTTOM = QPolygonF([
    QPointF(24.0, 44.0), QPointF(32.0, 32.0), QPointF(40.0, 44.0),
])


@dataclass(frozen=True)
class Theme:
    """Sober, professional color palette tokens for a UI theme."""

    window: str
    surface: str
    surface_hover: str
    input_bg: str
    subtle: str
    subtle_hover: str
    border: str
    border_hover: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    tag: str
    danger_text: str
    danger_border: str
    danger_bg: str
    scrollbar: str
    scrollbar_hover: str
    type_colors: dict[str, str]


LIGHT_THEME = Theme(
    window="#F3F5F8",
    surface="#FFFFFF",
    surface_hover="#F8FAFC",
    input_bg="#FFFFFF",
    subtle="#E9EEF5",
    subtle_hover="#DCE4EE",
    border="#D5DFEB",
    border_hover="#94A3B8",
    text="#1E293B",
    text_secondary="#475569",
    text_muted="#64748B",
    accent="#2C4C7E",
    accent_hover="#213A63",
    accent_text="#FFFFFF",
    tag="#4E6582",
    danger_text="#B42318",
    danger_border="#FECDCA",
    danger_bg="#FEF3F2",
    scrollbar="#CBD5E1",
    scrollbar_hover="#94A3B8",
    type_colors={
        "note": "#52606D",
        "task": "#2B5B84",
        "idea": "#9E6316",
        "reminder": "#A8383B",
        "question": "#634A87",
        "decision": "#236B52",
    },
)

DARK_THEME = Theme(
    window="#13161C",
    surface="#1B2028",
    surface_hover="#212731",
    input_bg="#151921",
    subtle="#232934",
    subtle_hover="#2D3543",
    border="#2A313E",
    border_hover="#475569",
    text="#E2E8F0",
    text_secondary="#94A3B8",
    text_muted="#64748B",
    accent="#3B639C",
    accent_hover="#4A74B0",
    accent_text="#F8FAFC",
    tag="#7E95B4",
    danger_text="#F07167",
    danger_border="#692726",
    danger_bg="#2C1A1D",
    scrollbar="#2E3646",
    scrollbar_hover="#475569",
    type_colors={
        "note": "#94A3B8",
        "task": "#6FA1D2",
        "idea": "#D49B4B",
        "reminder": "#D67477",
        "question": "#A58AD1",
        "decision": "#5EAE92",
    },
)


def is_dark_theme() -> bool:
    """Return True when the application palette has a dark window background."""
    return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128


def current_theme() -> Theme:
    """Return the active Theme for the current application palette."""
    return DARK_THEME if is_dark_theme() else LIGHT_THEME


def _common_controls_qss(t: Theme) -> str:
    return f"""
    QTextEdit, QPlainTextEdit, QListWidget {{
        background-color: {t.input_bg};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: 6px;
        padding: 6px 10px;
        selection-background-color: {t.accent};
        selection-color: {t.accent_text};
    }}
    QTextEdit:focus {{
        border: 1px solid {t.accent};
    }}
    QTextEdit:disabled {{
        background-color: {t.window};
        color: {t.text_muted};
    }}
    QPushButton {{
        background-color: {t.subtle};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: 6px;
        padding: 5px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {t.subtle_hover};
        border-color: {t.border_hover};
    }}
    QPushButton:pressed {{
        background-color: {t.border};
    }}
    QPushButton:disabled {{
        background-color: {t.window};
        color: {t.text_muted};
        border-color: {t.border};
    }}
    QPushButton#btnSave {{
        background-color: {t.accent};
        color: {t.accent_text};
        border: 1px solid {t.accent};
        font-weight: 600;
        padding: 5px 18px;
    }}
    QPushButton#btnSave:hover {{
        background-color: {t.accent_hover};
        border-color: {t.accent_hover};
    }}
    QPushButton#dangerButton:hover {{
        background-color: {t.danger_bg};
        color: {t.danger_text};
        border-color: {t.danger_border};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 2px 4px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {t.scrollbar};
        min-height: 28px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t.scrollbar_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0px 4px 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {t.scrollbar};
        min-width: 28px;
        border-radius: 3px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {t.scrollbar_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    """


def window_stylesheet(t: Theme) -> str:
    """Build the QSS stylesheet for MainWindow using the given theme."""
    return _common_controls_qss(t) + f"""
    QMainWindow, QStackedWidget, QWidget#timelinePage, QWidget#readerPage, QWidget#columnContainer {{
        background-color: {t.window};
        color: {t.text};
    }}
    QScrollArea {{
        border: none;
        border-top: 1px solid {t.border};
        background: transparent;
    }}
    QLabel {{
        color: {t.text};
        background: transparent;
    }}
    QLabel#appTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {t.text};
    }}
    QLabel#mutedLabel {{
        color: {t.text_muted};
        font-size: 12px;
    }}
    QLabel#dayHeader {{
        font-size: 11px;
        font-weight: 700;
        color: {t.text_muted};
        padding-top: 6px;
        padding-bottom: 0px;
    }}
    QLineEdit#search {{
        padding: 9px 14px;
        border: 1px solid {t.border};
        border-radius: 8px;
        background-color: {t.input_bg};
        color: {t.text};
        font-size: 13px;
        selection-background-color: {t.accent};
        selection-color: {t.accent_text};
    }}
    QLineEdit#search:hover {{
        border-color: {t.border_hover};
    }}
    QLineEdit#search:focus {{
        border: 1px solid {t.accent};
    }}
    QPushButton#chip {{
        padding: 5px 13px;
        border: 1px solid {t.border};
        border-radius: 13px;
        background-color: {t.surface};
        color: {t.text_secondary};
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton#chip:hover {{
        background-color: {t.subtle};
        color: {t.text};
        border-color: {t.border_hover};
    }}
    QPushButton#chip:checked {{
        background-color: {t.accent};
        color: {t.accent_text};
        border-color: {t.accent};
        font-weight: 600;
    }}
    QFrame#card {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 10px;
    }}
    QFrame#card:hover {{
        background-color: {t.surface_hover};
        border-color: {t.border_hover};
    }}
    QLabel#cardTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {t.text};
    }}
    QLabel#cardPreview {{
        font-size: 13px;
        color: {t.text_secondary};
    }}
    QLabel#cardTags {{
        font-size: 12px;
        color: {t.tag};
        padding-top: 2px;
    }}
    QFrame#readerCard {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 12px;
    }}
    QLineEdit#titleEdit {{
        font-size: 22px;
        font-weight: 700;
        color: {t.text};
        border: none;
        background: transparent;
        padding: 2px 0px;
        selection-background-color: {t.accent};
        selection-color: {t.accent_text};
    }}
    QLineEdit#titleEdit:hover, QLineEdit#titleEdit:focus,
    QLineEdit#tagsEdit:hover, QLineEdit#tagsEdit:focus,
    QPlainTextEdit#bodyEdit:focus {{
        border: none;
    }}
    QLineEdit#tagsEdit {{
        font-size: 13px;
        color: {t.text_secondary};
        border: none;
        background: transparent;
        padding: 2px 0px;
        selection-background-color: {t.accent};
        selection-color: {t.accent_text};
    }}
    QPlainTextEdit#bodyEdit {{
        font-size: 14px;
        color: {t.text};
        border: none;
        background: transparent;
        padding: 4px 0px;
    }}
    QFrame#separator {{
        border: none;
        background-color: {t.border};
    }}
    """


def dialog_stylesheet(t: Theme) -> str:
    """Build the QSS stylesheet for ConfigurationDialog using the given theme."""
    return _common_controls_qss(t) + f"""
    QDialog {{
        background-color: {t.window};
        color: {t.text};
    }}
    QLabel {{
        background: transparent;
        color: {t.text};
    }}
    QLabel#statusHint {{
        color: {t.text_muted};
        font-size: 12px;
    }}
    QTabWidget::pane {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 8px;
        border-top-left-radius: 0px;
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {t.subtle};
        color: {t.text_secondary};
        border: 1px solid {t.border};
        border-bottom: none;
        padding: 8px 16px;
        margin-right: 4px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        background-color: {t.subtle_hover};
        color: {t.text};
    }}
    QTabBar::tab:selected {{
        background-color: {t.surface};
        color: {t.text};
        font-weight: 600;
        border-top: 2px solid {t.accent};
        border-bottom: 1px solid {t.surface};
    }}
    QGroupBox {{
        background-color: transparent;
        border: 1px solid {t.border};
        border-radius: 8px;
        margin-top: 12px;
        padding: 14px 12px 12px 12px;
        font-weight: 600;
        color: {t.text};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: {t.text_secondary};
    }}
    QListWidget {{
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 7px 10px;
        border-radius: 5px;
    }}
    QListWidget::item:hover {{
        background-color: {t.subtle};
    }}
    QListWidget::item:selected {{
        background-color: {t.accent};
        color: {t.accent_text};
        font-weight: 600;
    }}
    QSplitter::handle {{
        background: transparent;
        width: 12px;
    }}
    """


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
        painter.drawLine(QPointF(25.0, 46.0), QPointF(39.0, 46.0))

    painter.end()
    return pixmap


@functools.lru_cache(maxsize=4)
def get_qicon(color: str) -> QIcon:
    """Return the cached QIcon for the given state color."""
    return QIcon(create_icon_pixmap(color))
