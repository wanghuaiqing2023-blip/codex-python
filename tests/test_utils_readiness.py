from __future__ import annotations

import asyncio

import pytest

import pycodex.utils.readiness as readiness
from pycodex.utils.readiness import FlagAlreadyReady, ReadinessFlag, Token, TokenLockFailed


@pytest.mark.asyncio
async def test_subscribe_and_mark_ready_roundtrip() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::subscribe_and_mark_ready_roundtrip
    flag = ReadinessFlag()
    token = await flag.subscribe()

    assert await flag.mark_ready(token)
    assert flag.is_ready()


@pytest.mark.asyncio
async def test_subscribe_after_ready_returns_error() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::subscribe_after_ready_returns_none
    flag = ReadinessFlag()
    token = await flag.subscribe()
    assert await flag.mark_ready(token)

    with pytest.raises(FlagAlreadyReady):
        await flag.subscribe()


@pytest.mark.asyncio
async def test_mark_ready_rejects_unknown_token() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::mark_ready_rejects_unknown_token
    flag = ReadinessFlag()

    assert not await flag.mark_ready(Token(42))
    assert not flag._ready
    assert flag.is_ready()


@pytest.mark.asyncio
async def test_wait_ready_unblocks_after_mark_ready() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::wait_ready_unblocks_after_mark_ready
    flag = ReadinessFlag()
    token = await flag.subscribe()
    waiter = asyncio.create_task(flag.wait_ready())

    await asyncio.sleep(0)
    assert not waiter.done()
    assert await flag.mark_ready(token)
    await asyncio.wait_for(waiter, timeout=1)


@pytest.mark.asyncio
async def test_mark_ready_twice_uses_single_token() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::mark_ready_twice_uses_single_token
    flag = ReadinessFlag()
    token = await flag.subscribe()

    assert await flag.mark_ready(token)
    assert not await flag.mark_ready(token)


@pytest.mark.asyncio
async def test_is_ready_without_subscribers_marks_flag_ready() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::is_ready_without_subscribers_marks_flag_ready
    flag = ReadinessFlag()

    assert flag.is_ready()
    assert flag.is_ready()
    with pytest.raises(FlagAlreadyReady):
        await flag.subscribe()


@pytest.mark.asyncio
async def test_subscribe_returns_error_when_lock_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::subscribe_returns_error_when_lock_is_held
    flag = ReadinessFlag()
    monkeypatch.setattr(readiness, "LOCK_TIMEOUT_SECONDS", 0.01)

    await flag._lock.acquire()
    try:
        with pytest.raises(TokenLockFailed):
            await flag.subscribe()
    finally:
        flag._lock.release()


@pytest.mark.asyncio
async def test_subscribe_skips_zero_token() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::subscribe_skips_zero_token
    flag = ReadinessFlag()
    flag._next_id = 0

    token = await flag.subscribe()

    assert token != Token(0)
    assert await flag.mark_ready(token)


@pytest.mark.asyncio
async def test_subscribe_avoids_duplicate_tokens() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Rust test: tests::subscribe_avoids_duplicate_tokens
    flag = ReadinessFlag()
    token = await flag.subscribe()
    flag._next_id = token.value

    token2 = await flag.subscribe()

    assert token2 != token


def test_i32_wrap_matches_rust_atomic_i32_wraparound() -> None:
    # Source: codex/codex-rs/utils/readiness/src/lib.rs
    # Contract: next_id is an i32 token source; zero is reserved and skipped.
    assert readiness._i32_wrap(2**31) == -(2**31)
    assert readiness._i32_wrap(2**31 + 1) == -(2**31) + 1
