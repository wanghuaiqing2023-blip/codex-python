"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pycodex.protocol import AgentStatus, BaseInstructions, ContentItem, ModelInfo, Op, RateLimitSnapshot, RateLimitWindow, ReasoningEffort, ReasoningSummary, ResponseItem, TokenUsage, TruncationPolicyConfig, UserInput
from typing import Any, Callable, Iterable

def snapshot_allows_startup(snapshot: RateLimitSnapshot, min_remaining_percent: int) -> bool:
    if snapshot.rate_limit_reached_type is not None:
        return False
    max_used_percent = 100.0 - float(_clamp(int(min_remaining_percent), 0, 100))
    return window_allows_startup(snapshot.primary, max_used_percent) and window_allows_startup(snapshot.secondary, max_used_percent)


def window_allows_startup(window: RateLimitWindow | None, max_used_percent: float) -> bool:
    if window is None:
        return True
    return float(window.used_percent) <= float(max_used_percent)


async def rate_limits_ok(auth_manager: Any, config: Any) -> bool:
    checked = await rate_limits_check(auth_manager, config)
    return True if checked is None else bool(checked)


async def rate_limits_check(auth_manager: Any, config: Any) -> bool | None:
    auth = await _auth_manager_auth(auth_manager)
    if auth is None or not await _uses_codex_backend(auth):
        return None
    client = await _backend_client_from_auth(auth_manager, config, auth)
    if client is None:
        return None
    getter = getattr(client, 'get_rate_limits_many', None)
    if not callable(getter):
        return None
    try:
        snapshots = await _maybe_await(getter())
    except Exception:
        return None
    parsed = [_rate_limit_snapshot(snapshot) for snapshot in list(snapshots or ())]
    if not parsed:
        return None
    selected = next((snapshot for snapshot in parsed if snapshot.limit_id == CODEX_LIMIT_ID), parsed[0])
    memories_config = getattr(config, 'memories', None)
    min_remaining_percent = int(getattr(memories_config, 'min_rate_limit_remaining_percent', 0))
    return snapshot_allows_startup(selected, min_remaining_percent)


from pycodex.memories.write.guard_limits import CODEX_LIMIT_ID
from pycodex.memories.write.prompts import _clamp
from pycodex.memories.write.runtime import _auth_manager_auth
from pycodex.memories.write.runtime import _backend_client_from_auth
from pycodex.memories.write.runtime import _maybe_await
from pycodex.memories.write.runtime import _rate_limit_snapshot
from pycodex.memories.write.runtime import _uses_codex_backend
