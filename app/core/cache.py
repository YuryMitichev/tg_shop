import time
from typing import Any


class TTLCache:
    """Простой in-memory кэш с TTL (без внешних зависимостей)."""

    def __init__(self, ttl: float = 30.0) -> None:
        self._ttl = ttl
        self._store: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> tuple[bool, Any]:
        entry = self._store.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            self._store.pop(key, None)
            return False, None
        return True, value

    def set(self, key: Any, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: Any) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
