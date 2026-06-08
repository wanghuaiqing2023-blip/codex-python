"""Source-verified public interface slice for ``codex-extension-api``.

Rust source:
- ``codex/codex-rs/ext/extension-api/src/lib.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pycodex.tools import *  # re-export codex-tools Python surface, matching Rust pub use.


class ExtensionEventSink(Protocol):
    async def send_event(self, event: Any) -> None: ...


class NoopExtensionEventSink:
    async def send_event(self, event: Any) -> None:
        return None


class ResponseItemInjector(Protocol):
    async def inject_response_item(self, item: Any) -> None: ...


class NoopResponseItemInjector:
    async def inject_response_item(self, item: Any) -> None:
        return None


class AgentSpawner(Protocol):
    async def spawn_agent(self, request: Any) -> Any: ...


@dataclass
class PromptFragment:
    text: str


class PromptSlot(str):
    pass


@dataclass
class ThreadStartInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadResumeInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadStopInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadIdleInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnStartInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnStopInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnAbortInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnErrorInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolStartInput:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolFinishInput:
    fields: dict[str, Any] = field(default_factory=dict)


class ToolCallSource(str):
    pass


@dataclass
class ToolCallOutcome:
    fields: dict[str, Any] = field(default_factory=dict)


class ConfigContributor:
    pass


class ContextContributor:
    pass


class TurnItemContributor:
    pass


class TurnLifecycleContributor:
    pass


class ThreadLifecycleContributor:
    pass


class ToolLifecycleContributor:
    pass


class ToolContributor:
    pass


class TokenUsageContributor:
    pass


class ApprovalReviewContributor:
    pass


@dataclass
class ExtensionData:
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtensionRegistry:
    extensions: list[Any] = field(default_factory=list)


class ExtensionRegistryBuilder:
    def __init__(self) -> None:
        self.extensions: list[Any] = []

    def build(self) -> ExtensionRegistry:
        return ExtensionRegistry(self.extensions)


def empty_extension_registry() -> ExtensionRegistry:
    return ExtensionRegistry()


AgentSpawnFuture = Any
ResponseItemInjectionFuture = Any
ToolLifecycleFuture = Any


__all__ = [name for name in globals() if not name.startswith("_")]
