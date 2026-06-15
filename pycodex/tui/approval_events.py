"""TUI-owned approval request event models.

Upstream source: ``codex/codex-rs/tui/src/approval_events.rs``.
The Rust module stores approval prompts while streaming output may defer UI
presentation. Python keeps the same local behavior contract and uses semantic
DTOs for app-server decision payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from ._porting import RustTuiModule
from .diff_model import FileChange

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="approval_events",
    source="codex/codex-rs/tui/src/approval_events.rs",
    status="complete",
)


@dataclass(frozen=True)
class CommandExecutionApprovalDecision:
    """Semantic equivalent of app-server command approval decisions."""

    kind: str
    execpolicy_amendment: Optional[Any] = None
    network_policy_amendment: Optional[Any] = None

    @classmethod
    def accept(cls) -> "CommandExecutionApprovalDecision":
        return cls("accept")

    @classmethod
    def accept_for_session(cls) -> "CommandExecutionApprovalDecision":
        return cls("accept_for_session")

    @classmethod
    def cancel(cls) -> "CommandExecutionApprovalDecision":
        return cls("cancel")

    @classmethod
    def accept_with_execpolicy_amendment(cls, amendment: Any) -> "CommandExecutionApprovalDecision":
        return cls("accept_with_execpolicy_amendment", execpolicy_amendment=amendment)

    @classmethod
    def apply_network_policy_amendment(cls, amendment: Any) -> "CommandExecutionApprovalDecision":
        return cls("apply_network_policy_amendment", network_policy_amendment=amendment)


@dataclass
class ExecApprovalRequestEvent:
    call_id: str
    command: Union[List[str], Tuple[str, ...]]
    cwd: Union[str, Path]
    approval_id: Optional[str] = None
    turn_id: str = ""
    reason: Optional[str] = None
    proposed_execpolicy_amendment: Optional[Any] = None
    proposed_network_policy_amendments: Optional[Union[List[Any], Tuple[Any, ...]]] = None
    available_decisions: Optional[Union[List[Any], Tuple[Any, ...]]] = None
    network_approval_context: Optional[Any] = None
    additional_permissions: Optional[Any] = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if self.approval_id is not None and not isinstance(self.approval_id, str):
            raise TypeError("approval_id must be a string or None")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if not isinstance(self.command, (list, tuple)) or not all(isinstance(part, str) for part in self.command):
            raise TypeError("command must be a list of strings")
        self.command = list(self.command)
        self.cwd = Path(self.cwd)
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string or None")
        if self.available_decisions is not None:
            self.available_decisions = list(self.available_decisions)
        if self.proposed_network_policy_amendments is not None:
            self.proposed_network_policy_amendments = list(self.proposed_network_policy_amendments)

    def effective_approval_id(self) -> str:
        return self.approval_id if self.approval_id is not None else self.call_id

    def effective_available_decisions(self) -> List[Any]:
        if self.available_decisions is not None:
            return list(self.available_decisions)
        return self.default_available_decisions(
            network_approval_context=self.network_approval_context,
            proposed_execpolicy_amendment=self.proposed_execpolicy_amendment,
            proposed_network_policy_amendments=self.proposed_network_policy_amendments,
            additional_permissions=self.additional_permissions,
        )

    @staticmethod
    def default_available_decisions(
        network_approval_context: Optional[Any] = None,
        proposed_execpolicy_amendment: Optional[Any] = None,
        proposed_network_policy_amendments: Optional[Union[List[Any], Tuple[Any, ...]]] = None,
        additional_permissions: Optional[Any] = None,
    ) -> List[CommandExecutionApprovalDecision]:
        if network_approval_context is not None:
            decisions = [
                CommandExecutionApprovalDecision.accept(),
                CommandExecutionApprovalDecision.accept_for_session(),
            ]
            allow_amendment = _first_allow_network_amendment(proposed_network_policy_amendments)
            if allow_amendment is not None:
                decisions.append(CommandExecutionApprovalDecision.apply_network_policy_amendment(allow_amendment))
            decisions.append(CommandExecutionApprovalDecision.cancel())
            return decisions

        if additional_permissions is not None:
            return [
                CommandExecutionApprovalDecision.accept(),
                CommandExecutionApprovalDecision.cancel(),
            ]

        decisions = [CommandExecutionApprovalDecision.accept()]
        if proposed_execpolicy_amendment is not None:
            decisions.append(CommandExecutionApprovalDecision.accept_with_execpolicy_amendment(proposed_execpolicy_amendment))
        decisions.append(CommandExecutionApprovalDecision.cancel())
        return decisions


@dataclass
class ApplyPatchApprovalRequestEvent:
    call_id: str
    changes: Dict[Path, FileChange]
    turn_id: str = ""
    reason: Optional[str] = None
    grant_root: Optional[Path] = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if not isinstance(self.changes, dict):
            raise TypeError("changes must be a dict")
        converted: Dict[Path, FileChange] = {}
        for path, change in self.changes.items():
            if not isinstance(change, FileChange):
                raise TypeError("change values must be FileChange")
            converted[Path(path)] = change
        self.changes = converted
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string or None")
        if self.grant_root is not None:
            self.grant_root = Path(self.grant_root)


def _first_allow_network_amendment(amendments: Optional[Union[List[Any], Tuple[Any, ...]]]) -> Optional[Any]:
    for amendment in amendments or ():
        if _network_amendment_action(amendment) == "allow":
            return amendment
    return None


def _network_amendment_action(amendment: Any) -> Optional[str]:
    if isinstance(amendment, Mapping):
        action = amendment.get("action")
    else:
        action = getattr(amendment, "action", None)
    if action is None:
        return None
    value = getattr(action, "value", action)
    return str(value).lower()


__all__ = [
    "ApplyPatchApprovalRequestEvent",
    "CommandExecutionApprovalDecision",
    "ExecApprovalRequestEvent",
    "RUST_MODULE",
]
