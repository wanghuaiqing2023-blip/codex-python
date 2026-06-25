"""Parity tests for ``codex-tui/src/onboarding/trust_directory.rs``."""

from __future__ import annotations

from pathlib import Path

from pycodex.tui.onboarding.trust_directory import (
    StepState,
    TrustDirectorySelection,
    TrustDirectoryWidget,
)


def test_release_event_does_not_change_selection():
    widget = TrustDirectoryWidget(
        cwd=Path("."),
        trust_target=Path("."),
        highlighted=TrustDirectorySelection.Quit,
    )

    widget.handle_key_event({"kind": "release", "key": "enter"})
    assert widget.selection is None
    assert not widget.should_quit()

    widget.handle_key_event({"kind": "press", "key": "enter"})
    assert widget.should_quit()


def test_key_routing_trust_quit_and_highlight():
    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."), error="bad")

    widget.handle_key_event({"key": "down"})
    assert widget.highlighted is TrustDirectorySelection.Quit
    widget.handle_key_event({"key": "up"})
    assert widget.highlighted is TrustDirectorySelection.Trust

    widget.handle_key_event({"key": "1"})
    assert widget.selection is TrustDirectorySelection.Trust
    assert widget.error is None
    assert widget.get_step_state() is StepState.Complete

    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."))
    widget.handle_key_event({"key": "2"})
    assert widget.should_quit()
    assert widget.highlighted is TrustDirectorySelection.Quit
    assert widget.get_step_state() is StepState.Complete

    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."))
    widget.handle_key_event({"key": "esc"})
    assert widget.should_quit()


def test_enter_uses_highlighted_selection():
    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."), highlighted=TrustDirectorySelection.Trust)
    widget.handle_key_event({"key": "enter"})
    assert widget.selection is TrustDirectorySelection.Trust

    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."), highlighted=TrustDirectorySelection.Quit)
    widget.handle_key_event({"key": "enter"})
    assert widget.should_quit()


def test_step_state_in_progress_until_selection_or_quit():
    widget = TrustDirectoryWidget(cwd=Path("."), trust_target=Path("."))
    assert widget.get_step_state() is StepState.InProgress
    widget.handle_trust()
    assert widget.get_step_state() is StepState.Complete


def test_render_plan_for_git_repo_without_warning():
    widget = TrustDirectoryWidget(
        cwd=Path("/workspace/project"),
        trust_target=Path("/workspace/project"),
        highlighted=TrustDirectorySelection.Trust,
    )

    plan = widget.render_ref()

    assert not plan.show_git_root_warning
    assert plan.lines[0] == "> You are in /workspace/project"
    assert any("Do you trust the contents of this directory?" in line for line in plan.lines)
    assert "› 1. Yes, continue" in plan.lines
    assert "  2. No, quit" in plan.lines
    assert plan.lines[-1] == "  Press Enter to continue"


def test_render_plan_for_subdirectory_error_and_windows_hint():
    widget = TrustDirectoryWidget(
        cwd=Path("/workspace/project/sub"),
        trust_target=Path("/workspace/project"),
        show_windows_create_sandbox_hint=True,
        highlighted=TrustDirectorySelection.Quit,
        error="cannot persist trust",
    )

    plan = widget.render_ref()

    assert plan.show_git_root_warning
    assert any("repository root: /workspace/project" in line for line in plan.lines)
    assert "  1. Yes, continue" in plan.lines
    assert "› 2. No, quit" in plan.lines
    assert "  cannot persist trust" in plan.lines
    assert plan.lines[-1] == "  Press Enter to continue and create a sandbox..."
