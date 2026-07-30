"""Response injection owned by ``codex-extension-api::capabilities::response_items``."""

from __future__ import annotations

from typing import Any, Awaitable, Protocol


ResponseItemInjectionFuture = Awaitable[None | list[Any]]


class ResponseItemInjector(Protocol):
    def inject_response_items(self, items: list[Any]) -> ResponseItemInjectionFuture: ...


class NoopResponseItemInjector:
    async def inject_response_items(self, items: list[Any]) -> list[Any]:
        return items


__all__ = [
    "NoopResponseItemInjector",
    "ResponseItemInjectionFuture",
    "ResponseItemInjector",
]
