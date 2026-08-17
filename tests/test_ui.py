"""Unit tests for eloquent_notes.ui module."""

from PIL import Image
from PyQt6.QtGui import QIcon
import pytest

from eloquent_notes import ui


@pytest.mark.parametrize("color", ["red", "orange", "gray", "unknown"])
def test_create_icon_image(color):
    """Test create_icon_image creates valid PIL images for all color options."""
    img = ui.create_icon_image(color)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"

    # Ensure non-transparent pixels exist
    assert img.getbbox() is not None


@pytest.mark.parametrize("color", ["red", "orange", "gray"])
def test_get_qicon(qapp, color):
    """Test get_qicon converts PIL images to valid Qt QIcon objects."""
    qicon = ui.get_qicon(color)
    assert isinstance(qicon, QIcon)
    assert not qicon.isNull()


def test_get_qicon_cached(qapp):
    """Test that repeated calls return the cached QIcon instance."""
    icon1 = ui.get_qicon("red")
    icon2 = ui.get_qicon("red")
    assert icon1 is icon2
