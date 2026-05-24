import unittest

from pycodex.core import (
    ApprovalStore,
    ExecApprovalRequirement,
    HookToolName,
    PermissionRequestPayload,
    SandboxOverride,
    default_exec_approval_requirement,
    managed_network_for_sandbox_permissions,
    sandbox_override_for_first_attempt,
    with_cached_approval,
)
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    ReviewDecision,
    SandboxPermissions,
)


class ToolSandboxingTests(unittest.TestCase):
    def test_bash_permission_request_payload_omits_missing_description(self) -> None:
        self.assertEqual(
            PermissionRequestPayload.bash("echo hi"),
            PermissionRequestPayload(tool_name=HookToolName.bash(), tool_input={"command": "echo hi"}),
        )

    def test_bash_permission_request_payload_includes_description_when_present(self) -> None:
        self.assertEqual(
            PermissionRequestPayload.bash("echo hi", "network-access example.com"),
            PermissionRequestPayload(
                tool_name=HookToolName.bash(),
                tool_input={
                    "command": "echo hi",
                    "description": "network-access example.com",
                },
            ),
        )

    def test_external_sandbox_skips_exec_approval_on_request(self) -> None:
        self.assertEqual(
            default_exec_approval_requirement(
                AskForApproval.ON_REQUEST,
                FileSystemSandboxPolicy.external_sandbox(),
            ),
            ExecApprovalRequirement.skip(),
        )

    def test_restricted_sandbox_requires_exec_approval_on_request(self) -> None:
        self.assertEqual(
            default_exec_approval_requirement(
                AskForApproval.ON_REQUEST,
                FileSystemSandboxPolicy.default(),
            ),
            ExecApprovalRequirement.needs_approval(),
        )

    def test_default_exec_approval_requirement_rejects_sandbox_prompt_when_granular_disables_it(self) -> None:
        policy = GranularApprovalConfig(
            sandbox_approval=False,
            rules=True,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=True,
        )

        self.assertEqual(
            default_exec_approval_requirement(policy, FileSystemSandboxPolicy.default()),
            ExecApprovalRequirement.forbidden("approval policy disallowed sandbox approval prompt"),
        )

    def test_default_exec_approval_requirement_keeps_prompt_when_granular_allows_sandbox_approval(self) -> None:
        policy = GranularApprovalConfig(
            sandbox_approval=True,
            rules=False,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=False,
        )

        self.assertEqual(
            default_exec_approval_requirement(policy, FileSystemSandboxPolicy.default()),
            ExecApprovalRequirement.needs_approval(),
        )

    def test_never_and_on_failure_skip_default_exec_approval(self) -> None:
        for policy in (AskForApproval.NEVER, AskForApproval.ON_FAILURE):
            with self.subTest(policy=policy):
                self.assertEqual(
                    default_exec_approval_requirement(policy, FileSystemSandboxPolicy.default()),
                    ExecApprovalRequirement.skip(),
                )

    def test_unless_trusted_always_requires_default_exec_approval(self) -> None:
        self.assertEqual(
            default_exec_approval_requirement(
                AskForApproval.UNLESS_TRUSTED,
                FileSystemSandboxPolicy.unrestricted(),
            ),
            ExecApprovalRequirement.needs_approval(),
        )

    def test_additional_permissions_allow_bypass_sandbox_first_attempt_when_execpolicy_skips(self) -> None:
        self.assertEqual(
            sandbox_override_for_first_attempt(
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                ExecApprovalRequirement.skip(bypass_sandbox=True),
                FileSystemSandboxPolicy.default(),
            ),
            SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT,
        )

    def test_guardian_bypasses_sandbox_for_explicit_escalation_on_first_attempt(self) -> None:
        self.assertEqual(
            sandbox_override_for_first_attempt(
                SandboxPermissions.REQUIRE_ESCALATED,
                ExecApprovalRequirement.skip(),
                FileSystemSandboxPolicy.default(),
            ),
            SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT,
        )

    def test_deny_read_blocks_explicit_escalation_but_preserves_policy_bypass(self) -> None:
        file_system_policy = FileSystemSandboxPolicy.restricted(
            (
                FileSystemSandboxEntry(
                    FileSystemPath.glob_pattern("**/*.env"),
                    FileSystemAccessMode.DENY,
                ),
            )
        )

        self.assertEqual(
            sandbox_override_for_first_attempt(
                SandboxPermissions.REQUIRE_ESCALATED,
                ExecApprovalRequirement.skip(),
                file_system_policy,
            ),
            SandboxOverride.NO_OVERRIDE,
        )
        self.assertEqual(
            sandbox_override_for_first_attempt(
                SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS,
                ExecApprovalRequirement.skip(bypass_sandbox=True),
                file_system_policy,
            ),
            SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT,
        )

    def test_exec_approval_requirement_exposes_proposed_amendment_for_skip_and_prompt(self) -> None:
        amendment = ExecPolicyAmendment.new(["git", "status"])
        self.assertEqual(
            ExecApprovalRequirement.skip(proposed_execpolicy_amendment=amendment).proposed_amendment(),
            amendment,
        )
        self.assertEqual(
            ExecApprovalRequirement.needs_approval(proposed_execpolicy_amendment=amendment).proposed_amendment(),
            amendment,
        )
        self.assertIsNone(ExecApprovalRequirement.forbidden("no").proposed_amendment())

    def test_cached_approval_skips_fetch_only_when_all_keys_are_approved_for_session(self) -> None:
        store = ApprovalStore()
        calls: list[str] = []

        def fetch() -> ReviewDecision:
            calls.append("fetch")
            return ReviewDecision.approved_for_session()

        self.assertEqual(
            with_cached_approval(store, [{"path": "a.py"}, {"path": "b.py"}], fetch),
            ReviewDecision.approved_for_session(),
        )
        self.assertEqual(calls, ["fetch"])
        self.assertEqual(
            with_cached_approval(store, [{"path": "a.py"}], fetch),
            ReviewDecision.approved_for_session(),
        )
        self.assertEqual(calls, ["fetch"])

    def test_cached_approval_empty_keys_and_denials_do_not_cache(self) -> None:
        store = ApprovalStore()
        calls: list[str] = []

        def fetch_denied() -> ReviewDecision:
            calls.append("denied")
            return ReviewDecision.denied()

        def fetch_approved() -> ReviewDecision:
            calls.append("approved")
            return ReviewDecision.approved()

        self.assertEqual(with_cached_approval(store, [], fetch_approved), ReviewDecision.approved())
        self.assertEqual(with_cached_approval(store, ["apply.patch"], fetch_denied), ReviewDecision.denied())
        self.assertEqual(with_cached_approval(store, ["apply.patch"], fetch_denied), ReviewDecision.denied())
        self.assertEqual(calls, ["approved", "denied", "denied"])

    def test_managed_network_is_removed_for_explicit_escalation_only(self) -> None:
        network = object()
        self.assertIs(
            managed_network_for_sandbox_permissions(network, SandboxPermissions.USE_DEFAULT),
            network,
        )
        self.assertIs(
            managed_network_for_sandbox_permissions(network, SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS),
            network,
        )
        self.assertIsNone(
            managed_network_for_sandbox_permissions(network, SandboxPermissions.REQUIRE_ESCALATED)
        )


if __name__ == "__main__":
    unittest.main()
