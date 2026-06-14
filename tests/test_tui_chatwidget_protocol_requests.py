from __future__ import annotations

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


class Widget:
    def __init__(self) -> None:
        self.config = SimpleNamespace(cwd="/repo")
        self.events: list[tuple] = []

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder


def test_handle_server_request_routes_approval_permission_elicitation_and_user_input() -> None:
    widget = Widget()

    handle_server_request(widget, ServerRequest("CommandExecutionRequestApproval", id="r1", params={"command": "ls"}))
    handle_server_request(widget, ServerRequest("FileChangeRequestApproval", id="r2", params={"path": "a.py"}))
    handle_server_request(widget, ServerRequest("McpServerElicitationRequest", request_id="e1", params={"prompt": "p"}))
    handle_server_request(widget, ServerRequest("PermissionsRequestApproval", id="r3", params={"profile": "auto"}))
    handle_server_request(widget, ServerRequest("ToolRequestUserInput", id="r4", params={"question": "q"}))

    assert widget.events == [
        ("on_exec_approval_request", "r1", {"command": "ls", "cwd": "/repo"}),
        ("on_apply_patch_approval_request", "r2", {"path": "a.py"}),
        ("on_elicitation_request", "e1", {"prompt": "p"}),
        ("on_request_permissions", {"profile": "auto"}),
        ("on_request_user_input", {"question": "q"}),
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
        action={"kind": "command"},
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
