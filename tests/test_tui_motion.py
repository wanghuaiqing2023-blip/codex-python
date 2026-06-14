"""Parity tests for Rust ``codex-tui::motion``.

Rust source: ``codex/codex-rs/tui/src/motion.rs``.
"""

from pathlib import Path

import pycodex.tui.motion as motion_module
from pycodex.tui.line_truncation import Span
from pycodex.tui.motion import (
    MotionMode,
    ReducedMotionIndicator,
    activity_indicator,
    animated_activity_indicator,
    animation_primitive_allowlisted_path,
    animation_primitives_are_only_used_by_motion_module,
    shimmer_text,
)


def test_motion_mode_from_animations_enabled() -> None:
    assert MotionMode.from_animations_enabled(True) is MotionMode.Animated
    assert MotionMode.from_animations_enabled(False) is MotionMode.Reduced


def test_reduced_motion_activity_indicator_uses_explicit_fallback() -> None:
    assert activity_indicator(None, MotionMode.Reduced, ReducedMotionIndicator.Hidden) is None
    assert activity_indicator(None, MotionMode.Reduced, ReducedMotionIndicator.StaticBullet) == Span("•", style="dim")


def test_reduced_motion_shimmer_text_is_plain_text() -> None:
    assert shimmer_text("Loading", MotionMode.Reduced) == [Span("Loading")]
    assert shimmer_text("", MotionMode.Reduced) == []


def test_animated_motion_returns_semantic_spans() -> None:
    assert activity_indicator(None, MotionMode.Animated, ReducedMotionIndicator.Hidden) == Span("•")
    assert shimmer_text("Loading", MotionMode.Animated) == [Span("Loading", style="shimmer")]


def test_animated_activity_indicator_uses_shimmer_when_stdout_truecolor(monkeypatch) -> None:
    # Rust: truecolor stdout delegates the activity glyph to shimmer_spans("•").
    monkeypatch.setattr(motion_module, "supports_truecolor_stdout", lambda: True)

    assert animated_activity_indicator(None) == Span("•", style="shimmer")


def test_animated_activity_indicator_blinks_on_six_hundred_ms_ticks(monkeypatch) -> None:
    # Rust: motion.rs::animated_activity_indicator uses (elapsed_ms / 600).is_multiple_of(2).
    monkeypatch.setattr(motion_module.time, "monotonic", lambda: 10.0)
    assert animated_activity_indicator(10.0) == Span("•")

    monkeypatch.setattr(motion_module.time, "monotonic", lambda: 10.6)
    assert animated_activity_indicator(10.0) == Span("◦", style="dim")

    monkeypatch.setattr(motion_module.time, "monotonic", lambda: 11.2)
    assert animated_activity_indicator(10.0) == Span("•")


def test_animated_activity_indicator_tick_boundaries_use_integer_milliseconds(monkeypatch) -> None:
    # Rust: Instant::elapsed().as_millis() truncates to integer milliseconds.
    for elapsed, expected in [
        (0.599, Span("•")),
        (0.600, Span("◦", style="dim")),
        (0.600999, Span("◦", style="dim")),
        (1.199, Span("◦", style="dim")),
        (1.200, Span("•")),
    ]:
        monkeypatch.setattr(motion_module.time, "monotonic", lambda elapsed=elapsed: 10.0 + elapsed)
        assert animated_activity_indicator(10.0) == expected


def test_animation_primitive_allowlisted_path() -> None:
    assert animation_primitive_allowlisted_path("motion.rs")
    assert animation_primitive_allowlisted_path("shimmer.rs")
    assert not animation_primitive_allowlisted_path("chatwidget/rendering.rs")


def test_animation_primitives_are_only_used_by_motion_module(tmp_path: Path) -> None:
    (tmp_path / "motion.rs").write_text("spinner();\nshimmer_spans();\n", encoding="utf-8")
    (tmp_path / "shimmer.rs").write_text("shimmer_spans();\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / "bad.rs").write_text("fn x() { shimmer_spans(); }\n", encoding="utf-8")
    (child / "bad_spinner.rs").write_text("fn y() { spinner(); }\n", encoding="utf-8")
    (child / "comment.rs").write_text("// spinner();\n", encoding="utf-8")

    violations = animation_primitives_are_only_used_by_motion_module(tmp_path)
    assert violations == [
        "child/bad.rs:1 contains a direct `shimmer_spans(...)` call; use crate::motion instead",
        "child/bad_spinner.rs:1 contains a direct `spinner(...)` call; use crate::motion instead",
    ]
