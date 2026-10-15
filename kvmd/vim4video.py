# SPDX-License-Identifier: GPL-3.0-or-later
"""Persist the shared VIM4 encoder selection across supervised restarts."""

import os
import tempfile
from pathlib import Path


CODEC_PATH = Path("/var/lib/kvmd/video-codec")


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
    # Concurrent requests must never expose a partial selection to the supervisor.
    with tempfile.NamedTemporaryFile(mode="w", dir=CODEC_PATH.parent, delete=False) as file:
        name = file.name
        try:
            file.write(codec + "\n")
            file.flush()
            os.fsync(file.fileno())
            os.replace(name, CODEC_PATH)
        finally:
            if os.path.exists(name):
                os.unlink(name)
