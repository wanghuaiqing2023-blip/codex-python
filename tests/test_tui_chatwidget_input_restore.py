from collections import deque

from pycodex.tui.chatwidget.input_restore import (
    ComposerDraftSnapshot,
    InputRestoreModel,
    LocalImageAttachment,
    PendingSteer,
    PendingSteerCompareKey,
    QueuedUserMessage,
    TextElement,
    ThreadComposerState,
    ThreadInputState,
    UserMessage,
    UserMessageHistoryRecord,
    UserMessageHistoryRecordKind,
    merge_user_messages,
    merge_user_messages_with_history_record,
    user_message_for_restore,
)


def message(text, *, local=(), remote=(), elements=()):
    return UserMessage(
        text=text,
        local_images=[LocalImageAttachment(path=p) for p in local],
        remote_image_urls=list(remote),
        text_elements=list(elements),
    )


def test_initial_user_message_submission_takes_pending_once():
    model = InputRestoreModel(initial_user_message=message("hello"))
    model.set_initial_user_message_submit_suppressed(True)

    model.submit_initial_user_message_if_pending()
    model.submit_initial_user_message_if_pending()

    assert model.suppress_initial_user_message_submit is True
    assert [submitted.text for submitted, _ in model.submitted_messages] == ["hello"]
    assert model.initial_user_message is None


def test_pop_next_prefers_rejected_steers_and_merges_history_records():
    model = InputRestoreModel()
    model.input_queue.queued_user_messages.append(QueuedUserMessage.from_message(message("queued")))
    model.input_queue.rejected_steers_queue.extend([message("raw-a"), message("raw-b")])
    model.input_queue.rejected_steer_history_records.append(
        UserMessageHistoryRecord.override_text("shown-a")
    )

    queued, history = model.pop_next_queued_user_message()

    assert queued.user_message.text == "shown-a\nraw-b"
    assert history.kind is UserMessageHistoryRecordKind.OVERRIDE
    assert history.override.text == "shown-a\nraw-b"
    assert not model.input_queue.rejected_steers_queue
    assert model.input_queue.queued_user_messages[0].user_message.text == "queued"


def test_pop_latest_restores_history_override_from_queued_then_rejected():
    model = InputRestoreModel()
    model.input_queue.rejected_steers_queue.append(message("rejected-raw"))
    model.input_queue.rejected_steer_history_records.append(
        UserMessageHistoryRecord.override_text("rejected-shown")
    )
    model.input_queue.queued_user_messages.append(
        QueuedUserMessage.from_message(message("queued-raw"))
    )
    model.input_queue.queued_user_message_history_records.append(
        UserMessageHistoryRecord.override_text("queued-shown")
    )

    assert model.pop_latest_queued_user_message().text == "queued-shown"
    assert model.pop_latest_queued_user_message().text == "rejected-shown"
    assert model.pop_latest_queued_user_message() is None


def test_enqueue_rejected_steer_moves_pending_and_refreshes_preview():
    model = InputRestoreModel()
    assert model.enqueue_rejected_steer() is False

    model.input_queue.pending_steers.append(
        PendingSteer(message("steer"), UserMessageHistoryRecord.override_text("shown"))
    )
    assert model.enqueue_rejected_steer() is True

    assert not model.input_queue.pending_steers
    assert model.input_queue.rejected_steers_queue[0].text == "steer"
    assert model.input_queue.rejected_steer_history_records[0].override.text == "shown"
    assert model.pending_preview_refreshes == 1


def test_drain_pending_messages_for_restore_orders_rejected_pending_queued_then_composer():
    model = InputRestoreModel(
        composer=ComposerDraftSnapshot(text="draft", remote_image_urls=["https://img"]),
    )
    model.input_queue.rejected_steers_queue.append(message("rejected"))
    model.input_queue.pending_steers.append(PendingSteer(message("pending")))
    model.input_queue.queued_user_messages.append(QueuedUserMessage.from_message(message("queued")))

    combined = model.drain_pending_messages_for_restore()

    assert combined.text == "rejected\npending\nqueued\ndraft"
    assert combined.remote_image_urls == ["https://img"]
    assert not model.input_queue.rejected_steers_queue
    assert not model.input_queue.pending_steers
    assert not model.input_queue.queued_user_messages


def test_on_interrupted_turn_submits_pending_steers_immediately_or_restores_queue():
    immediate = InputRestoreModel()
    immediate.input_queue.submit_pending_steers_after_interrupt = True
    immediate.input_queue.pending_steers.append(PendingSteer(message("steer-a")))
    immediate.input_queue.pending_steers.append(PendingSteer(message("steer-b")))

    immediate.on_interrupted_turn("esc")

    assert immediate.history_events == [("info", "Model interrupted to submit steer instructions.")]
    assert immediate.submitted_messages[0][0].text == "steer-a\nsteer-b"
    assert immediate.redraw_requests == 1

    restore = InputRestoreModel()
    restore.input_queue.queued_user_messages.append(QueuedUserMessage.from_message(message("queued")))
    restore.on_interrupted_turn("budget")

    assert restore.history_events == [("error", "Turn interrupted: budget")]
    assert restore.composer.text == "queued"
    assert restore.restored_messages[0].text == "queued"


def test_capture_and_restore_thread_input_state_resizes_missing_records_and_keys():
    model = InputRestoreModel(
        composer=ComposerDraftSnapshot(text="draft", pending_pastes=[("a", "b")])
    )
    model.input_queue.pending_steers.append(PendingSteer(message("pending")))
    model.input_queue.rejected_steers_queue.append(message("rejected"))
    model.input_queue.queued_user_messages.append(QueuedUserMessage.from_message(message("queued")))
    model.task_running = True
    model.agent_turn_running = True

    state = model.capture_thread_input_state()

    assert state.composer.text == "draft"
    assert list(state.pending_steer_compare_keys) == [PendingSteerCompareKey("pending", 0)]
    assert state.task_running is True
    assert state.agent_turn_running is True

    restored = InputRestoreModel()
    restored.restore_thread_input_state(
        ThreadInputState(
            composer=ThreadComposerState(text="restored", pending_pastes=[("x", "y")]),
            pending_steers=deque([message("pending")]),
            rejected_steers_queue=deque([message("rejected")]),
            queued_user_messages=deque([QueuedUserMessage.from_message(message("queued"))]),
            task_running=True,
            agent_turn_running=True,
        )
    )

    assert restored.composer.text == "restored"
    assert restored.composer.pending_pastes == [("x", "y")]
    assert (
        restored.input_queue.pending_steers[0].history_record.kind
        is UserMessageHistoryRecordKind.USER_MESSAGE_TEXT
    )
    assert (
        restored.input_queue.rejected_steer_history_records[0].kind
        is UserMessageHistoryRecordKind.USER_MESSAGE_TEXT
    )
    assert (
        restored.input_queue.queued_user_message_history_records[0].kind
        is UserMessageHistoryRecordKind.USER_MESSAGE_TEXT
    )
    assert restored.task_running is True
    assert restored.agent_turn_running is True
    assert restored.redraw_requests == 1


def test_restore_none_clears_input_and_composer_state_and_autosend_flag_round_trips():
    model = InputRestoreModel(
        composer=ComposerDraftSnapshot(text="draft", remote_image_urls=["https://img"])
    )
    model.input_queue.pending_steers.append(PendingSteer(message("pending")))
    model.input_queue.rejected_steers_queue.append(message("rejected"))
    model.input_queue.queued_user_messages.append(QueuedUserMessage.from_message(message("queued")))
    model.task_running = True
    model.set_queue_autosend_suppressed(True)

    model.restore_thread_input_state(None)

    assert model.input_queue.suppress_queue_autosend is False
    assert model.composer.text == ""
    assert model.remote_image_urls == []
    assert not model.input_queue.pending_steers
    assert not model.input_queue.rejected_steers_queue
    assert not model.input_queue.queued_user_messages
    assert model.redraw_requests == 1


def test_drain_pending_messages_for_restore_returns_none_without_pending_or_followups():
    model = InputRestoreModel(composer=ComposerDraftSnapshot(text="draft"))

    assert model.drain_pending_messages_for_restore() is None
    assert model.composer.text == "draft"


def test_merge_helpers_rebase_text_elements_and_apply_non_empty_overrides():
    first = message("abc", elements=[TextElement((0, 1), "first")])
    second = message("de", elements=[TextElement((0, 2), "second")])

    merged = merge_user_messages([first, second])
    assert merged.text == "abc\nde"
    assert [element.byte_range for element in merged.text_elements] == [(0, 1), (4, 6)]

    restored = user_message_for_restore(
        message("raw"),
        UserMessageHistoryRecord.override_text("shown"),
    )
    assert restored.text == "shown"

    merged_with_history, history = merge_user_messages_with_history_record(
        [
            (message("raw-a"), UserMessageHistoryRecord.override_text("shown-a")),
            (message("raw-b"), UserMessageHistoryRecord.text()),
        ]
    )
    assert merged_with_history.text == "shown-a\nraw-b"
    assert history.override.text == "shown-a\nraw-b"
