from datetime import timedelta

from pycodex.tui.bottom_pane import (
    APPROVAL_PROMPT_TYPING_IDLE_DELAY,
    DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED,
    QUIT_SHORTCUT_TIMEOUT,
    BottomPane,
    BottomPaneParams,
    CancellationEvent,
    LocalImageAttachment,
    MentionBinding,
    ctrl_c_on_modal_consumes_without_showing_quit_hint,
    delayed_approval_shows_after_idle,
    delayed_approval_waits_for_idle_composer,
    drain_pending_submission_state_clears_assets,
    esc_dismisses_view_when_not_preferred,
    esc_routes_to_view_when_preferred,
    interrupt_key_sends_interrupt_when_task_running,
    paste_completes_active_view_and_reenables_composer,
    status_and_context_setters_round_trip,
    test_pane,
)


def test_bottom_pane_module_constants_match_rust_defaults():
    assert QUIT_SHORTCUT_TIMEOUT == timedelta(seconds=1)
    assert APPROVAL_PROMPT_TYPING_IDLE_DELAY == timedelta(seconds=1)
    assert DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED is False


def test_local_image_attachment_preserves_placeholder_and_path():
    attachment = LocalImageAttachment("[image]", "fixtures/example.png")

    assert attachment.placeholder == "[image]"
    assert str(attachment.path).endswith("fixtures\\example.png") or str(attachment.path).endswith("fixtures/example.png")


def test_mention_binding_preserves_mention_and_path():
    binding = MentionBinding("@README.md", "README.md")

    assert binding.mention == "@README.md"
    assert binding.path == "README.md"


def test_cancellation_event_variants_match_rust_enum():
    assert CancellationEvent.HANDLED.value == "handled"
    assert CancellationEvent.NOT_HANDLED.value == "not_handled"


def test_bottom_pane_semantic_container_round_trips_core_state():
    pane = BottomPane.new(BottomPaneParams(placeholder_text="Ask Codex"))
    pane.insert_str("hello")
    pane.add_local_image(LocalImageAttachment("[img]", "image.png"))
    pane.add_mention_binding(MentionBinding("@file", "file.py"))
    pane.set_remote_image_urls(["https://example.invalid/image.png"])

    drained = pane.drain_pending_submission_state()

    assert pane.placeholder_text == "Ask Codex"
    assert drained["text"] == "hello"
    assert len(drained["images"]) == 1
    assert len(drained["mentions"]) == 1
    assert drained["remote_image_urls"] == ["https://example.invalid/image.png"]
    assert pane.composer_text() == ""
    assert pane.remote_image_urls() == []


def test_bottom_pane_rust_mod_semantic_helpers_cover_routing_contract():
    assert ctrl_c_on_modal_consumes_without_showing_quit_hint()
    assert esc_routes_to_view_when_preferred()
    assert esc_dismisses_view_when_not_preferred()
    assert paste_completes_active_view_and_reenables_composer()
    assert interrupt_key_sends_interrupt_when_task_running()
    assert delayed_approval_waits_for_idle_composer()
    assert delayed_approval_shows_after_idle()
    assert drain_pending_submission_state_clears_assets()
    assert status_and_context_setters_round_trip()


def test_bottom_pane_test_pane_constructs_rust_style_defaults():
    pane = test_pane()

    assert pane.has_input_focus()
    assert pane.no_modal_or_popup_active()
    assert pane.desired_height(80) == 1
