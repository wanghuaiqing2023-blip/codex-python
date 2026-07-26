from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pycodex.app_server_protocol.elicitation import (
    McpElicitationSchema,
    McpServerElicitationRequest,
    McpServerElicitationRequestParams,
)
from pycodex.core.mcp_tool_call import ElicitationResponse
from pycodex.core.session.mcp import (
    GuardianElicitationReview,
    PluginInstallElicitationTelemetryMetadata,
    guardian_elicitation_review_request,
    mcp_elicitation_response_from_guardian_decision_parts,
    plugin_install_elicitation_telemetry_metadata,
    request_mcp_server_elicitation,
    resolve_elicitation,
)
from pycodex.core.state import ActiveTurn, TurnState
from pycodex.protocol import (
    ElicitationAction,
    ElicitationRequest,
    ElicitationRequestEvent,
    EventMsg,
    ReviewDecision,
)


def _guardian_request(tool_params=...) -> dict[str, object]:
    meta: dict[str, object] = {
        "codex_approval_kind": "mcp_tool_call",
        "codex_request_type": "approval_request",
        "connector_id": "browser-use",
        "connector_name": "Browser Use",
        "tool_name": "access_browser_origin",
        "tool_title": "Access browser origin",
    }
    if tool_params is not ...:
        meta["tool_params"] = tool_params
    return {
        "server_name": "browser-use",
        "request_id": 7,
        "elicitation": McpServerElicitationRequest.form(
            "Allow origin?",
            McpElicitationSchema.empty_object(),
            meta=meta,
        ),
    }


def test_guardian_elicitation_review_request_builds_mcp_tool_call() -> None:
    result = guardian_elicitation_review_request(_guardian_request({"origin": "https://example.com"}))

    assert result.kind == "approval_request"
    assert result.approval_request is not None
    assert result.approval_request.kind == "mcp_tool_call"
    assert result.approval_request.data == {
        "id": "mcp_elicitation:browser-use:7",
        "server": "browser-use",
        "tool_name": "access_browser_origin",
        "arguments": {"origin": "https://example.com"},
        "connector_id": "browser-use",
        "connector_name": "Browser Use",
        "connector_description": None,
        "tool_title": "Access browser origin",
        "tool_description": None,
        "annotations": None,
    }


def test_guardian_elicitation_review_defaults_params_and_requires_opt_in() -> None:
    result = guardian_elicitation_review_request(_guardian_request())
    assert result.kind == "approval_request"
    assert result.approval_request is not None
    assert result.approval_request.data["arguments"] == {}

    request = _guardian_request()
    request["elicitation"].meta.pop("codex_request_type")
    assert guardian_elicitation_review_request(request) == GuardianElicitationReview.not_requested()


def test_guardian_elicitation_review_declines_unsupported_shapes() -> None:
    request = _guardian_request([])
    assert guardian_elicitation_review_request(request).kind == "decline"

    request = _guardian_request()
    request["elicitation"].meta.pop("tool_name")
    assert guardian_elicitation_review_request(request).kind == "decline"

    url_request = {
        "server_name": "browser-use",
        "request_id": 8,
        "elicitation": McpServerElicitationRequest(
            mode="url",
            message="Open URL",
            meta=_guardian_request()["elicitation"].meta,
            url="https://example.com",
            elicitation_id="elicit-1",
        ),
    }
    assert guardian_elicitation_review_request(url_request).kind == "decline"


def test_plugin_install_elicitation_telemetry_requires_install_suggestion() -> None:
    event = EventMsg.with_payload(
        "elicitation_request",
        ElicitationRequestEvent(
            turn_id="turn-1",
            server_name="codex_apps",
            id="request-1",
            request=ElicitationRequest.form(
                "Install Slack?",
                {"type": "object", "properties": {}},
                meta={
                    "codex_approval_kind": "tool_suggestion",
                    "suggest_type": "install",
                    "tool_type": "plugin",
                    "tool_id": "slack@openai-curated",
                    "tool_name": "Slack",
                },
            ),
        ),
    )

    assert plugin_install_elicitation_telemetry_metadata(event) == PluginInstallElicitationTelemetryMetadata(
        tool_type="plugin",
        tool_id="slack@openai-curated",
        tool_name="Slack",
    )
    event.payload.request.meta["suggest_type"] = "enable"
    assert plugin_install_elicitation_telemetry_metadata(event) is None


def test_guardian_decisions_map_to_elicitation_responses() -> None:
    approved = mcp_elicitation_response_from_guardian_decision_parts(ReviewDecision.approved(), None)
    denied = mcp_elicitation_response_from_guardian_decision_parts(
        ReviewDecision.denied(),
        "Denied by Guardian",
    )
    timed_out = mcp_elicitation_response_from_guardian_decision_parts(ReviewDecision.timed_out(), None)
    aborted = mcp_elicitation_response_from_guardian_decision_parts(ReviewDecision.abort(), None)

    assert approved.action is ElicitationAction.ACCEPT
    assert approved.content == {}
    assert approved.meta == {"approvals_reviewer": "auto_review"}
    assert denied.action is ElicitationAction.DECLINE
    assert denied.meta == {"approvals_reviewer": "auto_review", "message": "Denied by Guardian"}
    assert timed_out.action is ElicitationAction.DECLINE
    assert "message" in timed_out.meta
    assert aborted.action is ElicitationAction.CANCEL
    assert aborted.meta == {"approvals_reviewer": "auto_review"}


@pytest.mark.asyncio
async def test_mcp_server_elicitation_is_pending_until_session_resolves_it() -> None:
    events: list[EventMsg] = []

    class Manager:
        def elicitations_auto_deny(self) -> bool:
            return False

    session = SimpleNamespace(
        services=SimpleNamespace(mcp_connection_manager=Manager()),
        active_turn=ActiveTurn(turn_state=TurnState()),
        send_event=lambda _turn, event: events.append(event),
    )
    turn_context = SimpleNamespace(turn_metadata_state=None, session_telemetry=None)
    params = McpServerElicitationRequestParams(
        thread_id="thread-1",
        turn_id="turn-1",
        server_name="server",
        request=McpServerElicitationRequest.form(
            "Confirm?",
            McpElicitationSchema.empty_object(),
        ),
    )

    pending = asyncio.create_task(request_mcp_server_elicitation(session, turn_context, 7, params))
    await asyncio.sleep(0)
    assert not pending.done()
    assert [event.type for event in events] == ["elicitation_request"]

    response = ElicitationResponse(ElicitationAction.ACCEPT, {})
    await resolve_elicitation(session, "server", 7, response)
    outcome = await pending

    assert outcome.sent is True
    assert outcome.response == response
    assert session.active_turn.turn_state.pending_elicitations == {}


@pytest.mark.asyncio
async def test_mcp_server_elicitation_auto_deny_returns_without_emitting() -> None:
    class Manager:
        def elicitations_auto_deny(self) -> bool:
            return True

    session = SimpleNamespace(
        services=SimpleNamespace(mcp_connection_manager=Manager()),
        active_turn=ActiveTurn(turn_state=TurnState()),
        send_event=lambda *_args: (_ for _ in ()).throw(AssertionError("must not emit")),
    )
    params = McpServerElicitationRequestParams(
        thread_id="thread-1",
        turn_id="turn-1",
        server_name="server",
        request=McpServerElicitationRequest.form("Confirm?", McpElicitationSchema.empty_object()),
    )

    outcome = await request_mcp_server_elicitation(session, SimpleNamespace(), "id", params)

    assert outcome.sent is False
    assert outcome.response == ElicitationResponse(ElicitationAction.ACCEPT, {})
