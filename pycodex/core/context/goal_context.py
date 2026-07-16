# Rust-coordinate re-export for codex-core::context::goal_context.
#
# Contextual fragments are aggregated in pycodex.core.context. This module
# keeps the Rust module coordinate without duplicating GoalContext.

from __future__ import annotations

from . import GoalContext

__all__ = ['GoalContext']
