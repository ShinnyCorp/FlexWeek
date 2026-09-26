"""Draw FlexWeek's icon: a rounded square in the default accent with three week blocks in white.

    QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/brand.py

Writes desktop/assets/logo.png (512 px) and desktop/assets/logo.ico (256, 128, 64, 48, 32 and 16 px)
for the Windows build. Each size is drawn at that size rather than scaled down from the largest, so
the blocks stay sharp at 16 px. Run it again after the default accent changes.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from desktop.native.look import PALETTES  # noqa: E402

ASSETS = ROOT / "desktop" / "assets"
PNG_SIZE = 512
ICO_SIZES = (256, 128, 64, 48, 32, 16)
# The accent every default light look draws in.
BLUE = PALETTES["slate"]["accent"]
# Each block as (left, top, width) in a 1-by-1 square, all the same height: three rows of a day with
# work of different lengths starting at different times.
BLOCKS = ((0.22, 0.25, 0.56), (0.22, 0.44, 0.34), (0.38, 0.63, 0.40))
BLOCK_HEIGHT = 0.13
CORNER = 0.22


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(BLUE))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * CORNER, size * CORNER)
    painter.setBrush(QColor("#ffffff"))
    height = size * BLOCK_HEIGHT
    for left, top, width in BLOCKS:
        # Whole pixels at small sizes, so an edge is white or blue rather than a grey smear.
        rect = QRectF(round(size * left), round(size * top), round(size * width), max(2, round(height)))
        painter.drawRoundedRect(rect, rect.height() * 0.3, rect.height() * 0.3)
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data.data())


def dib_bytes(image: QImage) -> bytes:
    """An icon entry as Windows reads one below 256 px: a bitmap header, the colours bottom row first,
    then a mask of zeros, since the colours carry their own transparency."""
    size = image.width()
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in reversed(range(size)):
        row = bytearray()
        for x in range(size):
            color = image.pixelColor(x, y)
            row += bytes((color.blue(), color.green(), color.red(), color.alpha()))
        rows.append(bytes(row))
    mask_row = b"\0" * (((size + 31) // 32) * 4)
    return header + b"".join(rows) + mask_row * size


def ico_bytes(images: list[QImage]) -> bytes:
    entries = [png_bytes(image) if image.width() >= 256 else dib_bytes(image) for image in images]
    offset = 6 + 16 * len(images)
    directory = struct.pack("<HHH", 0, 1, len(images))
    for image, data in zip(images, entries, strict=True):
        side = image.width() % 256
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return directory + b"".join(entries)


def main() -> int:
    application = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not draw(PNG_SIZE).save(str(ASSETS / "logo.png"), "PNG"):
        print("Could not write logo.png", file=sys.stderr)
        return 1
    (ASSETS / "logo.ico").write_bytes(ico_bytes([draw(size) for size in ICO_SIZES]))
    print(f"Wrote {ASSETS / 'logo.png'} and {ASSETS / 'logo.ico'} in {BLUE}.")
    del application
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
