from __future__ import annotations

import asyncio
import hashlib

from pycodex.utils.cache import BlockingLruCache, sha1_digest


def test_disabled_without_runtime() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Rust test: tests::disabled_without_runtime
    cache = BlockingLruCache.new(2)
    cache.insert("first", 1)
    assert cache.get("first") is None

    assert cache.get_or_insert_with("first", lambda: 2) == 2
    assert cache.get("first") is None

    assert cache.remove("first") is None
    cache.clear()

    result = cache.with_mut(lambda inner: (inner.insert("tmp", 3), inner.get("tmp"))[1])
    assert result == 3
    assert cache.get("tmp") is None
    assert cache.blocking_lock() is None


def test_try_with_capacity_zero_returns_none() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Contract: try_with_capacity returns None for zero capacity.
    assert BlockingLruCache.try_with_capacity(0) is None
    assert BlockingLruCache.try_with_capacity(1) is not None


def test_sha1_digest_returns_twenty_byte_digest() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Contract: sha1_digest computes the SHA-1 digest of bytes.
    assert sha1_digest(b"codex") == hashlib.sha1(b"codex").digest()
    assert len(sha1_digest(b"codex")) == 20


def test_stores_and_retrieves_values_inside_runtime() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Rust test: tests::stores_and_retrieves_values
    async def run() -> None:
        cache = BlockingLruCache.new(2)
        assert cache.get("first") is None
        assert cache.insert("first", 1) is None
        assert cache.get("first") == 1

    asyncio.run(run())


def test_evicts_least_recently_used_inside_runtime() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Rust test: tests::evicts_least_recently_used
    async def run() -> None:
        cache = BlockingLruCache.new(2)
        cache.insert("a", 1)
        cache.insert("b", 2)
        assert cache.get("a") == 1

        cache.insert("c", 3)

        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3

    asyncio.run(run())


def test_get_or_insert_helpers_inside_runtime() -> None:
    # Source: codex/codex-rs/utils/cache/src/lib.rs
    # Contract: get_or_insert_with and get_or_try_insert_with cache cloned values when runtime exists.
    async def run() -> None:
        cache = BlockingLruCache.new(2)
        calls = 0

        def make_value() -> int:
            nonlocal calls
            calls += 1
            return 10

        assert cache.get_or_insert_with("k", make_value) == 10
        assert cache.get_or_insert_with("k", make_value) == 10
        assert cache.get_or_try_insert_with("k", make_value) == 10
        assert calls == 1

    asyncio.run(run())

