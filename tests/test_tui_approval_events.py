"""Parity tests for ``codex-tui/src/approval_events.rs``."""

from pathlib import Path

import pytest

from pycodex.tui.approval_events import (
    ApplyPatchApprovalRequestEvent,
    CommandExecutionApprovalDecision,
    ExecApprovalRequestEvent,
)
from pycodex.tui.diff_model import FileChange


def test_effective_approval_id_falls_back_to_call_id() -> None:
    # Rust: ExecApprovalRequestEvent::effective_approval_id
    plain = ExecApprovalRequestEvent(call_id="call-1", command=["git", "status"], cwd="/tmp")
    explicit = ExecApprovalRequestEvent(
        call_id="call-1",
        approval_id="approval-1",
        command=["git", "status"],
        cwd="/tmp",
    )
    assert plain.effective_approval_id() == "call-1"
    assert explicit.effective_approval_id() == "approval-1"


def test_effective_available_decisions_preserves_explicit_list() -> None:
    # Rust: Some(available_decisions) is cloned directly.
    decisions = ["custom-accept", "custom-cancel"]
    event = ExecApprovalRequestEvent(call_id="call", command=["cmd"], cwd="/tmp", available_decisions=decisions)
    assert event.effective_available_decisions() == decisions
    assert event.effective_available_decisions() is not decisions


def test_default_decisions_for_network_context_include_allow_amendment() -> None:
    # Rust: network context => Accept, AcceptForSession, first Allow amendment, Cancel.
    allow = {"action": "allow", "rule": "example.com"}
    deny = {"action": "deny", "rule": "blocked.com"}
    assert ExecApprovalRequestEvent.default_available_decisions(
        network_approval_context={"host": "example.com"},
        proposed_network_policy_amendments=[deny, allow],
        proposed_execpolicy_amendment="ignored",
    ) == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.accept_for_session(),
        CommandExecutionApprovalDecision.apply_network_policy_amendment(allow),
        CommandExecutionApprovalDecision.cancel(),
    ]


def test_default_decisions_for_network_context_without_allow_amendment() -> None:
    # Rust: no Allow amendment still gives Accept, AcceptForSession, Cancel.
    assert ExecApprovalRequestEvent.default_available_decisions(
        network_approval_context={"host": "example.com"},
        proposed_network_policy_amendments=[{"action": "deny"}],
    ) == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.accept_for_session(),
        CommandExecutionApprovalDecision.cancel(),
    ]


def test_default_decisions_for_additional_permissions() -> None:
    # Rust: additional permissions branch => Accept, Cancel.
    assert ExecApprovalRequestEvent.default_available_decisions(additional_permissions={"network": {}}) == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.cancel(),
    ]


def test_default_decisions_for_execpolicy_amendment() -> None:
    # Rust: normal exec branch includes AcceptWithExecpolicyAmendment when present.
    amendment = {"match": ["git"]}
    assert ExecApprovalRequestEvent.default_available_decisions(proposed_execpolicy_amendment=amendment) == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.accept_with_execpolicy_amendment(amendment),
        CommandExecutionApprovalDecision.cancel(),
    ]


def test_default_decisions_plain_exec() -> None:
    # Rust: normal exec branch without amendments => Accept, Cancel.
    assert ExecApprovalRequestEvent.default_available_decisions() == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.cancel(),
    ]


def test_apply_patch_approval_request_normalizes_paths_and_keeps_optional_fields() -> None:
    # Rust: ApplyPatchApprovalRequestEvent stores call_id, turn_id, changes, reason, grant_root.
    event = ApplyPatchApprovalRequestEvent(
        call_id="patch-1",
        turn_id="turn-1",
        changes={"new.py": FileChange.add("print('hi')\n")},
        reason="needs write",
        grant_root="/repo",
    )
    assert event.changes == {Path("new.py"): FileChange.add("print('hi')\n")}
    assert event.reason == "needs write"
    assert event.grant_root == Path("/repo")


def test_apply_patch_approval_request_rejects_invalid_change_values() -> None:
    # Rust serde type checks FileChange values; Python rejects non-FileChange changes.
    with pytest.raises(TypeError):
        ApplyPatchApprovalRequestEvent(call_id="patch", changes={Path("x.py"): {"type": "add"}})  # type: ignore[dict-item]


class _EnumLikeAction:
    def __init__(self, value: str) -> None:
        self.value = value


class _NetworkAmendment:
    def __init__(self, action: str, rule: str) -> None:
        self.action = _EnumLikeAction(action)
        self.rule = rule


def test_network_default_decisions_accept_enum_like_allow_action() -> None:
    # Rust: finds the first amendment whose action == NetworkPolicyRuleAction::Allow.
    deny = _NetworkAmendment("Deny", "blocked.com")
    allow = _NetworkAmendment("Allow", "example.com")

    assert ExecApprovalRequestEvent.default_available_decisions(
        network_approval_context={"host": "example.com"},
        proposed_network_policy_amendments=[deny, allow],
    ) == [
        CommandExecutionApprovalDecision.accept(),
        CommandExecutionApprovalDecision.accept_for_session(),
        CommandExecutionApprovalDecision.apply_network_policy_amendment(allow),
        CommandExecutionApprovalDecision.cancel(),
    ]
