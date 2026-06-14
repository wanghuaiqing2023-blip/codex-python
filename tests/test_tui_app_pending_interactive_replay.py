from pycodex.tui.app.pending_interactive_replay import (
    AppCommand,
    PendingInteractiveReplayState,
    ThreadEventStore,
    elicitation_request,
    exec_approval_request,
    exec_started,
    patch_approval_request,
    permissions_request,
    thread_event_snapshot_drops_answered_request_user_input_for_multi_prompt_turn,
    thread_event_snapshot_drops_pending_approvals_when_turn_completes,
    thread_event_snapshot_drops_pending_requests_when_thread_closes,
    thread_event_snapshot_drops_resolved_elicitation_after_outbound_resolution,
    thread_event_snapshot_drops_resolved_exec_approval_after_outbound_approval_id,
    thread_event_snapshot_drops_resolved_exec_approval_after_server_resolution,
    thread_event_snapshot_drops_resolved_patch_approval_after_outbound_approval,
    thread_event_snapshot_drops_resolved_request_user_input_after_server_resolution,
    thread_event_snapshot_drops_resolved_request_user_input_after_user_answer,
    thread_event_snapshot_keeps_newer_request_user_input_pending_when_same_turn_has_queue,
    thread_event_snapshot_keeps_pending_request_user_input,
    thread_event_store_reports_pending_thread_approvals,
    turn_completed,
    request_user_input_does_not_count_as_pending_thread_approval,
)


def test_pending_request_user_input_replays_until_answered_or_resolved():
    assert thread_event_snapshot_keeps_pending_request_user_input() is True
    assert thread_event_snapshot_drops_resolved_request_user_input_after_user_answer() is True
    assert thread_event_snapshot_drops_resolved_request_user_input_after_server_resolution() is True


def test_request_user_input_fifo_for_same_turn():
    assert thread_event_snapshot_drops_answered_request_user_input_for_multi_prompt_turn() is True
    assert thread_event_snapshot_keeps_newer_request_user_input_pending_when_same_turn_has_queue() is True


def test_exec_patch_elicitation_resolution_paths_match_rust_tests():
    assert thread_event_snapshot_drops_resolved_exec_approval_after_outbound_approval_id() is True
    assert thread_event_snapshot_drops_resolved_exec_approval_after_server_resolution() is True
    assert thread_event_snapshot_drops_resolved_patch_approval_after_outbound_approval() is True
    assert thread_event_snapshot_drops_resolved_elicitation_after_outbound_resolution() is True


def test_turn_completion_and_thread_close_clear_pending_requests():
    assert thread_event_snapshot_drops_pending_approvals_when_turn_completes() is True
    assert thread_event_snapshot_drops_pending_requests_when_thread_closes() is True


def test_pending_thread_approval_flags_exclude_request_user_input():
    assert thread_event_store_reports_pending_thread_approvals() is True
    assert request_user_input_does_not_count_as_pending_thread_approval() is True


def test_op_can_change_state_matches_rust_match_set():
    yes = ["ExecApproval", "PatchApproval", "ResolveElicitation", "RequestPermissionsResponse", "UserInputAnswer", "Shutdown"]
    no = ["TurnStart", "Other"]
    assert all(PendingInteractiveReplayState.op_can_change_state(AppCommand(kind)) for kind in yes)
    assert not any(PendingInteractiveReplayState.op_can_change_state(AppCommand(kind)) for kind in no)


def test_item_started_and_eviction_clear_matching_pending_request():
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("call-1", None, "turn-1"))
    store.push_notification(exec_started("call-1"))
    assert store.pending_interactive_replay.exec_approval_call_ids == set()

    store = ThreadEventStore.new(1)
    store.push_request(patch_approval_request("patch-1", "turn-1"))
    store.push_notification(turn_completed("other-turn"))
    assert store.pending_interactive_replay.patch_approval_call_ids == set()


def test_permissions_request_counts_as_pending_approval_and_clears_by_turn():
    store = ThreadEventStore.new(8)
    store.push_request(permissions_request("perm-1", "turn-1"))
    assert store.has_pending_thread_approvals() is True
    store.push_notification(turn_completed("turn-1"))
    assert store.has_pending_thread_approvals() is False


def test_snapshot_filters_only_interactive_request_kinds():
    store = ThreadEventStore.new(8)
    store.push_request({"kind": "NonInteractive", "request_id": 99, "params": {}})
    assert len(store.snapshot().events) == 1
    store.push_request(elicitation_request("server-1", "request-1"))
    store.note_outbound_op({"kind": "ResolveElicitation", "server_name": "server-1", "request_id": "request-1"})
    assert [event.kind for event in store.snapshot().events] == ["NonInteractive"]
