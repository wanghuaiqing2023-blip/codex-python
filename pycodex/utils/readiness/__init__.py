"""Readiness flag with token-based authorization and async waiting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

LOCK_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True)
class Token:
    value: int


class ReadinessError(Exception):
    pass


class TokenLockFailed(ReadinessError):
    def __init__(self) -> None:
        super().__init__("Failed to acquire readiness token lock")


class FlagAlreadyReady(ReadinessError):
    def __init__(self) -> None:
        super().__init__("Flag is already ready. Impossible to subscribe")


class ReadinessFlag:
    def __init__(self) -> None:
        self._ready = False
        self._next_id = 1
        self._tokens: set[Token] = set()
        self._lock = asyncio.Lock()
        self._event = asyncio.Event()

    def is_ready(self) -> bool:
        if self._ready:
            return True
        if not self._lock.locked() and not self._tokens:
            self._ready = True
            self._event.set()
            return True
        return self._ready

    async def subscribe(self) -> Token:
        if self._ready:
            raise FlagAlreadyReady()
        async with await self._lock_with_timeout():
            if self._ready:
                raise FlagAlreadyReady()
            while True:
                token = Token(self._next_id)
                self._next_id = _i32_wrap(self._next_id + 1)
                if token.value != 0 and token not in self._tokens:
                    self._tokens.add(token)
                    return token

    async def mark_ready(self, token: Token) -> bool:
        if self._ready or token.value == 0:
            return False
        async with await self._lock_with_timeout():
            if token not in self._tokens:
                return False
            self._tokens.remove(token)
            self._ready = True
            self._tokens.clear()
            self._event.set()
            return True

    async def wait_ready(self) -> None:
        if self.is_ready():
            return
        await self._event.wait()

    async def _lock_with_timeout(self) -> "_ReadinessLockGuard":
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=LOCK_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise TokenLockFailed() from exc
        return _ReadinessLockGuard(self._lock)

    def __repr__(self) -> str:
        return f"ReadinessFlag(ready={self._ready!r})"


class _ReadinessLockGuard:
    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._lock.release()


def _i32_wrap(value: int) -> int:
    value = ((value + 2**31) % 2**32) - 2**31
    return value


__all__ = [
    "FlagAlreadyReady",
    "LOCK_TIMEOUT_SECONDS",
    "ReadinessError",
    "ReadinessFlag",
    "Token",
    "TokenLockFailed",
]
