"""Pure orchestration decisions ported from ``core/src/tools/orchestrator.rs``."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import inspect
from pathlib import Path
from typing import Any, Mapping

from pycodex.core.guardian.review import (
    guardian_rejection_message as _guardian_rejection_message,
    guardian_timeout_message as _guardian_timeout_message,
)
from pycodex.core.network_policy_decision import network_approval_context_from_payload
from pycodex.core.sandbox_tags import SandboxType, get_platform_sandbox, should_require_platform_sandbox
from pycodex.core.tools.handlers.utils import session_strict_auto_review
from pycodex.core.tools.network_approval import (
    NetworkApprovalMode,
    begin_network_approval,
    finish_deferred_network_approval,
    finish_immediate_network_approval,
)
from pycodex.core.tools.sandboxing import (
    ApprovalCtx,
    ExecApprovalRequirement,
    SandboxAttempt,
    SandboxOverride,
    ToolCtx,
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
    WindowsSandboxLevel,
)

ApprovalPolicy = AskForApproval | GranularApprovalConfig

GUARDIAN_TIMEOUT_MESSAGE = _guardian_timeout_message()
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


class ToolOrchestrator:
    """Rust-shaped runtime orchestrator for approval, sandbox, and retry flow.

    Rust source: ``codex-rs/core/src/tools/orchestrator.rs``.
    Behavior anchor: ``ToolOrchestrator::run`` performs approval first, then a
    sandboxed first attempt, and retries without sandbox only for sandbox
    denials that the tool/policy allow to escalate.
    """

    def __init__(self, sandbox: Any = None) -> None:
        self.sandbox = sandbox if sandbox is not None else PythonSandboxManager()

    @classmethod
    def new(cls) -> "ToolOrchestrator":
        return cls()

    @staticmethod
    async def run_attempt(
        tool: Any,
        req: Any,
        tool_ctx: ToolCtx,
        attempt: SandboxAttempt,
        managed_network_active: bool,
    ) -> tuple[Any | ToolError, Any | None]:
        if not isinstance(tool_ctx, ToolCtx):
            raise TypeError("tool_ctx must be ToolCtx")
        if not isinstance(attempt, SandboxAttempt):
            raise TypeError("attempt must be SandboxAttempt")
        if not isinstance(managed_network_active, bool):
            raise TypeError("managed_network_active must be a bool")

        network_approval = None
        network_spec_factory = getattr(tool, "network_approval_spec", None)
        network_spec = (
            await _maybe_await(network_spec_factory(req, tool_ctx))
            if callable(network_spec_factory)
            else None
        )
        if network_spec is not None:
            network_service = _network_approval_service(tool_ctx.session)
            if network_service is None:
                return (
                    ToolError.rejected("network approval requested but session has no network approval service"),
                    None,
                )
            turn_id = _field(tool_ctx.turn, "sub_id") or _field(tool_ctx.turn, "id") or ""
            network_approval = begin_network_approval(
                network_service,
                str(turn_id),
                managed_network_active,
                network_spec,
            )

        attempt_with_network = attempt
        if network_approval is not None:
            attempt_with_network = replace(
                attempt,
                network_denial_cancellation_token=network_approval.cancellation_token,
            )

        run_method = getattr(tool, "run", None)
        if not callable(run_method):
            raise TypeError("tool must provide run(req, attempt, tool_ctx)")
        run_result = await _maybe_await(run_method(req, attempt_with_network, tool_ctx))

        if network_approval is None:
            return (run_result, None)

        network_service = _network_approval_service(tool_ctx.session)
        if network_service is None:
            return (
                ToolError.rejected("network approval requested but session has no network approval service"),
                None,
            )
        if network_approval.mode is NetworkApprovalMode.IMMEDIATE:
            try:
                finish_immediate_network_approval(network_service, network_approval)
            except Exception as err:  # noqa: BLE001 - preserve Rust Result-style boundary.
                return (ToolError.rejected(str(err)), None)
            return (run_result, None)

        deferred = network_approval.into_deferred()
        if isinstance(run_result, ToolError):
            try:
                finish_deferred_network_approval(network_service, deferred)
            except Exception as err:  # noqa: BLE001
                return (ToolError.rejected(str(err)), None)
            return (run_result, None)
        return (run_result, deferred)

    async def run(
        self,
        tool: Any,
        req: Any,
        tool_ctx: ToolCtx,
        turn_ctx: Any,
        approval_policy: ApprovalPolicy,
    ) -> OrchestratorRunResult | ToolError:
        if not isinstance(tool_ctx, ToolCtx):
            raise TypeError("tool_ctx must be ToolCtx")

        telemetry = _field(turn_ctx, "session_telemetry")
        strict_auto_review = await session_strict_auto_review(tool_ctx.session)
        use_guardian = _routes_approval_to_guardian(turn_ctx) or strict_auto_review
        already_approved = False

        permission_profile = _field(turn_ctx, "permission_profile")
        if permission_profile is None:
            raise TypeError("turn_ctx must expose permission_profile")
        file_system_sandbox_policy = _turn_ctx_call(turn_ctx, "file_system_sandbox_policy")
        if file_system_sandbox_policy is None:
            file_system_sandbox_policy = permission_profile.file_system_sandbox_policy()
        network_sandbox_policy = _turn_ctx_call(turn_ctx, "network_sandbox_policy")
        if network_sandbox_policy is None:
            network_sandbox_policy = permission_profile.network_sandbox_policy()

        requirement_factory = getattr(tool, "exec_approval_requirement", None)
        requirement = (
            await _maybe_await(requirement_factory(req))
            if callable(requirement_factory)
            else None
        )
        if requirement is None:
            requirement = default_exec_approval_requirement(approval_policy, file_system_sandbox_policy)
        if not isinstance(requirement, ExecApprovalRequirement):
            raise TypeError("exec_approval_requirement must return ExecApprovalRequirement or None")

        approval = approval_step_decision(
            requirement,
            strict_auto_review=strict_auto_review,
            routes_to_guardian=use_guardian,
        )
        if approval.error is not None:
            return approval.error
        if approval.kind is OrchestratorApprovalKind.SKIPPED:
            await _emit_tool_decision(telemetry, tool_ctx, ReviewDecision.approved(), "config")
        elif approval.kind is OrchestratorApprovalKind.REQUESTED:
            guardian_review_id = _new_guardian_review_id() if approval.guardian_review_id_required else None
            approval_ctx = ApprovalCtx(
                session=tool_ctx.session,
                turn=tool_ctx.turn,
                call_id=tool_ctx.call_id,
                guardian_review_id=guardian_review_id,
                retry_reason=requirement.reason,
                network_approval_context=None,
            )
            outcome = await request_approval(
                tool,
                req,
                tool_ctx.call_id,
                approval_ctx,
                tool_ctx,
                evaluate_permission_request_hooks=approval.evaluate_permission_request_hooks,
                telemetry=telemetry,
            )
            if outcome.error is not None:
                return outcome.error
            rejection = await reject_if_not_approved_for_tool_ctx(
                tool_ctx,
                guardian_review_id,
                outcome.decision,
            )
            if rejection is not None:
                return rejection
            already_approved = approval.already_approved

        sandbox_permissions_factory = getattr(tool, "sandbox_permissions", None)
        sandbox_permissions = (
            await _maybe_await(sandbox_permissions_factory(req))
            if callable(sandbox_permissions_factory)
            else SandboxPermissions.USE_DEFAULT
        )
        sandbox_override = sandbox_override_for_first_attempt(
            SandboxPermissions(sandbox_permissions),
            requirement,
            file_system_sandbox_policy,
        )
        managed_network_active = _field(turn_ctx, "network") is not None
        if sandbox_override is SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT:
            initial_sandbox = SandboxType.NONE
        else:
            initial_sandbox = _select_initial_sandbox(
                self.sandbox,
                file_system_sandbox_policy,
                network_sandbox_policy,
                _call_optional(tool, "sandbox_preference"),
                _field(turn_ctx, "windows_sandbox_level"),
                managed_network_active,
            )

        sandbox_cwd = await _tool_sandbox_cwd(tool, req)
        if sandbox_cwd is None:
            sandbox_cwd = _field(turn_ctx, "cwd")
        if sandbox_cwd is None:
            raise TypeError("turn_ctx must expose cwd when tool.sandbox_cwd() is None")
        features = _field(turn_ctx, "features")
        config = _field(turn_ctx, "config")
        permissions_config = _field(config, "permissions")
        initial_attempt = SandboxAttempt(
            sandbox=initial_sandbox,
            permissions=permission_profile,
            enforce_managed_network=managed_network_active,
            manager=self.sandbox,
            sandbox_cwd=Path(sandbox_cwd),
            codex_linux_sandbox_exe=_field(turn_ctx, "codex_linux_sandbox_exe"),
            use_legacy_landlock=bool(_call_optional(features, "use_legacy_landlock")),
            windows_sandbox_level=_field(
                turn_ctx,
                "windows_sandbox_level",
                WindowsSandboxLevel.DISABLED,
            )
            or WindowsSandboxLevel.DISABLED,
            windows_sandbox_private_desktop=bool(_field(permissions_config, "windows_sandbox_private_desktop", False)),
        )

        first_result, first_deferred = await self.run_attempt(
            tool,
            req,
            tool_ctx,
            initial_attempt,
            managed_network_active,
        )
        if not isinstance(first_result, ToolError):
            return OrchestratorRunResult(first_result, first_deferred)

        denial = _sandbox_denial_parts(first_result)
        if denial is None:
            return first_result
        output, network_policy_decision = denial
        network_approval_context = None
        if managed_network_active and network_policy_decision is not None:
            network_approval_context = network_approval_context_from_payload(network_policy_decision)
            if network_approval_context is None:
                return first_result
        escalate_on_failure = _call_optional(tool, "escalate_on_failure")
        if escalate_on_failure is None:
            escalate_on_failure = True
        if not bool(escalate_on_failure):
            return first_result
        wants_approval = (
            await _maybe_await(getattr(tool, "wants_no_sandbox_approval")(approval_policy))
            if callable(getattr(tool, "wants_no_sandbox_approval", None))
            else wants_no_sandbox_approval(approval_policy)
        )
        if not wants_approval:
            allow_on_request_network_prompt = (
                isinstance(approval_policy, AskForApproval)
                and approval_policy is AskForApproval.ON_REQUEST
                and network_approval_context is not None
                and default_exec_approval_requirement(approval_policy, file_system_sandbox_policy).type
                == "needs_approval"
            )
            if not allow_on_request_network_prompt:
                return first_result

        retry_reason = (
            f'Network access to "{network_approval_context.host}" is blocked by policy.'
            if network_approval_context is not None
            else build_denial_reason_from_output(output)
        )
        bypass_retry_approval = (
            not strict_auto_review
            and bool(_call_optional(tool, "should_bypass_approval", approval_policy, already_approved))
            and network_approval_context is None
        )
        if not bypass_retry_approval:
            guardian_review_id = _new_guardian_review_id() if use_guardian else None
            approval_ctx = ApprovalCtx(
                session=tool_ctx.session,
                turn=tool_ctx.turn,
                call_id=tool_ctx.call_id,
                guardian_review_id=guardian_review_id,
                retry_reason=retry_reason,
                network_approval_context=network_approval_context,
            )
            outcome = await request_approval(
                tool,
                req,
                f"{tool_ctx.call_id}:retry",
                approval_ctx,
                tool_ctx,
                evaluate_permission_request_hooks=not strict_auto_review,
                telemetry=telemetry,
            )
            if outcome.error is not None:
                return outcome.error
            rejection = await reject_if_not_approved_for_tool_ctx(
                tool_ctx,
                guardian_review_id,
                outcome.decision,
            )
            if rejection is not None:
                return rejection

        retry_attempt = replace(
            initial_attempt,
            sandbox=SandboxType.NONE,
            codex_linux_sandbox_exe=None,
            network_denial_cancellation_token=None,
        )
        retry_result, retry_deferred = await self.run_attempt(
            tool,
            req,
            tool_ctx,
            retry_attempt,
            managed_network_active,
        )
        if isinstance(retry_result, ToolError):
            return retry_result
        return OrchestratorRunResult(retry_result, retry_deferred)


class PythonSandboxManager:
    """Small Python counterpart to the Rust SandboxManager selection surface."""

    def select_initial(
        self,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        network_sandbox_policy: Any,
        sandbox_preference: Any = None,
        windows_sandbox_level: Any = None,
        managed_network_active: bool = False,
    ) -> SandboxType:
        if sandbox_preference is not None:
            try:
                return SandboxType(sandbox_preference)
            except (TypeError, ValueError):
                pass
        if should_require_platform_sandbox(
            file_system_sandbox_policy,
            network_sandbox_policy,
            managed_network_active,
        ):
            return get_platform_sandbox(windows_sandbox_level is not None) or SandboxType.NONE
        return SandboxType.NONE

    def transform(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("sandbox transform is owned by the concrete tool runtime")


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
class ApprovalRequestOutcome:
    decision: ReviewDecision | None = None
    error: ToolError | None = None
    decision_source: str | None = None
    used_permission_request_hook: bool = False

    def __post_init__(self) -> None:
        if self.decision is not None and not isinstance(self.decision, ReviewDecision):
            object.__setattr__(self, "decision", ReviewDecision.from_mapping(self.decision))
        if self.error is not None and not isinstance(self.error, ToolError):
            raise TypeError("error must be ToolError or None")
        if self.decision is None and self.error is None:
            raise ValueError("approval request outcome must include a decision or error")
        if self.decision is not None and self.error is not None:
            raise ValueError("approval request outcome cannot include both decision and error")
        if self.decision_source is not None and not isinstance(self.decision_source, str):
            raise TypeError("decision_source must be a string or None")
        if not isinstance(self.used_permission_request_hook, bool):
            raise TypeError("used_permission_request_hook must be a bool")


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


async def request_approval(
    tool: Any,
    req: Any,
    permission_request_run_id: str,
    approval_ctx: Any,
    tool_ctx: Any,
    *,
    evaluate_permission_request_hooks: bool,
    run_permission_request_hooks: Any = None,
    telemetry: Any = None,
) -> ApprovalRequestOutcome:
    """Rust-shaped approval request helper.

    Rust source: ``codex-rs/core/src/tools/orchestrator.rs``.
    Behavior anchor: ``ToolOrchestrator::request_approval`` gives
    PermissionRequest hooks top precedence. A hook ``Allow`` becomes
    ``ReviewDecision::Approved``; a hook ``Deny { message }`` becomes
    ``ToolError::Rejected(message)``. Without a hook decision, the normal
    guardian/user approval path is used.
    """

    if not isinstance(permission_request_run_id, str):
        raise TypeError("permission_request_run_id must be a string")
    if not isinstance(evaluate_permission_request_hooks, bool):
        raise TypeError("evaluate_permission_request_hooks must be a bool")

    if evaluate_permission_request_hooks:
        payload = await _permission_request_payload(tool, req)
        if payload is not None:
            runner = run_permission_request_hooks or _field(approval_ctx, "run_permission_request_hooks")
            if callable(runner):
                hook_decision = await _maybe_await(
                    runner(
                        _field(approval_ctx, "session"),
                        _field(approval_ctx, "turn"),
                        permission_request_run_id,
                        payload,
                    )
                )
                normalized = _permission_request_hook_decision(hook_decision)
                if normalized is not None:
                    kind, message = normalized
                    if kind == "allow":
                        decision = ReviewDecision.approved()
                        await _emit_tool_decision(telemetry, tool_ctx, decision, "config")
                        return ApprovalRequestOutcome(
                            decision=decision,
                            decision_source="config",
                            used_permission_request_hook=True,
                        )
                    decision = ReviewDecision.denied()
                    await _emit_tool_decision(telemetry, tool_ctx, decision, "config")
                    return ApprovalRequestOutcome(
                        error=ToolError.rejected(message or "rejected by permission request hook"),
                        decision_source="config",
                        used_permission_request_hook=True,
                    )

    starter = getattr(tool, "start_approval_async", None)
    if not callable(starter):
        raise TypeError("tool must provide start_approval_async")
    decision = ReviewDecision.from_mapping(await _maybe_await(starter(req, approval_ctx)))
    source = "automated_reviewer" if _field(approval_ctx, "guardian_review_id") is not None else "user"
    await _emit_tool_decision(telemetry, tool_ctx, decision, source)
    return ApprovalRequestOutcome(decision=decision, decision_source=source)


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
    guardian_timeout_message: str | None = None,
) -> ToolError | None:
    decision = ReviewDecision.from_mapping(decision)
    if guardian_review_id is not None and not isinstance(guardian_review_id, str):
        raise TypeError("guardian_review_id must be a string or None")
    if guardian_rejection_message is not None and not isinstance(guardian_rejection_message, str):
        raise TypeError("guardian_rejection_message must be a string or None")
    if guardian_timeout_message is not None and not isinstance(guardian_timeout_message, str):
        raise TypeError("guardian_timeout_message must be a string or None")
    if decision.kind in {"denied", "abort"}:
        reason = guardian_rejection_message if guardian_review_id is not None else "rejected by user"
        return ToolError.rejected(reason or "rejected by user")
    if decision.kind == "timed_out":
        return ToolError.rejected(guardian_timeout_message or GUARDIAN_TIMEOUT_MESSAGE)
    if decision.kind in {"approved", "approved_for_session", "approved_execpolicy_amendment"}:
        return None
    if decision.kind == "network_policy_amendment":
        amendment = decision.network_policy_amendment
        if amendment is not None and amendment.action is NetworkPolicyRuleAction.ALLOW:
            return None
        return ToolError.rejected("rejected by user")
    raise ValueError(f"unsupported review decision kind: {decision.kind}")


async def reject_if_not_approved_for_tool_ctx(
    tool_ctx: Any,
    guardian_review_id: str | None,
    decision: ReviewDecision | str | dict[str, Any],
) -> ToolError | None:
    """Rust-shaped async wrapper for ``reject_if_not_approved``.

    Rust source: ``codex-rs/core/src/tools/orchestrator.rs``.
    Behavior anchor: ``ToolOrchestrator::reject_if_not_approved`` calls
    ``guardian_rejection_message(tool_ctx.session, review_id).await`` for
    guardian denied/abort decisions and ``guardian_timeout_message()`` for
    timed-out decisions.
    """

    if guardian_review_id is not None and not isinstance(guardian_review_id, str):
        raise TypeError("guardian_review_id must be a string or None")
    decision = ReviewDecision.from_mapping(decision)
    guardian_message: str | None = None
    if decision.kind in {"denied", "abort"} and guardian_review_id is not None:
        session = _tool_ctx_session(tool_ctx)
        guardian_message = await _guardian_rejection_message(session, guardian_review_id)
    return reject_if_not_approved(
        decision,
        guardian_review_id=guardian_review_id,
        guardian_rejection_message=guardian_message,
    )


def _tool_ctx_session(tool_ctx: Any) -> Any:
    if isinstance(tool_ctx, Mapping):
        return tool_ctx.get("session")
    return getattr(tool_ctx, "session", None)


def _routes_approval_to_guardian(turn_ctx: Any) -> bool:
    value = _turn_ctx_call(turn_ctx, "routes_approval_to_guardian", None)
    if value is None:
        value = _field(turn_ctx, "routes_approval_to_guardian", False)
    return bool(value)


def _new_guardian_review_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _turn_ctx_call(value: Any, key: str, default: Any = None) -> Any:
    field = _field(value, key, default)
    if callable(field):
        return field()
    return field


def _call_optional(value: Any, key: str, *args: Any) -> Any:
    field = _field(value, key)
    if callable(field):
        return field(*args)
    return field


def _select_initial_sandbox(
    sandbox: Any,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: Any,
    sandbox_preference: Any,
    windows_sandbox_level: Any,
    managed_network_active: bool,
) -> Any:
    selector = getattr(sandbox, "select_initial", None)
    if not callable(selector):
        raise TypeError("sandbox manager must expose select_initial(...)")
    return selector(
        file_system_sandbox_policy,
        network_sandbox_policy,
        sandbox_preference,
        windows_sandbox_level,
        managed_network_active,
    )


async def _tool_sandbox_cwd(tool: Any, req: Any) -> Any:
    sandbox_cwd = getattr(tool, "sandbox_cwd", None)
    if not callable(sandbox_cwd):
        return None
    return await _maybe_await(sandbox_cwd(req))


def _network_approval_service(session: Any) -> Any:
    service = _field(session, "network_approval")
    if service is None:
        service = _field(session, "network_approval_service")
    if callable(service):
        return service()
    return service


def _sandbox_denial_parts(error: ToolError) -> tuple[ExecToolCallOutput, Any | None] | None:
    if not isinstance(error, ToolError) or error.type != "codex":
        return None
    payload = error.error
    if isinstance(payload, Mapping):
        sandbox = payload.get("sandbox")
        if sandbox != "denied":
            return None
        output = payload.get("output")
        network_policy_decision = payload.get("network_policy_decision")
    else:
        sandbox = _field(payload, "sandbox")
        if sandbox != "denied":
            return None
        output = _field(payload, "output")
        network_policy_decision = _field(payload, "network_policy_decision")
    if not isinstance(output, ExecToolCallOutput):
        raise TypeError("sandbox denial output must be ExecToolCallOutput")
    return (output, network_policy_decision)


async def _permission_request_payload(tool: Any, req: Any) -> Any | None:
    payload_factory = getattr(tool, "permission_request_payload", None)
    if not callable(payload_factory):
        return None
    return await _maybe_await(payload_factory(req))


def _permission_request_hook_decision(value: Any) -> tuple[str, str | None] | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.lower()
        if normalized in {"allow", "allowed", "approve", "approved"}:
            return ("allow", None)
        if normalized in {"deny", "denied", "decline", "rejected"}:
            return ("deny", None)
        raise ValueError(f"unknown permission request hook decision: {value}")
    behavior = _field(value, "behavior", None)
    if behavior is None:
        behavior = _field(value, "type", None)
    if behavior is None:
        behavior = _field(value, "kind", None)
    message = _field(value, "message", None)
    if behavior is None:
        return None
    normalized = str(behavior).lower()
    if normalized in {"allow", "allowed", "approve", "approved"}:
        return ("allow", None)
    if normalized in {"deny", "denied", "decline", "rejected"}:
        if message is not None and not isinstance(message, str):
            raise TypeError("permission request deny message must be a string or None")
        return ("deny", message)
    raise ValueError(f"unknown permission request hook decision: {behavior}")


async def _emit_tool_decision(telemetry: Any, tool_ctx: Any, decision: ReviewDecision, source: str) -> None:
    if telemetry is None:
        return
    emitter = getattr(telemetry, "tool_decision", None)
    if not callable(emitter):
        return
    await _maybe_await(emitter(_flat_tool_name_value(_field(tool_ctx, "tool_name")), _field(tool_ctx, "call_id"), decision, source))


def _flat_tool_name_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ".".join(str(item) for item in value)
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return str(value)


def _field(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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
    "ApprovalRequestOutcome",
    "ApprovalStepDecision",
    "DEFAULT_SANDBOX_DENIAL_RETRY_REASON",
    "GUARDIAN_TIMEOUT_MESSAGE",
    "InitialAttemptPlan",
    "OrchestratorApprovalKind",
    "OrchestratorAttemptKind",
    "OrchestratorRunResult",
    "RetryDecision",
    "PythonSandboxManager",
    "ToolOrchestrator",
    "ToolOrchestratorPlan",
    "approval_step_decision",
    "build_denial_reason_from_output",
    "build_tool_orchestrator_plan_for_session",
    "initial_attempt_plan",
    "reject_if_not_approved",
    "reject_if_not_approved_for_tool_ctx",
    "request_approval",
    "retry_decision_for_sandbox_denial",
]

