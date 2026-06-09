from types import SimpleNamespace

from pycodex.core.context import CollaborationModeInstructions
from pycodex.core.context_manager.updates import build_collaboration_mode_update_item
from pycodex.protocol import (
    COLLABORATION_MODE_CLOSE_TAG,
    COLLABORATION_MODE_OPEN_TAG,
    CollaborationMode,
    ModeKind,
    Settings,
)


def _mode(text: str | None, *, mode: ModeKind = ModeKind.DEFAULT) -> CollaborationMode:
    return CollaborationMode(
        mode=mode,
        settings=Settings(
            model="gpt-5.4",
            reasoning_effort=None,
            developer_instructions=text,
        ),
    )


def _xml(text: str) -> str:
    return f"{COLLABORATION_MODE_OPEN_TAG}{text}{COLLABORATION_MODE_CLOSE_TAG}"


def _context(collaboration_mode, *, include: bool = True):
    return SimpleNamespace(
        config=SimpleNamespace(include_collaboration_mode_instructions=include),
        collaboration_mode=collaboration_mode,
    )


def _update(previous_mode, next_mode, *, include: bool = True) -> str | None:
    return build_collaboration_mode_update_item(
        SimpleNamespace(collaboration_mode=previous_mode),
        _context(next_mode, include=include),
    )


def test_no_collaboration_instructions_by_default():
    # Rust source: codex/codex-rs/core/tests/suite/collaboration_instructions.rs
    # Rust test: no_collaboration_instructions_by_default.
    assert CollaborationModeInstructions.from_collaboration_mode(_mode(None)) is None
    assert build_collaboration_mode_update_item(None, _context(_mode("collab"))) is None


def test_user_input_includes_collaboration_instructions_after_override():
    # Rust test: user_input_includes_collaboration_instructions_after_override.
    fragment = CollaborationModeInstructions.from_collaboration_mode(_mode("collab instructions"))
    assert fragment is not None
    assert fragment.render() == _xml("collab instructions")


def test_collaboration_instructions_added_on_user_turn():
    # Rust test: collaboration_instructions_added_on_user_turn.
    assert _update(_mode(None), _mode("turn instructions")) == _xml("turn instructions")


def test_collaboration_instructions_omitted_when_disabled():
    # Rust test: collaboration_instructions_omitted_when_disabled.
    assert _update(_mode(None), _mode("turn instructions"), include=False) is None


def test_override_then_next_turn_uses_updated_collaboration_instructions():
    # Rust test: override_then_next_turn_uses_updated_collaboration_instructions.
    assert _update(_mode(None), _mode("override instructions")) == _xml("override instructions")


def test_user_turn_overrides_collaboration_instructions_after_override():
    # Rust test: user_turn_overrides_collaboration_instructions_after_override.
    rendered = _update(_mode("base instructions"), _mode("turn override"))
    assert rendered == _xml("turn override")
    assert "base instructions" not in rendered


def test_collaboration_mode_update_emits_new_instruction_message():
    # Rust test: collaboration_mode_update_emits_new_instruction_message.
    first = _update(_mode(None), _mode("first instructions"))
    second = _update(_mode("first instructions"), _mode("second instructions"))
    assert first == _xml("first instructions")
    assert second == _xml("second instructions")


def test_collaboration_mode_update_noop_does_not_append():
    # Rust test: collaboration_mode_update_noop_does_not_append.
    assert _update(_mode("same instructions"), _mode("same instructions")) is None


def test_collaboration_mode_update_emits_new_instruction_message_when_mode_changes():
    # Rust test: collaboration_mode_update_emits_new_instruction_message_when_mode_changes.
    previous = _mode("default mode instructions", mode=ModeKind.DEFAULT)
    next_mode = _mode("plan mode instructions", mode=ModeKind.PLAN)
    assert _update(previous, next_mode) == _xml("plan mode instructions")


def test_collaboration_mode_update_noop_does_not_append_when_mode_is_unchanged():
    # Rust test: collaboration_mode_update_noop_does_not_append_when_mode_is_unchanged.
    previous = _mode("mode-stable instructions", mode=ModeKind.DEFAULT)
    next_mode = _mode("mode-stable instructions", mode=ModeKind.DEFAULT)
    assert _update(previous, next_mode) is None


def test_resume_replays_collaboration_instructions():
    # Rust test: resume_replays_collaboration_instructions.
    resumed = CollaborationModeInstructions.from_collaboration_mode(_mode("resume instructions"))
    assert resumed is not None
    assert resumed.render() == _xml("resume instructions")


def test_empty_collaboration_instructions_are_ignored():
    # Rust test: empty_collaboration_instructions_are_ignored.
    assert CollaborationModeInstructions.from_collaboration_mode(_mode("")) is None
    assert _update(_mode(None), _mode("")) is None

