"""Pause-aware timeout clock."""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any


class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def cancelled(self) -> None:
        await self._event.wait()


class Stopwatch:
    def __init__(self, limit: float | None = None) -> None:
        self.limit = limit
        self._elapsed = 0.0
        self._running_since: float | None = monotonic()
        self._active_pauses = 0
        self._condition = asyncio.Condition()

    @classmethod
    def new(cls, limit: float) -> "Stopwatch":
        return cls(limit)

    @classmethod
    def unlimited(cls) -> "Stopwatch":
        return cls(None)

    def elapsed(self) -> float:
        current = self._elapsed
        if self._running_since is not None:
            current += monotonic() - self._running_since
        return current

    def cancellation_token(self) -> CancellationToken:
        token = CancellationToken()
        if self.limit is not None:
            asyncio.create_task(self._cancel_after_limit(token))
        return token

    async def pause_for(self, awaitable: Any) -> Any:
        await self._pause()
        try:
            return await awaitable
        finally:
            await self._resume()

    async def _cancel_after_limit(self, token: CancellationToken) -> None:
        assert self.limit is not None
        while not token.is_cancelled():
            async with self._condition:
                elapsed = self.elapsed()
                if elapsed >= self.limit:
                    break
                remaining = self.limit - elapsed
                if self._running_since is None:
                    await self._condition.wait()
                    continue
            try:
                await asyncio.wait_for(self._wait_for_change(), timeout=remaining)
            except TimeoutError:
                break
        token.cancel()

    async def _wait_for_change(self) -> None:
        async with self._condition:
            await self._condition.wait()

    async def _pause(self) -> None:
        async with self._condition:
            self._active_pauses += 1
            if self._active_pauses == 1 and self._running_since is not None:
                self._elapsed += monotonic() - self._running_since
                self._running_since = None
                self._condition.notify_all()

    async def _resume(self) -> None:
        async with self._condition:
            if self._active_pauses == 0:
                return
            self._active_pauses -= 1
            if self._active_pauses == 0 and self._running_since is None:
                self._running_since = monotonic()
                self._condition.notify_all()


__all__ = ["CancellationToken", "Stopwatch"]
