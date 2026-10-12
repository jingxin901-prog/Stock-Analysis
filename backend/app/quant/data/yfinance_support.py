"""Shared runtime configuration for yfinance provider access."""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_CACHE_LOCK = threading.Lock()
_CACHE_CONFIGURED = False


def configure_yfinance_cache(yfinance_module: Any) -> None:
    """Point yfinance SQLite caches at an explicitly writable directory."""

    global _CACHE_CONFIGURED
    if _CACHE_CONFIGURED:
        return
    with _CACHE_LOCK:
        if _CACHE_CONFIGURED:
            return
        configured_path = os.getenv("QUANTAI_YFINANCE_CACHE_DIR")
        cache_path = (
            Path(configured_path).expanduser()
            if configured_path
            else Path(tempfile.gettempdir()) / "quantai-yfinance-cache"
        )
        cache_path.mkdir(parents=True, exist_ok=True)
        yfinance_module.set_tz_cache_location(str(cache_path))
        _CACHE_CONFIGURED = True
