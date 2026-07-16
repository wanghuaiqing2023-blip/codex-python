from pathlib import Path

from pycodex.protocol.approvals import FileChange
from pycodex.protocol.request_permissions import RequestPermissionProfile

from pycodex.tui.chatwidget.tool_requests import (
    ApplyPatchApprovalRequestEvent,
    ElicitationParams,
    ExecApprovalRequestEvent,
    GuardianAssessmentAction,
    GuardianAssessmentActionKind,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    RequestPermissionsEvent,
    ToolRequestUserInputParams,
    ToolRequestsModel,
    UserInputQuestion,
    guardian_action_summary,
    guardian_command,
    permission_request_summary,
    user_input_request_summary,
)
from pycodex.tui.history_cell.base import line_text


# Rust source: codex/codex-rs/tui/src/chatwidget/tool_requests.rs
def test_exec_and_apply_patch_requests_push_approval_and_notifications():
    model = ToolRequestsModel(cwd=Path("/repo"), thread_id="thread")

    model.handle_exec_approval_now(
        ExecApprovalRequestEvent(
            call_id="exec",
            started_at_ms=0,
            command=("echo", "hello world"),
            cwd=Path("/repo"),
            approval_id="exec",
        )
    )
    model.handle_apply_patch_approval_now(
        ApplyPatchApprovalRequestEvent(
            call_id="patch",
            started_at_ms=0,
            changes={Path("a.py"): FileChange.add("change")},
        )
    )

    assert model.answer_stream_flushes == 2
    assert model.notifications[0].kind == "exec_approval_requested"
    assert model.notifications[0].command == "echo 'hello world'"
    assert model.approval_requests[0].kind == "exec"
    assert model.approval_requests[0].data["id"] == "exec"
    assert model.notifications[1].kind == "edit_approval_requested"
    assert model.approval_requests[1].kind == "apply_patch"
    assert model.ambient_pet_notifications == ["Waiting", "Waiting"]
    assert model.redraw_requests == 2


def test_defer_routes_requests_without_handling_now():
    model = ToolRequestsModel(defer_items=True)
    exec_ev = ExecApprovalRequestEvent(call_id="exec", started_at_ms=0, command=("ls",), cwd=Path("/repo"))
    patch_ev = ApplyPatchApprovalRequestEvent(call_id="p", started_at_ms=0, changes={})
    input_ev = ToolRequestUserInputParams("t", "turn", "item", ())
    permission_ev = RequestPermissionsEvent(
        call_id="perm", started_at_ms=0, reason=None, permissions=RequestPermissionProfile()
    )
    elicitation = ElicitationParams.from_mapping(
        {
            "thread_id": "t",
            "turn_id": "turn",
            "server_name": "srv",
            "mode": "form",
            "message": "Approve?",
            "requested_schema": {"type": "object", "properties": {}},
        }
    )

    model.on_exec_approval_request("id", exec_ev)
    model.on_apply_patch_approval_request("id", patch_ev)
    model.on_request_user_input(input_ev)
    model.on_request_permissions(permission_ev)
    model.on_elicitation_request("el", elicitation)

    assert model.deferred_queue.exec_approvals == [exec_ev]
    assert model.deferred_queue.apply_patch_approvals == [patch_ev]
    assert model.deferred_queue.user_inputs == [input_ev]
    assert model.deferred_queue.permission_requests == [permission_ev]
    assert model.deferred_queue.elicitations == [("el", elicitation)]
    assert model.approval_requests == []


def test_guardian_in_progress_updates_pending_footer_and_terminal_clears_it():
    model = ToolRequestsModel()
    action = GuardianAssessmentAction(
        GuardianAssessmentActionKind.APPLY_PATCH,
        files=(Path("a.py"), Path("b.py")),
    )

    model.on_guardian_assessment(
        GuardianAssessmentEvent("g1", GuardianAssessmentStatus.IN_PROGRESS, action)
    )

    assert model.status_indicator_ensures == 1
    assert model.interrupt_hint_visible is True
    assert model.status_updates[-1]["header"] == "Reviewing approval request"
    assert model.status_updates[-1]["details"] == "apply_patch touching 2 files"
    assert model.redraw_requests == 1

    model.on_guardian_assessment(
        GuardianAssessmentEvent("g1", GuardianAssessmentStatus.APPROVED, action)
    )

    assert [line_text(line) for line in model.boxed_history[-1].display_lines(120)] == [
        "\u2714 Request approved for apply_patch touching 2 files"
    ]
    assert model.redraw_requests == 2


def test_guardian_denied_records_recent_denial_and_command_decision():
    model = ToolRequestsModel()
    action = GuardianAssessmentAction(
        GuardianAssessmentActionKind.COMMAND,
        command="python -m pytest",
    )
    event = GuardianAssessmentEvent("g2", GuardianAssessmentStatus.DENIED, action)

    model.on_guardian_assessment(event)

    denials = list(model.recent_auto_review_denials.entries())
    assert [denial.id for denial in denials] == ["g2"]
    assert [line_text(line) for line in model.boxed_history[-1].display_lines(120)] == [
        "\u2717 Request denied for codex to run python -m pytest"
    ]


def test_guardian_action_summary_and_command_helpers_cover_non_command_actions():
    assert permission_request_summary("permission request", "  because ") == "permission request: because"
    assert guardian_action_summary(
        GuardianAssessmentAction(GuardianAssessmentActionKind.EXECVE, program="python", argv=("-m", "pytest"))
    ) == "-m pytest"
    assert guardian_command(
        GuardianAssessmentAction(GuardianAssessmentActionKind.EXECVE, program="python", argv=())
    ) == ("python",)
    assert guardian_action_summary(
        GuardianAssessmentAction(
            GuardianAssessmentActionKind.MCP_TOOL_CALL,
            server="srv",
            tool_name="tool",
            connector_name="conn",
        )
    ) == "MCP tool on conn"
    assert guardian_action_summary(
        GuardianAssessmentAction(GuardianAssessmentActionKind.NETWORK_ACCESS, target="example.com")
    ) == "network access to example.com"


def test_elicitation_routes_form_or_declines_unsupported_url():
    model = ToolRequestsModel(thread_id="thread")

    model.handle_elicitation_request_now(
        "form",
        ElicitationParams.from_mapping(
            {
                "thread_id": "thread",
                "turn_id": "turn",
                "server_name": "srv",
                "mode": "form",
                "message": "approve?",
                "requested_schema": {"type": "object", "properties": {}},
            }
        ),
    )
    model.handle_elicitation_request_now(
        "valid-url",
        ElicitationParams.from_mapping(
            {
                "thread_id": "thread",
                "turn_id": "turn",
                "server_name": "srv",
                "mode": "url",
                "message": "complete action",
                "url": "https://example.com/action",
                "elicitation_id": "external-action",
            }
        ),
    )
    model.handle_elicitation_request_now(
        "url",
        ElicitationParams.from_mapping(
            {
                "thread_id": "thread",
                "turn_id": "turn",
                "server_name": "srv",
                "mode": "url",
                "message": "open",
                "url": "not-a-valid-url",
                "elicitation_id": "e",
            }
        ),
    )

    assert model.elicitation_forms[0].request_id == "form"
    assert model.app_link_views[0].elicitation_target.request_id == "valid-url"
    assert model.declined_elicitations == [("srv", "url")]
    assert [note.kind for note in model.notifications] == [
        "elicitation_requested",
        "elicitation_requested",
        "elicitation_requested",
    ]


def test_user_input_request_title_summary_and_permissions_request():
    model = ToolRequestsModel(thread_id="thread")
    one = ToolRequestUserInputParams(
        "thread", "turn", "one", (UserInputQuestion("q1", "  Name  ", "What is your name?"),)
    )
    many = ToolRequestUserInputParams(
        "thread", "turn", "many", (UserInputQuestion("q1", "", "A"), UserInputQuestion("q2", "", "B"))
    )

    assert user_input_request_summary(one.questions) == "Name"
    model.handle_request_user_input_now(one)
    model.handle_request_user_input_now(many)
    model.handle_request_permissions_now(
        RequestPermissionsEvent(
            call_id="perm",
            started_at_ms=0,
            reason="need net",
            permissions=RequestPermissionProfile(),
        )
    )

    assert model.notifications[0].title == "Name"
    assert model.notifications[1].title == "2 questions requested"
    assert model.user_input_requests == [one, many]
    assert model.approval_requests[-1].kind == "permissions"
    assert model.approval_requests[-1].data["call_id"] == "perm"
