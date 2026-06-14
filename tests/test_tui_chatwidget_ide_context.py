from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/ide_context.rs
# Behavior contract: /ide command toggling and args, IDE context fetch/apply
# routing, prompt-fetch warning suppression, and status-indicator sync.

from pathlib import Path

from pycodex.tui.chatwidget.ide_context import IdeContextDeps, IdeContextState, IdeContextWidgetState


class IdeError(Exception):
    def prompt_skip_hint(self):
        return "skip hint"

    def user_facing_hint(self):
        return "user hint"


def widget(fetch=None, has_prompt=True):
    applied = []

    def default_fetch(cwd):
        return {"cwd": cwd, "context": True}

    def apply(context, items):
        applied.append((context, list(items)))
        items.append({"ide_context": context})

    state = IdeContextWidgetState(
        cwd=Path("/repo"),
        deps=IdeContextDeps(fetch or default_fetch, apply, lambda context: has_prompt),
    )
    state.applied = applied
    return state


def test_ide_context_state_enable_disable_and_mark_available_reset_warning_flag():
    state = IdeContextState()
    assert state.is_enabled() is False

    state.enable()
    state.prompt_fetch_warned = True
    state.mark_available()
    assert state.is_enabled() is True
    assert state.prompt_fetch_warned is False

    state.prompt_fetch_warned = True
    state.disable()
    assert state.is_enabled() is False
    assert state.prompt_fetch_warned is False


def test_handle_ide_command_toggles_enabled_state_and_messages():
    state = widget()

    state.handle_ide_command()
    assert state.ide_context.is_enabled() is True
    assert state.indicator_active is True
    assert state.info_messages[-1] == (
        "IDE context is on.",
        "Future messages will include your current IDE selection and open tabs.",
    )

    state.handle_ide_command()
    assert state.ide_context.is_enabled() is False
    assert state.indicator_active is False
    assert state.info_messages[-1] == ("IDE context is off.", None)


def test_handle_ide_command_args_on_off_status_and_usage_error():
    state = widget(has_prompt=False)

    state.handle_ide_command_args("on")
    assert state.ide_context.is_enabled() is True
    assert state.info_messages[-1] == ("IDE context is on.", "Connected to your IDE.")

    state.handle_ide_command_args("status")
    assert state.info_messages[-1] == ("IDE context is on.", "Connected to your IDE.")

    state.handle_ide_command_args("off")
    assert state.ide_context.is_enabled() is False
    assert state.info_messages[-1] == ("IDE context is off.", None)

    state.handle_ide_command_args("wat")
    assert state.error_messages == ["Usage: /ide [on|off|status]"]


def test_add_status_message_disables_when_fetch_fails():
    state = widget(fetch=lambda cwd: (_ for _ in ()).throw(IdeError("boom")))
    state.ide_context.enable()

    state.add_ide_context_status_message()

    assert state.ide_context.is_enabled() is False
    assert state.indicator_active is False
    assert state.info_messages == [("IDE context could not be enabled.", "user hint")]


def test_maybe_apply_ide_context_is_noop_when_disabled():
    state = widget()
    items = ["message"]

    state.maybe_apply_ide_context(items)

    assert items == ["message"]
    assert state.applied == []


def test_maybe_apply_ide_context_applies_context_and_resets_warning_on_success():
    state = widget()
    state.ide_context.enable()
    state.ide_context.prompt_fetch_warned = True
    items = ["message"]

    state.maybe_apply_ide_context(items)

    assert state.ide_context.prompt_fetch_warned is False
    assert state.indicator_active is True
    assert items[-1]["ide_context"]["cwd"] == Path("/repo")
    assert state.applied[0][1] == ["message"]


def test_maybe_apply_ide_context_warns_once_until_context_available():
    calls = {"count": 0}

    def fetch(cwd):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise IdeError("boom")
        return {"ok": True}

    state = widget(fetch=fetch)
    state.ide_context.enable()
    items = []

    state.maybe_apply_ide_context(items)
    state.maybe_apply_ide_context(items)
    assert state.info_messages == [("IDE context was skipped for this message.", "skip hint")]
    assert state.ide_context.prompt_fetch_warned is True

    state.maybe_apply_ide_context(items)
    assert state.ide_context.prompt_fetch_warned is False
    assert items[-1] == {"ide_context": {"ok": True}}
