"""State DB bridge boundary.

Ported from ``codex/codex-rs/core/src/state_db_bridge.rs``. The Rust module is
a thin bridge to ``codex_rollout::state_db``; this Python version preserves the
async ``init_state_db(config) -> Optional[StateDbHandle]`` shape with an
injectable initializer rather than inventing a database implementation.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


StateDbInitializer = Callable[[Any], Any | Awaitable[Any | None] | None]


@dataclass(frozen=True)
class StateDbHandle:
    inner: Any

    def __post_init__(self) -> None:
        if self.inner is None:
            raise ValueError("StateDbHandle inner value cannot be None")


async def init_state_db(
    config: Any,
    initializer: StateDbInitializer | None = None,
) -> StateDbHandle | None:
    init = initializer or _initializer_from_config(config)
    if init is None:
        return None
    result = init(config)
    if isinstance(result, Awaitable) or inspect.isawaitable(result):
        result = await result
    if result is None:
        return None
    if isinstance(result, StateDbHandle):
        return result
    return StateDbHandle(result)


def _initializer_from_config(config: Any) -> StateDbInitializer | None:
    initializer = getattr(config, "rollout_state_db_init", None)
    if callable(initializer):
        return initializer
    services = getattr(config, "services", None)
    initializer = getattr(services, "rollout_state_db_init", None)
    if callable(initializer):
        return initializer
    if isinstance(config, dict):
        initializer = config.get("rollout_state_db_init")
        if callable(initializer):
            return initializer
    return None


__all__ = [
    "StateDbHandle",
    "StateDbInitializer",
    "init_state_db",
]
