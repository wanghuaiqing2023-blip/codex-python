"""Thread session-state helpers for Rust ``codex-tui::app::thread_session_state``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_session_state.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_session_state",
    source="codex/codex-rs/tui/src/app/thread_session_state.rs",
)


@dataclass(eq=True)
class ThreadSessionState:
    thread_id: str
    cwd: str
    model: str = "gpt-test"
    model_provider_id: str = "test-provider"
    service_tier: str | None = None
    approval_policy: str = "never"
    approvals_reviewer: str = "user"
    permission_profile: Any = "read_only"
    active_permission_profile: Any | None = None
    thread_name: str | None = None
    runtime_workspace_roots: list[str] | None = None
    instruction_source_paths: list[str] | None = None
    reasoning_effort: Any | None = None
    collaboration_mode: Any | None = None
    personality: Any | None = None
    message_history: Any | None = None
    rollout_path: str | None = None

    def copy_with(self, **updates: Any) -> "ThreadSessionState":
        return replace(self, **updates)


@dataclass(eq=True)
class ThreadReadSnapshot:
    thread_id: str
    cwd: str
    name: str | None = None
    model_provider: str = "test-provider"
    path: str | None = None


def test_thread_session(thread_id: str, cwd: str | Path) -> ThreadSessionState:
    path = str(cwd)
    return ThreadSessionState(
        thread_id=thread_id,
        cwd=path,
        runtime_workspace_roots=[path],
        instruction_source_paths=[],
        rollout_path="",
    )


def sync_service_tier_to_cached_sessions(
    *,
    active_thread_id: str | None,
    primary_thread_id: str | None,
    primary_session: ThreadSessionState | None,
    channel_sessions: dict[str, ThreadSessionState],
    service_tier: str | None,
) -> tuple[ThreadSessionState | None, dict[str, ThreadSessionState]]:
    if active_thread_id is None:
        return primary_session, dict(channel_sessions)
    updated_channels = dict(channel_sessions)
    if primary_thread_id == active_thread_id and primary_session is not None:
        primary_session = primary_session.copy_with(service_tier=service_tier)
    if active_thread_id in updated_channels:
        updated_channels[active_thread_id] = updated_channels[active_thread_id].copy_with(service_tier=service_tier)
    return primary_session, updated_channels


def sync_permission_settings_to_cached_sessions(
    *,
    active_thread_id: str | None,
    primary_thread_id: str | None,
    primary_session: ThreadSessionState | None,
    channel_sessions: dict[str, ThreadSessionState],
    approval_policy: str,
    approvals_reviewer: str,
    permission_profile: Any,
    active_permission_profile: Any | None,
) -> tuple[ThreadSessionState | None, dict[str, ThreadSessionState]]:
    if active_thread_id is None:
        return primary_session, dict(channel_sessions)
    updates = {
        "approval_policy": approval_policy,
        "approvals_reviewer": approvals_reviewer,
        "permission_profile": permission_profile,
        "active_permission_profile": active_permission_profile,
    }
    updated_channels = dict(channel_sessions)
    if primary_thread_id == active_thread_id and primary_session is not None:
        primary_session = primary_session.copy_with(**updates)
    if active_thread_id in updated_channels:
        updated_channels[active_thread_id] = updated_channels[active_thread_id].copy_with(**updates)
    return primary_session, updated_channels


def session_state_for_thread_read(
    *,
    thread_id: str,
    thread: ThreadReadSnapshot | dict[str, Any],
    primary_session: ThreadSessionState | None,
    current_model: str,
    model_provider_id: str,
    service_tier: str | None,
    approval_policy: str,
    approvals_reviewer: str,
    active_permission_profile: Any | None,
    permission_profile: Any,
    workspace_roots: list[str],
    reasoning_effort: Any | None = None,
    session_model: str | None = None,
) -> ThreadSessionState:
    thread_cwd = thread["cwd"] if isinstance(thread, dict) else thread.cwd
    thread_name = thread.get("name") if isinstance(thread, dict) else thread.name
    thread_model_provider = thread.get("model_provider", model_provider_id) if isinstance(thread, dict) else thread.model_provider
    thread_path = thread.get("path") if isinstance(thread, dict) else thread.path
    if primary_session is not None:
        session = primary_session.copy_with()
        if session.thread_id != thread_id:
            session = session.copy_with(collaboration_mode=None, personality=None)
    else:
        session = ThreadSessionState(
            thread_id=thread_id,
            cwd=str(thread_cwd),
            model=current_model,
            model_provider_id=model_provider_id,
            service_tier=service_tier,
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=permission_profile,
            active_permission_profile=active_permission_profile,
            runtime_workspace_roots=list(workspace_roots),
            instruction_source_paths=[],
            reasoning_effort=reasoning_effort,
            rollout_path=thread_path,
        )
    model = session.model
    if session_model is not None:
        model = session_model
    elif thread_path is not None:
        model = ""
    return session.copy_with(
        thread_id=thread_id,
        thread_name=thread_name,
        model=model,
        model_provider_id=thread_model_provider,
        cwd=str(thread_cwd),
        permission_profile=permission_profile,
        active_permission_profile=active_permission_profile,
        instruction_source_paths=[],
        rollout_path=thread_path,
        message_history=None,
    )


async def sync_active_thread_service_tier_to_cached_session(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_session_state.sync_active_thread_service_tier_to_cached_session App/channel path is not ported")


async def sync_active_thread_permission_settings_to_cached_session(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_session_state.sync_active_thread_permission_settings_to_cached_session App/channel path is not ported")


__all__ = [
    "RUST_MODULE",
    "ThreadReadSnapshot",
    "ThreadSessionState",
    "session_state_for_thread_read",
    "sync_active_thread_permission_settings_to_cached_session",
    "sync_active_thread_service_tier_to_cached_session",
    "sync_permission_settings_to_cached_sessions",
    "sync_service_tier_to_cached_sessions",
    "test_thread_session",
]
