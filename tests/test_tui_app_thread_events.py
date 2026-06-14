from pycodex.tui.app.thread_events import (
    FeedbackThreadEvent,
    SideParentStatus,
    ThreadBufferedEvent,
    ThreadEventStore,
    exec_approval_request,
    file_change_item_changes,
    hook_completed_notification,
    hook_started_notification,
    test_turn,
    thread_event_store_clear_active_turn_id_resets_cached_turn,
    thread_event_store_rebase_preserves_hook_notifications,
    thread_event_store_rebase_preserves_resolved_request_state,
    thread_event_store_restores_active_turn_from_snapshot_turns,
    thread_event_store_tracks_active_turn_lifecycle,
    turn_completed_notification,
    turn_id_matches,
    turn_started_notification,
)
from pycodex.tui.app.pending_interactive_replay import (
    AppCommand,
    ServerNotification,
    ServerRequest,
    request_user_input_request,
)


def test_thread_event_store_tracks_active_turn_lifecycle():
    assert thread_event_store_tracks_active_turn_lifecycle() is True


def test_thread_event_store_restores_and_clears_active_turn():
    assert thread_event_store_restores_active_turn_from_snapshot_turns() is True
    assert thread_event_store_clear_active_turn_id_resets_cached_turn() is True


def test_rebase_preserves_resolved_request_state_and_hooks():
    assert thread_event_store_rebase_preserves_resolved_request_state() is True
    assert thread_event_store_rebase_preserves_hook_notifications() is True


def test_event_survives_session_refresh_matches_rust_variants():
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.request(ServerRequest("Other", 1, {}))) is True
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.notification(hook_started_notification("t", "turn"))) is True
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.notification(hook_completed_notification("t", "turn"))) is True
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.feedback_submission(FeedbackThreadEvent("bug", False, "team", "ok"))) is True
    assert ThreadEventStore.event_survives_session_refresh(ThreadBufferedEvent.notification(ServerNotification("Warning"))) is False


def test_snapshot_filters_resolved_requests_but_keeps_other_events():
    store = ThreadEventStore.new(8)
    request = exec_approval_request("thread-1", "turn-1", "call-1")
    store.push_request(request)
    store.note_outbound_op(AppCommand("ExecApproval", id="call-1", turn_id="turn-1"))
    store.buffer.append(ThreadBufferedEvent.notification(ServerNotification("Warning")))
    assert [event.kind for event in store.snapshot().events] == ["Notification"]


def test_capacity_eviction_updates_pending_request_state():
    store = ThreadEventStore.new(1)
    store.push_request(exec_approval_request("thread-1", "turn-1", "call-1"))
    store.push_notification(ServerNotification("Warning"))
    assert store.pending_replay_requests() == []
    assert store.has_pending_thread_approvals() is False


def test_side_parent_pending_status_prefers_user_input_then_approval():
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("input-1", "turn-1"))
    assert store.side_parent_pending_status() is SideParentStatus.NEEDS_INPUT

    store.note_outbound_op(AppCommand("UserInputAnswer", id="turn-1"))
    store.push_request(exec_approval_request("thread-1", "turn-1", "call-1"))
    assert store.side_parent_pending_status() is SideParentStatus.NEEDS_APPROVAL


def test_turn_id_and_file_change_lookup_helpers():
    assert turn_id_matches("", "turn-any") is True
    assert turn_id_matches("turn-1", "turn-1") is True
    assert turn_id_matches("turn-1", "turn-2") is False
    assert file_change_item_changes({"kind": "FileChange", "id": "file-1", "changes": ["a"]}, "file-1") == ["a"]


def test_file_change_changes_searches_buffer_then_turns():
    store = ThreadEventStore.new(8)
    store.push_notification(ServerNotification("ItemStarted", turn_id="turn-1", item={"kind": "FileChange", "id": "file-1", "changes": ["buffer"]}))
    assert store.file_change_changes("turn-1", "file-1") == ["buffer"]

    store = ThreadEventStore.new(8)
    store.set_turns([test_turn("turn-1", "Completed", [{"kind": "FileChange", "id": "file-1", "changes": ["turn"]}])])
    assert store.file_change_changes("turn-1", "file-1") == ["turn"]


def test_apply_thread_rollback_resets_buffer_pending_and_active_turn():
    store = ThreadEventStore.new(8)
    store.push_notification(turn_started_notification("thread-1", "turn-1"))
    store.push_request(exec_approval_request("thread-1", "turn-1", "call-1"))
    store.apply_thread_rollback({"thread": {"turns": [test_turn("turn-old", "Completed")]}})
    assert store.active_turn_id() is None
    assert store.buffer == []
    assert store.has_pending_thread_approvals() is False
    assert [turn.id for turn in store.turns] == ["turn-old"]
