"""Host capabilities owned by ``codex-extension-api::capabilities``."""

from .agent import AgentSpawnFuture, AgentSpawner
from .events import ExtensionEventSink, NoopExtensionEventSink
from .response_items import (
    NoopResponseItemInjector,
    ResponseItemInjectionFuture,
    ResponseItemInjector,
)

__all__ = [
    "AgentSpawnFuture",
    "AgentSpawner",
    "ExtensionEventSink",
    "NoopExtensionEventSink",
    "NoopResponseItemInjector",
    "ResponseItemInjectionFuture",
    "ResponseItemInjector",
]
