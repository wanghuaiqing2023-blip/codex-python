"""Typed extension registry aligned with ``codex-extension-api::registry``."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from typing import Any

from .capabilities import ExtensionEventSink, NoopExtensionEventSink
from .state import ExtensionData


_CONTRIBUTOR_KINDS = (
    "approval_review",
    "thread_lifecycle",
    "turn_lifecycle",
    "config",
    "token_usage",
    "context",
    "tool",
    "tool_lifecycle",
    "turn_item",
)


class ExtensionRegistryBuilder:
    def __init__(self, event_sink: ExtensionEventSink | None = None) -> None:
        self._event_sink = event_sink or NoopExtensionEventSink()
        self._contributors: dict[str, list[Any]] = {kind: [] for kind in _CONTRIBUTOR_KINDS}

    @classmethod
    def new(cls) -> "ExtensionRegistryBuilder":
        return cls()

    @classmethod
    def with_event_sink(cls, event_sink: ExtensionEventSink) -> "ExtensionRegistryBuilder":
        return cls(event_sink)

    def event_sink(self) -> ExtensionEventSink:
        return self._event_sink

    def approval_review_contributor(self, contributor: Any) -> None:
        self._add("approval_review", contributor)

    def thread_lifecycle_contributor(self, contributor: Any) -> None:
        self._add("thread_lifecycle", contributor)

    def turn_lifecycle_contributor(self, contributor: Any) -> None:
        self._add("turn_lifecycle", contributor)

    def config_contributor(self, contributor: Any) -> None:
        self._add("config", contributor)

    def token_usage_contributor(self, contributor: Any) -> None:
        self._add("token_usage", contributor)

    def prompt_contributor(self, contributor: Any) -> None:
        self._add("context", contributor)

    def tool_contributor(self, contributor: Any) -> None:
        self._add("tool", contributor)

    def tool_lifecycle_contributor(self, contributor: Any) -> None:
        self._add("tool_lifecycle", contributor)

    def turn_item_contributor(self, contributor: Any) -> None:
        self._add("turn_item", contributor)

    def build(self) -> "ExtensionRegistry":
        return ExtensionRegistry(
            event_sink=self._event_sink,
            contributors={kind: tuple(values) for kind, values in self._contributors.items()},
        )

    def _add(self, kind: str, contributor: Any) -> None:
        if contributor is None:
            raise TypeError("contributor must not be None")
        self._contributors[kind].append(contributor)


class ExtensionRegistry:
    def __init__(self, *, event_sink: ExtensionEventSink, contributors: dict[str, tuple[Any, ...]]) -> None:
        self._event_sink = event_sink
        self._contributors = contributors

    def event_sink(self) -> ExtensionEventSink:
        return self._event_sink

    def thread_lifecycle_contributors(self) -> tuple[Any, ...]:
        return self._get("thread_lifecycle")

    def turn_lifecycle_contributors(self) -> tuple[Any, ...]:
        return self._get("turn_lifecycle")

    def config_contributors(self) -> tuple[Any, ...]:
        return self._get("config")

    def token_usage_contributors(self) -> tuple[Any, ...]:
        return self._get("token_usage")

    def context_contributors(self) -> tuple[Any, ...]:
        return self._get("context")

    def tool_contributors(self) -> tuple[Any, ...]:
        return self._get("tool")

    def tool_lifecycle_contributors(self) -> tuple[Any, ...]:
        return self._get("tool_lifecycle")

    def turn_item_contributors(self) -> tuple[Any, ...]:
        return self._get("turn_item")

    async def approval_review(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        prompt: str,
    ) -> Any | None:
        for contributor in self._get("approval_review"):
            result = contributor.contribute(session_store, thread_store, prompt)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                return result
        return None

    def _get(self, kind: str) -> tuple[Any, ...]:
        values: Iterable[Any] = self._contributors.get(kind, ())
        return tuple(values)


def empty_extension_registry() -> ExtensionRegistry:
    return ExtensionRegistryBuilder.new().build()


__all__ = ["ExtensionRegistry", "ExtensionRegistryBuilder", "empty_extension_registry"]
