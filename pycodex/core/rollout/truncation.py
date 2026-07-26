"""Rust ``codex_core::rollout::truncation`` re-export."""

from pycodex.core.thread_rollout_truncation import (
    fork_turn_positions_in_rollout,
    initial_history_has_prior_user_turns,
    truncate_rollout_before_nth_user_message_from_start,
    truncate_rollout_to_last_n_fork_turns,
    user_message_positions_in_rollout,
)

__all__ = [
    "fork_turn_positions_in_rollout",
    "initial_history_has_prior_user_turns",
    "truncate_rollout_before_nth_user_message_from_start",
    "truncate_rollout_to_last_n_fork_turns",
    "user_message_positions_in_rollout",
]
