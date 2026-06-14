"""Approval, denial, and review-status transcript cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/approvals.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import shlex
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from .base import PlainHistoryCell, PrefixedWrappedHistoryCell

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::approvals",
    source="codex/codex-rs/tui/src/history_cell/approvals.rs",
)

MAX_EXEC_SNIPPET_GRAPHEMES = 80
APPROVED_SYMBOL = "OK "
DENIED_SYMBOL = "NO "


def _line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def line_text(line: Line) -> str:
    return _line_text(line)


def _truncate_text(text: str, max_graphemes: int) -> str:
    if len(text) <= max_graphemes:
        return text
    return text[: max(0, max_graphemes - 1)] + "…"


def strip_bash_lc_and_escape(command: Iterable[str]) -> str:
    """Semantic equivalent of Rust command display normalization.

    The full helper lives outside this module.  This keeps the important local
    contract: hide the common ``bash -lc`` wrapper and render a shell-ish
    command string.
    """

    parts = [str(part) for part in command]
    if len(parts) >= 3 and parts[0] in {"bash", "/bin/bash", "sh", "/bin/sh"} and parts[1] == "-lc":
        return parts[2]
    return " ".join(shlex.quote(part) for part in parts)


def truncate_exec_snippet(full_cmd: str) -> str:
    first, sep, _rest = str(full_cmd).partition("\n")
    snippet = f"{first} ..." if sep else first
    return _truncate_text(snippet, MAX_EXEC_SNIPPET_GRAPHEMES)


def exec_snippet(command: Iterable[str]) -> str:
    return truncate_exec_snippet(strip_bash_lc_and_escape(command))


def non_empty_exec_snippet(command: Iterable[str]) -> str | None:
    snippet = exec_snippet(command)
    return snippet if snippet else None


class ApprovalDecisionActor(Enum):
    User = "user"
    Guardian = "guardian"

    @classmethod
    def coerce(cls, value: "ApprovalDecisionActor | str | Any") -> "ApprovalDecisionActor":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value)).lower()
        if name == "user":
            return cls.User
        if name in {"guardian", "auto_reviewer", "auto-reviewer"}:
            return cls.Guardian
        raise ValueError(f"unknown approval decision actor: {value!r}")

    def subject(self) -> str:
        return "You " if self is ApprovalDecisionActor.User else "Auto-reviewer "


@dataclass(frozen=True)
class ApprovalDecisionSubject:
    kind: str
    command: tuple[str, ...] = ()
    target: str | None = None

    @classmethod
    def command_subject(cls, command: Iterable[str]) -> "ApprovalDecisionSubject":
        return cls("command", tuple(str(part) for part in command), None)

    @classmethod
    def network_access(cls, target: str) -> "ApprovalDecisionSubject":
        return cls("network", (), str(target))

    @classmethod
    def coerce(cls, value: "ApprovalDecisionSubject | dict[str, Any] | Any") -> "ApprovalDecisionSubject":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            if "command" in value:
                return cls.command_subject(value["command"])
            if "target" in value:
                return cls.network_access(value["target"])
            if value.get("kind") == "network":
                return cls.network_access(value.get("target", ""))
        command = getattr(value, "command", None)
        if command is not None:
            return cls.command_subject(command)
        target = getattr(value, "target", None)
        if target is not None:
            return cls.network_access(target)
        raise TypeError(f"cannot coerce approval subject: {value!r}")


class NetworkPolicyRuleAction(Enum):
    Allow = "allow"
    Deny = "deny"

    @classmethod
    def coerce(cls, value: "NetworkPolicyRuleAction | str | Any") -> "NetworkPolicyRuleAction":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value)).lower()
        if name == "allow":
            return cls.Allow
        if name == "deny":
            return cls.Deny
        raise ValueError(f"unknown network policy rule action: {value!r}")


@dataclass(frozen=True)
class ExecPolicyAmendment:
    command: tuple[str, ...]

    @classmethod
    def coerce(cls, value: "ExecPolicyAmendment | dict[str, Any] | Any") -> "ExecPolicyAmendment":
        if isinstance(value, cls):
            return value
        command = value.get("command") if isinstance(value, dict) else getattr(value, "command")
        return cls(tuple(str(part) for part in command))


@dataclass(frozen=True)
class NetworkPolicyAmendment:
    host: str
    action: NetworkPolicyRuleAction

    @classmethod
    def coerce(
        cls, value: "NetworkPolicyAmendment | dict[str, Any] | Any"
    ) -> "NetworkPolicyAmendment":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            host = value.get("host", "")
            action = value.get("action", "allow")
        else:
            host = getattr(value, "host", "")
            action = getattr(value, "action", "allow")
        return cls(str(host), NetworkPolicyRuleAction.coerce(action))


@dataclass(frozen=True)
class ReviewDecision:
    kind: str
    proposed_execpolicy_amendment: ExecPolicyAmendment | None = None
    network_policy_amendment: NetworkPolicyAmendment | None = None

    @classmethod
    def approved(cls) -> "ReviewDecision":
        return cls("approved")

    @classmethod
    def approved_execpolicy_amendment(cls, amendment: Any) -> "ReviewDecision":
        return cls("approved_execpolicy_amendment", ExecPolicyAmendment.coerce(amendment))

    @classmethod
    def approved_for_session(cls) -> "ReviewDecision":
        return cls("approved_for_session")

    @classmethod
    def network_policy_amendment_decision(cls, amendment: Any) -> "ReviewDecision":
        return cls("network_policy_amendment", None, NetworkPolicyAmendment.coerce(amendment))

    @classmethod
    def denied(cls) -> "ReviewDecision":
        return cls("denied")

    @classmethod
    def timed_out(cls) -> "ReviewDecision":
        return cls("timed_out")

    @classmethod
    def abort(cls) -> "ReviewDecision":
        return cls("abort")

    @classmethod
    def coerce(cls, value: "ReviewDecision | str | dict[str, Any] | Any") -> "ReviewDecision":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            kind = str(value.get("kind", "")).lower()
            if kind == "approved_execpolicy_amendment":
                return cls.approved_execpolicy_amendment(value.get("proposed_execpolicy_amendment"))
            if kind == "network_policy_amendment":
                return cls.network_policy_amendment_decision(value.get("network_policy_amendment"))
            return cls.coerce(kind)
        name = str(getattr(value, "name", value)).replace("-", "_").lower()
        if name == "approved":
            return cls.approved()
        if name == "approved_for_session":
            return cls.approved_for_session()
        if name == "denied":
            return cls.denied()
        if name in {"timedout", "timed_out"}:
            return cls.timed_out()
        if name == "abort":
            return cls.abort()
        raise ValueError(f"unknown review decision: {value!r}")


def _summary_cell(summary: str, approved: bool) -> PrefixedWrappedHistoryCell:
    return PrefixedWrappedHistoryCell.new(Line.from_text(summary), APPROVED_SYMBOL if approved else DENIED_SYMBOL, "  ")


def _command_summary_or_request(command: tuple[str, ...], action_text: str) -> str:
    snippet = non_empty_exec_snippet(command)
    return f"{action_text} {snippet}" if snippet else action_text.replace("codex to run", "this request")


def new_approval_decision_cell(
    subject: ApprovalDecisionSubject | dict[str, Any] | Any,
    decision: ReviewDecision | str | dict[str, Any] | Any,
    actor: ApprovalDecisionActor | str | Any,
) -> PrefixedWrappedHistoryCell:
    subject = ApprovalDecisionSubject.coerce(subject)
    decision = ReviewDecision.coerce(decision)
    actor = ApprovalDecisionActor.coerce(actor)

    approved = decision.kind in {
        "approved",
        "approved_execpolicy_amendment",
        "approved_for_session",
        "network_policy_amendment",
    }

    if decision.kind == "approved":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = (
                f"{actor.subject()}approved codex to run {snippet} this time"
                if snippet
                else f"{actor.subject()}approved this request this time"
            )
        else:
            summary = f"{actor.subject()}approved codex network access to {subject.target} this time"
    elif decision.kind == "approved_execpolicy_amendment":
        amendment = decision.proposed_execpolicy_amendment
        snippet = exec_snippet(amendment.command if amendment else ())
        summary = f"{actor.subject()}approved codex to always run commands that start with {snippet}"
    elif decision.kind == "approved_for_session":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = (
                f"{actor.subject()}approved codex to run {snippet} every time this session"
                if snippet
                else f"{actor.subject()}approved this request every time this session"
            )
        else:
            summary = f"{actor.subject()}approved codex network access to {subject.target} every time this session"
    elif decision.kind == "network_policy_amendment":
        amendment = decision.network_policy_amendment
        target = subject.target if subject.kind == "network" else (amendment.host if amendment else "")
        if amendment and amendment.action is NetworkPolicyRuleAction.Allow:
            summary = f"{actor.subject()}persisted Codex network access to {target}"
            approved = True
        else:
            summary = f"{actor.subject()}denied codex network access to {target} and saved that rule"
            approved = False
    elif decision.kind == "denied":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            if actor is ApprovalDecisionActor.User:
                summary = (
                    f"{actor.subject()}did not approve codex to run {snippet}"
                    if snippet
                    else f"{actor.subject()}did not approve this request"
                )
            else:
                summary = f"Request denied for codex to run {snippet}" if snippet else "Request denied"
        else:
            summary = f"{actor.subject()}did not approve codex network access to {subject.target}"
        approved = False
    elif decision.kind == "timed_out":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = (
                f"Review timed out before codex could run {snippet}"
                if snippet
                else "Review timed out before this request could be approved"
            )
        else:
            summary = f"Review timed out before codex could access {subject.target}"
        approved = False
    elif decision.kind == "abort":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = (
                f"{actor.subject()}canceled the request to run {snippet}"
                if snippet
                else f"{actor.subject()}canceled this request"
            )
        else:
            summary = f"{actor.subject()}canceled the request for codex network access to {subject.target}"
        approved = False
    else:
        raise ValueError(f"unsupported review decision: {decision.kind}")

    return _summary_cell(summary, approved)


def _patch_file_summary(files: list[str]) -> str:
    if len(files) == 1:
        return f"a patch touching {files[0]}"
    return f"a patch touching {len(files)} files"


def new_guardian_denied_patch_request(files: Iterable[str]) -> PrefixedWrappedHistoryCell:
    file_list = [str(file) for file in files]
    return _summary_cell(f"Request denied for codex to apply {_patch_file_summary(file_list)}", False)


def new_guardian_denied_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(f"Request denied for {summary}", False)


def new_guardian_approved_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(f"Request approved for {summary}", True)


def new_guardian_timed_out_patch_request(files: Iterable[str]) -> PrefixedWrappedHistoryCell:
    file_list = [str(file) for file in files]
    return _summary_cell(f"Review timed out before codex could apply {_patch_file_summary(file_list)}", False)


def new_guardian_timed_out_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(f"Review timed out before {summary}", False)


def new_review_status_line(message: str) -> PlainHistoryCell:
    return PlainHistoryCell.new([Line.from_spans([Span(str(message), "cyan")])])


__all__ = [
    "APPROVED_SYMBOL",
    "ApprovalDecisionActor",
    "ApprovalDecisionSubject",
    "DENIED_SYMBOL",
    "ExecPolicyAmendment",
    "NetworkPolicyAmendment",
    "NetworkPolicyRuleAction",
    "RUST_MODULE",
    "ReviewDecision",
    "exec_snippet",
    "line_text",
    "new_approval_decision_cell",
    "new_guardian_approved_action_request",
    "new_guardian_denied_action_request",
    "new_guardian_denied_patch_request",
    "new_guardian_timed_out_action_request",
    "new_guardian_timed_out_patch_request",
    "new_review_status_line",
    "non_empty_exec_snippet",
    "strip_bash_lc_and_escape",
    "truncate_exec_snippet",
]
