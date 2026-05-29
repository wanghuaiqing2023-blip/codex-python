import unittest

from pycodex.core import (
    ApprovalStepDecision,
    ExecApprovalRequirement,
    OrchestratorApprovalKind,
    ToolOrchestratorPlan,
    approval_step_decision,
    build_denial_reason_from_output,
    initial_attempt_plan,
    reject_if_not_approved,
    retry_decision_for_sandbox_denial,
)
from pycodex.protocol import (
    AskForApproval,
    ExecToolCallOutput,
    FileSystemSandboxPolicy,
    NetworkPolicyAmendment,
    NetworkPolicyRuleAction,
    ReviewDecision,
    SandboxPermissions,
)


class ToolOrchestratorTests(unittest.TestCase):
    def test_skip_requirement_only_prompts_under_strict_auto_review(self) -> None:
        skipped = approval_step_decision(ExecApprovalRequirement.skip())
        strict = approval_step_decision(ExecApprovalRequirement.skip(), strict_auto_review=True)

        self.assertEqual(skipped.kind, OrchestratorApprovalKind.SKIPPED)
        self.assertFalse(skipped.already_approved)
        self.assertFalse(skipped.evaluate_permission_request_hooks)
        self.assertEqual(strict.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(strict.already_approved)
        self.assertTrue(strict.guardian_review_id_required)
        self.assertFalse(strict.evaluate_permission_request_hooks)

    def test_needs_approval_routes_to_guardian_and_disables_hooks_for_strict_review(self) -> None:
        normal = approval_step_decision(ExecApprovalRequirement.needs_approval(), routes_to_guardian=True)
        strict = approval_step_decision(ExecApprovalRequirement.needs_approval(), strict_auto_review=True)

        self.assertEqual(normal.kind, OrchestratorApprovalKind.REQUESTED)
        self.assertTrue(normal.guardian_review_id_required)
        self.assertTrue(normal.evaluate_permission_request_hooks)
        self.assertFalse(strict.evaluate_permission_request_hooks)
        self.assertTrue(strict.guardian_review_id_required)

    def test_forbidden_requirement_returns_rejected_tool_error(self) -> None:
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

    def test_reject_if_not_approved_matches_rust_decisions(self) -> None:
        self.assertIsNone(reject_if_not_approved(ReviewDecision.approved()))
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
        self.assertEqual(reject_if_not_approved(ReviewDecision.timed_out()).message, "automated review timed out")

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

    def test_retry_decision_network_policy_can_prompt_on_request(self) -> None:
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

    def test_retry_decision_on_request_without_network_context_does_not_retry(self) -> None:
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
