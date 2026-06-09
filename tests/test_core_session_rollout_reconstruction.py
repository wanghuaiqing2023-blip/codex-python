import pytest

from pycodex.core.session.rollout_reconstruction import (
    reconstruct_history_from_rollout,
    reconstruct_history_from_rollout_async,
    turn_ids_are_compatible,
)
from pycodex.rollout import RolloutReconstruction


def test_turn_ids_are_compatible_matches_rust_predicate():
    # Rust source: codex-rs/core/src/session/rollout_reconstruction.rs
    # fn turn_ids_are_compatible(active_turn_id, item_turn_id)
    assert turn_ids_are_compatible(None, None) is True
    assert turn_ids_are_compatible(None, "turn-1") is True
    assert turn_ids_are_compatible("turn-1", None) is True
    assert turn_ids_are_compatible("turn-1", "turn-1") is True
    assert turn_ids_are_compatible("turn-1", "turn-2") is False


@pytest.mark.asyncio
async def test_reconstruct_history_from_rollout_async_matches_sync_empty_replay():
    # Rust source: Session::reconstruct_history_from_rollout returns a
    # RolloutReconstruction bundle. Python keeps both sync and async facades
    # over the same replay implementation.
    sync_result = reconstruct_history_from_rollout(None, [])
    async_result = await reconstruct_history_from_rollout_async(None, [])

    assert isinstance(sync_result, RolloutReconstruction)
    assert async_result == sync_result
    assert async_result.history == ()
    assert async_result.previous_turn_settings is None
    assert async_result.reference_context_item is None
