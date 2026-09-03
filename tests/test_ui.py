"""Unit tests for eloquent_notes.ui module."""

import pytest
from PyQt6.QtGui import QIcon

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
