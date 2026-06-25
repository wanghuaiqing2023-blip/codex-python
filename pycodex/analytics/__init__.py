"""Source-verified public interface slice for ``codex-analytics``.

Rust source:
- ``codex/codex-rs/analytics/src/lib.rs``
- ``codex/codex-rs/analytics/src/accepted_lines.rs``
- ``codex/codex-rs/analytics/src/facts.rs``
- ``codex/codex-rs/analytics/src/events.rs``
"""

from __future__ import annotations

import hashlib
import http.client
import json
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_ORIGINATOR = "codex_cli_rs"
ANALYTICS_EVENT_DEDUPE_MAX_KEYS = 4096
ANALYTICS_EVENTS_TIMEOUT_SECONDS = 15


def now_unix_seconds() -> int:
    return int(time.time())


def now_unix_millis() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class AcceptedLineFingerprint:
    path_hash: str
    line_hash: str


@dataclass(frozen=True)
class AcceptedLineFingerprintSummary:
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]


@dataclass(frozen=True)
class AcceptedLineFingerprintEventInput:
    event_type: str
    turn_id: str
    thread_id: str
    product_surface: str | None
    model_slug: str | None
    completed_at: int
    repo_hash: str | None
    accepted_added_lines: int
    accepted_deleted_lines: int
    line_fingerprints: list[AcceptedLineFingerprint]


def fingerprint_hash(domain: str, value: str) -> str:
    hasher = hashlib.sha1()
    hasher.update(b"file-line-v1\0")
    hasher.update(domain.encode())
    hasher.update(b"\0")
    hasher.update(value.encode())
    return hasher.hexdigest()


def accepted_line_fingerprints_from_unified_diff(unified_diff: str) -> AcceptedLineFingerprintSummary:
    current_path: str | None = None
    in_hunk = False
    accepted_added_lines = 0
    accepted_deleted_lines = 0
    fingerprints: list[AcceptedLineFingerprint] = []
    for line in unified_diff.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk and line.startswith("+++ "):
            current_path = _normalize_diff_path(line[4:])
            continue
        if not in_hunk and line.startswith("--- "):
            continue
        if line.startswith("+"):
            accepted_added_lines += 1
            if current_path is not None:
                normalized = _normalize_effective_line(line[1:])
                if normalized is not None:
                    fingerprints.append(AcceptedLineFingerprint(fingerprint_hash("path", current_path), fingerprint_hash("line", normalized)))
            continue
        if line.startswith("-"):
            accepted_deleted_lines += 1
    return AcceptedLineFingerprintSummary(accepted_added_lines, accepted_deleted_lines, fingerprints)


def accepted_line_fingerprint_event_requests(
    input: AcceptedLineFingerprintEventInput,
) -> list[dict[str, Any]]:
    return [
        {
            "event_type": "codex_accepted_line_fingerprints",
            "event_params": {
                "event_type": input.event_type,
                "turn_id": input.turn_id,
                "thread_id": input.thread_id,
                "product_surface": input.product_surface,
                "model_slug": input.model_slug,
                "completed_at": input.completed_at,
                "repo_hash": input.repo_hash,
                "accepted_added_lines": input.accepted_added_lines,
                "accepted_deleted_lines": input.accepted_deleted_lines,
                "line_fingerprints": [],
            },
        }
    ]


ANALYTICS_RELEVANT_CLIENT_REQUEST_KINDS = frozenset(("TurnStart", "TurnSteer"))
ANALYTICS_RELEVANT_CLIENT_RESPONSE_KINDS = frozenset(
    ("ThreadStart", "ThreadResume", "ThreadFork", "TurnStart", "TurnSteer")
)
ANALYTICS_RELEVANT_NOTIFICATION_KINDS = frozenset(
    (
        "TurnStarted",
        "TurnCompleted",
        "TurnDiffUpdated",
        "ItemStarted",
        "ItemCompleted",
        "ItemGuardianApprovalReviewStarted",
        "ItemGuardianApprovalReviewCompleted",
    )
)


def should_send_in_isolated_request(event: dict[str, Any] | Any) -> bool:
    return _event_type(event) == "codex_accepted_line_fingerprints"


def track_event_request_batches(events: list[dict[str, Any] | Any]) -> list[list[dict[str, Any] | Any]]:
    batches: list[list[dict[str, Any] | Any]] = []
    current_batch: list[dict[str, Any] | Any] = []
    for event in events:
        if should_send_in_isolated_request(event):
            if current_batch:
                batches.append(current_batch)
                current_batch = []
            batches.append([event])
        else:
            current_batch.append(event)
    if current_batch:
        batches.append(current_batch)
    return batches


def send_track_events(auth: Any, base_url: str, events: list[dict[str, Any] | Any]) -> list[int]:
    if not events:
        return []
    resolved_auth = _resolve_auth(auth)
    if resolved_auth is None:
        return []
    if not _uses_codex_backend(resolved_auth):
        return []
    url = f"{base_url.rstrip('/')}/codex/analytics-events/events"
    statuses: list[int] = []
    for batch in track_event_request_batches(events):
        status = send_track_events_request(resolved_auth, url, batch)
        if status is not None:
            statuses.append(status)
    return statuses


def send_track_events_request(auth: Any, url: str, events: list[dict[str, Any] | Any]) -> int | None:
    if not events:
        return None
    body = json.dumps({"events": [_jsonable_event(event) for event in events]}, separators=(",", ":")).encode("utf-8")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid analytics endpoint: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = _auth_headers(resolved_auth=auth)
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(body))
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, parsed.port, timeout=ANALYTICS_EVENTS_TIMEOUT_SECONDS)
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()


def analytics_relevant_client_request(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_CLIENT_REQUEST_KINDS


def analytics_relevant_client_response(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_CLIENT_RESPONSE_KINDS


def analytics_relevant_notification(kind: str) -> bool:
    return kind in ANALYTICS_RELEVANT_NOTIFICATION_KINDS


def plugin_state_event_type(state: PluginState | str) -> str:
    state_value = _enum_value(state)
    return {
        PluginState.INSTALLED.value: "codex_plugin_installed",
        PluginState.UNINSTALLED.value: "codex_plugin_uninstalled",
        PluginState.ENABLED.value: "codex_plugin_enabled",
        PluginState.DISABLED.value: "codex_plugin_disabled",
    }[state_value]


def codex_app_metadata(
    tracking: TrackEventsContext,
    app: AppInvocation,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    return {
        "connector_id": app.connector_id,
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "app_name": app.app_name,
        "product_client_id": product_client_id,
        "invoke_type": _enum_value(app.invocation_type),
        "model_slug": tracking.model_slug,
    }


def codex_plugin_metadata(
    plugin: PluginTelemetryMetadata,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    summary = plugin.capability_summary
    return {
        "plugin_id": plugin.remote_plugin_id or plugin.plugin_id.as_key(),
        "plugin_name": plugin.plugin_id.plugin_name,
        "marketplace_name": plugin.plugin_id.marketplace_name,
        "has_skills": None if summary is None else summary.has_skills,
        "mcp_server_count": None if summary is None else len(summary.mcp_server_names),
        "connector_ids": None if summary is None else list(summary.app_connector_ids),
        "product_client_id": product_client_id,
    }


def codex_plugin_used_metadata(
    tracking: TrackEventsContext,
    plugin: PluginTelemetryMetadata,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    return {
        **codex_plugin_metadata(plugin, product_client_id=product_client_id),
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "model_slug": tracking.model_slug,
    }


def codex_hook_run_metadata(tracking: TrackEventsContext, hook: HookRunFact) -> dict[str, Any]:
    return {
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "model_slug": tracking.model_slug,
        "hook_name": analytics_hook_event_name(hook.event_name),
        "hook_source": analytics_hook_source(hook.hook_source),
        "status": analytics_hook_status(hook.status),
    }


def app_mentioned_event(tracking: TrackEventsContext, app: AppInvocation) -> dict[str, Any]:
    return {
        "event_type": "codex_app_mentioned",
        "event_params": codex_app_metadata(tracking, app),
    }


def app_used_event(tracking: TrackEventsContext, app: AppInvocation) -> dict[str, Any]:
    return {
        "event_type": "codex_app_used",
        "event_params": codex_app_metadata(tracking, app),
    }


def plugin_used_event(tracking: TrackEventsContext, plugin: PluginTelemetryMetadata) -> dict[str, Any]:
    return {
        "event_type": "codex_plugin_used",
        "event_params": codex_plugin_used_metadata(tracking, plugin),
    }


def plugin_management_event(state: PluginState | str, plugin: PluginTelemetryMetadata) -> dict[str, Any]:
    return {
        "event_type": plugin_state_event_type(state),
        "event_params": codex_plugin_metadata(plugin),
    }


def hook_run_event(tracking: TrackEventsContext, hook: HookRunFact) -> dict[str, Any]:
    return {
        "event_type": "codex_hook_run",
        "event_params": codex_hook_run_metadata(tracking, hook),
    }


def skill_invocation_event(
    tracking: TrackEventsContext,
    invocation: SkillInvocation,
    *,
    repo_url: str | None = None,
    repo_root: Path | str | None = None,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    return {
        "event_type": "skill_invocation",
        "skill_id": skill_id_for_local_skill(
            repo_url,
            None if repo_root is None else Path(repo_root),
            invocation.skill_path,
            invocation.skill_name,
        ),
        "skill_name": invocation.skill_name,
        "event_params": {
            "product_client_id": product_client_id,
            "skill_scope": analytics_skill_scope(invocation.skill_scope),
            "plugin_id": invocation.plugin_id,
            "repo_url": repo_url,
            "thread_id": tracking.thread_id,
            "turn_id": tracking.turn_id,
            "invoke_type": _enum_value(invocation.invocation_type),
            "model_slug": tracking.model_slug,
        },
    }


def skill_id_for_local_skill(
    repo_url: str | None,
    repo_root: Path | None,
    skill_path: Path | str,
    skill_name: str,
) -> str:
    normalized_path = normalize_path_for_skill_id(repo_url, repo_root, Path(skill_path))
    prefix = f"repo_{repo_url}" if repo_url is not None else "personal"
    raw_id = f"{prefix}_{normalized_path}_{skill_name}"
    return hashlib.sha1(raw_id.encode()).hexdigest()


def normalize_path_for_skill_id(repo_url: str | None, repo_root: Path | None, skill_path: Path) -> str:
    resolved_path = _canonical_or_self(skill_path)
    if repo_url is not None and repo_root is not None:
        resolved_root = _canonical_or_self(repo_root)
        try:
            resolved_path = resolved_path.relative_to(resolved_root)
        except ValueError:
            pass
    return str(resolved_path).replace("\\", "/")


def analytics_skill_scope(scope: Any) -> str:
    value = _enum_value(scope)
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"user", "repo", "system", "admin"}:
            return lowered
    raise ValueError(f"unknown skill scope: {scope!r}")


def analytics_hook_event_name(event_name: HookEventName | str) -> str:
    return event_name.value if isinstance(event_name, HookEventName) else str(event_name)


def analytics_hook_source(source: HookSource | str) -> str:
    return _enum_value(source)


def analytics_hook_status(status: HookRunStatus | str) -> str:
    return _enum_value(status)


def _event_type(event: dict[str, Any] | Any) -> str | None:
    if isinstance(event, dict):
        value = event.get("event_type")
        return value if isinstance(value, str) else None
    value = getattr(event, "event_type", None)
    return value if isinstance(value, str) else None


def _jsonable_event(event: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    to_json_dict = getattr(event, "to_json_dict", None)
    if callable(to_json_dict):
        value = to_json_dict()
        if isinstance(value, dict):
            return value
    if hasattr(event, "__dict__"):
        return dict(vars(event))
    raise TypeError(f"analytics event is not JSON serializable: {event!r}")


def _resolve_auth(auth: Any) -> Any | None:
    if auth is None:
        return None
    auth_method = getattr(auth, "auth", None)
    if callable(auth_method):
        return auth_method()
    return auth


def _uses_codex_backend(auth: Any) -> bool:
    uses_codex_backend = getattr(auth, "uses_codex_backend", None)
    if callable(uses_codex_backend):
        return bool(uses_codex_backend())
    if isinstance(auth, dict) and "uses_codex_backend" in auth:
        return bool(auth["uses_codex_backend"])
    return bool(getattr(auth, "codex_backend", False))


def _auth_headers(resolved_auth: Any) -> dict[str, str]:
    for name in ("to_auth_headers", "auth_headers", "headers"):
        value = getattr(resolved_auth, name, None)
        if callable(value):
            return {str(key): str(header_value) for key, header_value in value().items()}
        if isinstance(value, dict):
            return {str(key): str(header_value) for key, header_value in value.items()}
    if isinstance(resolved_auth, dict):
        headers = resolved_auth.get("headers")
        if isinstance(headers, dict):
            return {str(key): str(value) for key, value in headers.items()}
        token = resolved_auth.get("token") or resolved_auth.get("access_token")
        if token is not None:
            return {"Authorization": f"Bearer {token}"}
    token = getattr(resolved_auth, "token", None) or getattr(resolved_auth, "access_token", None)
    if token is not None:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _enum_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    return value


def _non_negative_int_or_none(value: int) -> int | None:
    return value if value >= 0 else None


def count_input_images(input_items: list[Any]) -> int:
    count = 0
    for item in input_items:
        if isinstance(item, dict):
            item_type = item.get("type") or item.get("kind")
        else:
            item_type = getattr(item, "type", None) or getattr(item, "kind", None) or item.__class__.__name__
        if str(item_type) in {"Image", "LocalImage", "image", "local_image"}:
            count += 1
    return count


def analytics_turn_status(status: TurnStatus | str | None) -> TurnStatus | str | None:
    value = _enum_value(status)
    if value in {TurnStatus.COMPLETED.value, TurnStatus.FAILED.value, TurnStatus.INTERRUPTED.value}:
        return value
    if value in {"InProgress", "in_progress", None}:
        return None
    return value


def _json_value(value: Any) -> Any:
    value = _enum_value(value)
    if isinstance(value, dict):
        return {str(key): _json_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(inner) for inner in value]
    return value


def _normalize_diff_path(path: str) -> str | None:
    path = path.strip()
    if path == "/dev/null":
        return None
    return path[2:] if path.startswith(("a/", "b/")) else path


def _normalize_effective_line(line: str) -> str | None:
    normalized = " ".join(line.split())
    if len(normalized) <= 3:
        return None
    if not any(ch.isalnum() or ch == "_" for ch in normalized):
        return None
    return normalized


def _canonical_or_self(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path


def build_track_events_context(model_slug: str, thread_id: str, turn_id: str) -> "TrackEventsContext":
    return TrackEventsContext(model_slug, thread_id, turn_id)


@dataclass(frozen=True)
class TrackEventsContext:
    model_slug: str
    thread_id: str
    turn_id: str


class _SnakeEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class AppServerRpcTransport(_SnakeEnum):
    STDIO = "stdio"
    WEBSOCKET = "websocket"
    IN_PROCESS = "in_process"


class GuardianReviewDecision(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"


class GuardianReviewTerminalStatus(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"
    FAILED_CLOSED = "failed_closed"


class GuardianReviewFailureReason(_SnakeEnum):
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROMPT_BUILD_ERROR = "prompt_build_error"
    SESSION_ERROR = "session_error"
    PARSE_ERROR = "parse_error"


class GuardianReviewSessionKind(_SnakeEnum):
    TRUNK_NEW = "trunk_new"
    TRUNK_REUSED = "trunk_reused"
    EPHEMERAL_FORKED = "ephemeral_forked"


class GuardianApprovalRequestSource(_SnakeEnum):
    MAIN_TURN = "main_turn"
    DELEGATED_SUBAGENT = "delegated_subagent"


class ReviewStatus(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"


class ReviewResolution(_SnakeEnum):
    NONE = "none"
    SESSION_APPROVAL = "session_approval"
    EXEC_POLICY_AMENDMENT = "exec_policy_amendment"
    NETWORK_POLICY_AMENDMENT = "network_policy_amendment"


class FinalApprovalOutcome(_SnakeEnum):
    UNKNOWN = "unknown"
    NOT_NEEDED = "not_needed"
    CONFIG_ALLOWED = "config_allowed"
    POLICY_FORBIDDEN = "policy_forbidden"
    GUARDIAN_APPROVED = "guardian_approved"
    GUARDIAN_DENIED = "guardian_denied"
    GUARDIAN_ABORTED = "guardian_aborted"
    USER_APPROVED = "user_approved"
    USER_APPROVED_FOR_SESSION = "user_approved_for_session"
    USER_DENIED = "user_denied"
    USER_ABORTED = "user_aborted"


class ToolItemTerminalStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    INTERRUPTED = "interrupted"


class ToolItemFailureKind(_SnakeEnum):
    TOOL_ERROR = "tool_error"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_ABORTED = "approval_aborted"
    SANDBOX_DENIED = "sandbox_denied"
    POLICY_FORBIDDEN = "policy_forbidden"


class CommandExecutionSource(str, Enum):
    AGENT = "agent"
    USER_SHELL = "userShell"
    UNIFIED_EXEC_STARTUP = "unifiedExecStartup"
    UNIFIED_EXEC_INTERACTION = "unifiedExecInteraction"


class WebSearchActionKind(_SnakeEnum):
    SEARCH = "search"
    OPEN_PAGE = "open_page"
    FIND_IN_PAGE = "find_in_page"
    OTHER = "other"


class GuardianApprovalReviewStatus(str, Enum):
    IN_PROGRESS = "InProgress"
    APPROVED = "Approved"
    DENIED = "Denied"
    TIMED_OUT = "TimedOut"
    ABORTED = "Aborted"


class ReviewSubjectKind(_SnakeEnum):
    COMMAND_EXECUTION = "command_execution"
    FILE_CHANGE = "file_change"
    MCP_TOOL_CALL = "mcp_tool_call"
    PERMISSIONS = "permissions"
    NETWORK_ACCESS = "network_access"


class Reviewer(_SnakeEnum):
    GUARDIAN = "guardian"
    USER = "user"


class ReviewTrigger(_SnakeEnum):
    INITIAL = "initial"
    SANDBOX_DENIAL = "sandbox_denial"
    NETWORK_POLICY_DENIAL = "network_policy_denial"
    EXECVE_INTERCEPT = "execve_intercept"


def guardian_review_result(
    status: GuardianApprovalReviewStatus | str,
) -> tuple[ReviewStatus, ReviewResolution] | None:
    value = _enum_value(status)
    if value in {GuardianApprovalReviewStatus.IN_PROGRESS.value, "in_progress"}:
        return None
    if value in {GuardianApprovalReviewStatus.APPROVED.value, ReviewStatus.APPROVED.value}:
        return (ReviewStatus.APPROVED, ReviewResolution.NONE)
    if value in {GuardianApprovalReviewStatus.DENIED.value, ReviewStatus.DENIED.value}:
        return (ReviewStatus.DENIED, ReviewResolution.NONE)
    if value in {GuardianApprovalReviewStatus.TIMED_OUT.value, ReviewStatus.TIMED_OUT.value}:
        return (ReviewStatus.TIMED_OUT, ReviewResolution.NONE)
    if value in {GuardianApprovalReviewStatus.ABORTED.value, ReviewStatus.ABORTED.value}:
        return (ReviewStatus.ABORTED, ReviewResolution.NONE)
    raise ValueError(f"unknown guardian review status: {status!r}")


def _permission_profile_empty(permissions: Any) -> bool:
    if permissions is None:
        return True
    if not isinstance(permissions, dict):
        return False
    return not any(value is not None for value in permissions.values())


def effective_permissions_review_result(response: dict[str, Any]) -> tuple[ReviewStatus, ReviewResolution]:
    permissions = response.get("permissions") if isinstance(response, dict) else None
    if _permission_profile_empty(permissions):
        return (ReviewStatus.DENIED, ReviewResolution.NONE)
    scope = response.get("scope") if isinstance(response, dict) else None
    scope_value = _enum_value(scope)
    if scope_value in {"Session", "session"}:
        return (ReviewStatus.APPROVED, ReviewResolution.SESSION_APPROVAL)
    return (ReviewStatus.APPROVED, ReviewResolution.NONE)


def _action_type(action: dict[str, Any]) -> str:
    return str(action.get("type") or action.get("kind") or action.get("action") or "")


def _request_permissions_network_enabled(permissions: dict[str, Any] | None) -> bool:
    if not isinstance(permissions, dict):
        return False
    network = permissions.get("network")
    if not isinstance(network, dict):
        return False
    return bool(network.get("enabled"))


def guardian_review_subject_metadata(
    action: dict[str, Any],
) -> tuple[ReviewSubjectKind, str, ReviewTrigger]:
    action_type = _action_type(action)
    if action_type in {"command", "command_execution"}:
        return (ReviewSubjectKind.COMMAND_EXECUTION, "command_execution", ReviewTrigger.INITIAL)
    if action_type == "execve":
        return (ReviewSubjectKind.COMMAND_EXECUTION, "command_execution", ReviewTrigger.EXECVE_INTERCEPT)
    if action_type in {"apply_patch", "file_change"}:
        return (ReviewSubjectKind.FILE_CHANGE, "apply_patch", ReviewTrigger.SANDBOX_DENIAL)
    if action_type == "network_access":
        return (ReviewSubjectKind.NETWORK_ACCESS, "network_access", ReviewTrigger.NETWORK_POLICY_DENIAL)
    if action_type == "request_permissions":
        permissions = action.get("permissions") if isinstance(action.get("permissions"), dict) else {}
        if _request_permissions_network_enabled(permissions):
            trigger = ReviewTrigger.NETWORK_POLICY_DENIAL
        elif permissions.get("file_system") is not None:
            trigger = ReviewTrigger.SANDBOX_DENIAL
        else:
            trigger = ReviewTrigger.INITIAL
        return (ReviewSubjectKind.PERMISSIONS, "permissions", trigger)
    if action_type in {"mcp_tool_call", "mcp"}:
        tool_name = str(action.get("tool_name") or action.get("tool") or "")
        return (ReviewSubjectKind.MCP_TOOL_CALL, tool_name, ReviewTrigger.INITIAL)
    raise ValueError(f"unknown guardian review action type: {action_type!r}")


def guardian_review_requested_additional_permissions(action: dict[str, Any]) -> bool:
    action_type = _action_type(action)
    if action_type in {"apply_patch", "file_change", "network_access"}:
        return True
    if action_type == "request_permissions":
        permissions = action.get("permissions") if isinstance(action.get("permissions"), dict) else {}
        return _request_permissions_network_enabled(permissions) or permissions.get("file_system") is not None
    if action_type in {"command", "command_execution", "execve", "mcp_tool_call", "mcp"}:
        return False
    raise ValueError(f"unknown guardian review action type: {action_type!r}")


def guardian_review_requested_network_access(action: dict[str, Any]) -> bool:
    action_type = _action_type(action)
    if action_type == "network_access":
        return True
    if action_type == "request_permissions":
        permissions = action.get("permissions") if isinstance(action.get("permissions"), dict) else {}
        return _request_permissions_network_enabled(permissions)
    if action_type in {"apply_patch", "file_change", "command", "command_execution", "execve", "mcp_tool_call", "mcp"}:
        return False
    raise ValueError(f"unknown guardian review action type: {action_type!r}")


class TurnSubmissionType(_SnakeEnum):
    DEFAULT = "default"
    QUEUED = "queued"


class ThreadInitializationMode(_SnakeEnum):
    NEW = "new"
    FORKED = "forked"
    RESUMED = "resumed"


class TurnStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class TurnSteerResult(_SnakeEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TurnSteerRejectionReason(_SnakeEnum):
    NO_ACTIVE_TURN = "no_active_turn"
    EXPECTED_TURN_MISMATCH = "expected_turn_mismatch"
    NON_STEERABLE_REVIEW = "non_steerable_review"
    NON_STEERABLE_COMPACT = "non_steerable_compact"
    EMPTY_INPUT = "empty_input"
    INPUT_TOO_LARGE = "input_too_large"


class InvocationType(str, Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"


class SkillScope(str, Enum):
    USER = "user"
    REPO = "repo"
    SYSTEM = "system"
    ADMIN = "admin"


class CompactionTrigger(_SnakeEnum):
    MANUAL = "manual"
    AUTO = "auto"


class CompactionReason(_SnakeEnum):
    USER_REQUESTED = "user_requested"
    CONTEXT_LIMIT = "context_limit"
    MODEL_DOWNSHIFT = "model_downshift"


class CompactionImplementation(_SnakeEnum):
    RESPONSES = "responses"
    RESPONSES_COMPACTION_V2 = "responses_compaction_v2"
    RESPONSES_COMPACT = "responses_compact"


class CompactionPhase(_SnakeEnum):
    STANDALONE_TURN = "standalone_turn"
    PRE_TURN = "pre_turn"
    MID_TURN = "mid_turn"


class CompactionStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CompactionStrategy(_SnakeEnum):
    MEMENTO = "memento"
    PREFIX_COMPACTION = "prefix_compaction"


class TurnSteerRequestError(Enum):
    NO_ACTIVE_TURN = "no_active_turn"
    EXPECTED_TURN_MISMATCH = "expected_turn_mismatch"
    NON_STEERABLE_REVIEW = "non_steerable_review"
    NON_STEERABLE_COMPACT = "non_steerable_compact"


class InputError(Enum):
    EMPTY = "empty"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class AnalyticsJsonRpcError:
    kind: str
    error: TurnSteerRequestError | InputError

    @classmethod
    def turn_steer(cls, error: TurnSteerRequestError) -> "AnalyticsJsonRpcError":
        return cls("TurnSteer", error)

    @classmethod
    def input(cls, error: InputError) -> "AnalyticsJsonRpcError":
        return cls("Input", error)


def turn_steer_rejection_reason_from_error(
    error: TurnSteerRequestError | InputError | AnalyticsJsonRpcError,
) -> TurnSteerRejectionReason:
    if isinstance(error, AnalyticsJsonRpcError):
        return turn_steer_rejection_reason_from_error(error.error)
    if error is TurnSteerRequestError.NO_ACTIVE_TURN:
        return TurnSteerRejectionReason.NO_ACTIVE_TURN
    if error is TurnSteerRequestError.EXPECTED_TURN_MISMATCH:
        return TurnSteerRejectionReason.EXPECTED_TURN_MISMATCH
    if error is TurnSteerRequestError.NON_STEERABLE_REVIEW:
        return TurnSteerRejectionReason.NON_STEERABLE_REVIEW
    if error is TurnSteerRequestError.NON_STEERABLE_COMPACT:
        return TurnSteerRejectionReason.NON_STEERABLE_COMPACT
    if error is InputError.EMPTY:
        return TurnSteerRejectionReason.EMPTY_INPUT
    if error is InputError.TOO_LARGE:
        return TurnSteerRejectionReason.INPUT_TOO_LARGE
    raise ValueError(f"unknown turn steer error: {error!r}")


class PluginState(_SnakeEnum):
    INSTALLED = "installed"
    UNINSTALLED = "uninstalled"
    ENABLED = "enabled"
    DISABLED = "disabled"


class HookEventName(str, Enum):
    PRE_TOOL_USE = "PreToolUse"
    PERMISSION_REQUEST = "PermissionRequest"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    STOP = "Stop"


class HookSource(_SnakeEnum):
    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    MDM = "mdm"
    SESSION_FLAGS = "session_flags"
    PLUGIN = "plugin"
    CLOUD_REQUIREMENTS = "cloud_requirements"
    LEGACY_MANAGED_CONFIG_FILE = "legacy_managed_config_file"
    LEGACY_MANAGED_CONFIG_MDM = "legacy_managed_config_mdm"
    UNKNOWN = "unknown"


class HookRunStatus(_SnakeEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class SkillInvocation:
    skill_name: str
    skill_scope: Any
    skill_path: Path
    plugin_id: str | None
    invocation_type: InvocationType


@dataclass
class SkillInvokedInput:
    tracking: TrackEventsContext
    invocations: list[SkillInvocation]


@dataclass
class AppInvocation:
    connector_id: str | None = None
    app_name: str | None = None
    invocation_type: InvocationType | None = None


@dataclass
class AppMentionedInput:
    tracking: TrackEventsContext
    mentions: list[AppInvocation]


@dataclass
class AppUsedInput:
    tracking: TrackEventsContext
    app: AppInvocation


@dataclass
class PluginId:
    plugin_name: str
    marketplace_name: str

    def as_key(self) -> str:
        return f"{self.plugin_name}@{self.marketplace_name}"


@dataclass
class PluginCapabilitySummary:
    has_skills: bool
    mcp_server_names: tuple[str, ...] = ()
    app_connector_ids: tuple[str, ...] = ()


@dataclass
class PluginTelemetryMetadata:
    plugin_id: PluginId
    remote_plugin_id: str | None = None
    capability_summary: PluginCapabilitySummary | None = None


@dataclass
class PluginUsedInput:
    tracking: TrackEventsContext
    plugin: PluginTelemetryMetadata


@dataclass
class PluginStateChangedInput:
    plugin: PluginTelemetryMetadata
    state: PluginState


@dataclass
class SubAgentThreadStartedInput:
    session_id: str
    thread_id: str
    parent_thread_id: str | None
    product_client_id: str
    client_name: str
    client_version: str
    model: str
    ephemeral: bool
    subagent_source: Any
    created_at: int


@dataclass
class TurnTokenUsageFact:
    turn_id: str
    thread_id: str
    token_usage: Any


@dataclass
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int


@dataclass
class ThreadMetadataState:
    session_id: str
    thread_source: Any | None = None
    initialization_mode: ThreadInitializationMode = ThreadInitializationMode.NEW
    subagent_source: str | None = None
    parent_thread_id: str | None = None


@dataclass
class ConnectionState:
    app_server_client: dict[str, Any]
    runtime: dict[str, Any]


@dataclass
class ThreadAnalyticsState:
    connection_id: int | None = None
    metadata: ThreadMetadataState | None = None


@dataclass
class CompletedTurnState:
    status: TurnStatus | str | None
    turn_error: Any | None
    completed_at: int
    duration_ms: int | None


@dataclass
class TurnToolCounts:
    total: int = 0
    shell_command: int = 0
    file_change: int = 0
    mcp_tool_call: int = 0
    dynamic_tool_call: int = 0
    subagent_tool_call: int = 0
    web_search: int = 0
    image_generation: int = 0

    def record(self, item_kind: str) -> None:
        if item_kind == "CommandExecution":
            self.shell_command += 1
        elif item_kind == "FileChange":
            self.file_change += 1
        elif item_kind == "McpToolCall":
            self.mcp_tool_call += 1
        elif item_kind == "DynamicToolCall":
            self.dynamic_tool_call += 1
        elif item_kind == "CollabAgentToolCall":
            self.subagent_tool_call += 1
        elif item_kind == "WebSearch":
            self.web_search += 1
        elif item_kind == "ImageGeneration":
            self.image_generation += 1
        else:
            return
        self.total += 1

    def record_item(self, item: Any) -> None:
        kind = thread_item_kind(item)
        if kind is not None:
            self.record(kind)


@dataclass
class TurnState:
    connection_id: int | None = None
    thread_id: str | None = None
    num_input_images: int | None = None
    resolved_config: "TurnResolvedConfigFact | None" = None
    started_at: int | None = None
    token_usage: TokenUsage | None = None
    completed: CompletedTurnState | None = None
    latest_diff: str | None = None
    steer_count: int = 0
    tool_counts: TurnToolCounts | None = None

    def __post_init__(self) -> None:
        if self.tool_counts is None:
            self.tool_counts = TurnToolCounts()


@dataclass
class CodexToolItemEventBase:
    thread_id: str
    turn_id: str
    item_id: str
    app_server_client: dict[str, Any]
    runtime: dict[str, Any]
    thread_source: Any | None
    subagent_source: str | None
    parent_thread_id: str | None
    tool_name: str
    started_at_ms: int
    completed_at_ms: int
    duration_ms: int | None
    execution_duration_ms: int | None
    review_count: int
    guardian_review_count: int
    user_review_count: int
    final_approval_outcome: FinalApprovalOutcome | str
    terminal_status: ToolItemTerminalStatus | str
    failure_kind: ToolItemFailureKind | str | None
    requested_additional_permissions: bool
    requested_network_access: bool


@dataclass(frozen=True)
class ToolItemKey:
    thread_id: str
    turn_id: str
    item_id: str


@dataclass
class ToolItemReviewSummary:
    review_count: int = 0
    guardian_review_count: int = 0
    user_review_count: int = 0
    final_approval_outcome: FinalApprovalOutcome | None = None
    requested_additional_permissions: bool = False
    requested_network_access: bool = False


@dataclass
class PendingReviewState:
    thread_id: str
    turn_id: str
    item_id: str | None
    review_id: str
    subject_kind: ReviewSubjectKind | str
    subject_name: str
    trigger: ReviewTrigger | str
    started_at_ms: int
    requested_additional_permissions: bool
    requested_network_access: bool


@dataclass
class GuardianReviewCompletedNotification:
    thread_id: str
    turn_id: str
    started_at_ms: int
    completed_at_ms: int
    review_id: str
    target_item_id: str | None
    status: GuardianApprovalReviewStatus | str
    action: dict[str, Any]


@dataclass
class HookRunFact:
    event_name: HookEventName | str
    hook_source: HookSource | str
    status: HookRunStatus | str


@dataclass
class HookRunInput:
    tracking: TrackEventsContext
    hook: HookRunFact


@dataclass
class CodexCompactionEvent:
    thread_id: str
    turn_id: str
    trigger: CompactionTrigger
    reason: CompactionReason
    implementation: CompactionImplementation
    phase: CompactionPhase
    strategy: CompactionStrategy
    status: CompactionStatus
    error: str | None
    active_context_tokens_before: int
    active_context_tokens_after: int
    started_at: int
    completed_at: int
    duration_ms: int | None


@dataclass
class CodexTurnSteerEvent:
    expected_turn_id: str | None
    accepted_turn_id: str | None
    num_input_images: int
    result: TurnSteerResult
    rejection_reason: TurnSteerRejectionReason | None
    created_at: int


@dataclass
class PendingTurnStartState:
    thread_id: str
    num_input_images: int


@dataclass
class PendingTurnSteerState:
    thread_id: str
    expected_turn_id: str
    num_input_images: int
    created_at: int


@dataclass
class TurnResolvedConfigFact:
    turn_id: str
    thread_id: str
    num_input_images: int
    submission_type: TurnSubmissionType | None
    ephemeral: bool
    session_source: Any
    model: str
    model_provider: str
    permission_profile: Any
    permission_profile_cwd: Path
    reasoning_effort: Any | None
    reasoning_summary: Any | None
    service_tier: Any | None
    approval_policy: Any
    approvals_reviewer: Any
    sandbox_network_access: bool
    collaboration_mode: Any
    personality: Any | None
    is_first_turn: bool


@dataclass
class GuardianReviewTrackContext:
    fields: dict[str, Any]


@dataclass
class GuardianReviewEventParams:
    thread_id: str
    turn_id: str
    review_id: str
    target_item_id: str | None
    approval_request_source: GuardianApprovalRequestSource | str
    reviewed_action: dict[str, Any]
    reviewed_action_truncated: bool
    decision: GuardianReviewDecision | str
    terminal_status: GuardianReviewTerminalStatus | str
    failure_reason: GuardianReviewFailureReason | str | None
    risk_level: Any | None
    user_authorization: Any | None
    outcome: Any | None
    guardian_thread_id: str | None
    guardian_session_kind: GuardianReviewSessionKind | str | None
    guardian_model: str | None
    guardian_reasoning_effort: str | None
    had_prior_review_context: bool | None
    review_timeout_ms: int
    tool_call_count: int | None
    time_to_first_token_ms: int | None
    completion_latency_ms: int | None
    started_at: int
    completed_at: int | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    total_tokens: int | None


class GuardianReviewAnalyticsResult(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    FAILED = "failed"


class AnalyticsEventsClient:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.recorded_facts: list[dict[str, Any]] = []

    @classmethod
    def disabled(cls) -> "AnalyticsEventsClient":
        return cls(enabled=False)

    async def record_events(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def record_fact(self, fact: dict[str, Any]) -> None:
        if self.enabled:
            self.recorded_facts.append(fact)

    def track_request(self, connection_id: int, request_id: Any, request_kind: str) -> None:
        if analytics_relevant_client_request(request_kind):
            self.record_fact(
                {
                    "type": "ClientRequest",
                    "connection_id": connection_id,
                    "request_id": request_id,
                    "request_kind": request_kind,
                }
            )

    def track_response(self, connection_id: int, request_id: Any, response_kind: str) -> None:
        if analytics_relevant_client_response(response_kind):
            self.record_fact(
                {
                    "type": "ClientResponse",
                    "connection_id": connection_id,
                    "request_id": request_id,
                    "response_kind": response_kind,
                }
            )

    def track_notification(self, notification_kind: str) -> None:
        if analytics_relevant_notification(notification_kind):
            self.record_fact({"type": "Notification", "notification_kind": notification_kind})


class AnalyticsEventsQueue:
    def __init__(self) -> None:
        self.app_used_emitted_keys: set[tuple[str, str]] = set()
        self.plugin_used_emitted_keys: set[tuple[str, str]] = set()

    def should_enqueue_app_used(self, tracking: TrackEventsContext, app: AppInvocation) -> bool:
        if app.connector_id is None:
            return True
        if len(self.app_used_emitted_keys) >= ANALYTICS_EVENT_DEDUPE_MAX_KEYS:
            self.app_used_emitted_keys.clear()
        key = (tracking.turn_id, app.connector_id)
        if key in self.app_used_emitted_keys:
            return False
        self.app_used_emitted_keys.add(key)
        return True

    def should_enqueue_plugin_used(self, tracking: TrackEventsContext, plugin: PluginTelemetryMetadata) -> bool:
        if len(self.plugin_used_emitted_keys) >= ANALYTICS_EVENT_DEDUPE_MAX_KEYS:
            self.plugin_used_emitted_keys.clear()
        key = (tracking.turn_id, plugin.plugin_id.as_key())
        if key in self.plugin_used_emitted_keys:
            return False
        self.plugin_used_emitted_keys.add(key)
        return True


class AnalyticsReducer:
    def __init__(self) -> None:
        self.requests: dict[tuple[int, Any], tuple[str, Any]] = {}
        self.turns: dict[str, TurnState] = {}
        self.connections: dict[int, ConnectionState] = {}
        self.threads: dict[str, ThreadAnalyticsState] = {}
        self.tool_items_started_at_ms: dict[ToolItemKey, int] = {}
        self.item_review_summaries: dict[ToolItemKey, ToolItemReviewSummary] = {}
        self.pending_reviews: dict[Any, PendingReviewState] = {}

    def thread_context(self, thread_id: str) -> tuple[ConnectionState, ThreadMetadataState] | None:
        thread_state = self.threads.get(thread_id)
        if thread_state is None or thread_state.connection_id is None or thread_state.metadata is None:
            return None
        connection_state = self.connections.get(thread_state.connection_id)
        if connection_state is None:
            return None
        return connection_state, thread_state.metadata

    def ingest_skill_invoked(self, input: SkillInvokedInput) -> list[dict[str, Any]]:
        return [skill_invocation_event(input.tracking, invocation) for invocation in input.invocations]

    def ingest_app_mentioned(self, input: AppMentionedInput) -> list[dict[str, Any]]:
        return [app_mentioned_event(input.tracking, mention) for mention in input.mentions]

    def ingest_app_used(self, input: AppUsedInput) -> list[dict[str, Any]]:
        return [app_used_event(input.tracking, input.app)]

    def ingest_hook_run(self, input: HookRunInput) -> list[dict[str, Any]]:
        return [hook_run_event(input.tracking, input.hook)]

    def ingest_plugin_used(self, input: PluginUsedInput) -> list[dict[str, Any]]:
        return [plugin_used_event(input.tracking, input.plugin)]

    def ingest_plugin_state_changed(self, input: PluginStateChangedInput) -> list[dict[str, Any]]:
        return [plugin_management_event(input.state, input.plugin)]

    def ingest_client_request(
        self,
        *,
        connection_id: int,
        request_id: Any,
        request_kind: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params = params or {}
        if request_kind == "TurnStart":
            self.track_turn_start_request(
                connection_id=connection_id,
                request_id=request_id,
                thread_id=str(params.get("thread_id") or ""),
                input_items=params.get("input") or params.get("input_items") or [],
            )
        elif request_kind == "TurnSteer":
            self.track_turn_steer_request(
                connection_id=connection_id,
                request_id=request_id,
                thread_id=str(params.get("thread_id") or ""),
                expected_turn_id=str(params.get("expected_turn_id") or ""),
                input_items=params.get("input") or params.get("input_items") or [],
                created_at=params.get("created_at"),
            )
        return []

    def ingest_client_response(
        self,
        *,
        connection_id: int,
        request_id: Any,
        response_kind: str,
        response: dict[str, Any] | None = None,
        app_server_client: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
        thread_metadata: ThreadMetadataState | None = None,
    ) -> list[dict[str, Any]]:
        response = response or {}
        if response_kind in {"ThreadStart", "ThreadResume", "ThreadFork"}:
            thread = response.get("thread") or response
            thread_id = thread.get("thread_id") or thread.get("id")
            session_id = thread.get("session_id")
            model = response.get("model") or thread.get("model")
            if thread_id is None or session_id is None or model is None:
                return []
            mode = {
                "ThreadStart": ThreadInitializationMode.NEW,
                "ThreadResume": ThreadInitializationMode.RESUMED,
                "ThreadFork": ThreadInitializationMode.FORKED,
            }[response_kind]
            return self.ingest_thread_response(
                connection_id=connection_id,
                thread_id=str(thread_id),
                session_id=str(session_id),
                model=str(model),
                ephemeral=bool(thread.get("ephemeral", False)),
                thread_source=thread.get("thread_source"),
                initialization_mode=mode,
                created_at=int(thread.get("created_at", 0)),
            )
        if response_kind == "TurnStart":
            if app_server_client is None or runtime is None or thread_metadata is None:
                return []
            turn = response.get("turn") or response
            turn_id = turn.get("turn_id") or turn.get("id")
            if turn_id is None:
                return []
            return self.ingest_turn_start_response(
                connection_id=connection_id,
                request_id=request_id,
                turn_id=str(turn_id),
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
            )
        if response_kind == "TurnSteer":
            if app_server_client is None or runtime is None or thread_metadata is None:
                return []
            turn_id = response.get("turn_id") or response.get("id")
            if turn_id is None:
                return []
            return self.ingest_turn_steer_response(
                connection_id=connection_id,
                request_id=request_id,
                accepted_turn_id=str(turn_id),
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
            )
        return []

    def ingest_initialize(
        self,
        *,
        connection_id: int,
        product_client_id: str,
        client_name: str,
        client_version: str,
        rpc_transport: str,
        experimental_api_enabled: bool | None,
        runtime: dict[str, Any],
    ) -> list[dict[str, Any]]:
        self.connections[connection_id] = ConnectionState(
            app_server_client={
                "product_client_id": product_client_id,
                "client_name": client_name,
                "client_version": client_version,
                "rpc_transport": rpc_transport,
                "experimental_api_enabled": experimental_api_enabled,
            },
            runtime=dict(runtime),
        )
        return []

    def ingest_thread_response(
        self,
        *,
        connection_id: int,
        thread_id: str,
        session_id: str,
        model: str,
        ephemeral: bool,
        thread_source: Any | None,
        initialization_mode: ThreadInitializationMode | str,
        created_at: int,
    ) -> list[dict[str, Any]]:
        connection_state = self.connections.get(connection_id)
        if connection_state is None:
            return []
        metadata = ThreadMetadataState(
            session_id=session_id,
            thread_source=thread_source,
            initialization_mode=initialization_mode,
            subagent_source=None,
            parent_thread_id=None,
        )
        self.threads[thread_id] = ThreadAnalyticsState(connection_id=connection_id, metadata=metadata)
        return [
            thread_initialized_event(
                thread_id=thread_id,
                session_id=session_id,
                app_server_client=connection_state.app_server_client,
                runtime=connection_state.runtime,
                model=model,
                ephemeral=ephemeral,
                thread_source=metadata.thread_source,
                initialization_mode=initialization_mode,
                subagent_source=metadata.subagent_source,
                parent_thread_id=metadata.parent_thread_id,
                created_at=max(created_at, 0),
            )
        ]

    def track_turn_start_request(
        self,
        *,
        connection_id: int,
        request_id: Any,
        thread_id: str,
        input_items: list[Any] | None = None,
        num_input_images: int | None = None,
    ) -> None:
        self.requests[(connection_id, request_id)] = (
            "TurnStart",
            PendingTurnStartState(
                thread_id=thread_id,
                num_input_images=count_input_images(input_items or []) if num_input_images is None else num_input_images,
            ),
        )

    def track_turn_steer_request(
        self,
        *,
        connection_id: int,
        request_id: Any,
        thread_id: str,
        expected_turn_id: str,
        input_items: list[Any] | None = None,
        num_input_images: int | None = None,
        created_at: int | None = None,
    ) -> None:
        self.requests[(connection_id, request_id)] = (
            "TurnSteer",
            PendingTurnSteerState(
                thread_id=thread_id,
                expected_turn_id=expected_turn_id,
                num_input_images=count_input_images(input_items or []) if num_input_images is None else num_input_images,
                created_at=now_unix_seconds() if created_at is None else created_at,
            ),
        )

    def ingest_turn_start_error_response(self, *, connection_id: int, request_id: Any) -> list[dict[str, Any]]:
        self.requests.pop((connection_id, request_id), None)
        return []

    def ingest_turn_steer_error_response(
        self,
        *,
        connection_id: int,
        request_id: Any,
        error_type: TurnSteerRejectionReason | AnalyticsJsonRpcError | TurnSteerRequestError | InputError | str | None,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        request = self.requests.pop((connection_id, request_id), None)
        if request is None:
            return []
        kind, pending = request
        if kind != "TurnSteer":
            return []
        return [
            codex_turn_steer_event(
                app_server_client=app_server_client,
                runtime=runtime,
                pending_request=pending,
                thread_metadata=thread_metadata,
                accepted_turn_id=None,
                result=TurnSteerResult.REJECTED,
                rejection_reason=error_type,
            )
        ]

    def ingest_turn_start_response(
        self,
        *,
        connection_id: int,
        request_id: Any,
        turn_id: str,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        request = self.requests.pop((connection_id, request_id), None)
        if request is None:
            return []
        kind, pending = request
        if kind != "TurnStart":
            return []
        turn_state = self.turns.setdefault(turn_id, TurnState())
        turn_state.connection_id = connection_id
        turn_state.thread_id = pending.thread_id
        turn_state.num_input_images = pending.num_input_images
        return self._maybe_emit_turn_event(
            turn_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
        )

    def ingest_turn_steer_response(
        self,
        *,
        connection_id: int,
        request_id: Any,
        accepted_turn_id: str,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        request = self.requests.pop((connection_id, request_id), None)
        if request is None:
            return []
        kind, pending = request
        if kind != "TurnSteer":
            return []
        turn_state = self.turns.get(accepted_turn_id)
        if turn_state is not None:
            turn_state.steer_count += 1
        return [
            codex_turn_steer_event(
                app_server_client=app_server_client,
                runtime=runtime,
                pending_request=pending,
                thread_metadata=thread_metadata,
                accepted_turn_id=accepted_turn_id,
                result=TurnSteerResult.ACCEPTED,
                rejection_reason=None,
            )
        ]

    def ingest_turn_resolved_config(
        self,
        input: TurnResolvedConfigFact,
        *,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        turn_state = self.turns.setdefault(input.turn_id, TurnState())
        turn_state.thread_id = input.thread_id
        turn_state.num_input_images = input.num_input_images
        turn_state.resolved_config = input
        return self._maybe_emit_turn_event(
            input.turn_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
        )

    def ingest_turn_started(self, *, turn_id: str, started_at: int | None) -> list[dict[str, Any]]:
        turn_state = self.turns.setdefault(turn_id, TurnState())
        turn_state.started_at = _non_negative_int_or_none(started_at) if started_at is not None else None
        return []

    def ingest_turn_diff_updated(self, *, thread_id: str, turn_id: str, diff: str) -> list[dict[str, Any]]:
        turn_state = self.turns.setdefault(turn_id, TurnState())
        turn_state.thread_id = thread_id
        turn_state.latest_diff = diff
        return []

    def ingest_turn_completed(
        self,
        *,
        turn_id: str,
        completed: CompletedTurnState,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        turn_state = self.turns.setdefault(turn_id, TurnState())
        turn_state.completed = completed
        events = self._maybe_emit_turn_event(
            turn_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
        )
        if events:
            self.turns.pop(turn_id, None)
        return events

    def ingest_turn_completed_notification(
        self,
        *,
        turn_id: str,
        status: TurnStatus | str | None,
        turn_error: Any | None,
        completed_at: int | None,
        duration_ms: int | None,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        completed = CompletedTurnState(
            status=analytics_turn_status(status),
            turn_error=turn_error,
            completed_at=0 if completed_at is None else (_non_negative_int_or_none(completed_at) or 0),
            duration_ms=None if duration_ms is None else _non_negative_int_or_none(duration_ms),
        )
        return self.ingest_turn_completed(
            turn_id=turn_id,
            completed=completed,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
        )

    def ingest_item_started(
        self,
        *,
        thread_id: str,
        turn_id: str,
        item: Any,
        started_at_ms: int,
    ) -> list[dict[str, Any]]:
        item_id = tracked_tool_item_id(item)
        started = _non_negative_int_or_none(started_at_ms)
        if item_id is None or started is None:
            return []
        self.tool_items_started_at_ms[ToolItemKey(thread_id, turn_id, item_id)] = started
        return []

    def ingest_item_completed(
        self,
        *,
        thread_id: str,
        turn_id: str,
        item: Any,
        completed_at_ms: int,
        app_server_client: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
        thread_metadata: ThreadMetadataState | None = None,
    ) -> list[dict[str, Any]]:
        item_id = tracked_tool_item_id(item)
        if item_id is None:
            return []
        turn_state = self.turns.get(turn_id)
        if turn_state is None:
            return []
        turn_state.tool_counts.record_item(item)
        key = ToolItemKey(thread_id, turn_id, item_id)
        started_at_ms = self.tool_items_started_at_ms.pop(key, None)
        if started_at_ms is None:
            return []
        completed = _non_negative_int_or_none(completed_at_ms)
        if completed is None:
            return []
        if app_server_client is None or runtime is None or thread_metadata is None:
            context = self.thread_context(thread_id)
            if context is None:
                return []
            connection_state, resolved_thread_metadata = context
            if app_server_client is None:
                app_server_client = connection_state.app_server_client
            if runtime is None:
                runtime = connection_state.runtime
            if thread_metadata is None:
                thread_metadata = resolved_thread_metadata
        event = tool_item_event(
            thread_id=thread_id,
            turn_id=turn_id,
            item=item,
            started_at_ms=started_at_ms,
            completed_at_ms=completed,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
            review_summary=self.item_review_summaries.get(key),
        )
        self.item_review_summaries.pop(key, None)
        return [] if event is None else [event]

    def _maybe_emit_turn_event(
        self,
        turn_id: str,
        *,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        turn_state = self.turns.get(turn_id)
        if turn_state is None or turn_state.connection_id is None:
            return []
        event = codex_turn_event(
            app_server_client=app_server_client,
            runtime=runtime,
            turn_id=turn_id,
            turn_state=turn_state,
            thread_metadata=thread_metadata,
        )
        if event is None:
            return []
        events = [event]
        accepted_line_input = accepted_line_event_input(turn_id, turn_state)
        if accepted_line_input is not None:
            events.extend(accepted_line_fingerprint_event_requests(accepted_line_input))
        return events

    def ingest_compaction(
        self,
        input: CodexCompactionEvent,
        *,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        return [
            codex_compaction_event(
                input,
                session_id=thread_metadata.session_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_source=thread_metadata.thread_source,
                subagent_source=thread_metadata.subagent_source,
                parent_thread_id=thread_metadata.parent_thread_id,
            )
        ]

    def ingest_subagent_thread_started(
        self,
        input: SubAgentThreadStartedInput,
        *,
        runtime: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        parent_thread_id = input.parent_thread_id or subagent_parent_thread_id(input.subagent_source)
        parent_state = self.threads.get(parent_thread_id) if parent_thread_id is not None else None
        parent_connection_id = None if parent_state is None else parent_state.connection_id
        thread_state = self.threads.setdefault(input.thread_id, ThreadAnalyticsState())
        if thread_state.metadata is None:
            thread_state.metadata = ThreadMetadataState(
                session_id=input.session_id,
                thread_source="subagent",
                initialization_mode=ThreadInitializationMode.NEW,
                subagent_source=subagent_source_name(input.subagent_source),
                parent_thread_id=parent_thread_id,
            )
        if thread_state.connection_id is None:
            thread_state.connection_id = parent_connection_id
        return [subagent_thread_started_event(input, runtime=runtime)]

    def ingest_guardian_review(
        self,
        input: GuardianReviewEventParams,
        *,
        session_id: str,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            guardian_review_event(
                input,
                session_id=session_id,
                app_server_client=app_server_client,
                runtime=runtime,
            )
        ]

    def record_item_review_summary(
        self,
        pending_review: PendingReviewState,
        *,
        reviewer: Reviewer | str,
        status: ReviewStatus | str,
        resolution: ReviewResolution | str,
    ) -> ToolItemReviewSummary | None:
        key = item_review_summary_key(pending_review)
        if key is None:
            return None
        summary = self.item_review_summaries.setdefault(key, ToolItemReviewSummary())
        summary.review_count += 1
        reviewer_value = _enum_value(reviewer)
        if reviewer_value == Reviewer.GUARDIAN.value:
            summary.guardian_review_count += 1
        elif reviewer_value == Reviewer.USER.value:
            summary.user_review_count += 1
        else:
            raise ValueError(f"unknown reviewer: {reviewer!r}")
        summary.final_approval_outcome = final_approval_outcome(reviewer, status, resolution)
        summary.requested_additional_permissions |= pending_review.requested_additional_permissions
        summary.requested_network_access |= pending_review.requested_network_access
        return summary

    def review_summary_for_item(self, thread_id: str, turn_id: str, item_id: str) -> ToolItemReviewSummary:
        return self.item_review_summaries.get(ToolItemKey(thread_id, turn_id, item_id), ToolItemReviewSummary())

    def emit_review_event(
        self,
        pending_review: PendingReviewState,
        *,
        reviewer: Reviewer | str,
        status: ReviewStatus | str,
        resolution: ReviewResolution | str,
        completed_at_ms: int,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> dict[str, Any]:
        self.record_item_review_summary(
            pending_review,
            reviewer=reviewer,
            status=status,
            resolution=resolution,
        )
        return codex_review_event(
            thread_id=pending_review.thread_id,
            turn_id=pending_review.turn_id,
            item_id=pending_review.item_id,
            review_id=pending_review.review_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_source=thread_metadata.thread_source,
            subagent_source=thread_metadata.subagent_source,
            parent_thread_id=thread_metadata.parent_thread_id,
            subject_kind=pending_review.subject_kind,
            subject_name=pending_review.subject_name,
            reviewer=reviewer,
            trigger=pending_review.trigger,
            status=status,
            resolution=resolution,
            started_at_ms=pending_review.started_at_ms,
            completed_at_ms=completed_at_ms,
            duration_ms=observed_duration_ms(pending_review.started_at_ms, completed_at_ms),
        )

    def track_pending_review(self, request_id: Any, pending_review: PendingReviewState) -> None:
        self.pending_reviews[request_id] = pending_review

    def ingest_server_request_aborted(
        self,
        *,
        request_id: Any,
        completed_at_ms: int,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        pending_review = self.pending_reviews.pop(request_id, None)
        if pending_review is None:
            return []
        return [
            self.emit_review_event(
                pending_review,
                reviewer=Reviewer.USER,
                status=ReviewStatus.ABORTED,
                resolution=ReviewResolution.NONE,
                completed_at_ms=completed_at_ms,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
            )
        ]

    def ingest_review_response(
        self,
        *,
        request_id: Any,
        reviewer: Reviewer | str,
        status: ReviewStatus | str,
        resolution: ReviewResolution | str,
        completed_at_ms: int,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        pending_review = self.pending_reviews.pop(request_id, None)
        if pending_review is None:
            return []
        return [
            self.emit_review_event(
                pending_review,
                reviewer=reviewer,
                status=status,
                resolution=resolution,
                completed_at_ms=completed_at_ms,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
            )
        ]

    def ingest_effective_permissions_approval_response(
        self,
        *,
        request_id: Any,
        response: dict[str, Any],
        completed_at_ms: int,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        status, resolution = effective_permissions_review_result(response)
        return self.ingest_review_response(
            request_id=request_id,
            reviewer=Reviewer.USER,
            status=status,
            resolution=resolution,
            completed_at_ms=completed_at_ms,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
        )

    def ingest_guardian_review_completed(
        self,
        notification: GuardianReviewCompletedNotification,
        *,
        app_server_client: dict[str, Any],
        runtime: dict[str, Any],
        thread_metadata: ThreadMetadataState,
    ) -> list[dict[str, Any]]:
        result = guardian_review_result(notification.status)
        if result is None:
            return []
        started_at_ms = _non_negative_int_or_none(notification.started_at_ms)
        completed_at_ms = _non_negative_int_or_none(notification.completed_at_ms)
        if started_at_ms is None or completed_at_ms is None:
            return []
        status, resolution = result
        subject_kind, subject_name, trigger = guardian_review_subject_metadata(notification.action)
        pending_review = PendingReviewState(
            thread_id=notification.thread_id,
            turn_id=notification.turn_id,
            item_id=notification.target_item_id,
            review_id=notification.review_id,
            subject_kind=subject_kind,
            subject_name=subject_name,
            trigger=trigger,
            started_at_ms=started_at_ms,
            requested_additional_permissions=guardian_review_requested_additional_permissions(notification.action),
            requested_network_access=guardian_review_requested_network_access(notification.action),
        )
        return [
            self.emit_review_event(
                pending_review,
                reviewer=Reviewer.GUARDIAN,
                status=status,
                resolution=resolution,
                completed_at_ms=completed_at_ms,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
            )
        ]


def codex_turn_event(
    *,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    turn_id: str,
    turn_state: TurnState,
    thread_metadata: ThreadMetadataState,
) -> dict[str, Any] | None:
    params = codex_turn_event_params(
        app_server_client=app_server_client,
        runtime=runtime,
        turn_id=turn_id,
        turn_state=turn_state,
        thread_metadata=thread_metadata,
    )
    if params is None:
        return None
    return {"event_type": "codex_turn_event", "event_params": params}


def thread_initialized_event(
    *,
    thread_id: str,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    model: str,
    ephemeral: bool,
    thread_source: Any | None,
    initialization_mode: ThreadInitializationMode | str,
    subagent_source: str | None,
    parent_thread_id: str | None,
    created_at: int,
) -> dict[str, Any]:
    return {
        "event_type": "codex_thread_initialized",
        "event_params": {
            "thread_id": thread_id,
            "session_id": session_id,
            "app_server_client": dict(app_server_client),
            "runtime": dict(runtime),
            "model": model,
            "ephemeral": ephemeral,
            "thread_source": _enum_value(thread_source),
            "initialization_mode": _enum_value(initialization_mode),
            "subagent_source": subagent_source,
            "parent_thread_id": parent_thread_id,
            "created_at": created_at,
        },
    }


def subagent_thread_started_event(
    input: SubAgentThreadStartedInput,
    *,
    runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_name = subagent_source_name(input.subagent_source)
    return thread_initialized_event(
        thread_id=input.thread_id,
        session_id=input.session_id,
        app_server_client={
            "product_client_id": input.product_client_id,
            "client_name": input.client_name,
            "client_version": input.client_version,
            "rpc_transport": "in_process",
            "experimental_api_enabled": None,
        },
        runtime={} if runtime is None else runtime,
        model=input.model,
        ephemeral=input.ephemeral,
        thread_source="subagent",
        initialization_mode=ThreadInitializationMode.NEW,
        subagent_source=source_name,
        parent_thread_id=input.parent_thread_id or subagent_parent_thread_id(input.subagent_source),
        created_at=input.created_at,
    )


def subagent_source_name(subagent_source: Any) -> str:
    value = _enum_value(subagent_source)
    if isinstance(value, dict):
        kind = value.get("kind") or value.get("type")
        if kind == "ThreadSpawn":
            return "thread_spawn"
        if kind == "MemoryConsolidation":
            return "memory_consolidation"
        if kind == "Review":
            return "review"
        if kind == "Compact":
            return "compact"
        if kind == "Other":
            other = value.get("value") or value.get("name")
            return str(other) if other is not None else "other"
    text = str(value)
    mapping = {
        "Review": "review",
        "review": "review",
        "Compact": "compact",
        "compact": "compact",
        "ThreadSpawn": "thread_spawn",
        "thread_spawn": "thread_spawn",
        "MemoryConsolidation": "memory_consolidation",
        "memory_consolidation": "memory_consolidation",
    }
    if text.startswith("Other:"):
        return text.split(":", 1)[1]
    return mapping.get(text, text)


def subagent_parent_thread_id(subagent_source: Any) -> str | None:
    value = _enum_value(subagent_source)
    if isinstance(value, dict) and (value.get("kind") or value.get("type")) == "ThreadSpawn":
        parent = value.get("parent_thread_id")
        return None if parent is None else str(parent)
    return None


def codex_compaction_event(
    input: CodexCompactionEvent,
    *,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_source: Any | None,
    subagent_source: str | None,
    parent_thread_id: str | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_compaction_event",
        "event_params": codex_compaction_event_params(
            input,
            session_id=session_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_source=thread_source,
            subagent_source=subagent_source,
            parent_thread_id=parent_thread_id,
        ),
    }


def codex_compaction_event_params(
    input: CodexCompactionEvent,
    *,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_source: Any | None,
    subagent_source: str | None,
    parent_thread_id: str | None,
) -> dict[str, Any]:
    return {
        "thread_id": input.thread_id,
        "session_id": session_id,
        "turn_id": input.turn_id,
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "thread_source": _enum_value(thread_source),
        "subagent_source": subagent_source,
        "parent_thread_id": parent_thread_id,
        "trigger": _enum_value(input.trigger),
        "reason": _enum_value(input.reason),
        "implementation": _enum_value(input.implementation),
        "phase": _enum_value(input.phase),
        "strategy": _enum_value(input.strategy),
        "status": _enum_value(input.status),
        "error": input.error,
        "active_context_tokens_before": input.active_context_tokens_before,
        "active_context_tokens_after": input.active_context_tokens_after,
        "started_at": input.started_at,
        "completed_at": input.completed_at,
        "duration_ms": input.duration_ms,
    }


def codex_review_event(
    *,
    thread_id: str,
    turn_id: str,
    item_id: str | None,
    review_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_source: Any | None,
    subagent_source: str | None,
    parent_thread_id: str | None,
    subject_kind: ReviewSubjectKind | str,
    subject_name: str,
    reviewer: Reviewer | str,
    trigger: ReviewTrigger | str,
    status: ReviewStatus | str,
    resolution: ReviewResolution | str,
    started_at_ms: int,
    completed_at_ms: int,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_review_event",
        "event_params": codex_review_event_params(
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
            review_id=review_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_source=thread_source,
            subagent_source=subagent_source,
            parent_thread_id=parent_thread_id,
            subject_kind=subject_kind,
            subject_name=subject_name,
            reviewer=reviewer,
            trigger=trigger,
            status=status,
            resolution=resolution,
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            duration_ms=duration_ms,
        ),
    }


def guardian_review_event(
    input: GuardianReviewEventParams,
    *,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": "codex_guardian_review",
        "event_params": guardian_review_event_params(
            input,
            session_id=session_id,
            app_server_client=app_server_client,
            runtime=runtime,
        ),
    }


def guardian_review_event_params(
    input: GuardianReviewEventParams,
    *,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "thread_id": input.thread_id,
        "turn_id": input.turn_id,
        "review_id": input.review_id,
        "target_item_id": input.target_item_id,
        "approval_request_source": _enum_value(input.approval_request_source),
        "reviewed_action": _json_value(input.reviewed_action),
        "reviewed_action_truncated": input.reviewed_action_truncated,
        "decision": _enum_value(input.decision),
        "terminal_status": _enum_value(input.terminal_status),
        "failure_reason": _enum_value(input.failure_reason),
        "risk_level": _enum_value(input.risk_level),
        "user_authorization": _enum_value(input.user_authorization),
        "outcome": _enum_value(input.outcome),
        "guardian_thread_id": input.guardian_thread_id,
        "guardian_session_kind": _enum_value(input.guardian_session_kind),
        "guardian_model": input.guardian_model,
        "guardian_reasoning_effort": input.guardian_reasoning_effort,
        "had_prior_review_context": input.had_prior_review_context,
        "review_timeout_ms": input.review_timeout_ms,
        "tool_call_count": input.tool_call_count,
        "time_to_first_token_ms": input.time_to_first_token_ms,
        "completion_latency_ms": input.completion_latency_ms,
        "started_at": input.started_at,
        "completed_at": input.completed_at,
        "input_tokens": input.input_tokens,
        "cached_input_tokens": input.cached_input_tokens,
        "output_tokens": input.output_tokens,
        "reasoning_output_tokens": input.reasoning_output_tokens,
        "total_tokens": input.total_tokens,
    }


def codex_review_event_params(
    *,
    thread_id: str,
    turn_id: str,
    item_id: str | None,
    review_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_source: Any | None,
    subagent_source: str | None,
    parent_thread_id: str | None,
    subject_kind: ReviewSubjectKind | str,
    subject_name: str,
    reviewer: Reviewer | str,
    trigger: ReviewTrigger | str,
    status: ReviewStatus | str,
    resolution: ReviewResolution | str,
    started_at_ms: int,
    completed_at_ms: int,
    duration_ms: int | None,
) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "turn_id": turn_id,
        "item_id": item_id,
        "review_id": review_id,
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "thread_source": _enum_value(thread_source),
        "subagent_source": subagent_source,
        "parent_thread_id": parent_thread_id,
        "subject_kind": _enum_value(subject_kind),
        "subject_name": subject_name,
        "reviewer": _enum_value(reviewer),
        "trigger": _enum_value(trigger),
        "status": _enum_value(status),
        "resolution": _enum_value(resolution),
        "started_at_ms": started_at_ms,
        "completed_at_ms": completed_at_ms,
        "duration_ms": duration_ms,
    }


def codex_tool_item_event_base_params(base: CodexToolItemEventBase) -> dict[str, Any]:
    return {
        "thread_id": base.thread_id,
        "turn_id": base.turn_id,
        "item_id": base.item_id,
        "app_server_client": dict(base.app_server_client),
        "runtime": dict(base.runtime),
        "thread_source": _enum_value(base.thread_source),
        "subagent_source": base.subagent_source,
        "parent_thread_id": base.parent_thread_id,
        "tool_name": base.tool_name,
        "started_at_ms": base.started_at_ms,
        "completed_at_ms": base.completed_at_ms,
        "duration_ms": base.duration_ms,
        "execution_duration_ms": base.execution_duration_ms,
        "review_count": base.review_count,
        "guardian_review_count": base.guardian_review_count,
        "user_review_count": base.user_review_count,
        "final_approval_outcome": _enum_value(base.final_approval_outcome),
        "terminal_status": _enum_value(base.terminal_status),
        "failure_kind": _enum_value(base.failure_kind),
        "requested_additional_permissions": base.requested_additional_permissions,
        "requested_network_access": base.requested_network_access,
    }


def final_approval_outcome(
    reviewer: Reviewer | str,
    status: ReviewStatus | str,
    resolution: ReviewResolution | str,
) -> FinalApprovalOutcome:
    reviewer_value = _enum_value(reviewer)
    status_value = _enum_value(status)
    resolution_value = _enum_value(resolution)
    if reviewer_value == Reviewer.GUARDIAN.value:
        if status_value == ReviewStatus.APPROVED.value:
            return FinalApprovalOutcome.GUARDIAN_APPROVED
        if status_value == ReviewStatus.DENIED.value:
            return FinalApprovalOutcome.GUARDIAN_DENIED
        return FinalApprovalOutcome.GUARDIAN_ABORTED
    if reviewer_value == Reviewer.USER.value:
        if status_value == ReviewStatus.APPROVED.value and resolution_value == ReviewResolution.SESSION_APPROVAL.value:
            return FinalApprovalOutcome.USER_APPROVED_FOR_SESSION
        if status_value == ReviewStatus.APPROVED.value:
            return FinalApprovalOutcome.USER_APPROVED
        if status_value == ReviewStatus.DENIED.value:
            return FinalApprovalOutcome.USER_DENIED
        return FinalApprovalOutcome.USER_ABORTED
    raise ValueError(f"unknown reviewer: {reviewer!r}")


def observed_duration_ms(started_at_ms: int, completed_at_ms: int) -> int | None:
    if completed_at_ms < started_at_ms:
        return None
    return completed_at_ms - started_at_ms


def accepted_line_event_input(turn_id: str, turn_state: TurnState) -> AcceptedLineFingerprintEventInput | None:
    if turn_state.latest_diff is None:
        return None
    summary = accepted_line_fingerprints_from_unified_diff(turn_state.latest_diff)
    if summary.accepted_added_lines == 0 and summary.accepted_deleted_lines == 0:
        return None
    if turn_state.thread_id is None or turn_state.resolved_config is None:
        return None
    return AcceptedLineFingerprintEventInput(
        event_type="codex.accepted_line_fingerprints",
        turn_id=turn_id,
        thread_id=turn_state.thread_id,
        product_surface="codex",
        model_slug=turn_state.resolved_config.model,
        completed_at=now_unix_seconds(),
        repo_hash=None,
        accepted_added_lines=summary.accepted_added_lines,
        accepted_deleted_lines=summary.accepted_deleted_lines,
        line_fingerprints=summary.line_fingerprints,
    )


def thread_item_kind(item: Any) -> str | None:
    raw_kind = _item_field(item, "kind", "type", "variant")
    if raw_kind is None:
        raw_kind = item.__class__.__name__
    kind = str(_enum_value(raw_kind))
    aliases = {
        "command_execution": "CommandExecution",
        "CommandExecution": "CommandExecution",
        "file_change": "FileChange",
        "FileChange": "FileChange",
        "mcp_tool_call": "McpToolCall",
        "McpToolCall": "McpToolCall",
        "dynamic_tool_call": "DynamicToolCall",
        "DynamicToolCall": "DynamicToolCall",
        "collab_agent_tool_call": "CollabAgentToolCall",
        "CollabAgentToolCall": "CollabAgentToolCall",
        "web_search": "WebSearch",
        "WebSearch": "WebSearch",
        "image_generation": "ImageGeneration",
        "ImageGeneration": "ImageGeneration",
    }
    return aliases.get(kind)


def tracked_tool_item_id(item: Any) -> str | None:
    if thread_item_kind(item) is None:
        return None
    item_id = _item_field(item, "id", "item_id")
    return None if item_id is None else str(item_id)


def tool_item_event(
    *,
    thread_id: str,
    turn_id: str,
    item: Any,
    started_at_ms: int,
    completed_at_ms: int,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_metadata: ThreadMetadataState,
    review_summary: ToolItemReviewSummary | None,
) -> dict[str, Any] | None:
    kind = thread_item_kind(item)
    item_id = tracked_tool_item_id(item)
    if item_id is None:
        return None
    if kind == "CommandExecution":
        outcome = command_execution_outcome(_item_field(item, "status"))
        if outcome is None:
            return None
        terminal_status, failure_kind = outcome
        action_counts = command_action_counts(_item_field(item, "command_actions", "actions") or [])
        base = tool_item_base(
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
            app_server_client=app_server_client,
            runtime=runtime,
            thread_metadata=thread_metadata,
            review_summary=review_summary,
            tool_name=command_execution_tool_name(_item_field(item, "source")),
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            terminal_status=terminal_status,
            failure_kind=failure_kind,
            execution_duration_ms=_duration_ms_or_none(_item_field(item, "duration_ms")),
        )
        return codex_command_execution_event(
            base=base,
            command_execution_source=command_execution_source(_item_field(item, "source")),
            exit_code=_item_field(item, "exit_code"),
            command_total_action_count=action_counts["total"],
            command_read_action_count=action_counts["read"],
            command_list_files_action_count=action_counts["list_files"],
            command_search_action_count=action_counts["search"],
            command_unknown_action_count=action_counts["unknown"],
        )
    if kind == "FileChange":
        outcome = tool_item_status_outcome(_item_field(item, "status"))
        if outcome is None:
            return None
        terminal_status, failure_kind = outcome
        changes = _item_field(item, "changes") or []
        counts = file_change_counts(changes)
        return codex_file_change_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name="apply_patch",
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=terminal_status,
                failure_kind=failure_kind,
                execution_duration_ms=None,
            ),
            file_change_count=len(changes),
            file_add_count=counts["add"],
            file_update_count=counts["update"],
            file_delete_count=counts["delete"],
            file_move_count=counts["move"],
        )
    if kind == "McpToolCall":
        outcome = mcp_tool_call_outcome(_item_field(item, "status"))
        if outcome is None:
            return None
        terminal_status, failure_kind = outcome
        tool_name = str(_item_field(item, "tool", "mcp_tool_name") or "")
        return codex_mcp_tool_call_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name=tool_name,
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=terminal_status,
                failure_kind=failure_kind,
                execution_duration_ms=_duration_ms_or_none(_item_field(item, "duration_ms")),
            ),
            mcp_server_name=str(_item_field(item, "server", "mcp_server_name") or ""),
            mcp_tool_name=tool_name,
            mcp_error_present=_item_field(item, "error") is not None,
        )
    if kind == "DynamicToolCall":
        outcome = mcp_tool_call_outcome(_item_field(item, "status"))
        if outcome is None:
            return None
        terminal_status, failure_kind = outcome
        content_items = _item_field(item, "content_items", "output_content_items")
        counts = dynamic_content_counts(content_items) if content_items is not None else None
        tool_name = str(_item_field(item, "tool", "dynamic_tool_name") or "")
        return codex_dynamic_tool_call_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name=tool_name,
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=terminal_status,
                failure_kind=failure_kind,
                execution_duration_ms=_duration_ms_or_none(_item_field(item, "duration_ms")),
            ),
            dynamic_tool_name=tool_name,
            success=_item_field(item, "success"),
            output_content_item_count=None if counts is None else counts["total"],
            output_text_item_count=None if counts is None else counts["text"],
            output_image_item_count=None if counts is None else counts["image"],
        )
    if kind == "CollabAgentToolCall":
        outcome = mcp_tool_call_outcome(_item_field(item, "status"))
        if outcome is None:
            return None
        terminal_status, failure_kind = outcome
        receiver_thread_ids = list(_item_field(item, "receiver_thread_ids") or [])
        agent_states = _item_field(item, "agents_states", "agent_states") or {}
        counts = collab_agent_state_counts(agent_states)
        return codex_collab_agent_tool_call_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name=collab_agent_tool_name(_item_field(item, "tool")),
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=terminal_status,
                failure_kind=failure_kind,
                execution_duration_ms=None,
            ),
            sender_thread_id=str(_item_field(item, "sender_thread_id") or ""),
            receiver_thread_count=len(receiver_thread_ids),
            receiver_thread_ids=receiver_thread_ids,
            requested_model=_item_field(item, "model", "requested_model"),
            requested_reasoning_effort=_enum_value(_item_field(item, "reasoning_effort", "requested_reasoning_effort")),
            agent_state_count=counts["total"],
            completed_agent_count=counts["completed"],
            failed_agent_count=counts["failed"],
        )
    if kind == "WebSearch":
        query = str(_item_field(item, "query") or "")
        action = _item_field(item, "action")
        return codex_web_search_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name="web_search",
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=ToolItemTerminalStatus.COMPLETED,
                failure_kind=None,
                execution_duration_ms=None,
            ),
            web_search_action=web_search_action_kind(action) if action is not None else None,
            query_present=bool(query.strip()),
            query_count=web_search_query_count(query, action),
        )
    if kind == "ImageGeneration":
        terminal_status, failure_kind = image_generation_outcome(_item_field(item, "status"))
        return codex_image_generation_event(
            base=tool_item_base(
                thread_id=thread_id,
                turn_id=turn_id,
                item_id=item_id,
                app_server_client=app_server_client,
                runtime=runtime,
                thread_metadata=thread_metadata,
                review_summary=review_summary,
                tool_name="image_generation",
                started_at_ms=started_at_ms,
                completed_at_ms=completed_at_ms,
                terminal_status=terminal_status,
                failure_kind=failure_kind,
                execution_duration_ms=None,
            ),
            revised_prompt_present=_item_field(item, "revised_prompt") is not None,
            saved_path_present=_item_field(item, "saved_path") is not None,
        )
    return None


def tool_item_base(
    *,
    thread_id: str,
    turn_id: str,
    item_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_metadata: ThreadMetadataState,
    review_summary: ToolItemReviewSummary | None,
    tool_name: str,
    started_at_ms: int,
    completed_at_ms: int,
    terminal_status: ToolItemTerminalStatus,
    failure_kind: ToolItemFailureKind | None,
    execution_duration_ms: int | None,
) -> CodexToolItemEventBase:
    return apply_tool_item_review_summary(
        CodexToolItemEventBase(
            thread_id=thread_id,
            turn_id=turn_id,
            item_id=item_id,
            app_server_client=dict(app_server_client),
            runtime=dict(runtime),
            thread_source=thread_metadata.thread_source,
            subagent_source=thread_metadata.subagent_source,
            parent_thread_id=thread_metadata.parent_thread_id,
            tool_name=tool_name,
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            duration_ms=observed_duration_ms(started_at_ms, completed_at_ms),
            execution_duration_ms=execution_duration_ms,
            review_count=0,
            guardian_review_count=0,
            user_review_count=0,
            final_approval_outcome=FinalApprovalOutcome.UNKNOWN,
            terminal_status=terminal_status,
            failure_kind=failure_kind,
            requested_additional_permissions=False,
            requested_network_access=False,
        ),
        review_summary,
    )


def command_execution_outcome(
    status: Any,
) -> tuple[ToolItemTerminalStatus, ToolItemFailureKind | None] | None:
    status_value = str(_enum_value(status))
    if status_value in {"InProgress", "in_progress"}:
        return None
    if status_value in {"Completed", "completed"}:
        return (ToolItemTerminalStatus.COMPLETED, None)
    if status_value in {"Failed", "failed"}:
        return (ToolItemTerminalStatus.FAILED, ToolItemFailureKind.TOOL_ERROR)
    if status_value in {"Declined", "declined"}:
        return (ToolItemTerminalStatus.REJECTED, ToolItemFailureKind.APPROVAL_DENIED)
    return None


def tool_item_status_outcome(
    status: Any,
) -> tuple[ToolItemTerminalStatus, ToolItemFailureKind | None] | None:
    status_value = str(_enum_value(status))
    if status_value in {"InProgress", "in_progress"}:
        return None
    if status_value in {"Completed", "completed"}:
        return (ToolItemTerminalStatus.COMPLETED, None)
    if status_value in {"Failed", "failed"}:
        return (ToolItemTerminalStatus.FAILED, ToolItemFailureKind.TOOL_ERROR)
    if status_value in {"Declined", "declined"}:
        return (ToolItemTerminalStatus.REJECTED, ToolItemFailureKind.APPROVAL_DENIED)
    return None


def mcp_tool_call_outcome(
    status: Any,
) -> tuple[ToolItemTerminalStatus, ToolItemFailureKind | None] | None:
    status_value = str(_enum_value(status))
    if status_value in {"InProgress", "in_progress"}:
        return None
    if status_value in {"Completed", "completed"}:
        return (ToolItemTerminalStatus.COMPLETED, None)
    if status_value in {"Failed", "failed"}:
        return (ToolItemTerminalStatus.FAILED, ToolItemFailureKind.TOOL_ERROR)
    return None


def image_generation_outcome(status: Any) -> tuple[ToolItemTerminalStatus, ToolItemFailureKind | None]:
    if str(_enum_value(status)) in {"failed", "error"}:
        return (ToolItemTerminalStatus.FAILED, ToolItemFailureKind.TOOL_ERROR)
    return (ToolItemTerminalStatus.COMPLETED, None)


def command_execution_source(source: Any) -> CommandExecutionSource | str:
    source_value = _enum_value(source)
    if source_value in {None, CommandExecutionSource.AGENT.value, "Agent"}:
        return CommandExecutionSource.AGENT
    if source_value in {CommandExecutionSource.USER_SHELL.value, "UserShell", "user_shell"}:
        return CommandExecutionSource.USER_SHELL
    if source_value in {CommandExecutionSource.UNIFIED_EXEC_STARTUP.value, "UnifiedExecStartup", "unified_exec_startup"}:
        return CommandExecutionSource.UNIFIED_EXEC_STARTUP
    if source_value in {
        CommandExecutionSource.UNIFIED_EXEC_INTERACTION.value,
        "UnifiedExecInteraction",
        "unified_exec_interaction",
    }:
        return CommandExecutionSource.UNIFIED_EXEC_INTERACTION
    return str(source_value)


def command_execution_tool_name(source: Any) -> str:
    normalized = command_execution_source(source)
    normalized_value = _enum_value(normalized)
    if normalized_value in {
        CommandExecutionSource.UNIFIED_EXEC_STARTUP.value,
        CommandExecutionSource.UNIFIED_EXEC_INTERACTION.value,
    }:
        return "unified_exec"
    if normalized_value == CommandExecutionSource.USER_SHELL.value:
        return "user_shell"
    return "shell"


def command_action_counts(command_actions: list[Any]) -> dict[str, int]:
    counts = {"total": len(command_actions), "read": 0, "list_files": 0, "search": 0, "unknown": 0}
    for action in command_actions:
        kind = str(_enum_value(_item_field(action, "kind", "type", "variant") or action.__class__.__name__))
        if kind in {"Read", "read"}:
            counts["read"] += 1
        elif kind in {"ListFiles", "list_files"}:
            counts["list_files"] += 1
        elif kind in {"Search", "search"}:
            counts["search"] += 1
        elif kind in {"Unknown", "unknown"}:
            counts["unknown"] += 1
    return counts


def file_change_counts(changes: list[Any]) -> dict[str, int]:
    counts = {"add": 0, "update": 0, "delete": 0, "move": 0}
    for change in changes:
        kind = str(_enum_value(_item_field(change, "kind", "type", "variant") or change.__class__.__name__))
        move_path = _item_field(change, "move_path")
        if kind in {"Add", "add"}:
            counts["add"] += 1
        elif kind in {"Delete", "delete"}:
            counts["delete"] += 1
        elif kind in {"Update", "update"} and move_path is not None:
            counts["move"] += 1
        elif kind in {"Update", "update"}:
            counts["update"] += 1
    return counts


def dynamic_content_counts(items: list[Any]) -> dict[str, int]:
    counts = {"total": len(items), "text": 0, "image": 0}
    for item in items:
        kind = str(_enum_value(_item_field(item, "kind", "type", "variant") or item.__class__.__name__))
        if kind in {"InputText", "input_text", "text"}:
            counts["text"] += 1
        elif kind in {"InputImage", "input_image", "image"}:
            counts["image"] += 1
    return counts


def web_search_action_kind(action: Any) -> WebSearchActionKind:
    kind = str(_enum_value(_item_field(action, "kind", "type", "variant") or action.__class__.__name__))
    if kind in {"Search", "search"}:
        return WebSearchActionKind.SEARCH
    if kind in {"OpenPage", "open_page"}:
        return WebSearchActionKind.OPEN_PAGE
    if kind in {"FindInPage", "find_in_page"}:
        return WebSearchActionKind.FIND_IN_PAGE
    return WebSearchActionKind.OTHER


def web_search_query_count(query: str, action: Any | None) -> int | None:
    if action is None:
        return 1 if query.strip() else None
    action_kind = web_search_action_kind(action)
    if action_kind is not WebSearchActionKind.SEARCH:
        return None
    queries = _item_field(action, "queries")
    action_query = _item_field(action, "query")
    if queries is not None:
        return len(queries)
    if action_query is not None:
        return 1
    return None


def collab_agent_tool_name(tool: Any) -> str:
    value = str(_enum_value(tool))
    mapping = {
        "SpawnAgent": "spawn_agent",
        "spawn_agent": "spawn_agent",
        "SendInput": "send_input",
        "send_input": "send_input",
        "ResumeAgent": "resume_agent",
        "resume_agent": "resume_agent",
        "Wait": "wait_agent",
        "wait": "wait_agent",
        "CloseAgent": "close_agent",
        "close_agent": "close_agent",
    }
    return mapping.get(value, value)


def collab_agent_state_counts(agent_states: Any) -> dict[str, int]:
    values = list(agent_states.values()) if isinstance(agent_states, dict) else list(agent_states)
    counts = {"total": len(values), "completed": 0, "failed": 0}
    for state in values:
        status = str(_enum_value(_item_field(state, "status") or state))
        if status in {"Completed", "completed"}:
            counts["completed"] += 1
        elif status in {"Errored", "errored", "Shutdown", "shutdown", "NotFound", "not_found"}:
            counts["failed"] += 1
    return counts


def _duration_ms_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return _non_negative_int_or_none(int(value))
    except (TypeError, ValueError):
        return None


def _item_field(item: Any, *names: str) -> Any:
    for name in names:
        if isinstance(item, dict) and name in item:
            return item[name]
        if hasattr(item, name):
            return getattr(item, name)
    return None


def item_review_summary_key(pending_review: PendingReviewState) -> ToolItemKey | None:
    subject_kind = _enum_value(pending_review.subject_kind)
    if subject_kind not in {
        ReviewSubjectKind.COMMAND_EXECUTION.value,
        ReviewSubjectKind.FILE_CHANGE.value,
        ReviewSubjectKind.MCP_TOOL_CALL.value,
    }:
        return None
    if pending_review.item_id is None:
        return None
    return ToolItemKey(pending_review.thread_id, pending_review.turn_id, pending_review.item_id)


def apply_tool_item_review_summary(
    base: CodexToolItemEventBase,
    summary: ToolItemReviewSummary | None,
) -> CodexToolItemEventBase:
    summary = summary or ToolItemReviewSummary()
    return replace(
        base,
        review_count=summary.review_count,
        guardian_review_count=summary.guardian_review_count,
        user_review_count=summary.user_review_count,
        final_approval_outcome=summary.final_approval_outcome or FinalApprovalOutcome.UNKNOWN,
        requested_additional_permissions=summary.requested_additional_permissions,
        requested_network_access=summary.requested_network_access,
    )


def codex_command_execution_event(
    *,
    base: CodexToolItemEventBase,
    command_execution_source: CommandExecutionSource | str,
    exit_code: int | None,
    command_total_action_count: int,
    command_read_action_count: int,
    command_list_files_action_count: int,
    command_search_action_count: int,
    command_unknown_action_count: int,
) -> dict[str, Any]:
    return {
        "event_type": "codex_command_execution_event",
        "event_params": codex_command_execution_event_params(
            base=base,
            command_execution_source=command_execution_source,
            exit_code=exit_code,
            command_total_action_count=command_total_action_count,
            command_read_action_count=command_read_action_count,
            command_list_files_action_count=command_list_files_action_count,
            command_search_action_count=command_search_action_count,
            command_unknown_action_count=command_unknown_action_count,
        ),
    }


def codex_command_execution_event_params(
    *,
    base: CodexToolItemEventBase,
    command_execution_source: CommandExecutionSource | str,
    exit_code: int | None,
    command_total_action_count: int,
    command_read_action_count: int,
    command_list_files_action_count: int,
    command_search_action_count: int,
    command_unknown_action_count: int,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "command_execution_source": _enum_value(command_execution_source),
            "exit_code": exit_code,
            "command_total_action_count": command_total_action_count,
            "command_read_action_count": command_read_action_count,
            "command_list_files_action_count": command_list_files_action_count,
            "command_search_action_count": command_search_action_count,
            "command_unknown_action_count": command_unknown_action_count,
        }
    )
    return params


def codex_file_change_event(
    *,
    base: CodexToolItemEventBase,
    file_change_count: int,
    file_add_count: int,
    file_update_count: int,
    file_delete_count: int,
    file_move_count: int,
) -> dict[str, Any]:
    return {
        "event_type": "codex_file_change_event",
        "event_params": codex_file_change_event_params(
            base=base,
            file_change_count=file_change_count,
            file_add_count=file_add_count,
            file_update_count=file_update_count,
            file_delete_count=file_delete_count,
            file_move_count=file_move_count,
        ),
    }


def codex_file_change_event_params(
    *,
    base: CodexToolItemEventBase,
    file_change_count: int,
    file_add_count: int,
    file_update_count: int,
    file_delete_count: int,
    file_move_count: int,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "file_change_count": file_change_count,
            "file_add_count": file_add_count,
            "file_update_count": file_update_count,
            "file_delete_count": file_delete_count,
            "file_move_count": file_move_count,
        }
    )
    return params


def codex_mcp_tool_call_event(
    *,
    base: CodexToolItemEventBase,
    mcp_server_name: str,
    mcp_tool_name: str,
    mcp_error_present: bool,
) -> dict[str, Any]:
    return {
        "event_type": "codex_mcp_tool_call_event",
        "event_params": codex_mcp_tool_call_event_params(
            base=base,
            mcp_server_name=mcp_server_name,
            mcp_tool_name=mcp_tool_name,
            mcp_error_present=mcp_error_present,
        ),
    }


def codex_mcp_tool_call_event_params(
    *,
    base: CodexToolItemEventBase,
    mcp_server_name: str,
    mcp_tool_name: str,
    mcp_error_present: bool,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "mcp_server_name": mcp_server_name,
            "mcp_tool_name": mcp_tool_name,
            "mcp_error_present": mcp_error_present,
        }
    )
    return params


def codex_dynamic_tool_call_event(
    *,
    base: CodexToolItemEventBase,
    dynamic_tool_name: str,
    success: bool | None,
    output_content_item_count: int | None,
    output_text_item_count: int | None,
    output_image_item_count: int | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_dynamic_tool_call_event",
        "event_params": codex_dynamic_tool_call_event_params(
            base=base,
            dynamic_tool_name=dynamic_tool_name,
            success=success,
            output_content_item_count=output_content_item_count,
            output_text_item_count=output_text_item_count,
            output_image_item_count=output_image_item_count,
        ),
    }


def codex_dynamic_tool_call_event_params(
    *,
    base: CodexToolItemEventBase,
    dynamic_tool_name: str,
    success: bool | None,
    output_content_item_count: int | None,
    output_text_item_count: int | None,
    output_image_item_count: int | None,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "dynamic_tool_name": dynamic_tool_name,
            "success": success,
            "output_content_item_count": output_content_item_count,
            "output_text_item_count": output_text_item_count,
            "output_image_item_count": output_image_item_count,
        }
    )
    return params


def codex_collab_agent_tool_call_event(
    *,
    base: CodexToolItemEventBase,
    sender_thread_id: str,
    receiver_thread_count: int,
    receiver_thread_ids: list[str] | None,
    requested_model: str | None,
    requested_reasoning_effort: str | None,
    agent_state_count: int | None,
    completed_agent_count: int | None,
    failed_agent_count: int | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_collab_agent_tool_call_event",
        "event_params": codex_collab_agent_tool_call_event_params(
            base=base,
            sender_thread_id=sender_thread_id,
            receiver_thread_count=receiver_thread_count,
            receiver_thread_ids=receiver_thread_ids,
            requested_model=requested_model,
            requested_reasoning_effort=requested_reasoning_effort,
            agent_state_count=agent_state_count,
            completed_agent_count=completed_agent_count,
            failed_agent_count=failed_agent_count,
        ),
    }


def codex_collab_agent_tool_call_event_params(
    *,
    base: CodexToolItemEventBase,
    sender_thread_id: str,
    receiver_thread_count: int,
    receiver_thread_ids: list[str] | None,
    requested_model: str | None,
    requested_reasoning_effort: str | None,
    agent_state_count: int | None,
    completed_agent_count: int | None,
    failed_agent_count: int | None,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "sender_thread_id": sender_thread_id,
            "receiver_thread_count": receiver_thread_count,
            "receiver_thread_ids": None if receiver_thread_ids is None else list(receiver_thread_ids),
            "requested_model": requested_model,
            "requested_reasoning_effort": requested_reasoning_effort,
            "agent_state_count": agent_state_count,
            "completed_agent_count": completed_agent_count,
            "failed_agent_count": failed_agent_count,
        }
    )
    return params


def codex_web_search_event(
    *,
    base: CodexToolItemEventBase,
    web_search_action: WebSearchActionKind | str | None,
    query_present: bool,
    query_count: int | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_web_search_event",
        "event_params": codex_web_search_event_params(
            base=base,
            web_search_action=web_search_action,
            query_present=query_present,
            query_count=query_count,
        ),
    }


def codex_web_search_event_params(
    *,
    base: CodexToolItemEventBase,
    web_search_action: WebSearchActionKind | str | None,
    query_present: bool,
    query_count: int | None,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "web_search_action": _enum_value(web_search_action),
            "query_present": query_present,
            "query_count": query_count,
        }
    )
    return params


def codex_image_generation_event(
    *,
    base: CodexToolItemEventBase,
    revised_prompt_present: bool,
    saved_path_present: bool,
) -> dict[str, Any]:
    return {
        "event_type": "codex_image_generation_event",
        "event_params": codex_image_generation_event_params(
            base=base,
            revised_prompt_present=revised_prompt_present,
            saved_path_present=saved_path_present,
        ),
    }


def codex_image_generation_event_params(
    *,
    base: CodexToolItemEventBase,
    revised_prompt_present: bool,
    saved_path_present: bool,
) -> dict[str, Any]:
    params = codex_tool_item_event_base_params(base)
    params.update(
        {
            "revised_prompt_present": revised_prompt_present,
            "saved_path_present": saved_path_present,
        }
    )
    return params


def codex_turn_event_params(
    *,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    turn_id: str,
    turn_state: TurnState,
    thread_metadata: ThreadMetadataState,
) -> dict[str, Any] | None:
    if (
        turn_state.thread_id is None
        or turn_state.num_input_images is None
        or turn_state.resolved_config is None
        or turn_state.completed is None
    ):
        return None
    resolved = turn_state.resolved_config
    completed = turn_state.completed
    token_usage = turn_state.token_usage
    tool_counts = turn_state.tool_counts or TurnToolCounts()
    return {
        "thread_id": turn_state.thread_id,
        "session_id": thread_metadata.session_id,
        "turn_id": turn_id,
        "submission_type": _enum_value(resolved.submission_type),
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "ephemeral": resolved.ephemeral,
        "thread_source": _enum_value(thread_metadata.thread_source),
        "initialization_mode": _enum_value(thread_metadata.initialization_mode),
        "subagent_source": thread_metadata.subagent_source,
        "parent_thread_id": thread_metadata.parent_thread_id,
        "model": resolved.model,
        "model_provider": resolved.model_provider,
        "sandbox_policy": sandbox_policy_mode(resolved.permission_profile),
        "reasoning_effort": none_mode(resolved.reasoning_effort),
        "reasoning_summary": none_mode(resolved.reasoning_summary),
        "service_tier": "default" if resolved.service_tier is None else str(_enum_value(resolved.service_tier)),
        "approval_policy": str(_enum_value(resolved.approval_policy)),
        "approvals_reviewer": str(_enum_value(resolved.approvals_reviewer)),
        "sandbox_network_access": resolved.sandbox_network_access,
        "collaboration_mode": collaboration_mode_mode(resolved.collaboration_mode),
        "personality": none_mode(resolved.personality),
        "num_input_images": turn_state.num_input_images,
        "is_first_turn": resolved.is_first_turn,
        "status": _enum_value(completed.status),
        "turn_error": completed.turn_error,
        "steer_count": turn_state.steer_count,
        "total_tool_call_count": tool_counts.total,
        "shell_command_count": tool_counts.shell_command,
        "file_change_count": tool_counts.file_change,
        "mcp_tool_call_count": tool_counts.mcp_tool_call,
        "dynamic_tool_call_count": tool_counts.dynamic_tool_call,
        "subagent_tool_call_count": tool_counts.subagent_tool_call,
        "web_search_count": tool_counts.web_search,
        "image_generation_count": tool_counts.image_generation,
        "input_tokens": None if token_usage is None else token_usage.input_tokens,
        "cached_input_tokens": None if token_usage is None else token_usage.cached_input_tokens,
        "output_tokens": None if token_usage is None else token_usage.output_tokens,
        "reasoning_output_tokens": None if token_usage is None else token_usage.reasoning_output_tokens,
        "total_tokens": None if token_usage is None else token_usage.total_tokens,
        "duration_ms": completed.duration_ms,
        "started_at": turn_state.started_at,
        "completed_at": completed.completed_at,
    }


def codex_turn_steer_event(
    *,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    pending_request: PendingTurnSteerState,
    thread_metadata: ThreadMetadataState,
    accepted_turn_id: str | None,
    result: TurnSteerResult | str,
    rejection_reason: TurnSteerRejectionReason | AnalyticsJsonRpcError | TurnSteerRequestError | InputError | str | None,
) -> dict[str, Any]:
    return {
        "event_type": "codex_turn_steer_event",
        "event_params": codex_turn_steer_event_params(
            app_server_client=app_server_client,
            runtime=runtime,
            pending_request=pending_request,
            thread_metadata=thread_metadata,
            accepted_turn_id=accepted_turn_id,
            result=result,
            rejection_reason=rejection_reason,
        ),
    }


def codex_turn_steer_event_params(
    *,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    pending_request: PendingTurnSteerState,
    thread_metadata: ThreadMetadataState,
    accepted_turn_id: str | None,
    result: TurnSteerResult | str,
    rejection_reason: TurnSteerRejectionReason | AnalyticsJsonRpcError | TurnSteerRequestError | InputError | str | None,
) -> dict[str, Any]:
    return {
        "thread_id": pending_request.thread_id,
        "session_id": thread_metadata.session_id,
        "expected_turn_id": pending_request.expected_turn_id,
        "accepted_turn_id": accepted_turn_id,
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "thread_source": _enum_value(thread_metadata.thread_source),
        "subagent_source": thread_metadata.subagent_source,
        "parent_thread_id": thread_metadata.parent_thread_id,
        "num_input_images": pending_request.num_input_images,
        "result": _enum_value(result),
        "rejection_reason": rejection_reason_value(rejection_reason),
        "created_at": pending_request.created_at,
    }


def rejection_reason_value(
    rejection_reason: TurnSteerRejectionReason | AnalyticsJsonRpcError | TurnSteerRequestError | InputError | str | None,
) -> str | None:
    if rejection_reason is None:
        return None
    if isinstance(rejection_reason, (AnalyticsJsonRpcError, TurnSteerRequestError, InputError)):
        return turn_steer_rejection_reason_from_error(rejection_reason).value
    return str(_enum_value(rejection_reason))


def apply_accepted_turn_steer(turns: dict[str, TurnState], accepted_turn_id: str) -> None:
    turn_state = turns.get(accepted_turn_id)
    if turn_state is not None:
        turn_state.steer_count += 1


def sandbox_policy_mode(permission_profile: Any) -> str | None:
    if isinstance(permission_profile, str):
        return permission_profile
    if isinstance(permission_profile, dict):
        value = permission_profile.get("sandbox_policy") or permission_profile.get("mode") or permission_profile.get("kind")
        if isinstance(value, str):
            lowered = value.lower()
            if lowered == "managed":
                file_system = permission_profile.get("file_system") or permission_profile.get("file_system_sandbox_policy") or {}
                network = permission_profile.get("network") or permission_profile.get("network_sandbox_policy") or {}
                fs_value = _enum_value(file_system.get("mode") if isinstance(file_system, dict) else file_system)
                network_value = _enum_value(network.get("mode") if isinstance(network, dict) else network)
                fs_text = str(fs_value).lower()
                network_text = str(network_value).lower()
                if fs_text in {"unrestricted", "full_disk", "full_disk_write", "full_access"}:
                    return "full_access" if network_text in {"enabled", "unrestricted", "full_access"} else "external_sandbox"
            return value
    return str(_enum_value(permission_profile)) if permission_profile is not None else None


def collaboration_mode_mode(mode: Any) -> str | None:
    value = _enum_value(mode)
    if value is None:
        return None
    lowered = str(value).lower()
    if lowered == "plan":
        return "plan"
    return "default"


def none_mode(value: Any) -> str | None:
    raw = _enum_value(value)
    if raw is None:
        return None
    if str(raw).lower() == "none":
        return None
    return str(raw)


GuardianReviewedAction = dict[str, Any]


__all__ = [name for name in globals() if not name.startswith("_")]
