"""Number formatting helpers used by protocol display paths.

Ported from ``codex/codex-rs/protocol/src/num_format.rs``. The Rust
implementation is locale-aware and falls back to en-US; this Python port uses
the standard-library en-US-style grouping deterministically.
"""

from __future__ import annotations

import math


def format_with_separators(value: int) -> str:
    return f"{value:,}"


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def _format_scaled(value: int, scale: int, frac_digits: int) -> str:
    factor = 10**frac_digits
    scaled = _round_half_up((value / scale) * factor)
    if frac_digits == 0:
        return format_with_separators(scaled)
    whole, fraction = divmod(scaled, factor)
    return f"{format_with_separators(whole)}.{fraction:0{frac_digits}d}"


def format_si_suffix(value: int) -> str:
    value = max(value, 0)
    if value < 1000:
        return format_with_separators(value)

    for scale, suffix in ((1_000, "K"), (1_000_000, "M"), (1_000_000_000, "G")):
        floating = float(value)
        if _round_half_up(100.0 * floating / scale) < 1000.0:
            return f"{_format_scaled(value, scale, 2)}{suffix}"
        if _round_half_up(10.0 * floating / scale) < 1000.0:
            return f"{_format_scaled(value, scale, 1)}{suffix}"
        if _round_half_up(floating / scale) < 1000.0:
            return f"{_format_scaled(value, scale, 0)}{suffix}"

    return f"{format_with_separators(_round_half_up(value / 1_000_000_000))}G"
