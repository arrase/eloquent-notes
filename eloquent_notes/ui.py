"""System tray icon generation.

Renders colored circle icons with state indicators (microphone, recording
dot, hourglass) using Pillow and converts them to Qt QIcon objects.
"""

import functools
from io import BytesIO

from PIL import Image, ImageDraw
from PyQt6.QtGui import QIcon, QPixmap

COLOR_RED = (220, 38, 38, 255)
COLOR_ORANGE = (217, 119, 6, 255)
COLOR_GRAY = (75, 85, 99, 255)
COLOR_WHITE = (255, 255, 255, 255)


def create_icon_image(color: str) -> Image.Image:
    """Create a 64x64 RGBA icon image for the given state color."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if color == "red":
        draw.ellipse((4, 4, 60, 60), fill=COLOR_RED)
        draw.ellipse((22, 22, 42, 42), fill=COLOR_WHITE)
    elif color == "orange":
        draw.ellipse((4, 4, 60, 60), fill=COLOR_ORANGE)
        draw.polygon([(24, 20), (40, 20), (32, 32)], fill=COLOR_WHITE)
        draw.polygon([(32, 32), (24, 44), (40, 44)], fill=COLOR_WHITE)
    else:
        draw.ellipse((4, 4, 60, 60), fill=COLOR_GRAY)
        draw.rounded_rectangle((26, 18, 38, 34), radius=6, fill=COLOR_WHITE)
        draw.arc((20, 24, 44, 38), 0, 180, fill=COLOR_WHITE, width=3)
        draw.line((32, 38, 32, 46), fill=COLOR_WHITE, width=3)
        draw.line((22, 46, 42, 46), fill=COLOR_WHITE, width=3)

    return image


@functools.lru_cache(maxsize=4)
def get_qicon(color: str) -> QIcon:
    """Convert a Pillow icon image to a Qt QIcon."""
    pil_img = create_icon_image(color)
    byte_arr = BytesIO()
    pil_img.save(byte_arr, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(byte_arr.getvalue(), "PNG")
    return QIcon(pixmap)
