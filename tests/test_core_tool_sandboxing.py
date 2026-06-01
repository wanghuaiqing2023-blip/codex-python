import unittest
from pathlib import Path
from typing import Any

from pycodex.core import (
    ApprovalStore,
    ExecApprovalRequirement,
    HookToolName,
    PermissionRequestPayload,
    SandboxAttempt,
    SandboxOverride,
    ToolCtx,
    ToolError,
    default_exec_approval_requirement,
    managed_network_for_sandbox_permissions,
    sandbox_override_for_first_attempt,
    should_bypass_approval,
    wants_no_sandbox_approval,
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
    PermissionProfile,
    ReviewDecision,
    SandboxPermissions,
    ToolName,
    WindowsSandboxLevel,
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

    def test_permission_request_payload_rejects_non_rust_shapes(self) -> None:
        with self.assertRaises(TypeError):
            PermissionRequestPayload("Bash", {})  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PermissionRequestPayload(HookToolName.bash(), [])  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PermissionRequestPayload.bash(123)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            PermissionRequestPayload.bash("echo hi", 123)  # type: ignore[arg-type]

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
            ExecApprovalRequirement.skip(proposed_execpolicy_amendment=amendment).proposed_execpolicy_amendment_ref(),
            amendment,
        )
        self.assertEqual(
            ExecApprovalRequirement.needs_approval(proposed_execpolicy_amendment=amendment).proposed_amendment(),
            amendment,
        )
        self.assertIsNone(ExecApprovalRequirement.forbidden("no").proposed_amendment())

    def test_exec_approval_requirement_rejects_invalid_variant_shapes(self) -> None:
        with self.assertRaises(ValueError):
            ExecApprovalRequirement("future")
        with self.assertRaises(TypeError):
            ExecApprovalRequirement.skip(bypass_sandbox=1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ExecApprovalRequirement("skip", reason="why")
        with self.assertRaises(ValueError):
            ExecApprovalRequirement("needs_approval", bypass_sandbox=True)
        with self.assertRaises(TypeError):
            ExecApprovalRequirement("forbidden")
        with self.assertRaises(TypeError):
            ExecApprovalRequirement.skip(proposed_execpolicy_amendment=object())  # type: ignore[arg-type]

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

    def test_tool_ctx_matches_runtime_boundary_shape(self) -> None:
        ctx = ToolCtx(
            session=object(),
            turn=object(),
            call_id="call-1",
            tool_name=ToolName.plain("shell_command"),
        )

        self.assertEqual(ctx.call_id, "call-1")
        self.assertEqual(ctx.tool_name, ToolName.plain("shell_command"))
        with self.assertRaises(TypeError):
            ToolCtx(object(), object(), 1, ToolName.plain("x"))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            ToolCtx(object(), object(), "call", "x")  # type: ignore[arg-type]

    def test_tool_error_variants_reject_invalid_shapes(self) -> None:
        self.assertEqual(ToolError.rejected("no").message, "no")
        self.assertEqual(ToolError.codex({"kind": "fatal"}).error, {"kind": "fatal"})
        with self.assertRaises(TypeError):
            ToolError.rejected(123)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            ToolError("rejected", message="no", error=object())
        with self.assertRaises(ValueError):
            ToolError("codex", message="no", error=object())
        with self.assertRaises(ValueError):
            ToolError("future")

    def test_sandbox_attempt_preserves_runtime_options_and_uses_manager_transform(self) -> None:
        class _Manager:
            def __init__(self) -> None:
                self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

            def transform(self, *args: Any, **kwargs: Any) -> dict[str, str]:
                self.calls.append((args, kwargs))
                return {"ok": "true"}

        attempt = SandboxAttempt(
            sandbox="linux-seccomp",
            permissions=PermissionProfile.workspace_write(),
            enforce_managed_network=True,
            manager=_Manager(),
            sandbox_cwd="/repo",
            codex_linux_sandbox_exe="/usr/bin/codex-linux-sandbox",
            use_legacy_landlock=True,
            windows_sandbox_level=WindowsSandboxLevel.DISABLED,
            windows_sandbox_private_desktop=False,
        )
        result = attempt.env_for(["echo", "hi"])

        self.assertEqual(attempt.sandbox_cwd, Path("/repo"))
        self.assertEqual(attempt.codex_linux_sandbox_exe, Path("/usr/bin/codex-linux-sandbox"))
        self.assertEqual(result, {"ok": "true"})
        self.assertEqual(attempt.manager.calls, [( (["echo", "hi"], ), {})])

        with self.assertRaises(TypeError):
            SandboxAttempt(
                sandbox="none",
                permissions=object(),  # type: ignore[arg-type]
                enforce_managed_network=False,
                manager=object(),
                sandbox_cwd=Path("/repo"),
            )

        attempt_without_transform = SandboxAttempt(
            sandbox="linux-seccomp",
            permissions=PermissionProfile.workspace_write(),
            enforce_managed_network=True,
            manager=object(),
            sandbox_cwd="/repo",
        )
        with self.assertRaises(AttributeError):
            attempt_without_transform.env_for(["echo", "hi"])

    def test_should_bypass_approval_matches_appovable_default(self) -> None:
        self.assertTrue(should_bypass_approval(AskForApproval.ON_REQUEST, True))
        self.assertTrue(should_bypass_approval(AskForApproval.NEVER, False))
        self.assertFalse(should_bypass_approval(AskForApproval.ON_REQUEST, False))

    def test_wants_no_sandbox_approval_matches_appovable_default(self) -> None:
        self.assertTrue(wants_no_sandbox_approval(AskForApproval.ON_FAILURE))
        self.assertTrue(wants_no_sandbox_approval(AskForApproval.UNLESS_TRUSTED))
        self.assertFalse(wants_no_sandbox_approval(AskForApproval.NEVER))
        self.assertFalse(wants_no_sandbox_approval(AskForApproval.ON_REQUEST))
        self.assertTrue(
            wants_no_sandbox_approval(
                GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=True,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                )
            )
        )
        self.assertFalse(
            wants_no_sandbox_approval(
                GranularApprovalConfig(
                    sandbox_approval=False,
                    rules=True,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
