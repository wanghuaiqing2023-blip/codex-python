"""Typed extension-owned state aligned with ``codex-extension-api::state``."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any, TypeVar


T = TypeVar("T")


class ExtensionData:
    """Host-owned, type-keyed extension data for one runtime scope."""

    def __init__(self, level_id: str) -> None:
        if not isinstance(level_id, str):
            raise TypeError("level_id must be a string")
        self._level_id = level_id
        self._entries: dict[type[Any], Any] = {}
        self._lock = RLock()

    def level_id(self) -> str:
        return self._level_id

    def get(self, value_type: type[T]) -> T | None:
        _require_type(value_type)
        with self._lock:
            value = self._entries.get(value_type)
        return value

    def get_or_init(self, value_type: type[T], init: Callable[[], T]) -> T:
        _require_type(value_type)
        if not callable(init):
            raise TypeError("init must be callable")
        with self._lock:
            if value_type not in self._entries:
                value = init()
                if not isinstance(value, value_type):
                    raise TypeError("initializer returned an incompatible value")
                self._entries[value_type] = value
            return self._entries[value_type]

    def insert(self, value: T) -> T | None:
        value_type = type(value)
        with self._lock:
            previous = self._entries.get(value_type)
            self._entries[value_type] = value
        return previous

    def remove(self, value_type: type[T]) -> T | None:
        _require_type(value_type)
        with self._lock:
            return self._entries.pop(value_type, None)


def _require_type(value_type: type[Any]) -> None:
    if not isinstance(value_type, type):
        raise TypeError("value_type must be a type")


__all__ = ["ExtensionData"]
