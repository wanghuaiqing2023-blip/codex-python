from __future__ import annotations

from pycodex.tui.app.thread_session_state import (
    ThreadReadSnapshot,
    session_state_for_thread_read,
    sync_permission_settings_to_cached_sessions,
    sync_service_tier_to_cached_sessions,
    test_thread_session,
)


def test_permission_settings_sync_updates_active_snapshot_without_rewriting_side_thread() -> None:
    main = test_thread_session("main", "/tmp/main")
    side = test_thread_session("side", "/tmp/side").copy_with(
        approval_policy="on-request",
        permission_profile="workspace_write",
    )

    primary, channels = sync_permission_settings_to_cached_sessions(
        active_thread_id="main",
        primary_thread_id="main",
        primary_session=main,
        channel_sessions={"main": main, "side": side},
        approval_policy="on-request",
        approvals_reviewer="auto_review",
        permission_profile="workspace_write",
        active_permission_profile="builtin_workspace",
    )

    assert primary == main.copy_with(
        approval_policy="on-request",
        approvals_reviewer="auto_review",
        permission_profile="workspace_write",
        active_permission_profile="builtin_workspace",
    )
    assert channels["main"] == primary
    assert channels["side"] == side


def test_service_tier_sync_updates_active_cached_session() -> None:
    session = test_thread_session("main", "/tmp/main").copy_with(service_tier="fast")

    primary, channels = sync_service_tier_to_cached_sessions(
        active_thread_id="main",
        primary_thread_id="main",
        primary_session=session,
        channel_sessions={"main": session},
        service_tier=None,
    )

    assert primary == session.copy_with(service_tier=None)
    assert channels["main"] == session.copy_with(service_tier=None)


def test_thread_read_fallback_uses_active_permission_settings_and_clears_cross_thread_fields() -> None:
    primary = test_thread_session("primary", "/tmp/primary").copy_with(
        permission_profile="workspace_write",
        collaboration_mode="pair",
        personality="friendly",
    )
    thread = ThreadReadSnapshot(
        thread_id="read",
        cwd="/tmp/read",
        name="read thread",
        model_provider="read-provider",
        path=None,
    )

    session = session_state_for_thread_read(
        thread_id="read",
        thread=thread,
        primary_session=primary,
        current_model="gpt-test",
        model_provider_id="test-provider",
        service_tier=None,
        approval_policy="never",
        approvals_reviewer="user",
        active_permission_profile="active-from-widget",
        permission_profile="active-widget-profile",
        workspace_roots=["/tmp/read"],
    )

    assert session.thread_id == "read"
    assert session.thread_name == "read thread"
    assert session.model_provider_id == "read-provider"
    assert session.cwd == "/tmp/read"
    assert session.permission_profile == "active-widget-profile"
    assert session.active_permission_profile == "active-from-widget"
    assert session.collaboration_mode is None
    assert session.personality is None


def test_thread_read_with_rollout_path_clears_model_when_session_model_missing() -> None:
    thread = ThreadReadSnapshot(thread_id="read", cwd="/tmp/read", path="/tmp/rollout.jsonl")

    session = session_state_for_thread_read(
        thread_id="read",
        thread=thread,
        primary_session=None,
        current_model="gpt-test",
        model_provider_id="provider",
        service_tier="default",
        approval_policy="never",
        approvals_reviewer="user",
        active_permission_profile=None,
        permission_profile="read_only",
        workspace_roots=["/tmp/read"],
        session_model=None,
    )

    assert session.model == ""
    assert session.rollout_path == "/tmp/rollout.jsonl"
