"""Host boundary for the deferred ``codex-guardian`` extension crate."""

from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable
from typing import Any

from pycodex.ext.extension_api import ExtensionRegistryBuilder
from pycodex.protocol import ThreadId


@dataclass(frozen=True)
class GuardianThreadContext:
    forked_from_thread_id: ThreadId


class GuardianExtension:
    def __init__(self, agent_spawner: Any) -> None:
        self.agent_spawner = agent_spawner

    async def spawn_subagent(self, forked_from_thread_id: Any, request: Any) -> Any:
        result = self.agent_spawner.spawn_subagent(forked_from_thread_id, request)
        return await result if isawaitable(result) else result

    async def on_thread_start(self, input: Any) -> None:
        try:
            thread_id = ThreadId.from_string(input.thread_store.level_id())
        except (TypeError, ValueError):
            return
        input.thread_store.insert(GuardianThreadContext(thread_id))


def install(registry: ExtensionRegistryBuilder, agent_spawner: Any) -> GuardianExtension:
    extension = GuardianExtension(agent_spawner)
    registry.thread_lifecycle_contributor(extension)
    return extension


__all__ = ["GuardianExtension", "GuardianThreadContext", "install"]
