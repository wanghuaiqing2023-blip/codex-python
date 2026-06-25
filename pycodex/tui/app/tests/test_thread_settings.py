from __future__ import annotations

import asyncio

from pycodex.tui.app.thread_settings import (
    CollaborationMode,
    ModeKind,
    ThreadSessionState,
    ThreadSettings,
    ThreadSettingsUpdateParams,
    active_thread_model_setting_update_params,
    apply_thread_settings_to_session,
    override_turn_context_settings_update_params,
    send_thread_settings_update,
    sync_active_thread_model_setting,
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


def test_active_thread_model_setting_update_params_requires_active_thread() -> None:
    """Rust codex-tui app::thread_settings active_thread_model_setting_update_params branch."""

    assert active_thread_model_setting_update_params({"active_thread_id": None}, "gpt-new") is None

    params = active_thread_model_setting_update_params({"active_thread_id": "thread-1"}, "gpt-new")

    assert params == ThreadSettingsUpdateParams(
        thread_id="thread-1",
        model="gpt-new",
        collaboration_mode=CollaborationMode(),
    )


def test_override_turn_context_settings_update_params_maps_rust_fields() -> None:
    """Rust codex-tui app::thread_settings sync_override_turn_context_settings params mapping."""

    op = {
        "kind": "OverrideTurnContext",
        "cwd": "/tmp/project",
        "approval_policy": "on-request",
        "approvals_reviewer": "auto_review",
        "active_permission_profile": {"id": "workspace"},
        "model": "gpt-5",
        "effort": "high",
        "summary": True,
        "service_tier": "flex",
        "collaboration_mode": CollaborationMode(mode=ModeKind.Other),
        "personality": "friendly",
    }

    params = override_turn_context_settings_update_params("thread-1", op)

    assert params == ThreadSettingsUpdateParams(
        thread_id="thread-1",
        cwd="/tmp/project",
        approval_policy="on-request",
        approvals_reviewer="auto_review",
        permissions="workspace",
        model="gpt-5",
        effort="high",
        summary=True,
        service_tier="flex",
        collaboration_mode=CollaborationMode(mode=ModeKind.Other),
        personality="friendly",
    )


def test_send_thread_settings_update_skips_empty_params() -> None:
    """Rust codex-tui app::thread_settings send_thread_settings_update skips no-op params."""

    class Server:
        def __init__(self) -> None:
            self.calls = []

        async def thread_settings_update(self, params: ThreadSettingsUpdateParams) -> None:
            self.calls.append(params)

    server = Server()

    result = asyncio.run(send_thread_settings_update({}, server, ThreadSettingsUpdateParams(thread_id="thread-1")))

    assert result.sent is False
    assert server.calls == []


def test_sync_active_thread_model_setting_sends_params_to_app_server() -> None:
    """Rust codex-tui app::thread_settings sync_active_thread_model_setting sends changed params."""

    class Server:
        def __init__(self) -> None:
            self.calls = []

        async def thread_settings_update(self, params: ThreadSettingsUpdateParams) -> None:
            self.calls.append(params)

    server = Server()

    result = asyncio.run(sync_active_thread_model_setting({"active_thread_id": "thread-1"}, server, "gpt-new"))

    assert result.sent is True
    assert server.calls == [
        ThreadSettingsUpdateParams(
            thread_id="thread-1",
            model="gpt-new",
            collaboration_mode=CollaborationMode(),
        )
    ]


def test_send_thread_settings_update_records_error_message_on_failure() -> None:
    """Rust codex-tui app::thread_settings send_thread_settings_update reports app-server errors."""

    class Server:
        async def thread_settings_update(self, _params: ThreadSettingsUpdateParams) -> None:
            raise RuntimeError("offline")

    app = {"errors": []}

    result = asyncio.run(
        send_thread_settings_update(app, Server(), ThreadSettingsUpdateParams(thread_id="thread-1", model="gpt-new"))
    )

    assert result.sent is False
    assert result.error_message == "Failed to update thread settings: offline"
    assert app["errors"] == ["Failed to update thread settings: offline"]
