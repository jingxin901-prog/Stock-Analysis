"""Transparent on-disk fallback cache for current fundamental snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

_CACHE_LOCK = threading.Lock()
_CACHE_VERSION = 1


def write_fundamental_cache(ticker: str, snapshot: dict[str, Any]) -> None:
    """Atomically persist one normalized provider snapshot."""

    cache_directory = _cache_directory()
    data_path = cache_directory / f"{_cache_key(ticker)}.json"
    temporary_path: Path | None = None
    payload = {"version": _CACHE_VERSION, "ticker": ticker, "snapshot": snapshot}
    try:
        with _CACHE_LOCK:
            cache_directory.mkdir(parents=True, exist_ok=True)
            descriptor, raw_path = tempfile.mkstemp(
                prefix="quantai-", suffix=".json", dir=cache_directory
            )
            os.close(descriptor)
            temporary_path = Path(raw_path)
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary_path.replace(data_path)
    except (OSError, TypeError, ValueError):
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink()


def read_fundamental_cache(ticker: str) -> dict[str, Any] | None:
    """Return a validated cached snapshot or ``None`` for an invalid entry."""

    data_path = _cache_directory() / f"{_cache_key(ticker)}.json"
    try:
        with _CACHE_LOCK:
            payload = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if payload.get("version") != _CACHE_VERSION or payload.get("ticker") != ticker:
        return None
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("ticker") != ticker:
        return None
    retrieved_at = snapshot.get("retrieved_at_utc")
    if not isinstance(retrieved_at, str) or not retrieved_at:
        return None
    return snapshot


def _cache_directory() -> Path:
    configured_path = os.getenv("QUANTAI_FUNDAMENTAL_CACHE_DIR")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(tempfile.gettempdir()) / "quantai-fundamental-cache"


def _cache_key(ticker: str) -> str:
    return hashlib.sha256(ticker.encode("utf-8")).hexdigest()
