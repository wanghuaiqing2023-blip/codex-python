"""Auto-compact token window state ported from Codex core.

This mirrors ``codex-rs/core/src/state/auto_compact_window.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pycodex.protocol import TokenUsage


@dataclass(frozen=True)
class AutoCompactWindowSnapshot:
    ordinal: int
    prefill_input_tokens: int | None = None


class AutoCompactWindowPrefillKind(str, Enum):
    SERVER_OBSERVED = "server_observed"
    ESTIMATED = "estimated"


@dataclass(frozen=True)
class AutoCompactWindowPrefill:
    kind: AutoCompactWindowPrefillKind
    tokens: int


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
    return min(max(value, 0) + max(increment, 0), (1 << 64) - 1)


__all__ = [
    "AutoCompactWindow",
    "AutoCompactWindowPrefill",
    "AutoCompactWindowPrefillKind",
    "AutoCompactWindowSnapshot",
]
