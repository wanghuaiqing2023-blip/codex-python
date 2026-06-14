from pycodex.tui.bottom_pane.chat_composer import (
    FOOTER_SPACING_HEIGHT,
    LARGE_PASTE_CHAR_THRESHOLD,
    MAX_USER_INPUT_TEXT_CHARS,
    ChatComposerConfig,
    ComposerDraftSnapshot,
    InputResult,
    QueuedInputAction,
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
