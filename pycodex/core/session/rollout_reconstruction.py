"""Session rollout reconstruction aligned with ``codex-core``.

Rust keeps this behavior in ``core/src/session/rollout_reconstruction.rs``.
Python's rollout replay engine lives in :mod:`pycodex.rollout`; this module
provides the core/session coordinate and Rust-shaped entrypoint names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pycodex.protocol import RolloutItem
from pycodex.rollout import (
    PreviousTurnSettings,
    RolloutReconstruction,
    _ParsedRolloutItem,
    _reconstruct_rollout_items,
    read_model_history_from_rollout,
    read_rollout_reconstruction_from_rollout,
)


def reconstruct_history_from_rollout(
    turn_context: Any,
    rollout_items: Sequence[RolloutItem | Mapping[str, Any]],
) -> RolloutReconstruction:
    """Rebuild model-visible history and resume metadata from rollout items."""

    _ = turn_context
    parsed = tuple(_parsed_rollout_item(item) for item in rollout_items)
    return _reconstruct_rollout_items(parsed)


async def reconstruct_history_from_rollout_async(
    turn_context: Any,
    rollout_items: Sequence[RolloutItem | Mapping[str, Any]],
) -> RolloutReconstruction:
    """Async facade matching Rust's async session method boundary."""

    return reconstruct_history_from_rollout(turn_context, rollout_items)


def turn_ids_are_compatible(active_turn_id: str | None, item_turn_id: str | None) -> bool:
    """Return Rust's compatibility predicate for active replay segments."""

    return active_turn_id is None or item_turn_id is None or item_turn_id == active_turn_id


def _parsed_rollout_item(item: RolloutItem | Mapping[str, Any]) -> _ParsedRolloutItem:
    rollout_item = item if isinstance(item, RolloutItem) else RolloutItem.from_mapping(item)
    return _ParsedRolloutItem(rollout_item.type, rollout_item.payload)


__all__ = [
    "PreviousTurnSettings",
    "RolloutReconstruction",
    "read_model_history_from_rollout",
    "read_rollout_reconstruction_from_rollout",
    "reconstruct_history_from_rollout",
    "reconstruct_history_from_rollout_async",
    "turn_ids_are_compatible",
]
