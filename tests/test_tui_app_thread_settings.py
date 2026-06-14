from __future__ import annotations

from pycodex.tui.app.thread_settings import (
    CollaborationMode,
    ModeKind,
    ThreadSessionState,
    ThreadSettings,
    ThreadSettingsUpdateParams,
    apply_thread_settings_to_session,
    thread_settings_update_has_changes,
)


def test_thread_settings_update_has_changes_matches_rust_field_list() -> None:
    assert not thread_settings_update_has_changes(ThreadSettingsUpdateParams(thread_id="thread-1"))
    assert thread_settings_update_has_changes(ThreadSettingsUpdateParams(thread_id="thread-1", cwd="/tmp"))
    assert thread_settings_update_has_changes(ThreadSettingsUpdateParams(thread_id="thread-1", effort="high"))
    assert thread_settings_update_has_changes(
        ThreadSettingsUpdateParams(thread_id="thread-1", collaboration_mode=CollaborationMode())
    )


def test_apply_thread_settings_to_session_updates_default_mode_model_and_effort() -> None:
    session = ThreadSessionState(model="old", reasoning_effort="low", cwd="/old")
    settings = ThreadSettings(
        model="new-model",
        model_provider="provider-2",
        service_tier="flex",
        effort="high",
        approval_policy="on-request",
        approvals_reviewer="auto_review",
        sandbox_policy="workspace-write",
        cwd="/tmp/project",
        collaboration_mode=CollaborationMode(mode=ModeKind.Default),
        active_permission_profile="workspace",
        personality="friendly",
    )

    result = apply_thread_settings_to_session(session, settings)

    assert result.model == "new-model"
    assert result.reasoning_effort == "high"
    assert result.model_provider_id == "provider-2"
    assert result.service_tier == "flex"
    assert result.approval_policy == "on-request"
    assert result.approvals_reviewer == "auto_review"
    assert result.permission_profile == {"sandbox_policy": "workspace-write", "cwd": "/tmp/project"}
    assert result.active_permission_profile == "workspace"
    assert result.cwd == "/tmp/project"
    assert result.runtime_workspace_roots == ["/tmp/project"]
    assert result.personality == "friendly"
    assert result.collaboration_mode is not None
    assert result.collaboration_mode.settings.model == "new-model"
    assert result.collaboration_mode.settings.reasoning_effort == "high"


def test_apply_thread_settings_to_session_preserves_model_for_non_default_collaboration_mode() -> None:
    session = ThreadSessionState(model="old", reasoning_effort="low")
    settings = ThreadSettings(
        model="new-model",
        model_provider="provider-2",
        service_tier=None,
        effort="high",
        approval_policy="never",
        approvals_reviewer="user",
        sandbox_policy="read-only",
        cwd="/tmp/project",
        collaboration_mode=CollaborationMode(mode=ModeKind.Other),
    )

    result = apply_thread_settings_to_session(session, settings)

    assert result.model == "old"
    assert result.reasoning_effort == "low"
    assert result.collaboration_mode is not None
    assert result.collaboration_mode.settings.model == "new-model"
    assert result.collaboration_mode.settings.reasoning_effort == "high"
