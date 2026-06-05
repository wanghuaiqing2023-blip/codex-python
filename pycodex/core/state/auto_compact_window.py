"""Auto-compact token window state ported from Codex core.

This mirrors ``codex-rs/core/src/state/auto_compact_window.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pycodex.protocol import TokenUsage

I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
U64_MAX = (1 << 64) - 1


@dataclass(frozen=True)
class AutoCompactWindowSnapshot:
    ordinal: int
    prefill_input_tokens: int | None = None

    def __post_init__(self) -> None:
        _ensure_u64(self.ordinal, "ordinal")
        if self.prefill_input_tokens is not None:
            _ensure_non_negative_i64(self.prefill_input_tokens, "prefill_input_tokens")


class AutoCompactWindowPrefillKind(str, Enum):
    SERVER_OBSERVED = "server_observed"
    ESTIMATED = "estimated"


@dataclass(frozen=True)
class AutoCompactWindowPrefill:
    kind: AutoCompactWindowPrefillKind
    tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AutoCompactWindowPrefillKind):
            raise TypeError("kind must be an AutoCompactWindowPrefillKind")
        _ensure_non_negative_i64(self.tokens, "tokens")


class AutoCompactWindow:
    def __init__(self) -> None:
        self.ordinal = 1
        self.prefill_input_tokens: AutoCompactWindowPrefill | None = None

    def clear_prefill(self) -> None:
        self.prefill_input_tokens = None

    def start_next(self) -> None:
        self.ordinal = _saturating_add_u64(self.ordinal, 1)
        self.clear_prefill()

    def ensure_server_observed_prefill_from_usage(self, usage: TokenUsage) -> None:
        if not isinstance(usage, TokenUsage):
            raise TypeError("usage must be a TokenUsage")
        if (
            self.prefill_input_tokens is not None
            and self.prefill_input_tokens.kind is AutoCompactWindowPrefillKind.SERVER_OBSERVED
        ):
            return

        self.prefill_input_tokens = AutoCompactWindowPrefill(
            AutoCompactWindowPrefillKind.SERVER_OBSERVED,
            max(usage.input_tokens, 0),
        )

    def set_estimated_prefill(self, tokens: int) -> None:
        _ensure_i64(tokens, "tokens")
        if (
            self.prefill_input_tokens is not None
            and self.prefill_input_tokens.kind is AutoCompactWindowPrefillKind.SERVER_OBSERVED
        ):
            return

        self.prefill_input_tokens = AutoCompactWindowPrefill(
            AutoCompactWindowPrefillKind.ESTIMATED,
            max(tokens, 0),
        )

    def snapshot(self) -> AutoCompactWindowSnapshot:
        return AutoCompactWindowSnapshot(
            ordinal=self.ordinal,
            prefill_input_tokens=(
                self.prefill_input_tokens.tokens
                if self.prefill_input_tokens is not None
                else None
            ),
        )


def _saturating_add_u64(value: int, increment: int) -> int:
    _ensure_u64(value, "value")
    _ensure_u64(increment, "increment")
    return min(value + increment, U64_MAX)


def _ensure_i64(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < I64_MIN or value > I64_MAX:
        raise ValueError(f"{name} out of i64 range")
    return value


def _ensure_non_negative_i64(value: int, name: str) -> int:
    _ensure_i64(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _ensure_u64(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > U64_MAX:
        raise ValueError(f"{name} out of u64 range")
    return value


__all__ = [
    "AutoCompactWindow",
    "AutoCompactWindowPrefill",
    "AutoCompactWindowPrefillKind",
    "AutoCompactWindowSnapshot",
    "U64_MAX",
]
