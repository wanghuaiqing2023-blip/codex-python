"""Shimmer span generation for ``codex-tui::shimmer``.

Rust source: ``codex/codex-rs/tui/src/shimmer.rs``.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ._porting import RustTuiModule
from .color import blend
from .line_truncation import Span
from .terminal_palette import default_bg, default_fg

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="shimmer",
    source="codex/codex-rs/tui/src/shimmer.rs",
)

PROCESS_START = time.monotonic()


@dataclass(frozen=True)
class ShimmerStyle:
    modifier: Optional[str] = None
    fg: Optional[Tuple[int, int, int]] = None


def elapsed_since_start(clock: Callable[[], float] = time.monotonic) -> float:
    return max(0.0, clock() - PROCESS_START)


def supports_truecolor_stdout() -> bool:
    """Semantic boundary for Rust ``supports_color::on_cached(Stream::Stdout)``."""

    return False


def shimmer_spans(
    text: str,
    *,
    elapsed_seconds: Optional[float] = None,
    has_true_color: Optional[bool] = None,
) -> List[Span]:
    chars = list(text)
    if not chars:
        return []

    padding = 10
    period = len(chars) + padding * 2
    sweep_seconds = 2.0
    elapsed = elapsed_since_start() if elapsed_seconds is None else max(0.0, elapsed_seconds)
    true_color = supports_truecolor_stdout() if has_true_color is None else has_true_color
    pos = int((elapsed % sweep_seconds) / sweep_seconds * period)
    band_half_width = 5.0
    base_color = default_fg() or (128, 128, 128)
    highlight_color = default_bg() or (255, 255, 255)

    spans: List[Span] = []
    for index, ch in enumerate(chars):
        dist = abs((index + padding) - pos)
        if dist <= band_half_width:
            x = math.pi * (dist / band_half_width)
            intensity = 0.5 * (1.0 + math.cos(x))
        else:
            intensity = 0.0

        if true_color:
            highlight = max(0.0, min(1.0, intensity))
            rgb = blend(highlight_color, base_color, highlight * 0.9)
            style = ShimmerStyle(modifier="bold", fg=rgb)
        else:
            style = color_for_level(intensity)
        spans.append(Span(ch, style=style))
    return spans


def color_for_level(intensity: float) -> ShimmerStyle:
    if intensity < 0.2:
        return ShimmerStyle(modifier="dim")
    if intensity < 0.6:
        return ShimmerStyle()
    return ShimmerStyle(modifier="bold")


__all__ = [
    "PROCESS_START",
    "RUST_MODULE",
    "ShimmerStyle",
    "color_for_level",
    "elapsed_since_start",
    "shimmer_spans",
    "supports_truecolor_stdout",
]
