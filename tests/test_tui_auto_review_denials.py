from pathlib import Path

from pycodex.tui.auto_review_denials import (
    GuardianAssessmentAction,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    RecentAutoReviewDenials,
    action_summary,
    denied_event,
    keeps_only_ten_most_recent_denials,
)


def test_keeps_only_ten_most_recent_denials_matches_rust_order():
    assert keeps_only_ten_most_recent_denials() == [
        "review-11",
        "review-10",
        "review-9",
        "review-8",
        "review-7",
        "review-6",
        "review-5",
        "review-4",
        "review-3",
        "review-2",
    ]


def test_push_ignores_non_denied_and_deduplicates_by_id():
    denials = RecentAutoReviewDenials()
    denials.push(GuardianAssessmentEvent(id="review-1", status=GuardianAssessmentStatus.APPROVED, action=GuardianAssessmentAction.command_action("ls")))
    assert denials.is_empty()

    denials.push(denied_event(1))
    denials.push(GuardianAssessmentEvent(id="review-1", status="Denied", action=GuardianAssessmentAction.command_action("echo newer")))
    entries = list(denials.entries())
    assert [entry.id for entry in entries] == ["review-1"]
    assert action_summary(entries[0].action) == "echo newer"


def test_take_removes_matching_denial():
    denials = RecentAutoReviewDenials()
    denials.push(denied_event(1))
    denials.push(denied_event(2))
    taken = denials.take("review-1")
    assert taken is not None
    assert taken.id == "review-1"
    assert [entry.id for entry in denials.entries()] == ["review-2"]
    assert denials.take("missing") is None


def test_action_summary_variants_follow_rust_text():
    assert action_summary(GuardianAssessmentAction.command_action("cargo test")) == "cargo test"
    assert action_summary(GuardianAssessmentAction.execve("python", ["python", "a b.py"])) == "python 'a b.py'"
    assert action_summary(GuardianAssessmentAction.execve("python", [])) == "python"
    assert action_summary(GuardianAssessmentAction.apply_patch([Path("a.py")])) == "apply_patch touching a.py"
    assert action_summary(GuardianAssessmentAction.apply_patch(["a.py", "b.py"])) == "apply_patch touching 2 files"
    assert action_summary(GuardianAssessmentAction.network_access("example.com")) == "network access to example.com"
    assert action_summary(GuardianAssessmentAction.mcp_tool_call("server", "tool", "connector")) == "MCP tool on connector"
    assert action_summary(GuardianAssessmentAction.mcp_tool_call("server", "tool")) == "MCP tool on server"
    assert action_summary(GuardianAssessmentAction.request_permissions("need files")) == "permission request: need files"
    assert action_summary(GuardianAssessmentAction.request_permissions()) == "permission request"


def test_dict_inputs_are_supported_for_protocol_facades():
    denials = RecentAutoReviewDenials()
    denials.push({"id": "review-dict", "status": "Denied", "action": {"kind": "NetworkAccess", "target": "api.example"}})
    entry = next(denials.entries())
    assert entry.id == "review-dict"
    assert action_summary(entry.action) == "network access to api.example"
