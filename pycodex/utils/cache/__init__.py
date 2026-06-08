"""Python port of ``codex-utils-cache`` public API.

Rust source:
- ``codex/codex-rs/utils/cache/src/lib.rs``
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")
R = TypeVar("R")


class BlockingLruCache(Generic[K, V]):
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be non-zero")
        self.capacity = capacity
        self._items: OrderedDict[K, V] = OrderedDict()

    @classmethod
    def new(cls, capacity: int) -> "BlockingLruCache[K, V]":
        return cls(capacity)

    @classmethod
    def try_with_capacity(cls, capacity: int) -> "BlockingLruCache[K, V] | None":
        return cls(capacity) if capacity > 0 else None

    def get_or_insert_with(self, key: K, value: Callable[[], V]) -> V:
        existing = self.get(key)
        if existing is not None:
            return existing
        created = value()
        self.insert(key, created)
        return created

    def get_or_try_insert_with(self, key: K, value: Callable[[], V]) -> V:
        existing = self.get(key)
        if existing is not None:
            return existing
        created = value()
        self.insert(key, created)
        return created

    def get(self, key: K) -> V | None:
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def insert(self, key: K, value: V) -> V | None:
        previous = self._items.pop(key, None)
        self._items[key] = value
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)
        return previous

    def remove(self, key: K) -> V | None:
        return self._items.pop(key, None)

    def clear(self) -> None:
        self._items.clear()

    def with_mut(self, callback: Callable[["BlockingLruCache[K, V]"], R]) -> R:
        return callback(self)

    def blocking_lock(self) -> "BlockingLruCache[K, V]":
        return self


def sha1_digest(data: bytes | bytearray | memoryview) -> bytes:
    return hashlib.sha1(bytes(data)).digest()


__all__ = ["BlockingLruCache", "sha1_digest"]
