"""TUI token usage models and display formatting.

Rust source: ``codex/codex-rs/tui/src/token_usage.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="token_usage",
    source="codex/codex-rs/tui/src/token_usage.rs",
    status="complete",
)

BASELINE_TOKENS = 12000


def _format_with_separators(value: int) -> str:
    return f"{int(value):,}"


def _rust_round(value: float) -> int:
    return int(value + 0.5) if value >= 0 else int(value - 0.5)


@dataclass(eq=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    def is_zero(self) -> bool:
        return self.total_tokens == 0

    def cached_input(self) -> int:
        return max(self.cached_input_tokens, 0)

    def non_cached_input(self) -> int:
        return max(self.input_tokens - self.cached_input(), 0)

    def blended_total(self) -> int:
        return max(self.non_cached_input() + max(self.output_tokens, 0), 0)

    def tokens_in_context_window(self) -> int:
        return self.total_tokens

    def percent_of_context_window_remaining(self, context_window: int) -> int:
        if context_window <= BASELINE_TOKENS:
            return 0
        effective_window = context_window - BASELINE_TOKENS
        used = max(self.tokens_in_context_window() - BASELINE_TOKENS, 0)
        remaining = max(effective_window - used, 0)
        percent = (remaining / effective_window) * 100.0
        return _rust_round(max(0.0, min(100.0, percent)))

    def __str__(self) -> str:
        cached = (
            f" (+ {_format_with_separators(self.cached_input())} cached)"
            if self.cached_input() > 0
            else ""
        )
        reasoning = (
            f" (reasoning {_format_with_separators(self.reasoning_output_tokens)})"
            if self.reasoning_output_tokens > 0
            else ""
        )
        return (
            f"Token usage: total={_format_with_separators(self.blended_total())} "
            f"input={_format_with_separators(self.non_cached_input())}{cached} "
            f"output={_format_with_separators(self.output_tokens)}{reasoning}"
        )


@dataclass(eq=True)
class TokenUsageInfo:
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
    last_token_usage: TokenUsage = field(default_factory=TokenUsage)
    model_context_window: int | None = None


def fmt(token_usage: TokenUsage) -> str:
    return str(token_usage)


__all__ = [
    "BASELINE_TOKENS",
    "RUST_MODULE",
    "TokenUsage",
    "TokenUsageInfo",
    "fmt",
]
