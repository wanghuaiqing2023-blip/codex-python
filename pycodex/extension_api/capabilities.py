"""Host capabilities aligned with ``codex-extension-api::capabilities``."""

from __future__ import annotations

from typing import Any, Protocol


class ExtensionEventSink(Protocol):
    def emit(self, event: Any) -> None: ...


class NoopExtensionEventSink:
    def emit(self, event: Any) -> None:
        return None

    async def send_event(self, event: Any) -> None:
        self.emit(event)


class ResponseItemInjector(Protocol):
    async def inject_response_items(self, items: list[Any]) -> None | list[Any]: ...


class NoopResponseItemInjector:
    async def inject_response_items(self, items: list[Any]) -> list[Any]:
        return items

    async def inject_response_item(self, item: Any) -> Any:
        remaining = await self.inject_response_items([item])
        return remaining[0]


class AgentSpawner(Protocol):
    async def spawn_subagent(self, forked_from_thread_id: Any, request: Any) -> Any: ...


AgentSpawnFuture = Any
ResponseItemInjectionFuture = Any


__all__ = [
    "AgentSpawnFuture",
    "AgentSpawner",
    "ExtensionEventSink",
    "NoopExtensionEventSink",
    "NoopResponseItemInjector",
    "ResponseItemInjectionFuture",
    "ResponseItemInjector",
]
