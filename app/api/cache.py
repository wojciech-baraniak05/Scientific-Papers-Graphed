from __future__ import annotations

import time
from typing import Any, Hashable

_REGISTRY: list["TTLCache"] = []


class TTLCache:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl = ttl_seconds
        self._store: dict[Hashable, tuple[Any, float]] = {}
        _REGISTRY.append(self)

    def get(self, key: Hashable) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self.ttl)

    def clear(self) -> None:
        self._store.clear()


def clear_all_caches() -> None:
    for cache in _REGISTRY:
        cache.clear()
