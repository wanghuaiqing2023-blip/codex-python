import asyncio
import unittest

from pycodex.core import (
    ApprovalRequestOutcome,
    ApprovalStepDecision,
    ExecApprovalRequirement,
    OrchestratorApprovalKind,
    ToolOrchestratorPlan,
    approval_step_decision,
    build_denial_reason_from_output,
    build_tool_orchestrator_plan_for_session,
    initial_attempt_plan,
    reject_if_not_approved,
    reject_if_not_approved_for_tool_ctx,
    request_approval,
    retry_decision_for_sandbox_denial,
)
from pycodex.core.guardian.review import GuardianRejection, guardian_timeout_message
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    ExecToolCallOutput,
    FileSystemSandboxPolicy,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ReviewDecision,
    SandboxPermissions,
)


class ToolOrchestratorTests(unittest.TestCase):
    def test_skip_requirement_only_prompts_under_strict_auto_review(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: ToolOrchestrator::run handles
        # ExecApprovalRequirement::Skip as config-approved unless strict
        # auto-review forces a guardian approval request with hooks disabled.
        skipped = approval_step_decision(ExecApprovalRequirement.skip())
        strict = approval_step_decision(ExecApprovalRequirement.skip(), strict_auto_review=True)

        self.assertEqual(skipped.kind, OrchestratorApprovalKind.SKIPPED)
        self.assertFalse(skipped.already_approved)
        self.assertFalse(skipped.evaluate_permission_request_hooks)
        self.assertFalse(skipped.guardian_review_id_required)
        self.assertEqual(strict.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(strict.already_approved)
        self.assertTrue(strict.guardian_review_id_required)
        self.assertFalse(strict.evaluate_permission_request_hooks)

    def test_needs_approval_routes_to_guardian_and_disables_hooks_for_strict_review(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: ExecApprovalRequirement::NeedsApproval requests
        # approval, routes to guardian when configured, and skips
        # PermissionRequest hooks during strict auto-review.
        normal = approval_step_decision(ExecApprovalRequirement.needs_approval(), routes_to_guardian=True)
        strict = approval_step_decision(ExecApprovalRequirement.needs_approval(), strict_auto_review=True)

        self.assertEqual(normal.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(normal.guardian_review_id_required)
        self.assertTrue(normal.evaluate_permission_request_hooks)
        self.assertTrue(normal.already_approved)
        self.assertFalse(strict.evaluate_permission_request_hooks)
        self.assertTrue(strict.guardian_review_id_required)
        self.assertTrue(strict.already_approved)

    def test_forbidden_requirement_returns_rejected_tool_error(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: ExecApprovalRequirement::Forbidden immediately
        # returns ToolError::Rejected with the requirement reason.
        decision = approval_step_decision(ExecApprovalRequirement.forbidden("no sandbox prompt"))

        self.assertEqual(decision.kind, OrchestratorApprovalKind.FORBIDDEN)
        self.assertEqual(decision.error.message, "no sandbox prompt")

    def test_initial_attempt_plan_uses_sandbox_override_helper(self) -> None:
        plan = initial_attempt_plan(
            SandboxPermissions.REQUIRE_ESCALATED,
            ExecApprovalRequirement.skip(),
            FileSystemSandboxPolicy.default(),
            managed_network_active=True,
        )

        self.assertTrue(plan.bypass_sandbox_first_attempt)
        self.assertTrue(plan.managed_network_active)

    def test_build_plan_combines_default_requirement_and_initial_attempt(self) -> None:
        plan = ToolOrchestratorPlan.build(
            explicit_requirement=None,
            approval_policy=AskForApproval.ON_REQUEST,
            file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            managed_network_active=False,
        )

        self.assertEqual(plan.approval.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertFalse(plan.initial_attempt.bypass_sandbox_first_attempt)

    def test_build_plan_for_session_reads_strict_auto_review(self) -> None:
        class Session:
            async def strict_auto_review(self):
                return True

        plan = asyncio.run(
            build_tool_orchestrator_plan_for_session(
                Session(),
                explicit_requirement=ExecApprovalRequirement.skip(),
                approval_policy=AskForApproval.NEVER,
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_permissions=SandboxPermissions.USE_DEFAULT,
                managed_network_active=False,
            )
        )

        self.assertEqual(plan.approval.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(plan.approval.strict_auto_review)
        self.assertTrue(plan.approval.guardian_review_id_required)

    def test_request_approval_permission_hook_allow_short_circuits_user_prompt(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: request_approval gives PermissionRequest hooks top
        # precedence; Allow maps to ReviewDecision::Approved and does not call
        # the normal approval path.
        class Tool:
            started = False

            def permission_request_payload(self, req):
                return {"tool_input": req}

            async def start_approval_async(self, _req, _approval_ctx):
                self.started = True
                return ReviewDecision.denied()

        class Telemetry:
            def __init__(self):
                self.events = []

            def tool_decision(self, tool_name, call_id, decision, source):
                self.events.append((tool_name, call_id, decision.kind, source))

        calls = []

        async def hook_runner(session, turn, run_id_suffix, payload):
            calls.append((session, turn, run_id_suffix, payload))
            return "allow"

        tool = Tool()
        telemetry = Telemetry()
        outcome = asyncio.run(
            request_approval(
                tool,
                {"command": "pwd"},
                "call-1",
                {"session": "session-1", "turn": "turn-1"},
                {"tool_name": "Bash", "call_id": "call-1"},
                evaluate_permission_request_hooks=True,
                run_permission_request_hooks=hook_runner,
                telemetry=telemetry,
            )
        )

        self.assertIsInstance(outcome, ApprovalRequestOutcome)
        self.assertEqual(outcome.decision, ReviewDecision.approved())
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.decision_source, "config")
        self.assertTrue(outcome.used_permission_request_hook)
        self.assertFalse(tool.started)
        self.assertEqual(calls, [("session-1", "turn-1", "call-1", {"tool_input": {"command": "pwd"}})])
        self.assertEqual(telemetry.events, [("Bash", "call-1", "approved", "config")])

    def test_request_approval_permission_hook_deny_returns_rejected_tool_error(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: PermissionRequestDecision::Deny { message } returns
        # ToolError::Rejected(message) and does not call start_approval_async.
        class Tool:
            started = False

            def permission_request_payload(self, _req):
                return {"command": "rm -rf tmp"}

            def start_approval_async(self, _req, _approval_ctx):
                self.started = True
                return ReviewDecision.approved()

        async def hook_runner(_session, _turn, _run_id_suffix, _payload):
            return {"behavior": "deny", "message": "blocked by hook"}

        tool = Tool()
        outcome = asyncio.run(
            request_approval(
                tool,
                object(),
                "call-2",
                {"session": object(), "turn": object()},
                {"tool_name": "Bash", "call_id": "call-2"},
                evaluate_permission_request_hooks=True,
                run_permission_request_hooks=hook_runner,
            )
        )

        self.assertIsNone(outcome.decision)
        self.assertEqual(outcome.error.message, "blocked by hook")
        self.assertEqual(outcome.decision_source, "config")
        self.assertTrue(outcome.used_permission_request_hook)
        self.assertFalse(tool.started)

    def test_request_approval_falls_back_to_guardian_or_user_approval_path(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: when hooks are disabled or produce no decision,
        # request_approval calls tool.start_approval_async and records user or
        # automated-reviewer as the decision source.
        class Tool:
            def __init__(self):
                self.requests = []

            def permission_request_payload(self, _req):
                return {"command": "git status"}

            async def start_approval_async(self, req, approval_ctx):
                self.requests.append((req, approval_ctx))
                return "approved_for_session"

        tool = Tool()
        approval_ctx = {"session": "session-1", "turn": "turn-1", "guardian_review_id": "review-1"}
        outcome = asyncio.run(
            request_approval(
                tool,
                "request",
                "call-3",
                approval_ctx,
                {"tool_name": ("shell", "exec"), "call_id": "call-3"},
                evaluate_permission_request_hooks=False,
            )
        )

        self.assertEqual(outcome.decision, ReviewDecision.approved_for_session())
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.decision_source, "automated_reviewer")
        self.assertFalse(outcome.used_permission_request_hook)
        self.assertEqual(tool.requests, [("request", approval_ctx)])

    def test_request_approval_hook_none_falls_back_to_normal_approval_path(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: PermissionRequest hooks take precedence only when
        # they return a decision; None falls through to start_approval_async.
        class Tool:
            def __init__(self):
                self.requests = []

            def permission_request_payload(self, _req):
                return {"command": "git status"}

            async def start_approval_async(self, req, approval_ctx):
                self.requests.append((req, approval_ctx))
                return ReviewDecision.approved()

        calls = []

        async def hook_runner(session, turn, run_id_suffix, payload):
            calls.append((session, turn, run_id_suffix, payload))
            return None

        tool = Tool()
        approval_ctx = {"session": "session-1", "turn": "turn-1"}
        outcome = asyncio.run(
            request_approval(
                tool,
                "request",
                "call-4",
                approval_ctx,
                {"tool_name": "Bash", "call_id": "call-4"},
                evaluate_permission_request_hooks=True,
                run_permission_request_hooks=hook_runner,
            )
        )

        self.assertEqual(outcome.decision, ReviewDecision.approved())
        self.assertIsNone(outcome.error)
        self.assertEqual(outcome.decision_source, "user")
        self.assertFalse(outcome.used_permission_request_hook)
        self.assertEqual(calls, [("session-1", "turn-1", "call-4", {"command": "git status"})])
        self.assertEqual(tool.requests, [("request", approval_ctx)])

    def test_reject_if_not_approved_matches_rust_decisions(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: reject_if_not_approved accepts approved variants
        # including ApprovedExecpolicyAmendment and ApprovedForSession, rejects
        # denied/abort/timed-out decisions with Rust-shaped messages.
        self.assertIsNone(reject_if_not_approved(ReviewDecision.approved()))
        self.assertIsNone(
            reject_if_not_approved(
                ReviewDecision.approved_execpolicy_amendment(
                    ExecPolicyAmendment.new(["npm"])
                )
            )
        )
        self.assertIsNone(reject_if_not_approved(ReviewDecision.approved_for_session()))
        self.assertEqual(reject_if_not_approved(ReviewDecision.denied()).message, "rejected by user")
        self.assertEqual(
            reject_if_not_approved(
                ReviewDecision.denied(),
                guardian_review_id="review-1",
                guardian_rejection_message="guardian said no",
            ).message,
            "guardian said no",
        )
        self.assertEqual(reject_if_not_approved(ReviewDecision.timed_out()).message, guardian_timeout_message())

    def test_reject_if_not_approved_for_tool_ctx_uses_guardian_rejection_store(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: reject_if_not_approved calls
        # guardian_rejection_message(tool_ctx.session, review_id).await for
        # guardian denied/abort decisions.
        class Session:
            def __init__(self) -> None:
                self.guardian_rejections = {"review-1": GuardianRejection("dangerous command")}

        class ToolCtx:
            def __init__(self) -> None:
                self.session = Session()

        tool_ctx = ToolCtx()
        error = asyncio.run(
            reject_if_not_approved_for_tool_ctx(
                tool_ctx,
                "review-1",
                ReviewDecision.denied(),
            )
        )

        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("This action was rejected due to unacceptable risk.", error.message)
        self.assertIn("Reason: dangerous command", error.message)
        self.assertEqual(tool_ctx.session.guardian_rejections, {})

    def test_network_policy_review_decision_allows_only_allow_amendments(self) -> None:
        allow = ReviewDecision.network_policy_amendment_decision(
            NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.ALLOW)
        )
        deny = ReviewDecision.network_policy_amendment_decision(
            NetworkPolicyAmendment("example.com", NetworkPolicyRuleAction.DENY)
        )

        self.assertIsNone(reject_if_not_approved(allow))
        self.assertEqual(reject_if_not_approved(deny).message, "rejected by user")

    def test_retry_decision_denies_when_tool_does_not_escalate(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: sandbox denial returns immediately when the tool
        # runtime does not support escalation on failure.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_FAILURE,
            already_approved=False,
            strict_auto_review=False,
            routes_to_guardian=False,
            tool_escalate_on_failure=False,
        )

        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.error.type, "codex")

    def test_retry_decision_bypasses_retry_approval_after_prior_approval(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: non-strict retry can bypass a second approval when
        # the original sandboxed attempt was already approved and no network
        # approval context is involved.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_FAILURE,
            already_approved=True,
            strict_auto_review=False,
            routes_to_guardian=False,
            tool_escalate_on_failure=True,
        )

        self.assertTrue(decision.should_retry)
        self.assertTrue(decision.bypass_retry_approval)
        self.assertFalse(decision.needs_approval)
        self.assertEqual(decision.reason, "command failed; retry without sandbox?")

    def test_retry_decision_strict_auto_review_requires_fresh_retry_approval(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: strict auto-review approval covers only the
        # sandboxed attempt; retrying without sandbox requires a fresh guardian
        # review and skips PermissionRequest hooks.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_FAILURE,
            already_approved=True,
            strict_auto_review=True,
            routes_to_guardian=False,
            tool_escalate_on_failure=True,
        )

        self.assertTrue(decision.should_retry)
        self.assertFalse(decision.bypass_retry_approval)
        self.assertTrue(decision.needs_approval)
        self.assertTrue(decision.guardian_review_id_required)
        self.assertFalse(decision.evaluate_permission_request_hooks)

    def test_retry_decision_network_policy_can_prompt_on_request(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: OnRequest may prompt for a network-policy sandbox
        # denial only when the default exec approval requirement would itself
        # need approval.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_REQUEST,
            already_approved=False,
            strict_auto_review=False,
            routes_to_guardian=True,
            tool_escalate_on_failure=True,
            network_approval_host="example.com",
            default_requirement=ExecApprovalRequirement.needs_approval(),
        )

        self.assertTrue(decision.should_retry)
        self.assertTrue(decision.needs_approval)
        self.assertTrue(decision.guardian_review_id_required)
        self.assertEqual(decision.reason, 'Network access to "example.com" is blocked by policy.')

    def test_retry_decision_network_policy_requires_default_prompt_requirement(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: the OnRequest network-policy exception is disabled
        # unless default_exec_approval_requirement yields NeedsApproval.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_REQUEST,
            already_approved=False,
            strict_auto_review=False,
            routes_to_guardian=True,
            tool_escalate_on_failure=True,
            network_approval_host="example.com",
            default_requirement=ExecApprovalRequirement.skip(),
        )

        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.error.type, "codex")

    def test_retry_decision_on_request_without_network_context_does_not_retry(self) -> None:
        # Rust source: codex-rs/core/src/tools/orchestrator.rs
        # Behavior anchor: OnRequest does not retry without sandbox for a plain
        # sandbox denial when no network approval context is present.
        decision = retry_decision_for_sandbox_denial(
            output=ExecToolCallOutput(exit_code=1),
            approval_policy=AskForApproval.ON_REQUEST,
            already_approved=False,
            strict_auto_review=False,
            routes_to_guardian=False,
            tool_escalate_on_failure=True,
        )

        self.assertFalse(decision.should_retry)

    def test_rejects_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            ApprovalStepDecision("skipped", "bad")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            approval_step_decision("skip")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            initial_attempt_plan(
                SandboxPermissions.USE_DEFAULT,
                ExecApprovalRequirement.skip(),
                "restricted",  # type: ignore[arg-type]
                False,
            )
        with self.assertRaises(TypeError):
            build_denial_reason_from_output(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
