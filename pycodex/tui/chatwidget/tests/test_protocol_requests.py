from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pycodex.tui.chatwidget.protocol_requests import (
    GuardianAssessmentDecisionSource,
    GuardianAssessmentStatus,
    GuardianRiskLevel,
    GuardianUserAuthorization,
    ServerRequest,
    TUI_STUB_MESSAGE,
    handle_server_request,
    handle_skills_list_response,
    on_deprecation_notice,
    on_guardian_review_notification,
    on_patch_apply_output_delta,
    on_shutdown_complete,
    on_turn_diff,
)
from pycodex.protocol.approvals import ApplyPatchApprovalRequestEvent, ExecApprovalRequestEvent
from pycodex.protocol.request_permissions import RequestPermissionsEvent


class Widget:
    def __init__(self) -> None:
        self.config = SimpleNamespace(cwd="/repo")
        self.events: list[tuple] = []

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder


# Rust source: codex/codex-rs/tui/src/chatwidget/protocol_requests.rs
def test_handle_server_request_routes_approval_permission_elicitation_and_user_input() -> None:
    widget = Widget()

    handle_server_request(widget, ServerRequest("CommandExecutionRequestApproval", id="r1", params={"command": "ls"}))
    handle_server_request(
        widget,
        ServerRequest(
            "FileChangeRequestApproval",
            id="r2",
            params={"item_id": "patch-1", "changes": {"a.py": {"type": "add", "content": "x"}}},
        ),
    )
    handle_server_request(
        widget,
        ServerRequest(
            "McpServerElicitationRequest",
            request_id="e1",
            params={
                "thread_id": "thread-1",
                "turn_id": "turn-1",
                "server_name": "server-1",
                "mode": "form",
                "message": "Approve?",
                "requested_schema": {"type": "object", "properties": {}},
            },
        ),
    )
    handle_server_request(
        widget,
        ServerRequest(
            "PermissionsRequestApproval",
            id="r3",
            params={"item_id": "perm-1", "permissions": {}},
        ),
    )
    handle_server_request(
        widget,
        ServerRequest(
            "ToolRequestUserInput",
            id="r4",
            params={
                "thread_id": "thread-1",
                "turn_id": "turn-1",
                "item_id": "item-1",
                "questions": [{"id": "q", "header": "Question", "question": "Pick", "options": None}],
            },
        ),
    )

    assert widget.events[0][0:2] == ("on_exec_approval_request", "r1")
    assert isinstance(widget.events[0][2], ExecApprovalRequestEvent)
    assert widget.events[0][2].command == ("ls",)
    assert widget.events[0][2].cwd == Path("/repo")
    assert widget.events[1][0:2] == ("on_apply_patch_approval_request", "r2")
    assert isinstance(widget.events[1][2], ApplyPatchApprovalRequestEvent)
    assert widget.events[1][2].call_id == "patch-1"
    assert widget.events[2][0:2] == ("on_elicitation_request", "e1")
    assert widget.events[2][2].thread_id == "thread-1"
    assert widget.events[3][0] == "on_request_permissions"
    assert isinstance(widget.events[3][1], RequestPermissionsEvent)
    assert widget.events[3][1].call_id == "perm-1"
    assert widget.events[4][0] == "on_request_user_input"
    assert widget.events[4][1].item_id == "item-1"


def test_exec_approval_parser_preserves_fixed_rust_decision_payload() -> None:
    # Fixed Rust commit 1c7832f, approval_events::ExecApprovalRequestEvent:
    # terminal routing must preserve policy and network amendments rather than
    # reducing an approval request to command text.
    widget = Widget()

    handle_server_request(
        widget,
        ServerRequest(
            "CommandExecutionRequestApproval",
            id="request-1",
            params={
                "call_id": "call-1",
                "approval_id": "approval-1",
                "turn_id": "turn-1",
                "started_at_ms": 42,
                "command": ["curl", "https://example.com"],
                "cwd": "/repo",
                "reason": "download fixture",
                "network_approval_context": {"host": "example.com", "protocol": "https"},
                "proposed_execpolicy_amendment": {"command": ["curl"]},
                "proposed_network_policy_amendments": [
                    {"host": "example.com", "action": "allow"}
                ],
                "available_decisions": [
                    "accept",
                    "acceptForSession",
                    {
                        "applyNetworkPolicyAmendment": {
                            "networkPolicyAmendment": {
                                "host": "example.com",
                                "action": "allow",
                            }
                        }
                    },
                    "cancel",
                ],
            },
        ),
    )

    event = widget.events[0][2]
    assert event.call_id == "call-1"
    assert event.effective_approval_id() == "approval-1"
    assert event.turn_id == "turn-1"
    assert event.started_at_ms == 42
    assert event.network_approval_context.host == "example.com"
    assert event.proposed_execpolicy_amendment.command == ("curl",)
    assert event.proposed_network_policy_amendments[0].host == "example.com"
    assert [decision.type for decision in event.effective_available_decisions()] == [
        "approved",
        "approved_for_session",
        "network_policy_amendment",
        "abort",
    ]


@pytest.mark.parametrize(
    "kind",
    [
        "DynamicToolCall",
        "AttestationGenerate",
        "ChatgptAuthTokensRefresh",
        "ApplyPatchApproval",
        "ExecCommandApproval",
    ],
)
def test_stub_request_variants_emit_error_only_when_live(kind: str) -> None:
    widget = Widget()

    handle_server_request(widget, ServerRequest(kind), replay_kind=None)

    assert widget.events == [("add_error_message", TUI_STUB_MESSAGE)]

    widget = Widget()
    handle_server_request(widget, ServerRequest(kind), replay_kind="Replay")
    assert widget.events == []


def test_guardian_review_notification_maps_status_risk_auth_and_completion() -> None:
    widget = Widget()

    event = on_guardian_review_notification(
        widget,
        id="g1",
        turn_id="t1",
        started_at_ms=10,
        review={
            "status": "Approved",
            "risk_level": "High",
            "user_authorization": "Medium",
            "rationale": "ok",
        },
        completion=(20, "Agent"),
        action={
            "kind": "Command",
            "source": "Shell",
            "command": "echo ok",
            "cwd": "/tmp",
        },
    )

    assert event.status == GuardianAssessmentStatus.APPROVED
    assert event.risk_level == GuardianRiskLevel.HIGH
    assert event.user_authorization == GuardianUserAuthorization.MEDIUM
    assert event.completed_at_ms == 20
    assert event.decision_source == GuardianAssessmentDecisionSource.AGENT
    assert widget.events == [("on_guardian_assessment", event)]


def test_small_notification_helpers_match_rust_side_effects() -> None:
    widget = Widget()

    handle_skills_list_response(widget, {"skills": []})
    on_shutdown_complete(widget)
    on_turn_diff(widget, "diff")
    on_deprecation_notice(widget, "old", "details")
    assert on_patch_apply_output_delta(widget, "item", "delta") is None

    assert ("on_list_skills", {"skills": []}) in widget.events
    assert ("request_immediate_exit",) in widget.events
    assert ("refresh_status_line",) in widget.events
    assert ("add_to_history", {"kind": "deprecation_notice", "summary": "old", "details": "details"}) in widget.events
    assert ("request_redraw",) in widget.events
