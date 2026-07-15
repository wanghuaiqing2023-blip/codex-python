"""Parity tests for codex-rs/tui/src/history_cell/approvals.rs."""

# Rust owner: codex-tui::history_cell::approvals.

from pycodex.tui.history_cell.approvals import (
    ApprovalDecisionActor,
    ApprovalDecisionSubject,
    ExecPolicyAmendment,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ReviewDecision,
    exec_snippet,
    line_text,
    new_approval_decision_cell,
    new_guardian_approved_action_request,
    new_guardian_denied_action_request,
    new_guardian_denied_patch_request,
    new_guardian_timed_out_action_request,
    new_guardian_timed_out_patch_request,
    new_review_status_line,
    non_empty_exec_snippet,
    truncate_exec_snippet,
)


def texts(cell, width=120):
    return [line_text(line) for line in cell.display_lines(width)]


def styled_spans(cell, width=120):
    return [
        [(span.content, span.style) for span in line.spans]
        for line in cell.display_lines(width)
    ]


def test_exec_snippet_strips_bash_lc_truncates_newlines_and_empty() -> None:
    assert exec_snippet(["bash", "-lc", "echo hello"]) == "echo hello"
    assert truncate_exec_snippet("echo one\necho two") == "echo one ..."
    assert non_empty_exec_snippet([]) is None


def test_user_approved_command_this_time_and_for_session() -> None:
    subject = ApprovalDecisionSubject.command_subject(["bash", "-lc", "echo hello"])

    once = new_approval_decision_cell(
        subject, ReviewDecision.approved(), ApprovalDecisionActor.User
    )
    session = new_approval_decision_cell(
        subject, ReviewDecision.approved_for_session(), ApprovalDecisionActor.User
    )

    # Rust snapshot: approvals__tests__short_command_approved.snap.
    assert texts(once) == ["✔ You approved codex to run echo hello this time"]
    assert texts(session) == [
        "✔ You approved codex to run echo hello every time this session"
    ]
    assert styled_spans(once) == [
        [
            ("✔ ", "green"),
            ("You ", None),
            ("approved", "bold"),
            (" codex to run ", None),
            ("echo hello", "dim"),
            (" this time", "bold"),
        ]
    ]


def test_guardian_denied_command_uses_request_wording() -> None:
    cell = new_approval_decision_cell(
        ApprovalDecisionSubject.command_subject(["rm", "-rf", "/tmp/x"]),
        ReviewDecision.denied(),
        ApprovalDecisionActor.Guardian,
    )

    assert texts(cell) == ["✗ Request denied for codex to run rm -rf /tmp/x"]
    assert styled_spans(cell) == [
        [
            ("✗ ", "red"),
            ("Request ", None),
            ("denied", "bold"),
            (" for codex to run ", None),
            ("rm -rf /tmp/x", "dim"),
        ]
    ]


def test_network_decisions_cover_temporary_and_persisted_rules() -> None:
    subject = ApprovalDecisionSubject.network_access("example.com")

    allowed = new_approval_decision_cell(
        subject, ReviewDecision.approved(), ApprovalDecisionActor.User
    )
    persisted = new_approval_decision_cell(
        subject,
        ReviewDecision.network_policy_amendment_decision(
            NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.Allow)
        ),
        ApprovalDecisionActor.User,
    )
    denied_saved = new_approval_decision_cell(
        subject,
        ReviewDecision.network_policy_amendment_decision(
            NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.Deny)
        ),
        ApprovalDecisionActor.User,
    )

    assert texts(allowed) == [
        "✔ You approved codex network access to example.com this time"
    ]
    assert texts(persisted) == ["✔ You persisted Codex network access to example.com"]
    assert texts(denied_saved) == [
        "✗ You denied codex network access to example.com and saved that rule"
    ]


def test_policy_amendment_and_timeout_and_abort_wording() -> None:
    amendment = ExecPolicyAmendment(("bash", "-lc", "cargo test"))
    policy = new_approval_decision_cell(
        ApprovalDecisionSubject.command_subject(["cargo", "test"]),
        ReviewDecision.approved_execpolicy_amendment(amendment),
        ApprovalDecisionActor.User,
    )
    timeout = new_approval_decision_cell(
        ApprovalDecisionSubject.command_subject(["cargo", "fmt"]),
        ReviewDecision.timed_out(),
        ApprovalDecisionActor.User,
    )
    abort = new_approval_decision_cell(
        ApprovalDecisionSubject.network_access("api.example.com"),
        ReviewDecision.abort(),
        ApprovalDecisionActor.User,
    )

    assert texts(policy) == [
        "✔ You approved codex to always run commands that start with cargo test"
    ]
    assert texts(timeout) == [
        "✗ Review timed out before codex could run cargo fmt"
    ]
    assert texts(abort) == [
        "✗ You canceled the request for codex network access to api.example.com"
    ]


def test_guardian_patch_and_action_helpers() -> None:
    assert texts(new_guardian_denied_patch_request(["a.py"])) == [
        "✗ Request denied for codex to apply a patch touching a.py"
    ]
    assert texts(new_guardian_denied_patch_request(["a.py", "b.py"])) == [
        "✗ Request denied for codex to apply a patch touching 2 files"
    ]
    assert texts(new_guardian_timed_out_patch_request(["a.py"])) == [
        "✗ Review timed out before codex could apply a patch touching a.py"
    ]
    assert texts(new_guardian_denied_action_request("opening file")) == [
        "✗ Request denied for opening file"
    ]
    assert texts(new_guardian_approved_action_request("opening file")) == [
        "✔ Request approved for opening file"
    ]
    assert texts(new_guardian_timed_out_action_request("opening file")) == [
        "✗ Review timed out before opening file"
    ]


def test_review_status_line_is_plain_cyan_cell() -> None:
    cell = new_review_status_line("Reviewing command")

    assert texts(cell) == ["Reviewing command"]
    assert cell.display_lines(80)[0].spans[0].style == "cyan"
