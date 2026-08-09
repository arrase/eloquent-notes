"""Unit tests for eloquent_notes.ui."""

import sys
from PIL import Image
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

import pytest

from eloquent_notes import ui


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication instance exists for QIcon testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


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
