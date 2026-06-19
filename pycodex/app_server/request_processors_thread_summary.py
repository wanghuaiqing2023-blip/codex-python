"""Thread-summary helper projection for ``codex-app-server``.

Rust ``src/request_processors/thread_summary.rs`` owns the local conversion
helpers used by thread list/summary responses: spawn-agent metadata overlay,
thread settings projection, started-notification sanitization, and test-only
conversation-summary materialization.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from pycodex.app_server_protocol import (
    ActivePermissionProfile as ApiActivePermissionProfile,
    ConversationGitInfo,
    ConversationSummary,
    GitInfo as ApiGitInfo,
    SandboxPolicy as ApiSandboxPolicy,
    Thread,
    ThreadSettings,
    ThreadStartedNotification,
    ThreadStatus,
)
from pycodex.app_server_protocol.thread_data import SessionSource as ApiSessionSource
from pycodex.protocol import (
    ActivePermissionProfile,
    CollaborationMode,
    PermissionProfile,
    SessionSource,
    Settings,
    SubAgentSource,
    ThreadSettingsSnapshot,
    USER_MESSAGE_BEGIN,
)


def with_thread_spawn_agent_metadata(
    source: SessionSource,
    agent_nickname: str | None,
    agent_role: str | None,
) -> SessionSource:
    """Overlay rollout metadata onto ``SessionSource::SubAgent(ThreadSpawn)``.

    Rust only applies the overlay when at least one metadata value is present
    and preserves existing per-source values when the external metadata is
    absent.
    """

    if agent_nickname is None and agent_role is None:
        return source
    if not isinstance(source, SessionSource):
        raise TypeError("source must be a SessionSource")
    subagent = source.subagent_source
    if source.type != "subagent" or subagent is None or subagent.type != "thread_spawn":
        return source
    return SessionSource.subagent(
        SubAgentSource.thread_spawn(
            parent_thread_id=subagent.parent_thread_id,
            depth=subagent.depth if subagent.depth is not None else 0,
            agent_path=subagent.agent_path,
            agent_nickname=agent_nickname or subagent.agent_nickname,
            agent_role=agent_role or subagent.agent_role,
        )
    )


def thread_response_active_permission_profile(
    active_permission_profile: ActivePermissionProfile | None,
) -> ApiActivePermissionProfile | None:
    """Map the core active-permission profile into the app-server payload."""

    if active_permission_profile is None:
        return None
    return ApiActivePermissionProfile.from_core(active_permission_profile)


def thread_response_sandbox_policy(
    permission_profile: PermissionProfile,
    cwd: Path | str,
) -> ApiSandboxPolicy:
    """Project a core permission profile through Rust's legacy sandbox bridge."""

    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    legacy_policy = permission_profile.to_legacy_sandbox_policy(Path(cwd))
    return ApiSandboxPolicy.from_core(legacy_policy)


def thread_settings_from_config_snapshot(config_snapshot: Any) -> ThreadSettings:
    """Build app-server ``ThreadSettings`` from a core ``ThreadConfigSnapshot``."""

    cwd = Path(_field(config_snapshot, "cwd"))
    permission_profile = _field(config_snapshot, "permission_profile")
    return _thread_settings(
        cwd=cwd,
        approval_policy=_field(config_snapshot, "approval_policy"),
        approvals_reviewer=_field(config_snapshot, "approvals_reviewer"),
        permission_profile=permission_profile,
        active_permission_profile=_field(config_snapshot, "active_permission_profile", None),
        model=_field(config_snapshot, "model"),
        model_provider=_field(config_snapshot, "model_provider_id"),
        service_tier=_field(config_snapshot, "service_tier", None),
        reasoning_effort=_field(config_snapshot, "reasoning_effort", None),
        reasoning_summary=_field(config_snapshot, "reasoning_summary", None),
        collaboration_mode=_field(config_snapshot, "collaboration_mode"),
        personality=_field(config_snapshot, "personality", None),
    )


def thread_settings_from_core_snapshot(snapshot: ThreadSettingsSnapshot) -> ThreadSettings:
    """Build app-server ``ThreadSettings`` from a protocol settings snapshot."""

    if not isinstance(snapshot, ThreadSettingsSnapshot):
        raise TypeError("snapshot must be a ThreadSettingsSnapshot")
    return _thread_settings(
        cwd=snapshot.cwd,
        approval_policy=snapshot.approval_policy,
        approvals_reviewer=snapshot.approvals_reviewer,
        permission_profile=snapshot.permission_profile,
        active_permission_profile=snapshot.active_permission_profile,
        model=snapshot.model,
        model_provider=snapshot.model_provider_id,
        service_tier=snapshot.service_tier,
        reasoning_effort=snapshot.reasoning_effort,
        reasoning_summary=snapshot.reasoning_summary,
        collaboration_mode=snapshot.collaboration_mode,
        personality=snapshot.personality,
    )


def thread_started_notification(thread: Thread) -> ThreadStartedNotification:
    """Return a started notification with thread turns cleared."""

    if not isinstance(thread, Thread):
        thread = Thread.from_mapping(thread)
    return ThreadStartedNotification(thread=replace(thread, turns=()))


def extract_conversation_summary(
    path: Path | str,
    head: Iterable[Mapping[str, Any]],
    session_meta: Mapping[str, Any],
    git: Mapping[str, Any] | None,
    fallback_provider: str,
    updated_at: str | None,
) -> ConversationSummary | None:
    """Extract the first user-message preview from rollout head items."""

    preview = _first_user_message(head)
    if preview is None:
        return None
    index = preview.find(USER_MESSAGE_BEGIN)
    if index >= 0:
        preview = preview[index + len(USER_MESSAGE_BEGIN) :].strip()
    timestamp = _optional_non_empty(session_meta.get("timestamp"))
    provider = session_meta.get("model_provider") or fallback_provider
    return ConversationSummary(
        conversation_id=session_meta["id"],
        timestamp=timestamp,
        updated_at=updated_at or timestamp,
        path=Path(path),
        preview=preview,
        model_provider=str(provider),
        cwd=Path(session_meta["cwd"]),
        cli_version=str(session_meta["cli_version"]),
        source=_core_session_source(session_meta.get("source")),
        git_info=map_git_info(git) if git is not None else None,
    )


def map_git_info(git_info: Mapping[str, Any]) -> ConversationGitInfo:
    """Map core rollout git metadata into conversation-summary git info."""

    return ConversationGitInfo(
        sha=git_info.get("commit_hash") or git_info.get("sha"),
        branch=git_info.get("branch"),
        origin_url=git_info.get("repository_url") or git_info.get("origin_url"),
    )


def summary_to_thread(summary: ConversationSummary, fallback_cwd: Path | str) -> Thread:
    """Materialize an app-server ``Thread`` from a conversation summary."""

    if not isinstance(summary, ConversationSummary):
        summary = ConversationSummary.from_mapping(summary)
    created_at = _unix_timestamp(summary.timestamp)
    updated_at = _unix_timestamp(summary.updated_at) or created_at
    cwd = _normalized_absolute_path(summary.cwd, fallback_cwd)
    thread_id = str(summary.conversation_id)
    source = _api_session_source(summary.source)
    return Thread(
        id=thread_id,
        session_id=thread_id,
        forked_from_id=None,
        preview=summary.preview,
        ephemeral=False,
        model_provider=summary.model_provider,
        created_at=created_at,
        updated_at=updated_at,
        status=ThreadStatus.not_loaded(),
        path=summary.path if str(summary.path) else None,
        cwd=cwd,
        cli_version=summary.cli_version,
        agent_nickname=summary.source.get_nickname(),
        agent_role=summary.source.get_agent_role(),
        source=source,
        thread_source=None,
        git_info=_api_git_info(summary.git_info),
        name=None,
        turns=(),
    )


def _thread_settings(
    *,
    cwd: Path | str,
    approval_policy: Any,
    approvals_reviewer: Any,
    permission_profile: PermissionProfile,
    active_permission_profile: ActivePermissionProfile | None,
    model: str,
    model_provider: str,
    service_tier: str | None,
    reasoning_effort: Any,
    reasoning_summary: Any,
    collaboration_mode: Any,
    personality: Any,
) -> ThreadSettings:
    return ThreadSettings(
        cwd=Path(cwd),
        approval_policy=_wire_value(approval_policy),
        approvals_reviewer=_wire_value(approvals_reviewer),
        sandbox_policy=thread_response_sandbox_policy(permission_profile, cwd),
        active_permission_profile=thread_response_active_permission_profile(active_permission_profile),
        model=model,
        model_provider=model_provider,
        service_tier=service_tier,
        effort=_wire_value(reasoning_effort),
        summary=_wire_value(reasoning_summary),
        collaboration_mode=_wire_value(collaboration_mode),
        personality=_wire_value(personality),
    )


def _field(value: Any, name: str, default: Any = ...):
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    else:
        marker = object()
        found = getattr(value, name, marker)
        if found is not marker:
            return found
    if default is ...:
        raise AttributeError(name)
    return default


def _wire_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, CollaborationMode):
        return {
            "mode": value.mode.value,
            "settings": {
                "model": value.settings.model,
                "reasoning_effort": (
                    value.settings.reasoning_effort.value
                    if value.settings.reasoning_effort is not None
                    else None
                ),
                "developer_instructions": value.settings.developer_instructions,
            },
        }
    if isinstance(value, Settings):
        return {
            "model": value.model,
            "reasoning_effort": value.reasoning_effort.value if value.reasoning_effort is not None else None,
            "developer_instructions": value.developer_instructions,
        }
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    return getattr(value, "value", value)


def _first_user_message(head: Iterable[Mapping[str, Any]]) -> str | None:
    first_user_message: str | None = None
    for item in head:
        if item.get("type") != "message" or item.get("role") != "user":
            continue
        content = item.get("content")
        message: str | None = None
        if isinstance(content, str):
            message = content
        elif isinstance(content, list):
            parts = [
                part.get("text")
                for part in content
                if isinstance(part, Mapping) and part.get("type") == "input_text" and isinstance(part.get("text"), str)
            ]
            if parts:
                message = "".join(parts)
        if message is None:
            continue
        if USER_MESSAGE_BEGIN in message:
            return message
        if first_user_message is None:
            first_user_message = message
    return first_user_message


def _optional_non_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _core_session_source(value: Any) -> SessionSource:
    if value is None:
        return SessionSource.vscode()
    if isinstance(value, SessionSource):
        return value
    if isinstance(value, str):
        return SessionSource.from_startup_arg(value)
    raise TypeError("session_meta source must be a core SessionSource or string")


def _unix_timestamp(value: str | None) -> int:
    if not value:
        return 0
    normalized = value.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp())


def _normalized_absolute_path(path: Path | str, fallback: Path | str) -> Path:
    candidate = Path(path)
    try:
        return candidate if candidate.is_absolute() else candidate.resolve()
    except OSError:
        return Path(fallback)


def _api_git_info(git_info: ConversationGitInfo | None) -> ApiGitInfo | None:
    if git_info is None:
        return None
    return ApiGitInfo(sha=git_info.sha, branch=git_info.branch, origin_url=git_info.origin_url)


def _api_session_source(source: SessionSource) -> ApiSessionSource:
    if source.type == "cli":
        return ApiSessionSource.cli()
    if source.type == "vscode":
        return ApiSessionSource.vscode()
    if source.type == "exec":
        return ApiSessionSource.exec()
    if source.type == "mcp":
        return ApiSessionSource.app_server()
    if source.type == "custom":
        return ApiSessionSource.custom(source.custom or "")
    if source.type == "subagent":
        payload = _subagent_source_payload(source.subagent_source)
        return ApiSessionSource.sub_agent(payload)
    return ApiSessionSource.unknown()


def _subagent_source_payload(source: SubAgentSource | None) -> Any:
    if source is None:
        return None
    if source.type == "thread_spawn":
        payload: dict[str, Any] = {
            "parent_thread_id": str(source.parent_thread_id),
            "depth": source.depth,
        }
        if source.agent_path is not None:
            payload["agent_path"] = str(source.agent_path)
        if source.agent_nickname is not None:
            payload["agent_nickname"] = source.agent_nickname
        if source.agent_role is not None:
            payload["agent_role"] = source.agent_role
        return {"thread_spawn": payload}
    if source.type == "other":
        return {"other": source.other or ""}
    return source.type


__all__ = [
    "extract_conversation_summary",
    "map_git_info",
    "summary_to_thread",
    "thread_response_active_permission_profile",
    "thread_response_sandbox_policy",
    "thread_settings_from_config_snapshot",
    "thread_settings_from_core_snapshot",
    "thread_started_notification",
    "with_thread_spawn_agent_metadata",
]
