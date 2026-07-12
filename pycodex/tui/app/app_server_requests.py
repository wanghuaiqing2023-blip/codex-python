"""Pending app-server request correlation state.

Rust counterpart: ``codex-rs/tui/src/app/app_server_requests.rs``.
"""

from __future__ import annotations

import inspect
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Tuple

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::app_server_requests",
    source="codex/codex-rs/tui/src/app/app_server_requests.rs",
    status="complete",
)


@dataclass(frozen=True)
class JSONRPCErrorError:
    code: int
    message: str
    data: Any = None


async def reject_app_server_request(
    app_server_client: Any,
    request_id: Any,
    reason: str,
) -> Optional[str]:
    """Reject an app-server request with Rust's JSON-RPC error shape.

    Rust returns ``Result<(), String>`` and maps transport errors to
    ``failed to reject app-server request: {err}``. Python mirrors that as
    ``None`` on success or the error string on failure.
    """

    error = JSONRPCErrorError(code=-32000, message=reason, data=None)
    try:
        result = app_server_client.reject_server_request(request_id, error)
        if inspect.isawaitable(result):
            await result
        return None
    except Exception as exc:
        return "failed to reject app-server request: {0}".format(exc)


@dataclass(frozen=True)
class AppServerRequestResolution:
    request_id: Any
    result: Any


@dataclass(frozen=True)
class UnsupportedAppServerRequest:
    request_id: Any
    message: str


@dataclass(frozen=True)
class ResolvedAppServerRequest:
    kind: str
    id: Optional[str] = None
    call_id: Optional[str] = None
    server_name: Optional[str] = None
    request_id: Any = None

    @classmethod
    def ExecApproval(cls, id: str) -> "ResolvedAppServerRequest":
        return cls("ExecApproval", id=id)

    @classmethod
    def FileChangeApproval(cls, id: str) -> "ResolvedAppServerRequest":
        return cls("FileChangeApproval", id=id)

    @classmethod
    def PermissionsApproval(cls, id: str) -> "ResolvedAppServerRequest":
        return cls("PermissionsApproval", id=id)

    @classmethod
    def UserInput(cls, call_id: str) -> "ResolvedAppServerRequest":
        return cls("UserInput", call_id=call_id)

    @classmethod
    def McpElicitation(cls, server_name: str, request_id: Any) -> "ResolvedAppServerRequest":
        return cls("McpElicitation", server_name=server_name, request_id=request_id)


@dataclass(frozen=True)
class PendingUserInputRequest:
    item_id: str
    request_id: Any


@dataclass(frozen=True)
class McpRequestKey:
    server_name: str
    request_id: Any


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _variant_and_payload(value: Any) -> Tuple[Optional[str], Any, Any]:
    variant = _field(value, "type", _field(value, "variant", _field(value, "kind")))
    if variant is not None:
        request_id = _field(value, "request_id")
        if request_id is None:
            request_id = _field(value, "id")
        payload = _field(value, "params", None)
        if payload is None:
            payload = _field(value, "payload", value)
        return str(variant), payload, request_id
    if isinstance(value, dict) and len(value) == 1:
        variant, payload = next(iter(value.items()))
        return str(variant), payload, _field(payload, "request_id")
    return value.__class__.__name__ if value is not None else None, value, _field(value, "request_id")


def _payload_id(payload: Any, name: str) -> str:
    return str(_field(payload, name))


def _payload_id_alias(payload: Any, *names: str) -> str:
    for name in names:
        value = _field(payload, name)
        if value is not None and str(value):
            return str(value)
    return ""


def _decision_value(decision: Any) -> Any:
    if hasattr(decision, "value"):
        return decision.value
    return decision


@dataclass
class PendingAppServerRequests:
    exec_approvals: Dict[str, Any] = field(default_factory=dict)
    file_change_approvals: Dict[str, Any] = field(default_factory=dict)
    permissions_approvals: Dict[str, Any] = field(default_factory=dict)
    user_inputs: Dict[str, Deque[PendingUserInputRequest]] = field(default_factory=dict)
    mcp_requests: Dict[McpRequestKey, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.exec_approvals.clear()
        self.file_change_approvals.clear()
        self.permissions_approvals.clear()
        self.user_inputs.clear()
        self.mcp_requests.clear()

    def note_server_request(self, request: Any) -> Optional[UnsupportedAppServerRequest]:
        variant, params, request_id = _variant_and_payload(request)
        if variant == "CommandExecutionRequestApproval":
            approval_id = _payload_id_alias(params, "approval_id", "approvalId", "item_id", "itemId", "call_id", "callId", "id")
            self.exec_approvals[str(approval_id)] = request_id
            return None
        if variant == "FileChangeRequestApproval":
            self.file_change_approvals[_payload_id_alias(params, "item_id", "itemId", "call_id", "callId", "id")] = request_id
            return None
        if variant == "PermissionsRequestApproval":
            self.permissions_approvals[_payload_id_alias(params, "item_id", "itemId", "call_id", "callId", "id")] = request_id
            return None
        if variant == "ToolRequestUserInput":
            turn_id = _payload_id(params, "turn_id")
            self.user_inputs.setdefault(turn_id, deque()).append(
                PendingUserInputRequest(_payload_id(params, "item_id"), request_id)
            )
            return None
        if variant == "McpServerElicitationRequest":
            key = McpRequestKey(str(_field(params, "server_name")), request_id)
            self.mcp_requests[key] = request_id
            return None
        if variant == "DynamicToolCall":
            return UnsupportedAppServerRequest(
                request_id,
                "Dynamic tool calls are not available in TUI yet.",
            )
        if variant == "ChatgptAuthTokensRefresh":
            return None
        if variant == "AttestationGenerate":
            return UnsupportedAppServerRequest(
                request_id,
                "Attestation generation is not available in TUI.",
            )
        if variant == "ApplyPatchApproval":
            return UnsupportedAppServerRequest(
                request_id,
                "Legacy patch approval requests are not available in TUI yet.",
            )
        if variant == "ExecCommandApproval":
            return UnsupportedAppServerRequest(
                request_id,
                "Legacy command approval requests are not available in TUI yet.",
            )
        return None

    def take_resolution(self, op: Any) -> Optional[AppServerRequestResolution]:
        variant, payload, _ = _variant_and_payload(op)
        if variant == "ExecApproval":
            id_ = _payload_id(payload, "id")
            request_id = self.exec_approvals.pop(id_, None)
            if request_id is None:
                return None
            return AppServerRequestResolution(
                request_id,
                {"decision": _decision_value(_field(payload, "decision"))},
            )
        if variant == "PatchApproval":
            id_ = _payload_id(payload, "id")
            request_id = self.file_change_approvals.pop(id_, None)
            if request_id is None:
                return None
            return AppServerRequestResolution(
                request_id,
                {"decision": _decision_value(_field(payload, "decision"))},
            )
        if variant == "RequestPermissionsResponse":
            id_ = _payload_id(payload, "id")
            request_id = self.permissions_approvals.pop(id_, None)
            if request_id is None:
                return None
            response = _field(payload, "response", {})
            strict = bool(_field(response, "strict_auto_review", False))
            return AppServerRequestResolution(
                request_id,
                {
                    "permissions": _field(response, "permissions"),
                    "scope": _decision_value(_field(response, "scope")),
                    "strict_auto_review": True if strict else None,
                },
            )
        if variant == "UserInputAnswer":
            pending = self.pop_user_input_request_for_turn(_payload_id(payload, "id"))
            if pending is None:
                return None
            return AppServerRequestResolution(
                pending.request_id,
                _field(payload, "response"),
            )
        if variant == "ResolveElicitation":
            key = McpRequestKey(str(_field(payload, "server_name")), _field(payload, "request_id"))
            request_id = self.mcp_requests.pop(key, None)
            if request_id is None:
                return None
            result = {
                "action": _decision_value(_field(payload, "decision")),
                "content": _field(payload, "content"),
            }
            meta = _field(payload, "meta")
            if meta is not None:
                result["_meta"] = meta
            return AppServerRequestResolution(request_id, result)
        return None

    def resolve_notification(self, request_id: Any) -> Optional[ResolvedAppServerRequest]:
        for id_, value in list(self.exec_approvals.items()):
            if value == request_id:
                del self.exec_approvals[id_]
                return ResolvedAppServerRequest.ExecApproval(id_)
        for id_, value in list(self.file_change_approvals.items()):
            if value == request_id:
                del self.file_change_approvals[id_]
                return ResolvedAppServerRequest.FileChangeApproval(id_)
        for id_, value in list(self.permissions_approvals.items()):
            if value == request_id:
                del self.permissions_approvals[id_]
                return ResolvedAppServerRequest.PermissionsApproval(id_)
        pending = self.remove_user_input_request(request_id)
        if pending is not None:
            return ResolvedAppServerRequest.UserInput(pending.item_id)
        for key, value in list(self.mcp_requests.items()):
            if value == request_id:
                del self.mcp_requests[key]
                return ResolvedAppServerRequest.McpElicitation(key.server_name, key.request_id)
        return None

    def contains_server_request(self, request: Any) -> bool:
        variant, _params, request_id = _variant_and_payload(request)
        if variant == "CommandExecutionRequestApproval":
            return request_id in self.exec_approvals.values()
        if variant == "FileChangeRequestApproval":
            return request_id in self.file_change_approvals.values()
        if variant == "PermissionsRequestApproval":
            return request_id in self.permissions_approvals.values()
        if variant == "ToolRequestUserInput":
            return any(p.request_id == request_id for q in self.user_inputs.values() for p in q)
        if variant == "McpServerElicitationRequest":
            return request_id in self.mcp_requests.values()
        return True

    def pop_user_input_request_for_turn(self, turn_id: str) -> Optional[PendingUserInputRequest]:
        queue = self.user_inputs.get(str(turn_id))
        if not queue:
            return None
        pending = queue.popleft()
        if not queue:
            self.user_inputs.pop(str(turn_id), None)
        return pending

    def remove_user_input_request(self, request_id: Any) -> Optional[PendingUserInputRequest]:
        for turn_id, queue in list(self.user_inputs.items()):
            for index, pending in enumerate(queue):
                if pending.request_id == request_id:
                    removed = queue[index]
                    del queue[index]
                    if not queue:
                        self.user_inputs.pop(turn_id, None)
                    return removed
        return None


def resolves_exec_approval_through_app_server_request_id() -> bool:
    pending = PendingAppServerRequests()
    request = {
        "CommandExecutionRequestApproval": {
            "request_id": 41,
            "approval_id": "approval-1",
            "item_id": "call-1",
        }
    }
    return (
        pending.note_server_request(request) is None
        and pending.take_resolution(
            {"type": "ExecApproval", "id": "approval-1", "decision": "accept"}
        )
        == AppServerRequestResolution(41, {"decision": "accept"})
    )


def resolves_permissions_and_user_input_through_app_server_request_id() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {"PermissionsRequestApproval": {"request_id": 7, "item_id": "perm-1"}}
    )
    pending.note_server_request(
        {
            "ToolRequestUserInput": {
                "request_id": 8,
                "turn_id": "turn-2",
                "item_id": "tool-1",
            }
        }
    )
    permissions = pending.take_resolution(
        {
            "type": "RequestPermissionsResponse",
            "id": "perm-1",
            "response": {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
                "strict_auto_review": False,
            },
        }
    )
    user_input = pending.take_resolution(
        {
            "type": "UserInputAnswer",
            "id": "turn-2",
            "response": {"answers": {"question": {"answers": ["yes"]}}},
        }
    )
    return (
        permissions == AppServerRequestResolution(
            7,
            {
                "permissions": {"network": {"enabled": True}},
                "scope": "session",
                "strict_auto_review": None,
            },
        )
        and user_input
        == AppServerRequestResolution(
            8,
            {"answers": {"question": {"answers": ["yes"]}}},
        )
    )


def correlates_mcp_elicitation_server_request_with_resolution() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "McpServerElicitationRequest": {
                "request_id": 12,
                "server_name": "example",
            }
        }
    )
    resolution = pending.take_resolution(
        {
            "type": "ResolveElicitation",
            "server_name": "example",
            "request_id": 12,
            "decision": "accept",
            "content": {"answer": "yes"},
            "meta": {"source": "tui"},
        }
    )
    return resolution == AppServerRequestResolution(
        12,
        {"action": "accept", "content": {"answer": "yes"}, "_meta": {"source": "tui"}},
    )


def rejects_dynamic_tool_calls_as_unsupported() -> bool:
    unsupported = PendingAppServerRequests().note_server_request(
        {"DynamicToolCall": {"request_id": 99}}
    )
    return unsupported == UnsupportedAppServerRequest(
        99,
        "Dynamic tool calls are not available in TUI yet.",
    )


def does_not_mark_chatgpt_auth_refresh_as_unsupported() -> bool:
    return (
        PendingAppServerRequests().note_server_request(
            {"ChatgptAuthTokensRefresh": {"request_id": 100}}
        )
        is None
    )


def resolves_patch_approval_through_app_server_request_id() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {"FileChangeRequestApproval": {"request_id": 13, "item_id": "patch-1"}}
    )
    return pending.take_resolution(
        {"type": "PatchApproval", "id": "patch-1", "decision": "cancel"}
    ) == AppServerRequestResolution(13, {"decision": "cancel"})


def resolve_notification_returns_resolved_exec_request() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "CommandExecutionRequestApproval": {
                "request_id": 41,
                "approval_id": "approval-1",
                "item_id": "call-1",
            }
        }
    )
    return (
        pending.resolve_notification(41)
        == ResolvedAppServerRequest.ExecApproval("approval-1")
        and pending.resolve_notification(41) is None
    )


def resolve_notification_returns_resolved_mcp_request() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "McpServerElicitationRequest": {
                "request_id": 12,
                "server_name": "example",
            }
        }
    )
    return pending.resolve_notification(12) == ResolvedAppServerRequest.McpElicitation(
        "example",
        12,
    )


def resolve_notification_returns_resolved_user_input_item_id() -> bool:
    pending = PendingAppServerRequests()
    pending.note_server_request(
        {
            "ToolRequestUserInput": {
                "request_id": 8,
                "turn_id": "turn-1",
                "item_id": "tool-1",
            }
        }
    )
    return pending.resolve_notification(8) == ResolvedAppServerRequest.UserInput("tool-1")


def same_turn_user_input_answers_resolve_app_server_requests_fifo() -> bool:
    pending = PendingAppServerRequests()
    for request_id, item_id in [(8, "tool-1"), (9, "tool-2")]:
        pending.note_server_request(
            {
                "ToolRequestUserInput": {
                    "request_id": request_id,
                    "turn_id": "turn-1",
                    "item_id": item_id,
                }
            }
        )
    response = {"answers": {}}
    first = pending.take_resolution({"type": "UserInputAnswer", "id": "turn-1", "response": response})
    second = pending.take_resolution({"type": "UserInputAnswer", "id": "turn-1", "response": response})
    return (
        first == AppServerRequestResolution(8, response)
        and second == AppServerRequestResolution(9, response)
    )


__all__ = [
    "AppServerRequestResolution",
    "JSONRPCErrorError",
    "McpRequestKey",
    "PendingAppServerRequests",
    "PendingUserInputRequest",
    "RUST_MODULE",
    "ResolvedAppServerRequest",
    "UnsupportedAppServerRequest",
    "correlates_mcp_elicitation_server_request_with_resolution",
    "does_not_mark_chatgpt_auth_refresh_as_unsupported",
    "rejects_dynamic_tool_calls_as_unsupported",
    "reject_app_server_request",
    "resolve_notification_returns_resolved_exec_request",
    "resolve_notification_returns_resolved_mcp_request",
    "resolve_notification_returns_resolved_user_input_item_id",
    "resolves_exec_approval_through_app_server_request_id",
    "resolves_patch_approval_through_app_server_request_id",
    "resolves_permissions_and_user_input_through_app_server_request_id",
    "same_turn_user_input_answers_resolve_app_server_requests_fifo",
]
