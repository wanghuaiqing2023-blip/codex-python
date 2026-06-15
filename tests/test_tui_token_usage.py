"""Parity tests for Rust ``codex-tui::token_usage``.

Rust source: ``codex/codex-rs/tui/src/token_usage.rs``.
"""

from pycodex.tui.token_usage import BASELINE_TOKENS, TokenUsage, TokenUsageInfo, fmt


def test_token_usage_zero_and_input_accounting() -> None:
    usage = TokenUsage(input_tokens=100, cached_input_tokens=25, output_tokens=40, total_tokens=140)
    assert not usage.is_zero()
    assert usage.cached_input() == 25
    assert usage.non_cached_input() == 75
    assert usage.blended_total() == 115
    assert usage.tokens_in_context_window() == 140


def test_token_usage_clamps_negative_values_like_rust() -> None:
    usage = TokenUsage(input_tokens=10, cached_input_tokens=50, output_tokens=-5, total_tokens=0)
    assert usage.is_zero()
    assert usage.cached_input() == 50
    assert usage.non_cached_input() == 0
    assert usage.blended_total() == 0


def test_percent_of_context_window_remaining_baseline_and_clamp() -> None:
    assert TokenUsage(total_tokens=0).percent_of_context_window_remaining(BASELINE_TOKENS) == 0
    assert TokenUsage(total_tokens=BASELINE_TOKENS).percent_of_context_window_remaining(24000) == 100
    assert TokenUsage(total_tokens=18000).percent_of_context_window_remaining(24000) == 50
    assert TokenUsage(total_tokens=12001).percent_of_context_window_remaining(12003) == 67
    assert TokenUsage(total_tokens=24000).percent_of_context_window_remaining(24000) == 0
    assert TokenUsage(total_tokens=999999).percent_of_context_window_remaining(24000) == 0


def test_display_format_includes_cached_and_reasoning_when_present() -> None:
    usage = TokenUsage(
        input_tokens=12000,
        cached_input_tokens=2000,
        output_tokens=3456,
        reasoning_output_tokens=789,
        total_tokens=15456,
    )
    assert str(usage) == "Token usage: total=13,456 input=10,000 (+ 2,000 cached) output=3,456 (reasoning 789)"
    assert fmt(usage) == str(usage)


def test_display_format_omits_zero_cached_and_reasoning() -> None:
    usage = TokenUsage(input_tokens=12, cached_input_tokens=0, output_tokens=3, reasoning_output_tokens=0)
    assert str(usage) == "Token usage: total=15 input=12 output=3"


def test_display_format_omits_negative_reasoning_suffix() -> None:
    # Rust: Display only appends reasoning suffix when reasoning_output_tokens > 0.
    usage = TokenUsage(input_tokens=12, cached_input_tokens=0, output_tokens=3, reasoning_output_tokens=-1)
    assert str(usage) == "Token usage: total=15 input=12 output=3"


def test_display_format_uses_blended_total_but_raw_output_value() -> None:
    usage = TokenUsage(input_tokens=12, cached_input_tokens=-4, output_tokens=-3)
    assert usage.cached_input() == 0
    assert usage.blended_total() == 12
    assert str(usage) == "Token usage: total=12 input=12 output=-3"


def test_token_usage_info_defaults() -> None:
    info = TokenUsageInfo()
    assert info.total_token_usage == TokenUsage()
    assert info.last_token_usage == TokenUsage()
    assert info.model_context_window is None
