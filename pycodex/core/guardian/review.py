"""Guardian review routing helpers.

Rust source:

- ``codex/codex-rs/core/src/guardian/review.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    GranularApprovalConfig,
    GuardianAssessmentDecisionSource,
    GuardianRiskLevel,
    SessionSource,
    SubAgentSource,
)


GUARDIAN_REVIEWER_NAME = "guardian"
GUARDIAN_REJECTION_INSTRUCTIONS = (
    "The agent must not attempt to achieve the same outcome via workaround, "
    "indirect execution, or policy circumvention. "
    "Proceed only with a materially safer alternative, "
    "or if the user explicitly approves the action after being informed of the risk. "
    "Otherwise, stop and request user input."
)
GUARDIAN_TIMEOUT_INSTRUCTIONS = (
    "The automatic permission approval review did not finish before its deadline. "
    "Do not assume the action is unsafe based on the timeout alone. "
    "You may retry once, or ask the user for guidance or explicit approval."
)
DEFAULT_GUARDIAN_REJECTION_RATIONALE = "Auto-reviewer denied the action without a specific rationale."
GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT = "delegated_subagent"
SANDBOX_PERMISSIONS_USE_DEFAULT = "use_default"
SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS = "with_additional_permissions"


@dataclass(frozen=True, slots=True)
class GuardianRejection:
    """Minimal Python surface for Rust ``GuardianRejection``."""

    rationale: str
    source: GuardianAssessmentDecisionSource = GuardianAssessmentDecisionSource.AGENT


@dataclass(frozen=True, slots=True)
class GuardianShellApprovalRequest:
    """Minimal Python surface for Rust ``GuardianApprovalRequest::Shell``."""

    id: str
    command: Any
    cwd: Any
    sandbox_permissions: str = SANDBOX_PERMISSIONS_USE_DEFAULT
    additional_permissions: Any = None
    justification: str | None = None


@dataclass(frozen=True, slots=True)
class GuardianApplyPatchApprovalRequest:
    """Minimal Python surface for Rust ``GuardianApprovalRequest::ApplyPatch``."""

    id: str
    cwd: Any
    files: tuple[Path, ...]
    patch: str


def routes_approval_to_guardian(parent_ctx: Any) -> bool:
    """Port of Rust ``guardian::review::routes_approval_to_guardian``."""

    explicit = getattr(parent_ctx, "routes_approval_to_guardian", None)
    if callable(explicit):
        return bool(explicit())
    if explicit is not None:
        return bool(explicit)

    approval_policy = _attribute_or_mapping(parent_ctx, "approval_policy")
    config = _attribute_or_mapping(parent_ctx, "config")
    approvals_reviewer = _attribute_or_mapping(parent_ctx, "approvals_reviewer")
    if approvals_reviewer is None and config is not None:
        approvals_reviewer = _attribute_or_mapping(config, "approvals_reviewer")

    approval_routes = approval_policy is AskForApproval.ON_REQUEST or isinstance(approval_policy, GranularApprovalConfig)
    if not approval_routes and isinstance(approval_policy, str):
        approval_routes = approval_policy in {AskForApproval.ON_REQUEST.value, "granular"}

    reviewer_routes = approvals_reviewer is ApprovalsReviewer.AUTO_REVIEW
    if not reviewer_routes and isinstance(approvals_reviewer, str):
        reviewer_routes = approvals_reviewer in {ApprovalsReviewer.AUTO_REVIEW.value, "auto_review"}

    return approval_routes and reviewer_routes


async def guardian_rejection_message(session: Any, review_id: str) -> str:
    """Port of Rust ``guardian::review::guardian_rejection_message``."""

    rejection = await _pop_guardian_rejection(session, review_id)
    return guardian_rejection_message_for_rejection(rejection)


def guardian_rejection_message_for_rejection(rejection: Any | None) -> str:
    """Format a stored guardian rejection using Rust's user-facing text."""

    rationale = _rejection_rationale(rejection)
    if rationale.strip() == "":
        rationale = DEFAULT_GUARDIAN_REJECTION_RATIONALE
    return (
        "This action was rejected due to unacceptable risk.\n"
        f"Reason: {rationale.strip()}\n"
        f"{GUARDIAN_REJECTION_INSTRUCTIONS}"
    )


def guardian_timeout_message() -> str:
    """Port of Rust ``guardian::review::guardian_timeout_message``."""

    return GUARDIAN_TIMEOUT_INSTRUCTIONS


def guardian_risk_level_str(level: GuardianRiskLevel) -> str:
    """Port of Rust ``guardian::review::guardian_risk_level_str``."""

    return {
        GuardianRiskLevel.LOW: "low",
        GuardianRiskLevel.MEDIUM: "medium",
        GuardianRiskLevel.HIGH: "high",
        GuardianRiskLevel.CRITICAL: "critical",
    }[level]


def is_guardian_reviewer_source(session_source: Any) -> bool:
    """Port of Rust ``guardian::review::is_guardian_reviewer_source``."""

    if isinstance(session_source, SessionSource):
        return _is_guardian_subagent_source(session_source.subagent_source) if session_source.type == "subagent" else False
    if isinstance(session_source, Mapping):
        if "subagent" in session_source:
            return _is_guardian_subagent_source(session_source["subagent"])
        if session_source.get("type") == "subagent":
            return _is_guardian_subagent_source(session_source.get("subagent_source", session_source.get("subagentSource")))
        return False
    return False


def apply_patch_files_for_guardian(cwd: Any, changes: Mapping[Any, Any]) -> tuple[Path, ...]:
    """Return Rust-style absolute-ish file paths for guardian patch review."""

    base = Path(cwd)
    return tuple(base / Path(path) for path in changes.keys())


def format_apply_patch_changes_for_guardian(changes: Mapping[Any, Any]) -> str:
    """Format ``FileChange`` mappings like Rust ``handle_patch_approval``."""

    return "\n".join(_format_file_change(path, change) for path, change in changes.items())


def _format_file_change(path: Any, change: Any) -> str:
    change_type = _change_field(change, "type")
    display_path = str(path)
    if change_type == "add":
        return f"*** Add File: {display_path}\n{_change_field(change, 'content')}"
    if change_type == "delete":
        return f"*** Delete File: {display_path}\n{_change_field(change, 'content')}"
    if change_type == "update":
        unified_diff = _change_field(change, "unified_diff")
        move_path = _change_field(change, "move_path")
        if move_path is not None:
            return f"*** Update File: {display_path}\n*** Move to: {move_path}\n{unified_diff}"
        return f"*** Update File: {display_path}\n{unified_diff}"
    raise ValueError(f"unknown file change type: {change_type}")


def _change_field(change: Any, key: str, default: Any = None) -> Any:
    if isinstance(change, Mapping):
        return change.get(key, default)
    return getattr(change, key, default)


async def _pop_guardian_rejection(session: Any, review_id: str) -> Any | None:
    services = _attribute_or_mapping(session, "services")
    store = _attribute_or_mapping(services, "guardian_rejections")
    if store is None:
        store = _attribute_or_mapping(session, "guardian_rejections")
    if store is None:
        return None
    if isinstance(store, MutableMapping):
        return store.pop(review_id, None)
    pop = getattr(store, "pop", None)
    if callable(pop):
        return await _maybe_await(pop(review_id, None))
    remove = getattr(store, "remove", None)
    if callable(remove):
        return await _maybe_await(remove(review_id))
    return None


def _rejection_rationale(rejection: Any | None) -> str:
    if rejection is None:
        return DEFAULT_GUARDIAN_REJECTION_RATIONALE
    if isinstance(rejection, Mapping):
        return str(rejection.get("rationale", ""))
    return str(getattr(rejection, "rationale", ""))


def _is_guardian_subagent_source(source: Any) -> bool:
    if isinstance(source, SubAgentSource):
        return source.type == "other" and source.other == GUARDIAN_REVIEWER_NAME
    if isinstance(source, Mapping):
        if "other" in source:
            return source["other"] == GUARDIAN_REVIEWER_NAME
        return source.get("type") == "other" and source.get("other") == GUARDIAN_REVIEWER_NAME
    if isinstance(source, str):
        return source == GUARDIAN_REVIEWER_NAME
    return False


def _attribute_or_mapping(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        result = value.get(key, default)
    else:
        result = getattr(value, key, default)
    return result() if callable(result) else result


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "GUARDIAN_REVIEWER_NAME",
    "GUARDIAN_REJECTION_INSTRUCTIONS",
    "GUARDIAN_TIMEOUT_INSTRUCTIONS",
    "GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT",
    "DEFAULT_GUARDIAN_REJECTION_RATIONALE",
    "GuardianApplyPatchApprovalRequest",
    "GuardianRejection",
    "GuardianShellApprovalRequest",
    "SANDBOX_PERMISSIONS_USE_DEFAULT",
    "SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS",
    "apply_patch_files_for_guardian",
    "format_apply_patch_changes_for_guardian",
    "guardian_rejection_message",
    "guardian_rejection_message_for_rejection",
    "guardian_risk_level_str",
    "guardian_timeout_message",
    "is_guardian_reviewer_source",
    "routes_approval_to_guardian",
]
