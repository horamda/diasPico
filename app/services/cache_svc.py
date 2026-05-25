from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, object]] = {}


def get_or_set(key: str, factory: Callable[[], T], ttl_seconds: int = 120) -> T:
    now = time.time()
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]  # type: ignore[return-value]

    value = factory()

    with _LOCK:
        _CACHE[key] = (now + ttl_seconds, value)
    return value


def clear(prefix: str | None = None) -> None:
    with _LOCK:
        if prefix is None:
            _CACHE.clear()
            return
        for key in list(_CACHE):
            if key.startswith(prefix):
                _CACHE.pop(key, None)
