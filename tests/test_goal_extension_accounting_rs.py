from pycodex.ext.goal.accounting import GoalAccountingState
from pycodex.protocol import ModeKind, TokenUsage


def usage(input_tokens: int, cached: int, output: int, reasoning: int, total: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output,
        reasoning_output_tokens=reasoning,
        total_tokens=total,
    )


def test_goal_accounting_uses_turn_start_baseline_for_exact_deltas() -> None:
    # Rust: codex-rs/ext/goal/tests/accounting.rs::
    # goal_accounting_uses_turn_start_baseline_for_exact_deltas.
    state = GoalAccountingState()
    state.start_turn("turn-1", ModeKind.DEFAULT, usage(100, 10, 30, 5, 135))

    recorded = state.record_token_usage("turn-1", usage(120, 14, 42, 8, 162))

    assert recorded is not None
    assert recorded.turn_delta == 28
    assert recorded.thread_unflushed_delta == 28


def test_goal_accounting_ignores_plan_mode_turns() -> None:
    # Rust: codex-rs/ext/goal/tests/accounting.rs::goal_accounting_ignores_plan_mode_turns.
    state = GoalAccountingState()
    state.start_turn("turn-1", ModeKind.PLAN, TokenUsage())

    assert state.record_token_usage("turn-1", usage(20, 5, 8, 2, 30)) is None
