from pathlib import Path

from pycodex.tui.chatwidget.session_flow import (
    MessageHistoryMetadata,
    SessionFlowModel,
    ThreadSessionState,
)


def session(**overrides):
    values = {
        "thread_id": "thread-1",
        "cwd": Path("/repo"),
        "model": "gpt-5",
        "reasoning_effort": "medium",
        "message_history": MessageHistoryMetadata(log_id="log", entry_count=7),
        "network_proxy": "proxy",
        "thread_name": "Thread",
        "forked_from_id": None,
        "fork_parent_title": None,
        "rollout_path": Path("/rollout.jsonl"),
        "runtime_workspace_roots": (Path("/repo"), Path("/repo/extra")),
        "service_tier": "flex",
        "approval_policy": "on-request",
        "permission_profile": "profile",
        "active_permission_profile": "active-profile",
        "approvals_reviewer": "reviewer",
        "personality": "warm",
        "collaboration_mode": None,
        "instruction_source_paths": (Path("/repo/AGENTS.md"),),
    }
    values.update(overrides)
    return ThreadSessionState(**values)


def test_handle_thread_session_applies_session_state_and_normal_header():
    model = SessionFlowModel(
        initial_user_message="hello",
        startup_tooltip_override="tip",
        connectors_feature_enabled=True,
        show_welcome_banner=True,
    )

    model.handle_thread_session(session(forked_from_id="parent", fork_parent_title="Parent thread"))

    assert model.thread_id == "thread-1"
    assert model.thread_name == "Thread"
    assert model.bottom_history_metadata == ("thread-1", "log", 7)
    assert model.skills is None
    assert model.session_network_proxy == "proxy"
    assert model.queue_submissions is False
    assert model.review_denial_resets == 1
    assert model.current_cwd == Path("/repo")
    assert model.workspace_roots == [Path("/repo"), Path("/repo/extra")]
    assert model.permissions_workspace_roots == [Path("/repo"), Path("/repo/extra")]
    assert model.approval_policy == "on-request"
    assert model.permission_snapshot.permission_profile == "profile"
    assert model.permission_snapshot.active_permission_profile == "active-profile"
    assert model.current_collaboration_mode.model == "gpt-5"
    assert model.active_collaboration_mask.reasoning_effort == "medium"
    assert model.applied_session_info_cells[0].startup_tooltip_override == "tip"
    assert model.applied_session_info_cells[0].show_fast_status is True
    assert model.submitted_user_messages == ["hello"]
    assert model.forked_thread_events[0].forked_from_id == "parent"
    assert model.emitted_history_lines == ["* Thread forked from Parent thread (parent)"]
    assert model.connector_prefetches == 1
    assert model.redraw_requests == 1


def test_quiet_session_clears_existing_session_header_and_suppresses_fork_event():
    model = SessionFlowModel(
        active_cell_is_session_header=True,
        initial_user_message="draft",
        suppress_initial_user_message_submit=True,
    )

    model.handle_thread_session_quiet(session(forked_from_id="parent"))

    assert model.active_cell_is_session_header is False
    assert model.active_cell_revision_bumps == 1
    assert model.applied_session_info_cells == []
    assert model.forked_thread_events == []
    assert model.submitted_user_messages == []
    assert model.initial_user_message == "draft"
    assert model.redraw_requests == 1


def test_side_thread_session_sets_instruction_paths_without_normal_header_or_fork_event():
    model = SessionFlowModel()

    model.handle_side_thread_session(session(forked_from_id="parent", instruction_source_paths=("/a", "/b")))

    assert model.instruction_source_paths == [Path("/a"), Path("/b")]
    assert model.applied_session_info_cells == []
    assert model.forked_thread_events == []
    assert model.thread_id == "thread-1"


def test_same_thread_does_not_reset_recent_review_denials():
    model = SessionFlowModel(thread_id="thread-1")

    model.handle_thread_session(session())

    assert model.review_denial_resets == 0


def test_explicit_collaboration_mode_uses_effective_mode_path():
    model = SessionFlowModel()

    model.handle_thread_session(session(collaboration_mode="plan"))

    assert model.active_collaboration_mask.reasoning_effort == "medium"
    assert model.collaboration_indicator_updates >= 2
    assert model.plan_mode_nudge_refreshes >= 2


def test_redraw_can_be_suppressed_after_session_configured():
    model = SessionFlowModel(suppress_session_configured_redraw=True)

    model.handle_thread_session(session())

    assert model.redraw_requests == 0


def test_emit_forked_thread_event_formats_missing_or_blank_title_by_id():
    model = SessionFlowModel()

    model.emit_forked_thread_event("abc", "  ")

    assert model.emitted_history_lines == ["* Thread forked from abc"]


def test_thread_name_update_only_applies_to_active_thread():
    model = SessionFlowModel(thread_id="thread-1")

    model.on_thread_name_updated("other", "Nope")
    assert model.thread_name is None
    assert model.rename_confirmation_cells == []

    model.on_thread_name_updated("thread-1", "New title")
    assert model.thread_name == "New title"
    assert model.rename_confirmation_cells[0].thread_name == "New title"
    assert model.status_surface_refreshes == 1
    assert model.redraw_requests == 1
    assert model.maybe_send_next_queued_input_calls == 1

    model.on_thread_name_updated("thread-1", None)
    assert model.thread_name is None
    assert len(model.rename_confirmation_cells) == 1
