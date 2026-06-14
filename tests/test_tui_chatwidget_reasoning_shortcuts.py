from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/reasoning_shortcuts.rs
# Behavior contract: reasoning effort rank/order, choices derived from active
# model preset, next effort movement in lower/raise direction, and boundary
# messages used by the ChatWidget shortcut handler.

from pycodex.protocol.config_types import ReasoningEffort
from pycodex.protocol.openai_models import ReasoningEffortPreset
from pycodex.tui.chatwidget.reasoning_shortcuts import (
    ReasoningShortcutDirection,
    effort_rank,
    handle_reasoning_shortcut_semantic,
    next_reasoning_effort,
    reasoning_choices,
)


def preset(default=ReasoningEffort.MEDIUM, supported=()):
    return {
        "default_reasoning_effort": default,
        "supported_reasoning_efforts": tuple(ReasoningEffortPreset(effort, effort.value) for effort in supported),
    }


def test_next_reasoning_effort_raises_from_default_anchor_matches_rust_test():
    choices = [ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH, ReasoningEffort.XHIGH]

    assert next_reasoning_effort(choices, ReasoningEffort.MEDIUM, ReasoningShortcutDirection.Raise) is ReasoningEffort.HIGH


def test_next_reasoning_effort_lowers_from_default_anchor_matches_rust_test():
    choices = [ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]

    assert next_reasoning_effort(choices, ReasoningEffort.MEDIUM, ReasoningShortcutDirection.Lower) is ReasoningEffort.LOW


def test_next_reasoning_effort_skips_to_supported_level_from_unsupported_current_matches_rust_test():
    choices = [ReasoningEffort.LOW, ReasoningEffort.HIGH]

    assert next_reasoning_effort(choices, ReasoningEffort.MEDIUM, ReasoningShortcutDirection.Raise) is ReasoningEffort.HIGH
    assert next_reasoning_effort(choices, ReasoningEffort.MEDIUM, ReasoningShortcutDirection.Lower) is ReasoningEffort.LOW


def test_next_reasoning_effort_clamps_at_bounds_matches_rust_test():
    choices = [ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]

    assert next_reasoning_effort(choices, ReasoningEffort.LOW, ReasoningShortcutDirection.Lower) is None
    assert next_reasoning_effort(choices, ReasoningEffort.HIGH, ReasoningShortcutDirection.Raise) is None


def test_next_reasoning_effort_single_option_is_noop_matches_rust_test():
    choices = [ReasoningEffort.HIGH]

    assert next_reasoning_effort(choices, ReasoningEffort.HIGH, ReasoningShortcutDirection.Raise) is None
    assert next_reasoning_effort(choices, ReasoningEffort.HIGH, ReasoningShortcutDirection.Lower) is None


def test_reasoning_choices_filters_in_enum_order_and_falls_back_to_default():
    assert reasoning_choices(preset(supported=[ReasoningEffort.HIGH, ReasoningEffort.LOW])) == [
        ReasoningEffort.LOW,
        ReasoningEffort.HIGH,
    ]
    assert reasoning_choices(preset(default=ReasoningEffort.MINIMAL, supported=[])) == [ReasoningEffort.MINIMAL]


def test_effort_rank_matches_rust_order():
    assert [effort_rank(effort) for effort in [
        ReasoningEffort.NONE,
        ReasoningEffort.MINIMAL,
        ReasoningEffort.LOW,
        ReasoningEffort.MEDIUM,
        ReasoningEffort.HIGH,
        ReasoningEffort.XHIGH,
    ]] == [0, 1, 2, 3, 4, 5]


def test_bound_message_matches_direction_and_effort_label():
    assert ReasoningShortcutDirection.Lower.bound_message(ReasoningEffort.LOW) == "Reasoning is already at the lowest level (low)."
    assert ReasoningShortcutDirection.Raise.bound_message(ReasoningEffort.HIGH) == "Reasoning is already at the highest level (high)."


def test_semantic_handler_covers_startup_unavailable_bounds_and_plan_mode():
    assert handle_reasoning_shortcut_semantic(
        recognized=False,
        modal_or_popup_active=False,
        session_configured=True,
        current_model="m",
        preset=preset(),
        effective_effort=None,
        direction="raise",
    ).handled is False
    assert handle_reasoning_shortcut_semantic(
        recognized=True,
        modal_or_popup_active=True,
        session_configured=True,
        current_model="m",
        preset=preset(),
        effective_effort=None,
        direction="raise",
    ).handled is False
    assert handle_reasoning_shortcut_semantic(
        recognized=True,
        modal_or_popup_active=False,
        session_configured=False,
        current_model="m",
        preset=preset(),
        effective_effort=None,
        direction="raise",
    ).info_message == "Reasoning shortcuts are disabled until startup completes."
    assert handle_reasoning_shortcut_semantic(
        recognized=True,
        modal_or_popup_active=False,
        session_configured=True,
        current_model="m",
        preset=None,
        effective_effort=None,
        direction="raise",
    ).info_message == "Reasoning shortcuts are unavailable for m."

    result = handle_reasoning_shortcut_semantic(
        recognized=True,
        modal_or_popup_active=False,
        session_configured=True,
        current_model="m",
        preset=preset(supported=[ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH]),
        effective_effort=None,
        direction="raise",
        plan_mode_active=True,
    )
    assert result.handled is True
    assert result.next_effort is ReasoningEffort.HIGH
    assert result.plan_mode_update is True
