from pycodex.tui.chatwidget.input_flow import (
    CollaborationModeMask,
    ExecCommandSource,
    InputFlowModel,
    InputResult,
    ModeKind,
    QueueDrain,
    QueuedInputAction,
    RunningCommand,
    TextElement,
    UserMessage,
)


def test_submitted_empty_message_is_ignored_without_refresh_like_rust_early_return():
    model = InputFlowModel()

    model.handle_composer_input_result(InputResult.submitted(""), had_modal_or_popup=True)

    assert model.submitted_messages == []
    assert model.pending_input_previews == []
    assert model.plan_mode_nudge_refreshes == 0


def test_submitted_message_submits_now_and_clears_reasoning_buffers():
    model = InputFlowModel(reasoning_buffer=["r"], full_reasoning_buffer=["full"])

    model.handle_composer_input_result(
        InputResult.submitted("hello", [TextElement("span")]),
        had_modal_or_popup=False,
    )

    assert model.submitted_messages[0].text == "hello"
    assert model.submitted_messages[0].text_elements == [TextElement("span")]
    assert model.reasoning_buffer == []
    assert model.full_reasoning_buffer == []
    assert model.status_headers == ["Working"]
    assert model.plan_mode_nudge_refreshes == 1


def test_submitted_message_queues_when_session_unconfigured_or_plan_streaming():
    unconfigured = InputFlowModel(session_configured=False)
    unconfigured.handle_composer_input_result(InputResult.submitted("later"), False)
    assert unconfigured.queued_user_message_texts() == ["later"]

    streaming = InputFlowModel(plan_streaming_in_tui=True)
    streaming.handle_composer_input_result(InputResult.submitted("after plan"), False)
    assert streaming.queued_user_message_texts() == ["after plan"]


def test_only_user_shell_commands_running_queues_non_shell_prompt_but_allows_bang():
    model = InputFlowModel(
        agent_turn_running=True,
        running_commands={"1": RunningCommand(ExecCommandSource.USER_SHELL)},
    )

    model.handle_composer_input_result(InputResult.submitted("plain followup"), False)
    model.handle_composer_input_result(InputResult.submitted("!pwd"), False)

    assert model.queued_user_message_texts() == ["plain followup"]
    assert model.submitted_messages[0].text == "!pwd"


def test_queued_input_result_uses_action_and_may_submit_when_idle():
    idle = InputFlowModel()
    idle.handle_composer_input_result(
        InputResult.queued("run", QueuedInputAction.RUN_SHELL),
        False,
    )
    assert idle.submitted_messages[0].text == "run"

    busy = InputFlowModel(task_running=True)
    busy.handle_composer_input_result(
        InputResult.queued("run later", QueuedInputAction.RUN_SHELL),
        False,
    )
    assert busy.input_queue.queued_user_messages[0].action is QueuedInputAction.RUN_SHELL
    assert busy.pending_input_previews[-1]["queued_messages"] == 1


def test_commands_dispatch_and_modal_close_triggers_queue_drain():
    model = InputFlowModel(bottom_pane_modal_active=False)
    model.input_queue.queued_user_messages.append(
        model.input_queue.queued_user_messages.__class__.__args__[0]  # type: ignore[attr-defined]
    ) if False else None

    model.handle_composer_input_result(InputResult.command("/help"), had_modal_or_popup=True)
    model.handle_composer_input_result(InputResult.service_tier_command("flex"), False)
    model.handle_composer_input_result(InputResult.command_with_args("/model", "gpt", []), False)

    assert model.slash_dispatches == ["/help"]
    assert model.service_tier_dispatches == ["flex"]
    assert model.slash_with_args_dispatches == [("/model", "gpt", [])]
    assert model.maybe_send_calls == 1


def test_maybe_send_next_queued_input_submits_one_plain_and_refreshes_preview():
    model = InputFlowModel()
    model.input_queue.queued_user_messages.append(
        model.input_queue.queued_user_messages.__class__.__mro__ if False else None
    )
    model.input_queue.queued_user_messages.clear()
    from pycodex.tui.chatwidget.input_flow import QueuedUserMessage

    model.input_queue.queued_user_messages.extend(
        [
            QueuedUserMessage(UserMessage("one")),
            QueuedUserMessage(UserMessage("two")),
        ]
    )
    model.input_queue.queued_user_message_history_records.extend(["h1", "h2"])

    assert model.maybe_send_next_queued_input() is True

    assert model.submitted_messages_with_history[0][0].text == "one"
    assert model.submitted_messages_with_history[0][1] == "h1"
    assert model.queued_user_message_texts() == ["two"]
    assert model.pending_input_previews[-1]["queued_messages"] == 1


def test_maybe_send_next_respects_suppression_and_running_turn():
    suppressed = InputFlowModel()
    suppressed.input_queue.suppress_queue_autosend = True
    assert suppressed.maybe_send_next_queued_input() is False

    running = InputFlowModel(task_running=True)
    assert running.maybe_send_next_queued_input() is False


def test_maybe_send_next_drains_slash_and_shell_until_stop():
    from pycodex.tui.chatwidget.input_flow import QueuedUserMessage

    model = InputFlowModel()
    model.input_queue.queued_user_messages.extend(
        [
            QueuedUserMessage(UserMessage("/help"), QueuedInputAction.PARSE_SLASH),
            QueuedUserMessage(UserMessage("pwd"), QueuedInputAction.RUN_SHELL),
        ]
    )
    model.queued_slash_handler = lambda message: QueueDrain.CONTINUE

    def shell_handler(message):
        model.input_queue.user_turn_pending_start = True
        return QueueDrain.STOP

    model.queued_shell_handler = shell_handler

    assert model.maybe_send_next_queued_input() is True
    assert model.queued_user_message_texts() == []


def test_submit_user_message_with_mode_applies_plan_effort_and_blocks_running_mode_switch():
    mask = CollaborationModeMask(mode=ModeKind.PLAN)
    model = InputFlowModel(plan_mode_reasoning_effort="high")

    model.submit_user_message_with_mode("plan text", mask)

    assert mask.reasoning_effort == "high"
    assert model.collaboration_masks_set == [mask]
    assert model.submitted_messages[0].text == "plan text"

    blocked = InputFlowModel(
        agent_turn_running=True,
        active_collaboration_mask=CollaborationModeMask(mode=ModeKind.OTHER),
    )
    blocked.submit_user_message_with_mode("switch", CollaborationModeMask(mode=ModeKind.PLAN))
    assert blocked.error_messages == ["Cannot switch collaboration mode while a turn is running."]
    assert blocked.submitted_messages == []


def test_submit_user_message_with_mode_queues_when_plan_streaming():
    model = InputFlowModel(plan_streaming_in_tui=True)

    model.submit_user_message_with_mode("queued", CollaborationModeMask(mode=ModeKind.OTHER))

    assert model.queued_user_message_texts() == ["queued"]
    assert model.submitted_messages == []


def test_set_queue_submissions_until_session_configured_gate():
    assert InputFlowModel(session_configured=False).set_queue_submissions_until_session_configured(True) is True
    assert InputFlowModel(session_configured=True).set_queue_submissions_until_session_configured(True) is False
    assert InputFlowModel(session_configured=False).set_queue_submissions_until_session_configured(False) is False
