"""Semantic port of codex-rs/tui/src/chatwidget/goal_validation.rs.

Rust implements these helpers on ``ChatWidget``. Python keeps them as
widget-like functions plus a mixin so this module owns only the objective length
validation contract, including the live-vs-queued cleanup difference.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Iterable

from pycodex.protocol import MAX_THREAD_GOAL_OBJECTIVE_CHARS

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::goal_validation",
    source="codex/codex-rs/tui/src/chatwidget/goal_validation.rs",
)

GOAL_TOO_LONG_FILE_HINT = "Put longer instructions in a file and refer to that file in the goal, for example: /goal follow the instructions in docs/goal.md."


class GoalObjectiveValidationSource(str, Enum):
    LIVE = "Live"
    QUEUED = "Queued"


def goal_objective_with_pending_pastes_is_allowed(
    widget: Any,
    args: str,
    text_elements: Iterable[Any] = (),
    expand_pending_pastes: Callable[[str, list[Any], list[Any]], tuple[str, Any]] | None = None,
) -> bool:
    bottom_pane = getattr(widget, "bottom_pane")
    pending_pastes = list(bottom_pane.composer_pending_pastes())
    if not pending_pastes:
        objective_chars = len(args.strip())
    else:
        if expand_pending_pastes is None:
            expand_pending_pastes = getattr(bottom_pane, "expand_pending_pastes", None)
        if expand_pending_pastes is None:
            raise NotImplementedError(
                "pending paste expansion requires bottom_pane.expand_pending_pastes or an explicit callback"
            )
        expanded, _ = expand_pending_pastes(args, list(text_elements), pending_pastes)
        objective_chars = len(str(expanded).strip())
    return goal_objective_char_count_is_allowed(
        widget,
        objective_chars,
        GoalObjectiveValidationSource.LIVE,
    )


def goal_objective_is_allowed(
    widget: Any,
    objective: str,
    source: GoalObjectiveValidationSource | str,
) -> bool:
    return goal_objective_char_count_is_allowed(widget, len(objective), source)


def goal_objective_char_count_is_allowed(
    widget: Any,
    actual_chars: int,
    source: GoalObjectiveValidationSource | str,
) -> bool:
    if actual_chars <= MAX_THREAD_GOAL_OBJECTIVE_CHARS:
        return True
    actual = f"{actual_chars:,}"
    limit = f"{MAX_THREAD_GOAL_OBJECTIVE_CHARS:,}"
    widget.add_error_message(
        f"Goal objective is too long: {actual} characters. Limit: {limit} characters. {GOAL_TOO_LONG_FILE_HINT}"
    )
    if _normalize_source(source) == GoalObjectiveValidationSource.LIVE:
        bottom_pane = getattr(widget, "bottom_pane")
        bottom_pane.set_composer_text("", [], [])
        bottom_pane.drain_pending_submission_state()
    return False


def _normalize_source(source: GoalObjectiveValidationSource | str) -> GoalObjectiveValidationSource:
    if isinstance(source, GoalObjectiveValidationSource):
        return source
    return GoalObjectiveValidationSource(str(source).split(".")[-1])


class GoalValidationMixin:
    """Mixin shape matching the Rust ``impl ChatWidget`` helpers."""

    def goal_objective_with_pending_pastes_is_allowed(
        self,
        args: str,
        text_elements: Iterable[Any] = (),
        expand_pending_pastes: Callable[[str, list[Any], list[Any]], tuple[str, Any]] | None = None,
    ) -> bool:
        return goal_objective_with_pending_pastes_is_allowed(
            self,
            args,
            text_elements,
            expand_pending_pastes,
        )

    def goal_objective_is_allowed(
        self,
        objective: str,
        source: GoalObjectiveValidationSource | str,
    ) -> bool:
        return goal_objective_is_allowed(self, objective, source)

    def goal_objective_char_count_is_allowed(
        self,
        actual_chars: int,
        source: GoalObjectiveValidationSource | str,
    ) -> bool:
        return goal_objective_char_count_is_allowed(self, actual_chars, source)


__all__ = [
    "GOAL_TOO_LONG_FILE_HINT",
    "GoalObjectiveValidationSource",
    "GoalValidationMixin",
    "RUST_MODULE",
    "goal_objective_char_count_is_allowed",
    "goal_objective_is_allowed",
    "goal_objective_with_pending_pastes_is_allowed",
]
