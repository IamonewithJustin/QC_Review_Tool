"""Resolve writable application data directory (dev vs PyInstaller bundle)."""

from __future__ import annotations

import sys
from pathlib import Path


def get_data_dir() -> Path:
    """
    Directory for config, SQLite DB, logs, and optional base_prompt.txt.
    When frozen (PyInstaller), uses a `data` folder next to the executable.
    In development, uses `<project_root>/data`.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "data"
