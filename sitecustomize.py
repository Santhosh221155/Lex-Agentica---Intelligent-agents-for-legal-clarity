"""Ensure the backend package directory is importable from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
backend_path = str(backend_dir)
if backend_dir.is_dir() and backend_path not in sys.path:
    sys.path.insert(0, backend_path)