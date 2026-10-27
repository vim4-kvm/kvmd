# SPDX-License-Identifier: GPL-3.0-or-later
"""Persist the shared VIM4 encoder selection across supervised restarts."""

import os
import tempfile
from pathlib import Path


CODEC_PATH = Path("/var/lib/kvmd/video-codec")
HEIGHT_PATH = Path("/var/lib/kvmd/video-output-height")
OUTPUT_HEIGHTS = (0, 480, 720, 1080, 1440, 1700, 2160)


def read_codec(default: str) -> str:
    try:
        codec = CODEC_PATH.read_text().strip()
    except FileNotFoundError:
        codec = default
    if codec not in ("h264", "h265"):
        raise ValueError("Video codec must be h264 or h265")
    return codec


def write_codec(codec: str) -> None:
    if codec not in ("h264", "h265"):
        raise ValueError("Video codec must be h264 or h265")
    _write_selection(CODEC_PATH, codec)


def read_output_height() -> int:
    try:
        height = int(HEIGHT_PATH.read_text().strip())
    except FileNotFoundError:
        return 0
    if height not in OUTPUT_HEIGHTS:
        raise ValueError("Unsupported video output height")
    return height


def write_output_height(height: int) -> None:
    if height not in OUTPUT_HEIGHTS:
        raise ValueError("Unsupported video output height")
    _write_selection(HEIGHT_PATH, str(height))


def _write_selection(path: Path, value: str) -> None:
    # Concurrent requests must never expose a partial selection to the supervisor.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        name = file.name
        try:
            file.write(value + "\n")
            file.flush()
            os.fsync(file.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
