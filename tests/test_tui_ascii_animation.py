"""Parity tests for Rust ``codex-tui::ascii_animation``.

Rust source: ``codex/codex-rs/tui/src/ascii_animation.rs``.
"""

from datetime import timedelta

from pycodex.tui.ascii_animation import AsciiAnimation
from pycodex.tui.frames import FRAME_TICK_DEFAULT


class FakeFrameRequester:
    def __init__(self) -> None:
        self.immediate = 0
        self.delays: list[timedelta] = []

    def schedule_frame(self) -> None:
        self.immediate += 1

    def schedule_frame_in(self, delay: timedelta) -> None:
        self.delays.append(delay)


def test_frame_tick_must_be_nonzero() -> None:
    assert FRAME_TICK_DEFAULT.total_seconds() * 1000 > 0


def test_with_variants_requires_non_empty_and_clamps_index() -> None:
    requester = FakeFrameRequester()
    variants = (("a",), ("b",))
    animation = AsciiAnimation.with_variants(requester, variants, 99, clock=lambda: 10.0)
    assert animation.variant_idx == 1
    assert animation.frames() == ("b",)

    try:
        AsciiAnimation.with_variants(requester, (), 0)
    except AssertionError as exc:
        assert "requires at least one animation variant" in str(exc)
    else:
        raise AssertionError("expected empty variants to assert")


def test_current_frame_uses_elapsed_tick_index_and_empty_frames() -> None:
    now = 0.0

    def clock() -> float:
        return now

    variants = (("a0", "a1", "a2"), ())
    animation = AsciiAnimation.with_variants(
        FakeFrameRequester(), variants, 0, clock=clock, frame_tick=timedelta(milliseconds=80)
    )
    now = 0.079
    assert animation.current_frame() == "a0"
    now = 0.080
    assert animation.current_frame() == "a1"
    now = 0.240
    assert animation.current_frame() == "a0"

    empty = AsciiAnimation.with_variants(FakeFrameRequester(), variants, 1, clock=clock)
    assert empty.current_frame() == ""


def test_zero_tick_uses_first_frame_and_immediate_schedule() -> None:
    requester = FakeFrameRequester()
    animation = AsciiAnimation.with_variants(
        requester, (("a", "b"),), 0, frame_tick=timedelta(milliseconds=0)
    )
    assert animation.current_frame() == "a"
    animation.schedule_next_frame()
    assert requester.immediate == 1
    assert requester.delays == []


def test_schedule_next_frame_aligns_to_next_tick() -> None:
    now = 1.0

    def clock() -> float:
        return now

    requester = FakeFrameRequester()
    animation = AsciiAnimation.with_variants(
        requester, (("a",),), 0, clock=clock, frame_tick=timedelta(milliseconds=80)
    )
    now = 1.000
    animation.schedule_next_frame()
    now = 1.010
    animation.schedule_next_frame()
    assert requester.delays == [timedelta(milliseconds=80), timedelta(milliseconds=70)]


def test_pick_random_variant_never_keeps_current_and_schedules_frame() -> None:
    requester = FakeFrameRequester()
    picks = iter([0, 0, 2])
    animation = AsciiAnimation.with_variants(
        requester,
        (("a",), ("b",), ("c",)),
        0,
        rng_range=lambda start, stop: next(picks),
    )
    assert animation.pick_random_variant() is True
    assert animation.variant_idx == 2
    assert requester.immediate == 1

    single = AsciiAnimation.with_variants(FakeFrameRequester(), (("a",),), 0)
    assert single.pick_random_variant() is False
