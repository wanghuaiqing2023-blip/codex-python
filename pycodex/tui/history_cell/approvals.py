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
APPROVED_SYMBOL = "✔ "
DENIED_SYMBOL = "✗ "


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


def _summary_cell(summary: Line, approved: bool) -> PrefixedWrappedHistoryCell:
    symbol = Span(APPROVED_SYMBOL, "green") if approved else Span(DENIED_SYMBOL, "red")
    return PrefixedWrappedHistoryCell.new(summary, symbol, "  ")


def new_approval_decision_cell(
    subject: ApprovalDecisionSubject | dict[str, Any] | Any,
    decision: ReviewDecision | str | dict[str, Any] | Any,
    actor: ApprovalDecisionActor | str | Any,
) -> PrefixedWrappedHistoryCell:
    subject = ApprovalDecisionSubject.coerce(subject)
    decision = ReviewDecision.coerce(decision)
    actor = ApprovalDecisionActor.coerce(actor)

    if decision.kind == "approved":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("approved", "bold"),
                    " codex to run ",
                    Span(snippet, "dim"),
                    Span(" this time", "bold"),
                ]
                if snippet
                else [
                    actor.subject(),
                    Span("approved", "bold"),
                    " this request",
                    Span(" this time", "bold"),
                ]
            )
        else:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("approved", "bold"),
                    " codex network access to ",
                    Span(subject.target or "", "dim"),
                    Span(" this time", "bold"),
                ]
            )
        approved = True
    elif decision.kind == "approved_execpolicy_amendment":
        amendment = decision.proposed_execpolicy_amendment
        snippet = exec_snippet(amendment.command if amendment else ())
        summary = Line.from_spans(
            [
                actor.subject(),
                Span("approved", "bold"),
                " codex to always run commands that start with ",
                Span(snippet, "dim"),
            ]
        )
        approved = True
    elif decision.kind == "approved_for_session":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("approved", "bold"),
                    " codex to run ",
                    Span(snippet, "dim"),
                    Span(" every time this session", "bold"),
                ]
                if snippet
                else [
                    actor.subject(),
                    Span("approved", "bold"),
                    " this request",
                    Span(" every time this session", "bold"),
                ]
            )
        else:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("approved", "bold"),
                    " codex network access to ",
                    Span(subject.target or "", "dim"),
                    Span(" every time this session", "bold"),
                ]
            )
        approved = True
    elif decision.kind == "network_policy_amendment":
        amendment = decision.network_policy_amendment
        target = subject.target if subject.kind == "network" else (amendment.host if amendment else "")
        if amendment and amendment.action is NetworkPolicyRuleAction.Allow:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("persisted", "bold"),
                    " Codex network access to ",
                    Span(target or "", "dim"),
                ]
            )
            approved = True
        else:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("denied", "bold"),
                    " codex network access to ",
                    Span(target or "", "dim"),
                    " and saved that rule",
                ]
            )
            approved = False
    elif decision.kind == "denied":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            if actor is ApprovalDecisionActor.User:
                summary = Line.from_spans(
                    [
                        actor.subject(),
                        Span("did not approve", "bold"),
                        " codex to run ",
                        Span(snippet, "dim"),
                    ]
                    if snippet
                    else [
                        actor.subject(),
                        Span("did not approve", "bold"),
                        " this request",
                    ]
                )
            else:
                summary = Line.from_spans(
                    ["Request ", Span("denied", "bold"), " for codex to run ", Span(snippet, "dim")]
                    if snippet
                    else ["Request ", Span("denied", "bold")]
                )
        else:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("did not approve", "bold"),
                    " codex network access to ",
                    Span(subject.target or "", "dim"),
                ]
            )
        approved = False
    elif decision.kind == "timed_out":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = Line.from_spans(
                ["Review ", Span("timed out", "bold"), " before codex could run ", Span(snippet, "dim")]
                if snippet
                else [
                    "Review ",
                    Span("timed out", "bold"),
                    " before this request could be approved",
                ]
            )
        else:
            summary = Line.from_spans(
                [
                    "Review ",
                    Span("timed out", "bold"),
                    " before codex could access ",
                    Span(subject.target or "", "dim"),
                ]
            )
        approved = False
    elif decision.kind == "abort":
        if subject.kind == "command":
            snippet = non_empty_exec_snippet(subject.command)
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("canceled", "bold"),
                    " the request to run ",
                    Span(snippet, "dim"),
                ]
                if snippet
                else [actor.subject(), Span("canceled", "bold"), " this request"]
            )
        else:
            summary = Line.from_spans(
                [
                    actor.subject(),
                    Span("canceled", "bold"),
                    " the request for codex network access to ",
                    Span(subject.target or "", "dim"),
                ]
            )
        approved = False
    else:
        raise ValueError(f"unsupported review decision: {decision.kind}")

    return _summary_cell(summary, approved)


def new_guardian_denied_patch_request(files: Iterable[str]) -> PrefixedWrappedHistoryCell:
    file_list = [str(file) for file in files]
    summary = ["Request ", Span("denied", "bold"), " for codex to apply ", "a patch touching "]
    if len(file_list) == 1:
        summary.append(Span(file_list[0], "dim"))
    else:
        summary.extend([Span(str(len(file_list)), "dim"), " files"])
    return _summary_cell(Line.from_spans(summary), False)


def new_guardian_denied_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(
        Line.from_spans(["Request ", Span("denied", "bold"), " for ", Span(summary, "dim")]),
        False,
    )


def new_guardian_approved_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(
        Line.from_spans(["Request ", Span("approved", "bold"), " for ", Span(summary, "dim")]),
        True,
    )


def new_guardian_timed_out_patch_request(files: Iterable[str]) -> PrefixedWrappedHistoryCell:
    file_list = [str(file) for file in files]
    summary = [
        "Review ",
        Span("timed out", "bold"),
        " before codex could apply ",
        "a patch touching ",
    ]
    if len(file_list) == 1:
        summary.append(Span(file_list[0], "dim"))
    else:
        summary.extend([Span(str(len(file_list)), "dim"), " files"])
    return _summary_cell(Line.from_spans(summary), False)


def new_guardian_timed_out_action_request(summary: str) -> PrefixedWrappedHistoryCell:
    return _summary_cell(
        Line.from_spans(["Review ", Span("timed out", "bold"), " before ", Span(summary, "dim")]),
        False,
    )


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
