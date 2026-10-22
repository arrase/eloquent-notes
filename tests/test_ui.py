"""Unit tests for eloquent_notes.ui module."""

from unittest.mock import patch

import pytest
from PyQt6.QtGui import QColor, QIcon, QPalette

from eloquent_notes import ui


@pytest.mark.parametrize("color", ["red", "orange", "gray"])
def test_create_icon_pixmap(qapp, color):
    """Test create_icon_pixmap renders a valid opaque 64x64 icon."""
    pixmap = ui.create_icon_pixmap(color)
    assert not pixmap.isNull()
    assert pixmap.width() == 64
    assert pixmap.height() == 64

    center = pixmap.toImage().pixelColor(32, 32)
    assert center.alpha() == 255


def test_create_icon_pixmap_unknown_raises(qapp):
    """Test that create_icon_pixmap fails fast on invalid color."""
    with pytest.raises(ValueError, match="Unknown icon status color"):
        ui.create_icon_pixmap("unknown")


@pytest.mark.parametrize("color", ["red", "orange", "gray"])
def test_get_qicon(qapp, color):
    """Test get_qicon returns a valid Qt QIcon for each state color."""
    qicon = ui.get_qicon(color)
    assert isinstance(qicon, QIcon)
    assert not qicon.isNull()


def test_get_qicon_cached(qapp):
    """Test that repeated calls return the cached QIcon instance."""
    icon1 = ui.get_qicon("red")
    icon2 = ui.get_qicon("red")
    assert icon1 is icon2


def test_app_icon_pixmap_and_cached_qicon(qapp):
    """Test create_app_icon_pixmap and get_app_icon return a valid cached 64x64 icon."""
    pixmap = ui.create_app_icon_pixmap()
    assert not pixmap.isNull()
    assert pixmap.width() == 64
    assert pixmap.height() == 64
    assert pixmap.toImage().pixelColor(32, 32).alpha() == 255

    icon = ui.get_app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    assert ui.get_app_icon() is icon



def test_theme_selection_and_stylesheets(qapp):
    """Test light and dark theme detection and stylesheet builders."""
    light_palette = QPalette()
    light_palette.setColor(QPalette.ColorRole.Window, QColor("#F3F5F8"))
    with patch("eloquent_notes.ui.QGuiApplication.palette", return_value=light_palette):
        assert not ui.is_dark_theme()
        assert ui.current_theme() is ui.LIGHT_THEME

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor("#13161C"))
    with patch("eloquent_notes.ui.QGuiApplication.palette", return_value=dark_palette):
        assert ui.is_dark_theme()
        assert ui.current_theme() is ui.DARK_THEME

    assert ui.LIGHT_THEME.window in ui.window_stylesheet(ui.LIGHT_THEME)
    assert ui.DARK_THEME.window in ui.window_stylesheet(ui.DARK_THEME)
    assert ui.LIGHT_THEME.surface in ui.dialog_stylesheet(ui.LIGHT_THEME)
    assert ui.DARK_THEME.surface in ui.dialog_stylesheet(ui.DARK_THEME)
