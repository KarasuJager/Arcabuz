"""Display the approved artwork without altering its source pixels or redesigning it."""

from contextlib import suppress
from importlib.resources import files

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel


def artwork():
    pixmap = QPixmap()
    # Keep the text identity usable if an installation is missing its artwork.
    with suppress(OSError):
        pixmap.loadFromData(files("fuzzrank.gui").joinpath("assets/fuzzrank-logo.png").read_bytes())
    return pixmap


def mark():
    source = artwork()
    if source.isNull():
        return source
    # Viewport onto the helmet/chart in the approved 1448x1086 composition.
    return source.copy(
        round(source.width() * 440 / 1448),
        round(source.height() * 100 / 1086),
        round(source.width() * 500 / 1448),
        round(source.height() * 540 / 1086),
    )


def icon():
    result = QIcon()
    source = mark()
    if source.isNull():
        return result
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(
            source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return result


def badge(size=88):
    widget = QLabel()
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setAccessibleName("FuzzRank guardian helmet and ranking mark")
    source = mark()
    if source.isNull():
        widget.setText("FR")
    else:
        widget.setPixmap(
            source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    widget.setFixedSize(size, size)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return widget
