from __future__ import annotations

import os
from pathlib import Path


DEFAULT_VERSION = "0.2.0"


def get_version() -> str:
    override = os.getenv("CUECARD_VERSION", "").strip()
    if override:
        return override

    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    if version_file.exists():
        file_version = version_file.read_text(encoding="utf-8").strip()
        if file_version:
            return file_version

    return DEFAULT_VERSION


__version__ = get_version()
