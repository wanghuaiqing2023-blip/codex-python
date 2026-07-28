"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class MemoryStartupResult:
    status: str
    memory_root: Path | None = None
    context: MemoryStartupContext | None = None


async def start_memories_startup_task(thread_manager: Any, auth_manager: Any, thread_id: Any, thread: Any, config: Any, source: Any) -> MemoryStartupResult:
    state_db_value = _thread_state_db(thread)
    skip_reason = memory_startup_skip_reason(config, source, state_db_value is not None)
    if skip_reason is not None:
        return MemoryStartupResult(skip_reason)
    context = MemoryStartupContext(thread_manager=thread_manager, auth_manager=auth_manager, thread_id=thread_id, thread=thread, config=config, source=source, state_db_value=state_db_value, counters=[], histograms=[])
    root = memory_root(_config_codex_home(config))
    root.mkdir(parents=True, exist_ok=True)
    await seed_extension_instructions(root)
    await phase1.prune(context, config)
    if not await guard.rate_limits_ok(auth_manager, config):
        context.counter('memory_startup', 1, (('status', 'skipped_rate_limit'),))
        return MemoryStartupResult('skipped_rate_limit', root, context)
    await phase1.run(context, config)
    await phase2.run(context, config)
    return MemoryStartupResult('completed', root, context)


def memory_startup_skip_reason(config: Any, source: Any, state_db_available: bool) -> str | None:
    if bool(getattr(config, 'ephemeral', False)):
        return 'skipped_ephemeral'
    if not _memory_feature_enabled(config):
        return 'skipped_feature_disabled'
    if _source_is_non_root_agent(source):
        return 'skipped_non_root_agent'
    if not state_db_available:
        return 'skipped_state_db_unavailable'
    return None


def _memory_feature_enabled(config: Any) -> bool:
    features = getattr(config, 'features', None)
    if features is None:
        return False
    enabled = getattr(features, 'enabled', None)
    if callable(enabled):
        for candidate in ('MemoryTool', 'memory_tool'):
            try:
                if bool(enabled(candidate)):
                    return True
            except (KeyError, TypeError, ValueError):
                continue
        return False
    if isinstance(features, dict):
        return bool(features.get('MemoryTool') or features.get('memory_tool'))
    if isinstance(features, (set, list, tuple, frozenset)):
        return 'MemoryTool' in features or 'memory_tool' in features
    return bool(getattr(features, 'MemoryTool', False) or getattr(features, 'memory_tool', False))


def _source_is_non_root_agent(source: Any) -> bool:
    checker = getattr(source, 'is_non_root_agent', None)
    if callable(checker):
        return bool(checker())
    kind = getattr(source, 'kind', source)
    if isinstance(kind, str):
        normalized = kind.strip().lower()
        return normalized.startswith('internal') or normalized.startswith('subagent')
    return False


from pycodex.memories.write import memory_root
from pycodex.memories.write import guard
from pycodex.memories.write import phase1
from pycodex.memories.write import phase2
from pycodex.memories.write.extensions.ad_hoc import seed_instructions as seed_extension_instructions
from pycodex.memories.write.phase1 import _thread_state_db
from pycodex.memories.write.runtime import MemoryStartupContext
from pycodex.memories.write.runtime import _config_codex_home
