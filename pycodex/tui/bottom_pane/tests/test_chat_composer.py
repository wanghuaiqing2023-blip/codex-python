from pycodex.tui.bottom_pane.chat_composer import (
    FOOTER_SPACING_HEIGHT,
    LARGE_PASTE_CHAR_THRESHOLD,
    MAX_USER_INPUT_TEXT_CHARS,
    ChatComposerConfig,
    ChatComposer,
    ChatComposerRenderSnapshot,
    ComposerDraftSnapshot,
    InputResult,
    KeyEvent,
    QueuedInputAction,
    expand_pending_pastes,
    plan_mode_nudge_line,
    user_input_too_large_message,
)


def test_chat_composer_constants_and_large_input_message_match_rust_copy():
    assert LARGE_PASTE_CHAR_THRESHOLD == 1000
    assert FOOTER_SPACING_HEIGHT == 0
    assert user_input_too_large_message(123) == (
        f"Message exceeds the maximum length of {MAX_USER_INPUT_TEXT_CHARS} characters (123 provided)."
    )


def test_queued_input_action_variants_match_rust():
    assert [action.name for action in QueuedInputAction] == ["Plain", "ParseSlash", "RunShell"]


def test_input_result_variants_preserve_payload_shapes():
    submitted = InputResult.Submitted("hello", ["element"])
    assert submitted.kind == "Submitted"
    assert submitted.text == "hello"
    assert submitted.text_elements == ["element"]

    queued = InputResult.Queued("run", action=QueuedInputAction.RunShell)
    assert queued.kind == "Queued"
    assert queued.action is QueuedInputAction.RunShell

    assert InputResult.Command("Diff").command == "Diff"
    assert InputResult.ServiceTierCommand("fast").kind == "ServiceTierCommand"
    with_args = InputResult.CommandWithArgs("Plan", "investigate", ["rebased"])
    assert with_args.kind == "CommandWithArgs"
    assert with_args.args == "investigate"
    assert with_args.text_elements == ["rebased"]
    assert InputResult.None_().kind == "None"


def test_chat_composer_config_default_and_plain_text_match_rust_flags():
    assert ChatComposerConfig.default() == ChatComposerConfig(True, True, True)
    assert ChatComposerConfig.plain_text() == ChatComposerConfig(False, False, False)


def test_composer_draft_snapshot_preserves_attachment_and_pending_fields():
    snapshot = ComposerDraftSnapshot(
        text="hello",
        text_elements=["e"],
        local_images=["local.png"],
        remote_image_urls=["https://example.com/img.png"],
        mention_bindings=["mention"],
        pending_pastes=[("[Pasted]", "data")],
    )
    assert snapshot.text == "hello"
    assert snapshot.pending_pastes == [("[Pasted]", "data")]


def test_plan_mode_nudge_line_keeps_visible_actions():
    line = " ".join(plan_mode_nudge_line())
    assert "Create a plan?" in line
    assert "Plan mode" in line
    assert "dismiss" in line


def test_handle_key_event_short_circuits_disabled_and_release_events():
    # Rust: codex-tui bottom_pane/chat_composer.rs ChatComposer::handle_key_event
    # returns (InputResult::None, false) before popup sync when input is disabled
    # or when crossterm reports KeyEventKind::Release.
    disabled = ChatComposer(input_enabled=False)
    result, handled = disabled.handle_key_event(KeyEvent.char_event("x"))
    assert result.kind == "None"
    assert handled is False
    assert disabled.dispatch_log == []
    assert disabled.sync_count == 0

    composer = ChatComposer()
    result, handled = composer.handle_key_event(KeyEvent.char_event("x", kind="release"))
    assert result.kind == "None"
    assert handled is False
    assert composer.dispatch_log == []
    assert composer.sync_count == 0


def test_handle_key_event_prioritizes_history_search_without_popup_sync():
    # Rust: existing history search handles the key directly, and the configured
    # history-search binding begins search before active popup dispatch.
    active = ChatComposer(history_search_active=True, active_popup="command")
    result, handled = active.handle_key_event(KeyEvent.char_event("a"))
    assert result.kind == "None"
    assert handled is False
    assert active.dispatch_log == ["history_search"]
    assert active.sync_count == 0

    composer = ChatComposer(active_popup="command")
    result, handled = composer.handle_key_event(KeyEvent.char_event("r", modifiers=("control",)))
    assert result.kind == "None"
    assert handled is True
    assert composer.history_search_active is True
    assert composer.dispatch_log == ["begin_history_search"]
    assert composer.sync_count == 0


def test_handle_key_event_dispatches_active_popup_then_syncs_popups():
    # Rust: active popup variants dispatch to popup-specific handlers, then
    # reset_vim_mode_after_successful_dispatch and sync_popups run once.
    composer = ChatComposer(
        active_popup="command",
        handlers={"slash_popup": lambda _event: (InputResult.Command("Diff"), True)},
    )
    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "Command"
    assert result.command == "Diff"
    assert handled is True
    assert composer.dispatch_log == ["slash_popup"]
    assert composer.reset_vim_count == 1
    assert composer.sync_count == 1


def test_handle_key_event_without_popup_supports_plain_text_submit_boundary():
    # Rust: when no popup is active, the top-level handler delegates to
    # handle_key_event_without_popup; detailed editing remains textarea.rs.
    composer = ChatComposer()
    result, handled = composer.handle_key_event(KeyEvent.char_event("h"))
    assert result.kind == "None"
    assert handled is True
    assert composer.dispatch_log == ["without_popup"]
    assert composer.sync_count == 1

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result == InputResult.Submitted("h")
    assert handled is True
    assert composer.dispatch_log == ["without_popup", "without_popup"]
    assert composer.sync_count == 2


def test_shift_enter_inserts_newline_without_submitting():
    # Rust source: codex-tui::bottom_pane::chat_composer::handle_key_event_without_popup.
    # Rust test: chatwidget/tests/composer_submission.rs
    # shift_enter_with_only_remote_images_does_not_submit_user_turn.
    # Contract: only plain Enter is a submit key; Shift+Enter is textarea input.
    composer = ChatComposer()
    composer.handle_key_event(KeyEvent.char_event("a"))

    result, handled = composer.handle_key_event(KeyEvent.key("enter", modifiers=("shift",)))

    assert result.kind == "None"
    assert handled is True
    assert composer.render().text == "a\n"
    assert composer.dispatch_log == ["without_popup", "without_popup"]

    result, handled = composer.handle_key_event(KeyEvent.char_event("b"))
    assert result.kind == "None"
    assert handled is True

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))
    assert result == InputResult.Submitted("a\nb")
    assert handled is True


def test_enter_with_only_remote_images_submits_empty_text_boundary():
    # Rust test: chatwidget/tests/composer_submission.rs
    # enter_with_only_remote_images_submits_user_turn, plus
    # chat_composer.rs::prepare_submission_with_only_remote_images_returns_empty_text.
    composer = ChatComposer(remote_image_urls=["https://example.com/remote-only.png"])

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result == InputResult.Submitted("")
    assert handled is True
    assert composer.current_text() == ""


def test_shift_enter_with_only_remote_images_does_not_submit():
    # Rust test: chatwidget/tests/composer_submission.rs
    # shift_enter_with_only_remote_images_does_not_submit_user_turn.
    composer = ChatComposer(remote_image_urls=["https://example.com/remote-only.png"])

    result, handled = composer.handle_key_event(KeyEvent.key("enter", modifiers=("shift",)))

    assert result.kind == "None"
    assert handled is True
    assert composer.remote_image_urls == ["https://example.com/remote-only.png"]


def test_enter_with_only_remote_images_does_not_submit_when_modal_active_or_disabled():
    # Rust tests:
    # enter_with_only_remote_images_does_not_submit_when_modal_is_active
    # enter_with_only_remote_images_does_not_submit_when_input_disabled.
    modal = ChatComposer(active_popup="review", remote_image_urls=["https://example.com/remote-only.png"])
    result, handled = modal.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "None"
    assert handled is False
    assert modal.remote_image_urls == ["https://example.com/remote-only.png"]

    disabled = ChatComposer(input_enabled=False, remote_image_urls=["https://example.com/remote-only.png"])
    result, handled = disabled.handle_key_event(KeyEvent.key("enter"))
    assert result.kind == "None"
    assert handled is False
    assert disabled.remote_image_urls == ["https://example.com/remote-only.png"]


def test_empty_enter_during_task_does_not_submit_or_queue():
    # Rust test: chatwidget/tests/composer_submission.rs
    # empty_enter_during_task_does_not_queue.
    composer = ChatComposer(is_task_running=True)

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result.kind == "None"
    assert handled is False
    assert composer.current_text() == ""


def test_large_paste_placeholder_expands_on_submit_and_clears_pending_state():
    # Rust tests: chat_composer.rs handle_paste_large_uses_placeholder_and_replaces_on_submit,
    # current_text_with_pending_expands_placeholders, and test_multiple_pastes_submission.
    payload = "x" * (LARGE_PASTE_CHAR_THRESHOLD + 1)
    composer = ChatComposer()

    assert composer.handle_paste(payload) is True
    assert composer.current_text() == f"[Pasted Content {len(payload)} chars]"
    assert composer.current_text_with_pending() == payload

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result == InputResult.Submitted(payload, composer.text_elements)
    assert handled is True
    assert composer.current_text() == ""
    assert composer.pending_pastes_value() == []


def test_pending_paste_expansion_is_fifo_and_normalizes_crlf():
    # Rust tests: current_text_with_pending_expands_overlapping_placeholders
    # and pasted_crlf_normalizes_newlines_for_elements.
    composer = ChatComposer()
    first = "a" * (LARGE_PASTE_CHAR_THRESHOLD + 4)
    second = "b\r\nc"

    composer.handle_paste(first)
    composer.handle_paste(second)

    assert composer.current_text_with_pending() == first + "b\nc"


def test_prepare_submission_rejects_expanded_input_over_limit_without_clearing_draft():
    # Rust tests: oversized direct and pending-paste submissions emit
    # user_input_too_large_message and suppress submission.
    placeholder = "[Pasted Content oversized chars]"
    payload = "x" * (MAX_USER_INPUT_TEXT_CHARS + 1)
    composer = ChatComposer(text=placeholder, pending_pastes=[(placeholder, payload)])

    result, handled = composer.handle_key_event(KeyEvent.key("enter"))

    assert result.kind == "None"
    assert handled is True
    assert composer.current_text() == placeholder
    assert composer.pending_pastes_value() == [(placeholder, payload)]
    assert composer.errors == [user_input_too_large_message(len(payload))]


def test_expand_pending_pastes_replaces_placeholders_once_in_order():
    # Rust source: ChatComposer::expand_pending_pastes walks pending placeholders
    # in order so duplicate-sized large pastes preserve FIFO payload mapping.
    text, elements = expand_pending_pastes(
        "<paste><paste>",
        [{"range": (0, 7), "placeholder": "<paste>"}],
        [("<paste>", "first"), ("<paste>", "second")],
    )

    assert text == "firstsecond"
    assert elements == [{"range": (0, 7), "placeholder": "<paste>"}]


def test_render_delegates_to_masked_render_and_returns_semantic_snapshot():
    # Rust: WidgetRef::render calls render_with_mask(..., None), which delegates
    # to render_with_mask_and_textarea_right_reserve(..., 0).
    composer = ChatComposer(text="secret", remote_image_urls=["https://example.com/a.png"], footer=["? for shortcuts"])
    buf = []
    snapshot = composer.render(area=(0, 0, 40, 6), buf=buf)
    assert isinstance(snapshot, ChatComposerRenderSnapshot)
    assert snapshot.text == "secret"
    assert snapshot.mask_char is None
    assert snapshot.textarea_right_reserve == 0
    assert snapshot.remote_image_urls == ("https://example.com/a.png",)
    assert snapshot.footer == ("? for shortcuts",)
    assert buf == [snapshot]
    assert composer.render_log == [("render_with_mask_and_textarea_right_reserve", (0, 0, 40, 6), None, 0)]

    masked = composer.render_with_mask(area=(0, 0, 40, 6), mask_char="*")
    assert masked.text == "******"
    assert masked.mask_char == "*"
