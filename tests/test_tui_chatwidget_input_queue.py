from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/input_queue.rs
# Behavior contract: keep queued messages, pending steers, and rejected steers
# separate in previews; clear resets every queue and pending-start flag covered
# by Rust tests.

from collections import deque

from pycodex.tui.chatwidget.input_queue import InputQueueState, PendingInputPreview, PendingSteer, user_message_preview_text


def test_preview_keeps_queue_categories_separate_matches_rust_test():
    state = InputQueueState()
    state.queued_user_messages.append("queued")
    state.rejected_steers_queue.append("rejected")
    state.pending_steers.append(PendingSteer("pending", "UserMessageText", {"message": "pending", "image_count": 0}))

    assert state.preview() == PendingInputPreview(
        queued_messages=["queued"],
        pending_steers=["pending"],
        rejected_steers=["rejected"],
    )


def test_clear_resets_all_input_queues_matches_rust_test():
    state = InputQueueState()
    state.queued_user_messages.append("queued")
    state.queued_user_message_history_records.append("queued history")
    state.rejected_steers_queue.append("rejected")
    state.rejected_steer_history_records.append("rejected history")
    state.pending_steers.append(PendingSteer("pending", "pending history"))
    state.user_turn_pending_start = True
    state.submit_pending_steers_after_interrupt = True
    state.suppress_queue_autosend = True

    state.clear()

    assert list(state.queued_user_messages) == []
    assert list(state.queued_user_message_history_records) == []
    assert state.user_turn_pending_start is False
    assert list(state.rejected_steers_queue) == []
    assert list(state.rejected_steer_history_records) == []
    assert list(state.pending_steers) == []
    assert state.submit_pending_steers_after_interrupt is False
    assert state.suppress_queue_autosend is True


def test_has_queued_follow_up_messages_checks_rejected_then_queued_but_not_pending_steers():
    state = InputQueueState()
    assert state.has_queued_follow_up_messages() is False

    state.pending_steers.append(PendingSteer("pending"))
    assert state.has_queued_follow_up_messages() is False

    state.queued_user_messages.append("queued")
    assert state.has_queued_follow_up_messages() is True

    state.queued_user_messages.clear()
    state.rejected_steers_queue.append("rejected")
    assert state.has_queued_follow_up_messages() is True


def test_preview_uses_history_records_in_lockstep_and_falls_back_to_message_text():
    state = InputQueueState(
        queued_user_messages=deque([{"text": "queued raw"}, {"text": "second raw"}]),
        queued_user_message_history_records=deque([{"text": "queued history"}]),
        rejected_steers_queue=deque([{"message": "rejected raw"}]),
        rejected_steer_history_records=deque([{"display": "rejected history"}]),
        pending_steers=deque([PendingSteer({"content": "pending raw"}, {"preview": "pending history"})]),
    )

    assert state.preview() == PendingInputPreview(
        queued_messages=["queued history", "second raw"],
        pending_steers=["pending history"],
        rejected_steers=["rejected history"],
    )


def test_enqueue_helpers_preserve_missing_history_record_fallback():
    state = InputQueueState()
    state.enqueue_user_message("queued")
    state.enqueue_rejected_steer("rejected", "rejected rendered")
    state.enqueue_pending_steer("pending")

    assert state.preview() == PendingInputPreview(
        queued_messages=["queued"],
        pending_steers=["pending"],
        rejected_steers=["rejected rendered"],
    )


def test_user_message_preview_text_supports_duck_typed_payloads():
    class Message:
        text = "object text"

    class History:
        history_text = "history text"

    assert user_message_preview_text(Message()) == "object text"
    assert user_message_preview_text(Message(), History()) == "history text"
    assert user_message_preview_text({"_payload": {"input": "payload text"}}) == "payload text"
