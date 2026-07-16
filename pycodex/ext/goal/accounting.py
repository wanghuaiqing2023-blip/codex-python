"""Goal accounting aligned with ``codex-goal-extension::accounting``."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum

from pycodex.protocol import ModeKind, TokenUsage
from pycodex.state import ThreadGoalStatus


class BudgetLimitedGoalDisposition(str, Enum):
    KEEP_ACTIVE = "keep_active"
    CLEAR_ACTIVE = "clear_active"


@dataclass(frozen=True)
class RecordedTokenDelta:
    turn_delta: int
    thread_unflushed_delta: int


@dataclass(frozen=True)
class GoalProgressSnapshot:
    current_token_usage: TokenUsage
    expected_goal_id: str
    time_delta_seconds: int
    token_delta: int


@dataclass(frozen=True)
class IdleGoalProgressSnapshot:
    expected_goal_id: str
    time_delta_seconds: int


@dataclass
class _TurnAccounting:
    current_token_usage: TokenUsage
    last_accounted_token_usage: TokenUsage
    active_goal_id: str | None
    account_tokens: bool

    @classmethod
    def new(cls, usage: TokenUsage, account_tokens: bool) -> "_TurnAccounting":
        return cls(usage, usage, None, account_tokens)

    def token_delta(self) -> int:
        return _token_delta_since_last_accounting(
            self.last_accounted_token_usage,
            self.current_token_usage,
        )


class GoalAccountingState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current_turn_id: str | None = None
        self._turns: dict[str, _TurnAccounting] = {}
        self._wall_clock_last_accounted_at = time.monotonic()
        self._wall_clock_active_goal_id: str | None = None
        self._budget_limit_reported_goal_id: str | None = None

    def start_turn(self, turn_id: str, collaboration_mode: ModeKind, usage: TokenUsage) -> None:
        with self._lock:
            self._current_turn_id = str(turn_id)
            self._turns[str(turn_id)] = _TurnAccounting.new(
                usage,
                collaboration_mode is not ModeKind.PLAN,
            )

    def current_turn_id(self) -> str | None:
        with self._lock:
            return self._current_turn_id

    def turn_is_current_active_goal(self, turn_id: str) -> bool:
        with self._lock:
            turn = self._turns.get(turn_id)
            return (
                self._current_turn_id == turn_id
                and turn is not None
                and turn.account_tokens
                and turn.active_goal_id is not None
            )

    def record_token_usage(self, turn_id: str, usage: TokenUsage) -> RecordedTokenDelta | None:
        with self._lock:
            turn = self._turns.get(str(turn_id))
            if turn is None:
                return None
            turn.current_token_usage = usage
            if not turn.account_tokens:
                return None
            delta = turn.token_delta()
            if delta <= 0:
                return None
            thread_delta = sum(
                max(candidate.token_delta(), 0)
                for candidate in self._turns.values()
                if candidate.account_tokens
            )
            return RecordedTokenDelta(delta, thread_delta)

    def mark_turn_goal_active(self, turn_id: str, goal_id: str) -> None:
        with self._lock:
            self._reset_budget_marker_for(goal_id)
            turn = self._turns.get(turn_id)
            if turn is not None:
                turn.active_goal_id = goal_id
                if self._current_turn_id == turn_id:
                    self._mark_wall_clock_active(goal_id)

    def mark_current_turn_goal_active(self, goal_id: str) -> str | None:
        with self._lock:
            turn_id = self._current_turn_id
            if turn_id is None or turn_id not in self._turns:
                return None
            self._reset_budget_marker_for(goal_id)
            turn = self._turns[turn_id]
            turn.active_goal_id = goal_id
            turn.last_accounted_token_usage = turn.current_token_usage
            self._mark_wall_clock_active(goal_id)
            return turn_id

    def mark_idle_goal_active(self, goal_id: str) -> None:
        with self._lock:
            self._reset_budget_marker_for(goal_id)
            self._mark_wall_clock_active(goal_id)

    def clear_current_turn_goal(self) -> str | None:
        with self._lock:
            turn_id = self._current_turn_id
            if turn_id is not None and turn_id in self._turns:
                self._turns[turn_id].active_goal_id = None
            self._clear_wall_clock_active()
            self._budget_limit_reported_goal_id = None
            return turn_id

    def clear_active_goal(self) -> None:
        self.clear_current_turn_goal()

    def progress_snapshot(self, turn_id: str) -> GoalProgressSnapshot | None:
        with self._lock:
            turn = self._turns.get(turn_id)
            if turn is None or not turn.account_tokens or turn.active_goal_id is None:
                return None
            token_delta = turn.token_delta()
            time_delta = (
                self._wall_clock_delta()
                if self._wall_clock_active_goal_id == turn.active_goal_id
                else 0
            )
            if token_delta <= 0 and time_delta == 0:
                return None
            return GoalProgressSnapshot(
                turn.current_token_usage,
                turn.active_goal_id,
                time_delta,
                token_delta,
            )

    def idle_progress_snapshot(self) -> IdleGoalProgressSnapshot | None:
        with self._lock:
            if self._wall_clock_active_goal_id is None:
                return None
            delta = self._wall_clock_delta()
            if delta == 0:
                return None
            return IdleGoalProgressSnapshot(self._wall_clock_active_goal_id, delta)

    def mark_progress_accounted_for_status(
        self,
        turn_id: str,
        snapshot: GoalProgressSnapshot,
        status: ThreadGoalStatus,
        disposition: BudgetLimitedGoalDisposition,
    ) -> None:
        with self._lock:
            clear = _should_clear_active_goal(status, disposition)
            turn = self._turns.get(turn_id)
            if turn is not None:
                turn.last_accounted_token_usage = snapshot.current_token_usage
                if clear:
                    turn.active_goal_id = None
            self._mark_wall_clock_accounted(snapshot.time_delta_seconds)
            if clear:
                self._clear_wall_clock_active()
            if status is not ThreadGoalStatus.BUDGET_LIMITED:
                self._budget_limit_reported_goal_id = None

    def finish_turn(self, turn_id: str) -> None:
        with self._lock:
            self._turns.pop(turn_id, None)
            if self._current_turn_id == turn_id:
                self._current_turn_id = None

    def mark_idle_progress_accounted_for_status(
        self,
        snapshot: IdleGoalProgressSnapshot,
        status: ThreadGoalStatus,
        disposition: BudgetLimitedGoalDisposition,
    ) -> None:
        with self._lock:
            clear = _should_clear_active_goal(status, disposition)
            self._mark_wall_clock_accounted(snapshot.time_delta_seconds)
            if clear:
                self._clear_wall_clock_active()
            if status is not ThreadGoalStatus.BUDGET_LIMITED:
                self._budget_limit_reported_goal_id = None

    def reset_idle_progress_baseline_and_clear_active_goal(self) -> None:
        with self._lock:
            self._wall_clock_last_accounted_at = time.monotonic()
            self._clear_wall_clock_active()
            self._budget_limit_reported_goal_id = None

    def mark_budget_limit_reported_if_new(self, goal_id: str) -> bool:
        with self._lock:
            if self._budget_limit_reported_goal_id == goal_id:
                return False
            self._budget_limit_reported_goal_id = goal_id
            return True

    def _wall_clock_delta(self) -> int:
        return max(0, int(time.monotonic() - self._wall_clock_last_accounted_at))

    def _mark_wall_clock_accounted(self, seconds: int) -> None:
        if seconds > 0:
            self._wall_clock_last_accounted_at += seconds

    def _mark_wall_clock_active(self, goal_id: str) -> None:
        if self._wall_clock_active_goal_id != goal_id:
            self._wall_clock_last_accounted_at = time.monotonic()
            self._wall_clock_active_goal_id = goal_id

    def _clear_wall_clock_active(self) -> None:
        self._wall_clock_active_goal_id = None
        self._wall_clock_last_accounted_at = time.monotonic()

    def _reset_budget_marker_for(self, goal_id: str) -> None:
        if self._budget_limit_reported_goal_id != goal_id:
            self._budget_limit_reported_goal_id = None


def goal_token_delta_for_usage(usage: TokenUsage) -> int:
    return max(usage.input_tokens - usage.cached_input_tokens, 0) + max(usage.output_tokens, 0)


def _token_delta_since_last_accounting(last: TokenUsage, current: TokenUsage) -> int:
    return goal_token_delta_for_usage(
        TokenUsage(
            input_tokens=max(current.input_tokens - last.input_tokens, 0),
            cached_input_tokens=max(current.cached_input_tokens - last.cached_input_tokens, 0),
            output_tokens=max(current.output_tokens - last.output_tokens, 0),
            reasoning_output_tokens=max(
                current.reasoning_output_tokens - last.reasoning_output_tokens,
                0,
            ),
            total_tokens=max(current.total_tokens - last.total_tokens, 0),
        )
    )


def _should_clear_active_goal(
    status: ThreadGoalStatus,
    disposition: BudgetLimitedGoalDisposition,
) -> bool:
    if status is ThreadGoalStatus.ACTIVE:
        return False
    if status is ThreadGoalStatus.BUDGET_LIMITED:
        return disposition is BudgetLimitedGoalDisposition.CLEAR_ACTIVE
    return True


__all__ = [
    "BudgetLimitedGoalDisposition",
    "GoalAccountingState",
    "GoalProgressSnapshot",
    "IdleGoalProgressSnapshot",
    "RecordedTokenDelta",
    "goal_token_delta_for_usage",
]
