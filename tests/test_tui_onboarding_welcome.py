"""Parity tests for ``codex-tui/src/onboarding/welcome.rs``."""

from __future__ import annotations

from pycodex.tui.onboarding.welcome import (
    AsciiAnimationModel,
    MIN_ANIMATION_HEIGHT,
    MIN_ANIMATION_WIDTH,
    StepState,
    WelcomeWidget,
    row_containing,
)


def test_welcome_renders_animation_on_first_draw():
    widget = WelcomeWidget.new(is_logged_in=False, animations_enabled=True)
    area = (0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT)
    frame_lines = len(widget.animation.current_frame())

    plan = widget.render_ref(area)

    assert plan.show_animation
    assert row_containing(plan.lines, "Welcome") == frame_lines + 1
    assert plan.welcome_row == frame_lines + 1
    assert widget.animation.scheduled_frames == 1


def test_welcome_skips_animation_below_height_breakpoint():
    widget = WelcomeWidget.new(is_logged_in=False, animations_enabled=True)
    area = (0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT - 1)

    plan = widget.render_ref(area)

    assert not plan.show_animation
    assert row_containing(plan.lines, "Welcome") == 0


def test_welcome_skips_animation_below_width_breakpoint_and_when_suppressed():
    widget = WelcomeWidget.new(is_logged_in=False, animations_enabled=True)
    assert not widget.render_ref((0, 0, MIN_ANIMATION_WIDTH - 1, MIN_ANIMATION_HEIGHT)).show_animation

    widget.update_layout_area((0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT - 1))
    assert not widget.render_ref((0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT)).show_animation

    widget.update_layout_area((0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT))
    widget.set_animations_suppressed(True)
    scheduled = widget.animation.scheduled_frames
    assert not widget.render_ref((0, 0, MIN_ANIMATION_WIDTH, MIN_ANIMATION_HEIGHT)).show_animation
    assert widget.animation.scheduled_frames == scheduled


def test_ctrl_dot_changes_animation_variant():
    widget = WelcomeWidget(
        is_logged_in=False,
        animation=AsciiAnimationModel(variants=(("frame-a",), ("frame-b",)), variant_idx=0),
        animations_enabled=True,
    )

    before = widget.animation.current_frame()
    widget.handle_key_event({"kind": "press", "char": ".", "modifiers": {"control"}})
    after = widget.animation.current_frame()

    assert before != after


def test_ctrl_shift_dot_changes_animation_variant():
    widget = WelcomeWidget(
        is_logged_in=False,
        animation=AsciiAnimationModel(variants=(("frame-a",), ("frame-b",)), variant_idx=0),
        animations_enabled=True,
    )

    before = widget.animation.current_frame()
    widget.handle_key_event({"kind": "press", "char": ".", "modifiers": {"control", "shift"}})
    after = widget.animation.current_frame()

    assert before != after


def test_toggle_key_ignores_release_and_disabled_animations():
    widget = WelcomeWidget(
        is_logged_in=False,
        animation=AsciiAnimationModel(variants=(("frame-a",), ("frame-b",)), variant_idx=0),
        animations_enabled=True,
    )
    widget.handle_key_event({"kind": "release", "char": ".", "modifiers": {"control"}})
    assert widget.animation.current_frame() == ("frame-a",)

    widget.animations_enabled = False
    widget.handle_key_event({"kind": "press", "char": ".", "modifiers": {"control"}})
    assert widget.animation.current_frame() == ("frame-a",)


def test_step_state_depends_on_login_state():
    assert WelcomeWidget.new(is_logged_in=True).get_step_state() is StepState.Hidden
    assert WelcomeWidget.new(is_logged_in=False).get_step_state() is StepState.Complete
