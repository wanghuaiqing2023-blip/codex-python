"""Extension registration from Rust ``memories/src/extension.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.ext.extension_api import ExtensionRegistryBuilder, PromptFragment
from pycodex.features import Feature

from .local import LocalMemoriesBackend
from .prompts import build_memory_tool_developer_instructions
from .tools import memory_tools


@dataclass(frozen=True)
class MemoriesExtensionConfig:
    enabled: bool
    dedicated_tools: bool
    codex_home: Path

    @classmethod
    def from_config(cls, config: Any) -> "MemoriesExtensionConfig":
        memories = _field(config, "memories", {})
        features = _field(config, "features")
        feature_enabled = bool(
            features is not None
            and callable(getattr(features, "enabled", None))
            and features.enabled(Feature.MEMORY_TOOL)
        )
        return cls(
            enabled=feature_enabled and bool(
                _field(memories, "use_memories", False)
            ),
            dedicated_tools=bool(_field(memories, "dedicated_tools", False)),
            codex_home=Path(_field(config, "codex_home")),
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

    async def contribute(
        self,
        session_store: Any,
        thread_store: Any,
    ) -> list[PromptFragment]:
        del session_store
        config = thread_store.get(MemoriesExtensionConfig)
        if config is None or not config.enabled:
            return []
        instructions = await build_memory_tool_developer_instructions(
            config.codex_home
        )
        if instructions is None:
            return []
        return [PromptFragment.developer_policy(instructions)]

    def tools(self, session_store: Any, thread_store: Any) -> list[Any]:
        del session_store
        config = thread_store.get(MemoriesExtensionConfig)
        if config is None or not config.enabled or not config.dedicated_tools:
            return []
        return memory_tools(
            LocalMemoriesBackend.from_codex_home(config.codex_home),
            self.metrics_client,
        )


def install(
    registry: ExtensionRegistryBuilder,
    metrics_client: Any = None,
) -> MemoriesExtension:
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
