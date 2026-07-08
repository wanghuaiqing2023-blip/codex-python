"""Parity tests for Rust ``codex-tui::bottom_pane::chat_composer::popup_state``."""

# Rust owner: codex-tui::bottom_pane::chat_composer::popup_state.
# Rust source: codex/codex-rs/tui/src/bottom_pane/chat_composer/popup_state.rs
from pycodex.tui.bottom_pane.chat_composer.popup_state import ActivePopup, PopupState


def test_popup_state_default_matches_rust_default() -> None:
    state = PopupState()

    assert state.active_popup == ActivePopup.none()
    assert state.active() is False
    assert state.dismissed_file_token is None
    assert state.current_file_query is None
    assert state.dismissed_mention_token is None


def test_popup_state_active_reports_non_none_variants() -> None:
    for popup in [
        ActivePopup.command(object()),
        ActivePopup.file(object()),
        ActivePopup.skill(object()),
        ActivePopup.mention_v2(object()),
    ]:
        assert PopupState(active_popup=popup).active() is True


def test_active_popup_preserves_variant_names_and_payloads() -> None:
    payload = {"popup": "value"}

    popup = ActivePopup.file(payload)

    assert popup.kind == "File"
    assert popup.value is payload
    assert popup.is_none() is False
    assert ActivePopup.none().is_none() is True


def test_popup_state_active_variant_can_be_replaced_like_rust_field_assignment() -> None:
    state = PopupState()
    command_payload = {"kind": "command"}
    skill_payload = {"kind": "skill"}

    none_popup = ActivePopup.none()
    assert none_popup.kind == "None"
    assert none_popup.value is None

    state.active_popup = ActivePopup.command(command_payload)
    assert state.active() is True
    assert state.active_popup.kind == "Command"
    assert state.active_popup.value is command_payload

    state.active_popup = ActivePopup.skill(skill_payload)
    assert state.active() is True
    assert state.active_popup.kind == "Skill"
    assert state.active_popup.value is skill_payload

    state.active_popup = ActivePopup.none()
    assert state.active() is False


def test_popup_state_preserves_dismissal_and_query_tokens() -> None:
    state = PopupState(
        dismissed_file_token="file-token",
        current_file_query="src/",
        dismissed_mention_token="mention-token",
    )

    assert state.dismissed_file_token == "file-token"
    assert state.current_file_query == "src/"
    assert state.dismissed_mention_token == "mention-token"
