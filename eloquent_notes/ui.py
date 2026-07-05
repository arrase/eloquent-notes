"""System tray icon generation.

Renders colored circle icons with state indicators (microphone, recording
dot, hourglass) using Pillow and converts them to Qt QIcon objects.
"""

from io import BytesIO

from PIL import Image, ImageDraw
from PyQt6.QtGui import QIcon, QPixmap


def create_icon_image(color):
    """Create a 64x64 RGBA icon image for the given state color."""
    # Create a 64x64 transparent RGBA image
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if color == "red":
        # Draw a red circle backdrop
        draw.ellipse((4, 4, 60, 60), fill=(220, 38, 38, 255))
        # Draw a white recording dot in the center
        draw.ellipse((22, 22, 42, 42), fill=(255, 255, 255, 255))
    elif color == "orange":
        # Draw an orange circle backdrop
        draw.ellipse((4, 4, 60, 60), fill=(217, 119, 6, 255))
        # Draw a white hourglass inside
        draw.polygon([(24, 20), (40, 20), (32, 32)], fill=(255, 255, 255, 255))
        draw.polygon([(32, 32), (24, 44), (40, 44)], fill=(255, 255, 255, 255))
    else:
        # Draw a gray circle backdrop
        draw.ellipse((4, 4, 60, 60), fill=(75, 85, 99, 255))
        # Draw a white microphone inside
        draw.rounded_rectangle((26, 18, 38, 34), radius=6, fill=(255, 255, 255, 255))
        draw.arc((20, 24, 44, 38), 0, 180, fill=(255, 255, 255, 255), width=3)
        draw.line((32, 38, 32, 46), fill=(255, 255, 255, 255), width=3)
        draw.line((22, 46, 42, 46), fill=(255, 255, 255, 255), width=3)
        
    return image

def get_qicon(color):
    """Convert a Pillow icon image to a Qt QIcon."""
    pil_img = create_icon_image(color)
    byte_arr = BytesIO()
    pil_img.save(byte_arr, format='PNG')
    pixmap = QPixmap()
    pixmap.loadFromData(byte_arr.getvalue(), 'PNG')
    return QIcon(pixmap)
