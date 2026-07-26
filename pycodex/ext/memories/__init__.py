"""Install boundary for the deferred ``codex-memories-extension`` crate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.extension_api import ExtensionRegistryBuilder


@dataclass(frozen=True)
class MemoriesExtensionConfig:
    enabled: bool
    dedicated_tools: bool
    codex_home: Any

    @classmethod
    def from_config(cls, config: Any) -> "MemoriesExtensionConfig":
        memories = _field(config, "memories", {})
        return cls(
            enabled=bool(_field(memories, "use_memories", False)),
            dedicated_tools=bool(_field(memories, "dedicated_tools", False)),
            codex_home=_field(config, "codex_home"),
        )


class MemoriesExtension:
    def __init__(self, metrics_client: Any = None) -> None:
        self.metrics_client = metrics_client

    async def on_thread_start(self, input: Any) -> None:
        input.thread_store.insert(MemoriesExtensionConfig.from_config(input.config))

    def on_config_changed(
        self,
        session_store: Any,
        thread_store: Any,
        previous_config: Any,
        new_config: Any,
    ) -> None:
        del session_store, previous_config
        thread_store.insert(MemoriesExtensionConfig.from_config(new_config))

    async def contribute(self, session_store: Any, thread_store: Any) -> list[Any]:
        del session_store, thread_store
        return []

    def tools(self, session_store: Any, thread_store: Any) -> list[Any]:
        del session_store, thread_store
        return []


def install(registry: ExtensionRegistryBuilder, metrics_client: Any = None) -> MemoriesExtension:
    extension = MemoriesExtension(metrics_client)
    registry.thread_lifecycle_contributor(extension)
    registry.config_contributor(extension)
    registry.prompt_contributor(extension)
    registry.tool_contributor(extension)
    return extension


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = ["MemoriesExtension", "MemoriesExtensionConfig", "install"]
