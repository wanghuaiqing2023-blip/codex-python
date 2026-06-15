"""Parity tests for Rust ``codex-tui::bottom_pane::chat_composer::draft_state``."""

from pycodex.tui.bottom_pane.chat_composer.draft_state import ComposerMentionBinding, DraftState
from pycodex.tui.bottom_pane.paste_burst import PasteBurst
from pycodex.tui.bottom_pane.textarea import TextArea, TextAreaState


def test_draft_state_new_matches_rust_defaults() -> None:
    # Rust contract: DraftState::new initializes all composer draft fields.
    state = DraftState.new()

    assert isinstance(state.textarea, TextArea)
    assert isinstance(state.textarea_state, TextAreaState)
    assert state.is_bash_mode is False
    assert state.pending_pastes == []
    assert state.input_enabled is True
    assert state.input_disabled_placeholder is None
    assert isinstance(state.paste_burst, PasteBurst)
    assert state.disable_paste_burst is False
    assert state.mention_bindings == {}
    assert state.recent_submission_mention_bindings == []


def test_draft_state_default_factories_are_not_shared() -> None:
    first = DraftState.new()
    second = DraftState.new()

    first.pending_pastes.append(("path", "payload"))
    first.mention_bindings[1] = ComposerMentionBinding(mention="@file", path="src/file.py")
    first.recent_submission_mention_bindings.append(object())

    assert second.pending_pastes == []
    assert second.mention_bindings == {}
    assert second.recent_submission_mention_bindings == []
    assert first.paste_burst is not second.paste_burst
    assert first.textarea is not second.textarea
    assert first.textarea_state is not second.textarea_state


def test_composer_mention_binding_preserves_fields_and_clone_like_equality() -> None:
    binding = ComposerMentionBinding(mention="@README.md", path="README.md")

    assert binding.mention == "@README.md"
    assert binding.path == "README.md"
    assert binding == ComposerMentionBinding(mention="@README.md", path="README.md")


def test_draft_state_mutable_flags_and_mention_key_shape_match_rust_fields() -> None:
    state = DraftState.new()

    state.is_bash_mode = True
    state.input_enabled = False
    state.input_disabled_placeholder = "Input disabled"
    state.disable_paste_burst = True
    state.pending_pastes.append(("marker", "payload"))
    state.mention_bindings[42] = ComposerMentionBinding("@src", "src")

    assert state.is_bash_mode is True
    assert state.input_enabled is False
    assert state.input_disabled_placeholder == "Input disabled"
    assert state.disable_paste_burst is True
    assert state.pending_pastes == [("marker", "payload")]
    assert set(state.mention_bindings) == {42}
    assert state.mention_bindings[42] == ComposerMentionBinding("@src", "src")


def test_pending_pastes_order_and_u64_mention_binding_keys_match_rust_shape() -> None:
    state = DraftState.new()
    max_u64 = (1 << 64) - 1

    state.pending_pastes.append(("first-marker", "first-payload"))
    state.pending_pastes.append(("second-marker", "second-payload"))
    state.mention_bindings[max_u64] = ComposerMentionBinding("@big", "big")

    assert state.pending_pastes == [
        ("first-marker", "first-payload"),
        ("second-marker", "second-payload"),
    ]
    assert state.mention_bindings[max_u64] == ComposerMentionBinding("@big", "big")
