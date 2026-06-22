from __future__ import annotations

import asyncio

import pytest

from pycodex.async_utils import CancelErr, CancellationToken, CancelledError, or_cancel


@pytest.mark.asyncio
async def test_returns_ok_when_future_completes_first() -> None:
    # Rust: codex-async-utils/src/lib.rs test returns_ok_when_future_completes_first.
    token = CancellationToken()

    async def value() -> int:
        return 42

    result = await or_cancel(value(), token)

    assert result == 42


@pytest.mark.asyncio
async def test_returns_err_when_token_cancelled_first() -> None:
    # Rust: codex-async-utils/src/lib.rs test returns_err_when_token_cancelled_first.
    token = CancellationToken()

    async def cancel_soon() -> None:
        await asyncio.sleep(0.01)
        token.cancel()

    async def slow_value() -> int:
        await asyncio.sleep(0.1)
        return 7

    cancel_task = asyncio.create_task(cancel_soon())
    with pytest.raises(CancelledError) as excinfo:
        await or_cancel(slow_value(), token)
    await cancel_task

    assert excinfo.value.kind is CancelErr.CANCELLED


@pytest.mark.asyncio
async def test_returns_err_when_token_already_cancelled() -> None:
    # Rust: codex-async-utils/src/lib.rs test returns_err_when_token_already_cancelled.
    token = CancellationToken()
    token.cancel()

    async def value() -> int:
        await asyncio.sleep(0.05)
        return 5

    with pytest.raises(CancelledError) as excinfo:
        await or_cancel(value(), token)

    assert excinfo.value.kind is CancelErr.CANCELLED
