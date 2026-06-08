"""Python port of ``codex-async-utils``.

Rust source:
- ``codex/codex-rs/async-utils/src/lib.rs``
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class CancelErr(str, Enum):
    CANCELLED = "cancelled"


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait_cancelled(self) -> None:
        await self._event.wait()


async def or_cancel(awaitable: Awaitable[T], token: CancellationToken) -> T:
    if token.cancelled():
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise CancelledError(CancelErr.CANCELLED)

    value_task = asyncio.create_task(awaitable)
    cancel_task = asyncio.create_task(token.wait_cancelled())
    done, pending = await asyncio.wait(
        {value_task, cancel_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if cancel_task in done:
        value_task.cancel()
        raise CancelledError(CancelErr.CANCELLED)
    return value_task.result()


class CancelledError(Exception):
    def __init__(self, kind: CancelErr = CancelErr.CANCELLED) -> None:
        super().__init__(kind.value)
        self.kind = kind


__all__ = ["CancelErr", "CancellationToken", "CancelledError", "or_cancel"]
