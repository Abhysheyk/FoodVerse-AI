"""Helpers that build real image bytes for upload tests."""

import io
import os
from typing import Any

from PIL import Image


def make_image(
    fmt: str = "PNG",
    size: tuple[int, int] = (32, 24),
    color: tuple[int, int, int] = (200, 40, 40),
    **save: Any,
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt, **save)
    return buf.getvalue()


def noise_png(side: int = 200) -> bytes:
    """Incompressible image, so file size is predictable (used for quota tests)."""
    img = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def jpeg_with_exif() -> bytes:
    """A JPEG carrying GPS coordinates and a rotation flag."""
    img = Image.new("RGB", (40, 20), (10, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 270 to display
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (12.0, 58.0, 0.0)
    gps[3] = "E"
    gps[4] = (77.0, 35.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def upload_files(content: bytes, name: str, mime: str) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, content, mime)}
