"""Thread targeting helpers for app-server requests and notifications.

Rust counterpart: ``codex-rs/tui/src/app/app_server_event_targets.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::app_server_event_targets",
    source="codex/codex-rs/tui/src/app/app_server_event_targets.rs",
    status="complete",
)


REQUEST_VARIANTS_WITH_THREAD_ID = {
    "CommandExecutionRequestApproval",
    "FileChangeRequestApproval",
    "ToolRequestUserInput",
    "McpServerElicitationRequest",
    "PermissionsRequestApproval",
    "DynamicToolCall",
}

REQUEST_VARIANTS_WITHOUT_THREAD_ID = {
    "ChatgptAuthTokensRefresh",
    "AttestationGenerate",
    "ApplyPatchApproval",
    "ExecCommandApproval",
}

THREAD_FIELD_NOTIFICATION_VARIANTS = {
    "Error",
    "ThreadStatusChanged",
    "ThreadArchived",
    "ThreadUnarchived",
    "ThreadClosed",
    "ThreadNameUpdated",
    "ThreadTokenUsageUpdated",
    "ThreadGoalUpdated",
    "ThreadGoalCleared",
    "ThreadSettingsUpdated",
    "TurnStarted",
    "HookStarted",
    "TurnCompleted",
    "HookCompleted",
    "TurnDiffUpdated",
    "TurnPlanUpdated",
    "ItemStarted",
    "ItemGuardianApprovalReviewStarted",
    "ItemGuardianApprovalReviewCompleted",
    "ItemCompleted",
    "RawResponseItemCompleted",
    "AgentMessageDelta",
    "PlanDelta",
    "CommandExecutionOutputDelta",
    "TerminalInteraction",
    "FileChangeOutputDelta",
    "FileChangePatchUpdated",
    "ServerRequestResolved",
    "McpToolCallProgress",
    "ReasoningSummaryTextDelta",
    "ReasoningSummaryPartAdded",
    "ReasoningTextDelta",
    "ContextCompacted",
    "ModelRerouted",
    "ModelVerification",
    "ThreadRealtimeStarted",
    "ThreadRealtimeItemAdded",
    "ThreadRealtimeTranscriptDelta",
    "ThreadRealtimeTranscriptDone",
    "ThreadRealtimeOutputAudioDelta",
    "ThreadRealtimeSdp",
    "ThreadRealtimeError",
    "ThreadRealtimeClosed",
    "GuardianWarning",
}

GLOBAL_NOTIFICATION_VARIANTS = {
    "SkillsChanged",
    "McpServerStatusUpdated",
    "McpServerOauthLoginCompleted",
    "AccountUpdated",
    "AccountRateLimitsUpdated",
    "AppListUpdated",
    "RemoteControlStatusChanged",
    "ExternalAgentConfigImportCompleted",
    "DeprecationNotice",
    "ConfigWarning",
    "FuzzyFileSearchSessionUpdated",
    "FuzzyFileSearchSessionCompleted",
    "CommandExecOutputDelta",
    "ProcessOutputDelta",
    "ProcessExited",
    "FsChanged",
    "WindowsWorldWritableWarning",
    "WindowsSandboxSetupCompleted",
    "AccountLoginCompleted",
}


@dataclass(frozen=True)
class ServerNotificationThreadTarget:
    kind: str
    thread_id: str | None = None

    @classmethod
    def Thread(cls, thread_id: Any) -> "ServerNotificationThreadTarget":
        return cls("Thread", _thread_id(thread_id))

    @classmethod
    def InvalidThreadId(cls, thread_id: Any) -> "ServerNotificationThreadTarget":
        return cls("InvalidThreadId", str(thread_id))

    @classmethod
    def Global(cls) -> "ServerNotificationThreadTarget":
        return cls("Global")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _thread_id(value: Any) -> str:
    return str(UUID(str(value)))


def _maybe_thread_id(value: Any) -> str | None:
    try:
        return _thread_id(value)
    except (TypeError, ValueError, AttributeError):
        return None


def _variant_and_payload(value: Any) -> tuple[str | None, Any]:
    variant = _field(value, "type")
    if variant is None:
        variant = _field(value, "variant")
    if variant is None:
        variant = _field(value, "kind")
    if variant is not None:
        return str(variant), _field(value, "params", _field(value, "notification", value))

    if isinstance(value, dict) and len(value) == 1:
        variant, payload = next(iter(value.items()))
        return str(variant), payload

    return value.__class__.__name__ if value is not None else None, value


def _extract_thread_id(payload: Any) -> Any:
    thread_id = _field(payload, "thread_id")
    if thread_id is not None:
        return thread_id
    thread = _field(payload, "thread")
    if thread is not None:
        return _field(thread, "id")
    return None


def server_request_thread_id(request: Any) -> str | None:
    """Return the valid thread id for request variants that carry one."""

    variant, payload = _variant_and_payload(request)
    if variant not in REQUEST_VARIANTS_WITH_THREAD_ID:
        return None
    return _maybe_thread_id(_extract_thread_id(payload))


def server_notification_thread_target(notification: Any) -> ServerNotificationThreadTarget:
    """Classify a notification as thread-targeted, invalid, or global."""

    variant, payload = _variant_and_payload(notification)
    if variant == "ThreadStarted":
        raw_thread_id = _extract_thread_id(payload)
    elif variant == "Warning":
        raw_thread_id = _field(payload, "thread_id")
    elif variant in THREAD_FIELD_NOTIFICATION_VARIANTS:
        raw_thread_id = _extract_thread_id(payload)
    elif variant in GLOBAL_NOTIFICATION_VARIANTS:
        raw_thread_id = None
    else:
        raw_thread_id = None

    if raw_thread_id is None:
        return ServerNotificationThreadTarget.Global()

    parsed = _maybe_thread_id(raw_thread_id)
    if parsed is None:
        return ServerNotificationThreadTarget.InvalidThreadId(raw_thread_id)
    return ServerNotificationThreadTarget.Thread(parsed)


def test_thread_settings() -> dict[str, Any]:
    return {
        "cwd": "/tmp/thread-settings",
        "approval_policy": "never",
        "approvals_reviewer": "user",
        "sandbox_policy": {"read_only": {"network_access": False}},
        "active_permission_profile": None,
        "model": "gpt-5.4",
        "model_provider": "openai",
        "service_tier": None,
        "effort": "high",
        "summary": None,
        "collaboration_mode": {"mode": "default"},
        "personality": None,
    }


def warning_notifications_without_threads_are_global() -> bool:
    notification = {"Warning": {"thread_id": None, "message": "warning"}}
    return server_notification_thread_target(notification) == ServerNotificationThreadTarget.Global()


def warning_notifications_route_to_threads_when_thread_id_is_present() -> bool:
    thread_id = "00000000-0000-0000-0000-000000000401"
    notification = {"Warning": {"thread_id": thread_id, "message": "warning"}}
    return server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(
        thread_id
    )


def guardian_warning_notifications_route_to_threads() -> bool:
    thread_id = "00000000-0000-0000-0000-000000000402"
    notification = {"GuardianWarning": {"thread_id": thread_id, "message": "warning"}}
    return server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(
        thread_id
    )


def thread_settings_updated_notifications_route_to_threads() -> bool:
    thread_id = "00000000-0000-0000-0000-000000000403"
    notification = {
        "ThreadSettingsUpdated": {
            "thread_id": thread_id,
            "thread_settings": test_thread_settings(),
        }
    }
    return server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(
        thread_id
    )


__all__ = [
    "GLOBAL_NOTIFICATION_VARIANTS",
    "REQUEST_VARIANTS_WITH_THREAD_ID",
    "REQUEST_VARIANTS_WITHOUT_THREAD_ID",
    "RUST_MODULE",
    "ServerNotificationThreadTarget",
    "THREAD_FIELD_NOTIFICATION_VARIANTS",
    "guardian_warning_notifications_route_to_threads",
    "server_notification_thread_target",
    "server_request_thread_id",
    "test_thread_settings",
    "thread_settings_updated_notifications_route_to_threads",
    "warning_notifications_route_to_threads_when_thread_id_is_present",
    "warning_notifications_without_threads_are_global",
]
