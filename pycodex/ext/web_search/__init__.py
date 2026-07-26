"""Install boundary for the deferred ``codex-web-search-extension`` crate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.extension_api import ExtensionRegistryBuilder


@dataclass(frozen=True)
class WebSearchExtensionConfig:
    enabled: bool

    @classmethod
    def from_config(cls, config: Any) -> "WebSearchExtensionConfig":
        mode = _field(config, "web_search_mode", "disabled")
        mode = _field(mode, "value", mode)
        return cls(enabled=str(mode).lower() != "disabled")


class WebSearchExtension:
    def __init__(self, auth_manager: Any) -> None:
        self.auth_manager = auth_manager

    async def on_thread_start(self, input: Any) -> None:
        input.thread_store.insert(WebSearchExtensionConfig.from_config(input.config))

    def on_config_changed(
        self,
        session_store: Any,
        thread_store: Any,
        previous_config: Any,
        new_config: Any,
    ) -> None:
        del session_store, previous_config
        thread_store.insert(WebSearchExtensionConfig.from_config(new_config))

    def tools(self, session_store: Any, thread_store: Any) -> list[Any]:
        del session_store, thread_store
        return []


def install(registry: ExtensionRegistryBuilder, auth_manager: Any) -> WebSearchExtension:
    extension = WebSearchExtension(auth_manager)
    registry.thread_lifecycle_contributor(extension)
    registry.config_contributor(extension)
    registry.tool_contributor(extension)
    return extension


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = ["WebSearchExtension", "WebSearchExtensionConfig", "install"]
