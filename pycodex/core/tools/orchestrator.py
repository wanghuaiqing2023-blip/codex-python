"""Pure orchestration decisions ported from ``core/src/tools/orchestrator.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.tools.handlers.utils import session_strict_auto_review
from pycodex.core.tools.sandboxing import (
    ExecApprovalRequirement,
    SandboxOverride,
    ToolError,
    default_exec_approval_requirement,
    sandbox_override_for_first_attempt,
    should_bypass_approval,
    wants_no_sandbox_approval,
)
from pycodex.protocol import (
    AskForApproval,
    ExecToolCallOutput,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkPolicyRuleAction,
    ReviewDecision,
    SandboxPermissions,
)

ApprovalPolicy = AskForApproval | GranularApprovalConfig

GUARDIAN_TIMEOUT_MESSAGE = "automated review timed out"
DEFAULT_SANDBOX_DENIAL_RETRY_REASON = "command failed; retry without sandbox?"


class OrchestratorApprovalKind(str, Enum):
    SKIPPED = "skipped"
    REQUESTED = "requested"
    FORBIDDEN = "forbidden"


class OrchestratorAttemptKind(str, Enum):
    INITIAL = "initial"
    RETRY_WITHOUT_SANDBOX = "retry_without_sandbox"


@dataclass(frozen=True)
class OrchestratorRunResult:
    output: Any
    deferred_network_approval: Any | None = None


@dataclass(frozen=True)
class ApprovalStepDecision:
    kind: OrchestratorApprovalKind
    requirement: ExecApprovalRequirement
    strict_auto_review: bool = False
    use_guardian: bool = False
    evaluate_permission_request_hooks: bool = True
    already_approved: bool = False
    guardian_review_id_required: bool = False
    error: ToolError | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OrchestratorApprovalKind):
            object.__setattr__(self, "kind", OrchestratorApprovalKind(self.kind))
        if not isinstance(self.requirement, ExecApprovalRequirement):
            raise TypeError("requirement must be ExecApprovalRequirement")
        for field_name in (
            "strict_auto_review",
            "use_guardian",
            "evaluate_permission_request_hooks",
            "already_approved",
            "guardian_review_id_required",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        if self.error is not None and not isinstance(self.error, ToolError):
            raise TypeError("error must be ToolError or None")


@dataclass(frozen=True)
class InitialAttemptPlan:
    sandbox_override: SandboxOverride
    bypass_sandbox_first_attempt: bool
    managed_network_active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_override, SandboxOverride):
            object.__setattr__(self, "sandbox_override", SandboxOverride(self.sandbox_override))
        if not isinstance(self.bypass_sandbox_first_attempt, bool):
            raise TypeError("bypass_sandbox_first_attempt must be a bool")
        if not isinstance(self.managed_network_active, bool):
            raise TypeError("managed_network_active must be a bool")


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    reason: str | None = None
    needs_approval: bool = False
    guardian_review_id_required: bool = False
    evaluate_permission_request_hooks: bool = True
    bypass_retry_approval: bool = False
    error: ToolError | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "should_retry",
            "needs_approval",
            "guardian_review_id_required",
            "evaluate_permission_request_hooks",
            "bypass_retry_approval",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string or None")
        if self.error is not None and not isinstance(self.error, ToolError):
            raise TypeError("error must be ToolError or None")


@dataclass(frozen=True)
class ToolOrchestratorPlan:
    approval: ApprovalStepDecision
    initial_attempt: InitialAttemptPlan

    @classmethod
    def build(
        cls,
        *,
        explicit_requirement: ExecApprovalRequirement | None,
        approval_policy: ApprovalPolicy,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        sandbox_permissions: SandboxPermissions,
        managed_network_active: bool,
        strict_auto_review: bool = False,
        routes_to_guardian: bool = False,
    ) -> "ToolOrchestratorPlan":
        requirement = explicit_requirement or default_exec_approval_requirement(
            approval_policy,
            file_system_sandbox_policy,
        )
        return cls(
            approval_step_decision(
                requirement,
                strict_auto_review=strict_auto_review,
                routes_to_guardian=routes_to_guardian,
            ),
            initial_attempt_plan(
                sandbox_permissions,
                requirement,
                file_system_sandbox_policy,
                managed_network_active,
            ),
        )

    def __post_init__(self) -> None:
        if not isinstance(self.approval, ApprovalStepDecision):
            raise TypeError("approval must be ApprovalStepDecision")
        if not isinstance(self.initial_attempt, InitialAttemptPlan):
            raise TypeError("initial_attempt must be InitialAttemptPlan")


def approval_step_decision(
    requirement: ExecApprovalRequirement,
    *,
    strict_auto_review: bool = False,
    routes_to_guardian: bool = False,
) -> ApprovalStepDecision:
    if not isinstance(requirement, ExecApprovalRequirement):
        raise TypeError("requirement must be ExecApprovalRequirement")
    if not isinstance(strict_auto_review, bool):
        raise TypeError("strict_auto_review must be a bool")
    if not isinstance(routes_to_guardian, bool):
        raise TypeError("routes_to_guardian must be a bool")
    use_guardian = routes_to_guardian or strict_auto_review
    if requirement.type == "skip":
        if strict_auto_review:
            return ApprovalStepDecision(
                OrchestratorApprovalKind.REQUESTED,
                requirement,
                strict_auto_review=True,
                use_guardian=True,
                evaluate_permission_request_hooks=False,
                already_approved=True,
                guardian_review_id_required=True,
            )
        return ApprovalStepDecision(
            OrchestratorApprovalKind.SKIPPED,
            requirement,
            use_guardian=use_guardian,
            evaluate_permission_request_hooks=False,
        )
    if requirement.type == "forbidden":
        return ApprovalStepDecision(
            OrchestratorApprovalKind.FORBIDDEN,
            requirement,
            use_guardian=use_guardian,
            evaluate_permission_request_hooks=False,
            error=ToolError.rejected(requirement.reason or ""),
        )
    if requirement.type == "needs_approval":
        return ApprovalStepDecision(
            OrchestratorApprovalKind.REQUESTED,
            requirement,
            strict_auto_review=strict_auto_review,
            use_guardian=use_guardian,
            evaluate_permission_request_hooks=not strict_auto_review,
            already_approved=True,
            guardian_review_id_required=use_guardian,
        )
    raise ValueError(f"unsupported exec approval requirement type: {requirement.type}")


async def build_tool_orchestrator_plan_for_session(
    session: Any,
    *,
    explicit_requirement: ExecApprovalRequirement | None,
    approval_policy: ApprovalPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    sandbox_permissions: SandboxPermissions,
    managed_network_active: bool,
    routes_to_guardian: bool = False,
) -> ToolOrchestratorPlan:
    return ToolOrchestratorPlan.build(
        explicit_requirement=explicit_requirement,
        approval_policy=approval_policy,
        file_system_sandbox_policy=file_system_sandbox_policy,
        sandbox_permissions=sandbox_permissions,
        managed_network_active=managed_network_active,
        strict_auto_review=await session_strict_auto_review(session),
        routes_to_guardian=routes_to_guardian,
    )


def initial_attempt_plan(
    sandbox_permissions: SandboxPermissions,
    requirement: ExecApprovalRequirement,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    managed_network_active: bool,
) -> InitialAttemptPlan:
    if not isinstance(requirement, ExecApprovalRequirement):
        raise TypeError("requirement must be ExecApprovalRequirement")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
    if not isinstance(managed_network_active, bool):
        raise TypeError("managed_network_active must be a bool")
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    override = sandbox_override_for_first_attempt(
        sandbox_permissions,
        requirement,
        file_system_sandbox_policy,
    )
    return InitialAttemptPlan(
        override,
        override is SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT,
        managed_network_active,
    )


def reject_if_not_approved(
    decision: ReviewDecision | str | dict[str, Any],
    *,
    guardian_review_id: str | None = None,
    guardian_rejection_message: str | None = None,
    guardian_timeout_message: str = GUARDIAN_TIMEOUT_MESSAGE,
) -> ToolError | None:
    decision = ReviewDecision.from_mapping(decision)
    if guardian_review_id is not None and not isinstance(guardian_review_id, str):
        raise TypeError("guardian_review_id must be a string or None")
    if guardian_rejection_message is not None and not isinstance(guardian_rejection_message, str):
        raise TypeError("guardian_rejection_message must be a string or None")
    if not isinstance(guardian_timeout_message, str):
        raise TypeError("guardian_timeout_message must be a string")
    if decision.kind in {"denied", "abort"}:
        reason = guardian_rejection_message if guardian_review_id is not None else "rejected by user"
        return ToolError.rejected(reason or "rejected by user")
    if decision.kind == "timed_out":
        return ToolError.rejected(guardian_timeout_message)
    if decision.kind in {"approved", "approved_for_session", "approved_execpolicy_amendment"}:
        return None
    if decision.kind == "network_policy_amendment":
        amendment = decision.network_policy_amendment
        if amendment is not None and amendment.action is NetworkPolicyRuleAction.ALLOW:
            return None
        return ToolError.rejected("rejected by user")
    raise ValueError(f"unsupported review decision kind: {decision.kind}")


def build_denial_reason_from_output(output: ExecToolCallOutput) -> str:
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("output must be ExecToolCallOutput")
    return DEFAULT_SANDBOX_DENIAL_RETRY_REASON


def retry_decision_for_sandbox_denial(
    *,
    output: ExecToolCallOutput,
    approval_policy: ApprovalPolicy,
    already_approved: bool,
    strict_auto_review: bool,
    routes_to_guardian: bool,
    tool_escalate_on_failure: bool,
    tool_wants_no_sandbox_approval: bool | None = None,
    network_approval_host: str | None = None,
    default_requirement: ExecApprovalRequirement | None = None,
) -> RetryDecision:
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("output must be ExecToolCallOutput")
    for field_name, value in (
        ("already_approved", already_approved),
        ("strict_auto_review", strict_auto_review),
        ("routes_to_guardian", routes_to_guardian),
        ("tool_escalate_on_failure", tool_escalate_on_failure),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{field_name} must be a bool")
    if network_approval_host is not None and not isinstance(network_approval_host, str):
        raise TypeError("network_approval_host must be a string or None")
    if default_requirement is not None and not isinstance(default_requirement, ExecApprovalRequirement):
        raise TypeError("default_requirement must be ExecApprovalRequirement or None")
    if not tool_escalate_on_failure:
        return RetryDecision(False, error=ToolError.codex({"sandbox": "denied", "output": output}))
    wants_approval = (
        wants_no_sandbox_approval(approval_policy)
        if tool_wants_no_sandbox_approval is None
        else tool_wants_no_sandbox_approval
    )
    if not isinstance(wants_approval, bool):
        raise TypeError("tool_wants_no_sandbox_approval must be a bool or None")
    if not wants_approval:
        allow_on_request_network_prompt = (
            isinstance(approval_policy, AskForApproval)
            and approval_policy is AskForApproval.ON_REQUEST
            and network_approval_host is not None
            and default_requirement is not None
            and default_requirement.type == "needs_approval"
        )
        if not allow_on_request_network_prompt:
            return RetryDecision(False, error=ToolError.codex({"sandbox": "denied", "output": output}))
    reason = (
        f'Network access to "{network_approval_host}" is blocked by policy.'
        if network_approval_host is not None
        else build_denial_reason_from_output(output)
    )
    bypass_retry_approval = (
        not strict_auto_review
        and should_bypass_approval(approval_policy, already_approved)
        and network_approval_host is None
    )
    needs_approval = not bypass_retry_approval
    use_guardian = routes_to_guardian or strict_auto_review
    return RetryDecision(
        True,
        reason=reason,
        needs_approval=needs_approval,
        guardian_review_id_required=needs_approval and use_guardian,
        evaluate_permission_request_hooks=needs_approval and not strict_auto_review,
        bypass_retry_approval=bypass_retry_approval,
    )


__all__ = [
    "ApprovalPolicy",
    "ApprovalStepDecision",
    "DEFAULT_SANDBOX_DENIAL_RETRY_REASON",
    "GUARDIAN_TIMEOUT_MESSAGE",
    "InitialAttemptPlan",
    "OrchestratorApprovalKind",
    "OrchestratorAttemptKind",
    "OrchestratorRunResult",
    "RetryDecision",
    "ToolOrchestratorPlan",
    "approval_step_decision",
    "build_denial_reason_from_output",
    "build_tool_orchestrator_plan_for_session",
    "initial_attempt_plan",
    "reject_if_not_approved",
    "retry_decision_for_sandbox_denial",
]

