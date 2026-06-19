"""Per-connection RPC gate for ``codex-app-server/src/connection_rpc_gate.rs``."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any


class ConnectionRpcGate:
    """Gate initialized RPC handlers per app-server connection.

    Closing the gate prevents queued handlers from starting while allowing
    handlers that already entered the gate to finish.
    """

    def __init__(self) -> None:
        self._accepting = True
        self._inflight = 0
        self._condition = asyncio.Condition()

    @classmethod
    def new(cls) -> "ConnectionRpcGate":
        return cls()

    async def run(self, future: Awaitable[None] | Callable[[], Awaitable[None] | None]) -> bool:
        async with self._condition:
            if not self._accepting:
                _close_unstarted(future)
                return False
            self._inflight += 1

        try:
            result = future() if callable(future) else future
            if isawaitable(result):
                await result
            return True
        finally:
            async with self._condition:
                self._inflight -= 1
                if self._inflight == 0:
                    self._condition.notify_all()

    async def shutdown(self) -> None:
        async with self._condition:
            self._accepting = False
            while self._inflight:
                await self._condition.wait()

    async def is_accepting(self) -> bool:
        async with self._condition:
            return self._accepting

    def inflight_count(self) -> int:
        return self._inflight


def _close_unstarted(value: Any) -> None:
    close = getattr(value, "close", None)
    if callable(close):
        close()


__all__ = ["ConnectionRpcGate"]
