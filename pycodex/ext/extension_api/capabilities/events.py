"""Event sink owned by ``codex-extension-api::capabilities::events``."""

from __future__ import annotations

from typing import Any, Protocol


class ExtensionEventSink(Protocol):
    def emit(self, event: Any) -> None: ...


class NoopExtensionEventSink:
    def emit(self, event: Any) -> None:
        del event


__all__ = ["ExtensionEventSink", "NoopExtensionEventSink"]
