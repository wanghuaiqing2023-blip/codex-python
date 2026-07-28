"""Session MCP behavior aligned with ``codex-core::session::mcp``."""

from __future__ import annotations

import asyncio
import inspect
import weakref
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from pycodex.app_server_protocol.mcp import McpServerElicitationRequest
from pycodex.core.guardian import (
    GuardianApprovalRequest,
    guardian_rejection_message,
    guardian_timeout_message,
    routes_approval_to_guardian,
)
from pycodex.core.mcp_tool_call import ElicitationResponse
from pycodex.protocol import (
    ElicitationAction,
    ElicitationRequest,
    ElicitationRequestEvent,
    EventMsg,
    RequestId,
    ReviewDecision,
)
from pycodex.protocol.mcp_approval_meta import (
    APPROVAL_KIND_KEY,
    APPROVAL_KIND_MCP_TOOL_CALL,
    APPROVAL_KIND_TOOL_SUGGESTION,
    APPROVALS_REVIEWER_KEY,
    CONNECTOR_DESCRIPTION_KEY,
    CONNECTOR_ID_KEY,
    CONNECTOR_NAME_KEY,
    REQUEST_TYPE_APPROVAL_REQUEST,
    REQUEST_TYPE_KEY,
    TOOL_DESCRIPTION_KEY,
    TOOL_NAME_KEY,
    TOOL_PARAMS_KEY,
    TOOL_TITLE_KEY,
)


MCP_ELICITATION_DECLINE_MESSAGE_KEY = "message"
TOOL_SUGGESTION_ACTION_INSTALL = "install"
TOOL_SUGGESTION_ACTION_KEY = "suggest_type"
TOOL_SUGGESTION_TOOL_ID_KEY = "tool_id"
TOOL_SUGGESTION_TOOL_TYPE_KEY = "tool_type"
AUTO_REVIEW_METADATA_VALUE = "auto_review"


@dataclass(frozen=True)
class GuardianElicitationReview:
    kind: str
    reason: str | None = None
    approval_request: GuardianApprovalRequest | None = None

    @classmethod
    def not_requested(cls) -> "GuardianElicitationReview":
        return cls("not_requested")

    @classmethod
    def decline(cls, reason: str) -> "GuardianElicitationReview":
        return cls("decline", reason=reason)

    @classmethod
    def approval(cls, request: GuardianApprovalRequest) -> "GuardianElicitationReview":
        return cls("approval_request", approval_request=request)


class GuardianMcpElicitationReviewer:
    def __init__(self, session: Any) -> None:
        self._session = weakref.ref(session)

    @classmethod
    def new(cls, session: Any) -> "GuardianMcpElicitationReviewer":
        return cls(session)

    async def review(self, request: Any) -> ElicitationResponse | None:
        session = self._session()
        if session is None:
            return None
        return await review_guardian_mcp_elicitation(session, request)


@dataclass(frozen=True)
class McpServerElicitationOutcome:
    response: ElicitationResponse | None
    sent: bool


@dataclass(frozen=True)
class PluginInstallElicitationTelemetryMetadata:
    tool_type: str
    tool_id: str
    tool_name: str


def mcp_elicitation_reviewer(self: Any) -> GuardianMcpElicitationReviewer:
    return GuardianMcpElicitationReviewer.new(self)


async def request_mcp_server_elicitation(
    self: Any,
    turn_context: Any,
    request_id: RequestId | str | int,
    params: Any,
) -> McpServerElicitationOutcome:
    manager = await _mcp_manager(self)
    auto_deny = getattr(manager, "elicitations_auto_deny", None)
    if callable(auto_deny) and bool(await _maybe_await(auto_deny())):
        return McpServerElicitationOutcome(
            ElicitationResponse(ElicitationAction.ACCEPT, {}, None),
            False,
        )

    server_name = str(_field(params, "server_name"))
    request = _protocol_elicitation_request(_field(params, "request"))
    protocol_id = RequestId.from_value(request_id)
    future = asyncio.get_running_loop().create_future()
    turn_state = _active_turn_state(self)
    if turn_state is not None:
        previous = turn_state.insert_pending_elicitation(server_name, protocol_id, future)
        if previous is not None and not previous.done():
            previous.cancel()

    event = EventMsg.with_payload(
        "elicitation_request",
        ElicitationRequestEvent(
            turn_id=_field(params, "turn_id"),
            server_name=server_name,
            id=protocol_id,
            request=request,
        ),
    )
    telemetry_metadata = plugin_install_elicitation_telemetry_metadata(event)
    _mark_user_input_requested(turn_context)
    await _maybe_await(self.send_event(turn_context, event))
    _record_plugin_install_elicitation(turn_context, telemetry_metadata)
    if turn_state is None:
        return McpServerElicitationOutcome(None, True)
    try:
        return McpServerElicitationOutcome(await future, True)
    except asyncio.CancelledError:
        return McpServerElicitationOutcome(None, True)


async def resolve_elicitation(
    self: Any,
    server_name: str,
    request_id: RequestId | str | int,
    response: ElicitationResponse,
) -> None:
    protocol_id = RequestId.from_value(request_id)
    turn_state = _active_turn_state(self)
    pending = None if turn_state is None else turn_state.remove_pending_elicitation(server_name, protocol_id)
    if pending is not None:
        if not pending.done():
            pending.set_result(response)
        return
    manager = await _mcp_manager(self)
    await _call_required(manager, "resolve_elicitation", server_name, request_id, response)


async def list_resources(self: Any, server: str, params: Any = None) -> Any:
    return await _call_required(await _mcp_manager(self), "list_resources", server, params)


async def list_resource_templates(self: Any, server: str, params: Any = None) -> Any:
    return await _call_required(await _mcp_manager(self), "list_resource_templates", server, params)


async def read_resource(self: Any, server: str, params: Any) -> Any:
    return await _call_required(await _mcp_manager(self), "read_resource", server, params)


async def call_tool(
    self: Any,
    server: str,
    tool: str,
    arguments: Any = None,
    meta: Any = None,
) -> Any:
    return await _call_required(await _mcp_manager(self), "call_tool", server, tool, arguments, meta)


async def refresh_mcp_servers_inner(
    self: Any,
    turn_context: Any,
    mcp_servers: Mapping[str, Any],
    store_mode: Any,
    elicitation_reviewer: Any = None,
) -> None:
    services = _field(self, "services")
    startup_token = _field(services, "mcp_startup_cancellation_token")
    await _cancel_token(startup_token)
    manager = await _mcp_manager(self)
    refresh = getattr(manager, "refresh", None)
    if callable(refresh):
        await _maybe_await(refresh(dict(mcp_servers), store_mode, turn_context, elicitation_reviewer))
        return
    replacement = getattr(manager, "replace_from_config", None)
    if callable(replacement):
        await _maybe_await(replacement(dict(mcp_servers), store_mode, turn_context, elicitation_reviewer))


async def refresh_mcp_servers_if_requested(
    self: Any,
    turn_context: Any,
    elicitation_reviewer: Any = None,
) -> None:
    refresh_config = await _take_pending_refresh(self)
    if refresh_config is None:
        return
    mcp_servers = _field(refresh_config, "mcp_servers")
    store_mode = _field(refresh_config, "mcp_oauth_credentials_store_mode")
    if not isinstance(mcp_servers, Mapping):
        return
    await refresh_mcp_servers_inner(self, turn_context, mcp_servers, store_mode, elicitation_reviewer)


async def refresh_mcp_servers_now(
    self: Any,
    turn_context: Any,
    mcp_servers: Mapping[str, Any],
    store_mode: Any,
    elicitation_reviewer: Any = None,
) -> None:
    await refresh_mcp_servers_inner(self, turn_context, mcp_servers, store_mode, elicitation_reviewer)


async def cancel_mcp_startup(self: Any) -> None:
    await _cancel_token(_field(_field(self, "services"), "mcp_startup_cancellation_token"))


async def review_guardian_mcp_elicitation(session: Any, request: Any) -> ElicitationResponse | None:
    active = await _maybe_await(session.active_turn_context_and_cancellation_token())
    if active is None:
        return None
    turn_context, _cancellation_token = active
    if not routes_approval_to_guardian(turn_context):
        return None
    review = guardian_elicitation_review_request(request)
    if review.kind == "not_requested":
        return None
    if review.kind == "decline":
        return mcp_elicitation_decline_without_message()
    reviewer = getattr(session, "review_approval_request", None)
    if not callable(reviewer) or review.approval_request is None:
        return None
    review_id = _new_guardian_review_id()
    decision = await _maybe_await(
        reviewer(turn_context, review_id, review.approval_request, None)
    )
    return await mcp_elicitation_response_from_guardian_decision(session, review_id, decision)


def guardian_elicitation_review_request(request: Any) -> GuardianElicitationReview:
    server_name = str(_field(request, "server_name"))
    request_id = _field(request, "request_id")
    elicitation = _field(request, "elicitation")
    mode = _field(elicitation, "mode")
    meta = _field(elicitation, "meta")
    if mode == "url":
        return (
            GuardianElicitationReview.decline(
                "guardian MCP elicitation review only supports form elicitations"
            )
            if meta_requests_approval_request(meta)
            else GuardianElicitationReview.not_requested()
        )
    if not isinstance(meta, Mapping):
        return GuardianElicitationReview.not_requested()
    if metadata_str(meta, REQUEST_TYPE_KEY) != REQUEST_TYPE_APPROVAL_REQUEST:
        return GuardianElicitationReview.not_requested()
    if metadata_str(meta, APPROVAL_KIND_KEY) != APPROVAL_KIND_MCP_TOOL_CALL:
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation metadata must declare mcp_tool_call approval kind"
        )
    schema = _field(elicitation, "requested_schema")
    if _schema_properties(schema):
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation review only supports empty form schemas"
        )
    tool_name = metadata_owned_string(meta, TOOL_NAME_KEY)
    if tool_name is None:
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation metadata must include a non-empty tool_name"
        )
    arguments = meta.get(TOOL_PARAMS_KEY, {})
    if not isinstance(arguments, Mapping):
        return GuardianElicitationReview.decline(
            "guardian MCP elicitation tool_params must be an object"
        )
    return GuardianElicitationReview.approval(
        GuardianApprovalRequest.mcp_tool_call(
            id=f"mcp_elicitation:{server_name}:{mcp_elicitation_request_id(request_id)}",
            server=server_name,
            tool_name=tool_name,
            arguments=dict(arguments),
            connector_id=metadata_owned_string(meta, CONNECTOR_ID_KEY),
            connector_name=metadata_owned_string(meta, CONNECTOR_NAME_KEY),
            connector_description=metadata_owned_string(meta, CONNECTOR_DESCRIPTION_KEY),
            tool_title=metadata_owned_string(meta, TOOL_TITLE_KEY),
            tool_description=metadata_owned_string(meta, TOOL_DESCRIPTION_KEY),
            annotations=None,
        )
    )


def meta_requests_approval_request(meta: Any) -> bool:
    return isinstance(meta, Mapping) and metadata_str(meta, REQUEST_TYPE_KEY) == REQUEST_TYPE_APPROVAL_REQUEST


def metadata_str(meta: Mapping[str, Any], key: str) -> str | None:
    value = meta.get(key)
    return value if isinstance(value, str) else None


def metadata_owned_string(meta: Mapping[str, Any], key: str) -> str | None:
    value = metadata_str(meta, key)
    if value is None or not value.strip():
        return None
    return value.strip()


def plugin_install_elicitation_telemetry_metadata(
    event: EventMsg,
) -> PluginInstallElicitationTelemetryMetadata | None:
    if event.type != "elicitation_request" or not isinstance(event.payload, ElicitationRequestEvent):
        return None
    request = event.payload.request
    if request.mode != "form" or not isinstance(request.meta, Mapping):
        return None
    meta = request.meta
    if (
        metadata_str(meta, APPROVAL_KIND_KEY) != APPROVAL_KIND_TOOL_SUGGESTION
        or metadata_str(meta, TOOL_SUGGESTION_ACTION_KEY) != TOOL_SUGGESTION_ACTION_INSTALL
    ):
        return None
    tool_type = metadata_owned_string(meta, TOOL_SUGGESTION_TOOL_TYPE_KEY)
    tool_id = metadata_owned_string(meta, TOOL_SUGGESTION_TOOL_ID_KEY)
    tool_name = metadata_owned_string(meta, TOOL_NAME_KEY)
    if tool_type is None or tool_id is None or tool_name is None:
        return None
    return PluginInstallElicitationTelemetryMetadata(tool_type, tool_id, tool_name)


def mcp_elicitation_request_id(request_id: Any) -> str:
    value = getattr(request_id, "value", request_id)
    return str(value)


async def mcp_elicitation_response_from_guardian_decision(
    session: Any,
    review_id: str,
    decision: ReviewDecision | Any,
) -> ElicitationResponse:
    decision = ReviewDecision.from_mapping(decision)
    denial_message = None
    if decision.type == "denied":
        denial_message = await guardian_rejection_message(session, review_id)
    return mcp_elicitation_response_from_guardian_decision_parts(decision, denial_message)


def mcp_elicitation_response_from_guardian_decision_parts(
    decision: ReviewDecision | Any,
    denial_message: str | None,
) -> ElicitationResponse:
    decision = ReviewDecision.from_mapping(decision)
    if decision.type in {
        "approved",
        "approved_for_session",
        "approved_execpolicy_amendment",
        "network_policy_amendment",
    }:
        return ElicitationResponse(ElicitationAction.ACCEPT, {}, mcp_elicitation_auto_meta())
    if decision.type == "denied":
        return mcp_elicitation_decline_with_message(denial_message or "Guardian denied this request.")
    if decision.type == "timed_out":
        return mcp_elicitation_decline_with_message(guardian_timeout_message())
    return ElicitationResponse(ElicitationAction.CANCEL, None, mcp_elicitation_auto_meta())


def mcp_elicitation_decline_with_message(message: str) -> ElicitationResponse:
    return ElicitationResponse(
        ElicitationAction.DECLINE,
        None,
        {
            MCP_ELICITATION_DECLINE_MESSAGE_KEY: message,
            APPROVALS_REVIEWER_KEY: AUTO_REVIEW_METADATA_VALUE,
        },
    )


def mcp_elicitation_decline_without_message() -> ElicitationResponse:
    return ElicitationResponse(ElicitationAction.DECLINE, None, mcp_elicitation_auto_meta())


def mcp_elicitation_auto_meta() -> dict[str, str]:
    return {APPROVALS_REVIEWER_KEY: AUTO_REVIEW_METADATA_VALUE}


def _protocol_elicitation_request(request: McpServerElicitationRequest | Any) -> ElicitationRequest:
    mode = _field(request, "mode")
    if mode == "form":
        schema = _field(request, "requested_schema")
        to_mapping = getattr(schema, "to_mapping", None)
        schema_value = to_mapping() if callable(to_mapping) else schema
        return ElicitationRequest.form(
            str(_field(request, "message")),
            schema_value,
            meta=_field(request, "meta"),
        )
    return ElicitationRequest.url(
        str(_field(request, "message")),
        str(_field(request, "url")),
        str(_field(request, "elicitation_id")),
        meta=_field(request, "meta"),
    )


def _schema_properties(schema: Any) -> Mapping[str, Any]:
    properties = _field(schema, "properties", {})
    return properties if isinstance(properties, Mapping) else {}


def _active_turn_state(session: Any) -> Any:
    active_turn = _field(session, "active_turn")
    return _field(active_turn, "turn_state")


async def _mcp_manager(session: Any) -> Any:
    manager = _field(_field(session, "services"), "mcp_connection_manager")
    read = getattr(manager, "read", None)
    return await _maybe_await(read()) if callable(read) else manager


async def _take_pending_refresh(session: Any) -> Any:
    pending = _field(session, "pending_mcp_server_refresh_config")
    take = getattr(pending, "take", None)
    if callable(take):
        return await _maybe_await(take())
    value = _field(pending, "value") if pending is not None else None
    if pending is not None and hasattr(pending, "value"):
        pending.value = None
        return value
    setattr(session, "pending_mcp_server_refresh_config", None)
    return pending


async def _cancel_token(token: Any) -> None:
    lock = getattr(token, "lock", None)
    if callable(lock):
        token = await _maybe_await(lock())
    cancel = getattr(token, "cancel", None)
    if callable(cancel):
        await _maybe_await(cancel())


def _mark_user_input_requested(turn_context: Any) -> None:
    marker = getattr(_field(turn_context, "turn_metadata_state"), "mark_user_input_requested_during_turn", None)
    if callable(marker):
        marker()


def _record_plugin_install_elicitation(
    turn_context: Any,
    metadata: PluginInstallElicitationTelemetryMetadata | None,
) -> None:
    if metadata is None:
        return
    recorder = getattr(_field(turn_context, "session_telemetry"), "record_plugin_install_elicitation_sent", None)
    if callable(recorder):
        recorder(metadata.tool_type, metadata.tool_id, metadata.tool_name)


def _new_guardian_review_id() -> str:
    import uuid

    return str(uuid.uuid4())


async def _call_required(target: Any, name: str, *args: Any) -> Any:
    method = getattr(target, name, None)
    if not callable(method):
        raise TypeError(f"MCP manager requires {name}()")
    return await _maybe_await(method(*args))


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "GuardianElicitationReview",
    "GuardianMcpElicitationReviewer",
    "McpServerElicitationOutcome",
    "PluginInstallElicitationTelemetryMetadata",
    "call_tool",
    "cancel_mcp_startup",
    "guardian_elicitation_review_request",
    "list_resource_templates",
    "list_resources",
    "mcp_elicitation_auto_meta",
    "mcp_elicitation_decline_with_message",
    "mcp_elicitation_decline_without_message",
    "mcp_elicitation_request_id",
    "mcp_elicitation_response_from_guardian_decision",
    "mcp_elicitation_response_from_guardian_decision_parts",
    "mcp_elicitation_reviewer",
    "plugin_install_elicitation_telemetry_metadata",
    "read_resource",
    "refresh_mcp_servers_if_requested",
    "refresh_mcp_servers_inner",
    "refresh_mcp_servers_now",
    "request_mcp_server_elicitation",
    "resolve_elicitation",
    "review_guardian_mcp_elicitation",
]
