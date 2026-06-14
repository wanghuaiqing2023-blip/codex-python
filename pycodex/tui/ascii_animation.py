"""ASCII animation driver for ``codex-tui::ascii_animation``.

Rust source: ``codex/codex-rs/tui/src/ascii_animation.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import random
import time
from typing import Any, Callable, Sequence

from ._porting import RustTuiModule
from .frames import ALL_VARIANTS, FRAME_TICK_DEFAULT

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ascii_animation",
    source="codex/codex-rs/tui/src/ascii_animation.rs",
)

Clock = Callable[[], float]
RandomRange = Callable[[int, int], int]


@dataclass
class AsciiAnimation:
    request_frame: Any
    variants: Sequence[Sequence[str]]
    variant_idx: int
    frame_tick: timedelta = FRAME_TICK_DEFAULT
    start: float = field(default_factory=time.monotonic)
    clock: Clock = time.monotonic
    rng_range: RandomRange | None = None

    @classmethod
    def new(cls, request_frame: Any) -> "AsciiAnimation":
        return cls.with_variants(request_frame, ALL_VARIANTS, 0)

    @classmethod
    def with_variants(
        cls,
        request_frame: Any,
        variants: Sequence[Sequence[str]],
        variant_idx: int,
        *,
        clock: Clock = time.monotonic,
        rng_range: RandomRange | None = None,
        frame_tick: timedelta = FRAME_TICK_DEFAULT,
    ) -> "AsciiAnimation":
        if not variants:
            raise AssertionError("AsciiAnimation requires at least one animation variant")
        clamped_idx = min(max(0, variant_idx), len(variants) - 1)
        now = clock()
        return cls(
            request_frame=request_frame,
            variants=variants,
            variant_idx=clamped_idx,
            frame_tick=frame_tick,
            start=now,
            clock=clock,
            rng_range=rng_range,
        )

    def schedule_next_frame(self) -> None:
        tick_ms = _duration_ms(self.frame_tick)
        if tick_ms == 0:
            self.request_frame.schedule_frame()
            return
        elapsed_ms = self._elapsed_ms()
        rem_ms = elapsed_ms % tick_ms
        delay_ms = tick_ms if rem_ms == 0 else tick_ms - rem_ms
        self.request_frame.schedule_frame_in(timedelta(milliseconds=delay_ms))

    def current_frame(self) -> str:
        frames = self.frames()
        if not frames:
            return ""
        tick_ms = _duration_ms(self.frame_tick)
        if tick_ms == 0:
            return frames[0]
        idx = (self._elapsed_ms() // tick_ms) % len(frames)
        return frames[int(idx)]

    def pick_random_variant(self) -> bool:
        if len(self.variants) <= 1:
            return False
        next_idx = self.variant_idx
        rng_range = self.rng_range or (lambda start, stop: random.randrange(start, stop))
        while next_idx == self.variant_idx:
            next_idx = rng_range(0, len(self.variants))
        self.variant_idx = next_idx
        self.request_frame.schedule_frame()
        return True

    def frames(self) -> Sequence[str]:
        return self.variants[self.variant_idx]

    def _elapsed_ms(self) -> int:
        elapsed_seconds = max(0.0, self.clock() - self.start)
        return int(elapsed_seconds * 1000)


def _duration_ms(duration: timedelta) -> int:
    return int(duration.total_seconds() * 1000)


__all__ = [
    "AsciiAnimation",
    "RUST_MODULE",
]
