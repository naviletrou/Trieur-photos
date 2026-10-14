"""Miniatures des photos pour l'interface."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

from ..model import RAW_EXT, VIDEO_EXT

try:
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
except ImportError:  # pragma: no cover
    Image = None

_cache: OrderedDict[tuple[str, int], QPixmap] = OrderedDict()
CACHE_SIZE = 300


def placeholder(size: int, text: str) -> QPixmap:
    pixmap = QPixmap(size, int(size * 0.75))
    pixmap.fill(QColor("#E9EDF1"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#5F6B7A"))
    font = QFont()
    font.setPointSize(11)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
    painter.end()
    return pixmap


def thumbnail(path: Path, size: int = 320) -> QPixmap:
    key = (str(path), size)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXT:
        pixmap = placeholder(size, "▶  Vidéo")
    elif Image is None:
        pixmap = placeholder(size, "Aperçu indisponible")
    else:
        try:
            with Image.open(path) as image:
                image.draft("RGB", (size * 2, size * 2))
                image = ImageOps.exif_transpose(image)
                image.thumbnail((size, size))
                image = image.convert("RGBA")
                qimage = QImage(image.tobytes("raw", "RGBA"), image.width, image.height, QImage.Format_RGBA8888)
                pixmap = QPixmap.fromImage(qimage.copy())
        except Exception:
            pixmap = placeholder(size, "Fichier RAW" if suffix in RAW_EXT else "Aperçu indisponible")
    _cache[key] = pixmap
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return pixmap
