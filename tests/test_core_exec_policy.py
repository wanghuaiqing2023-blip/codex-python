import os
import unittest
from pathlib import Path

from pycodex.execpolicy import (
    PROMPT_CONFLICT_REASON,
    REJECT_RULES_APPROVAL_REASON,
    REJECT_SANDBOX_APPROVAL_REASON,
    Decision,
    ExecApprovalRequest,
    ExecPolicyCommandOrigin,
    ExecPolicyCommands,
    ExecPolicyPrefixRule,
    UnmatchedCommandContext,
    commands_for_exec_policy,
    commands_for_intercepted_exec_policy,
    create_exec_approval_requirement_for_command,
    derive_forbidden_reason,
    derive_prompt_reason,
    derive_requested_execpolicy_amendment_from_prefix_rule,
    exec_approval_requirement_for_decision,
    match_exec_policy_rules_for_command,
    prefix_rule_would_approve_all_commands,
    profile_is_managed_read_only,
    prompt_is_rejected_by_policy,
    render_decision_for_unmatched_command,
    render_decisions_for_intercepted_exec_policy,
    render_intercepted_exec_policy_decision,
    strongest_decision,
)
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPermissions,
)


class CoreExecPolicyTests(unittest.TestCase):
    def test_prompt_is_rejected_by_policy_matches_upstream_reasons(self):
        granular = GranularApprovalConfig(
            sandbox_approval=False,
            rules=False,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=True,
        )

        self.assertEqual(prompt_is_rejected_by_policy(AskForApproval.NEVER, False), PROMPT_CONFLICT_REASON)
        self.assertEqual(prompt_is_rejected_by_policy(granular, False), REJECT_SANDBOX_APPROVAL_REASON)
        self.assertEqual(prompt_is_rejected_by_policy(granular, True), REJECT_RULES_APPROVAL_REASON)
        self.assertIsNone(prompt_is_rejected_by_policy(AskForApproval.ON_REQUEST, True))
        self.assertIsNone(
            prompt_is_rejected_by_policy(
                GranularApprovalConfig(True, True, mcp_elicitations=True),
                True,
            )
        )

    def test_commands_for_exec_policy_parses_plain_shell_wrappers(self):
        self.assertEqual(
            commands_for_exec_policy(["bash", "-lc", "cargo test -p codex-core"]),
            ExecPolicyCommands((("cargo", "test", "-p", "codex-core"),), False, ExecPolicyCommandOrigin.GENERIC),
        )
        self.assertEqual(
            commands_for_exec_policy(["zsh", "-lc", "cd repo && rg needle src | wc -l"]),
            ExecPolicyCommands(
                (("cd", "repo"), ("rg", "needle", "src"), ("wc", "-l")),
                False,
                ExecPolicyCommandOrigin.GENERIC,
            ),
        )

    def test_commands_for_exec_policy_falls_back_for_empty_shell_scripts(self):
        empty = ["bash", "-lc", ""]
        whitespace = ["bash", "-lc", "  \n\t  "]

        self.assertEqual(
            commands_for_exec_policy(empty),
            ExecPolicyCommands((tuple(empty),), False, ExecPolicyCommandOrigin.GENERIC),
        )
        self.assertEqual(
            commands_for_exec_policy(whitespace),
            ExecPolicyCommands((tuple(whitespace),), False, ExecPolicyCommandOrigin.GENERIC),
        )

    def test_commands_for_exec_policy_uses_heredoc_command_prefix(self):
        command = ["zsh", "-lc", "python3 <<'PY'\nprint('hello')\nPY"]

        self.assertEqual(
            commands_for_exec_policy(command),
            ExecPolicyCommands((("python3",),), True, ExecPolicyCommandOrigin.GENERIC),
        )

    def test_commands_for_intercepted_exec_policy_honors_shell_wrapper_parsing_flag(self):
        argv = ["not-bash", "-lc", "git status && pwd"]

        self.assertEqual(
            commands_for_intercepted_exec_policy(
                "/bin/bash",
                argv,
                enable_shell_wrapper_parsing=True,
            ),
            ExecPolicyCommands((("git", "status"), ("pwd",)), False, ExecPolicyCommandOrigin.GENERIC),
        )
        self.assertEqual(
            commands_for_intercepted_exec_policy(
                "/bin/bash",
                argv,
                enable_shell_wrapper_parsing=False,
            ),
            ExecPolicyCommands((("/bin/bash", "-lc", "git status && pwd"),), False, ExecPolicyCommandOrigin.GENERIC),
        )

    def test_intercepted_exec_policy_fallback_renders_each_candidate_command(self):
        self.assertEqual(
            render_decisions_for_intercepted_exec_policy(
                "/bin/bash",
                ["not-bash", "-lc", "ls && rm -rf /important/data"],
                _context(approval_policy=AskForApproval.ON_REQUEST),
                enable_shell_wrapper_parsing=True,
            ),
            (Decision.ALLOW, Decision.PROMPT),
        )

    def test_intercepted_exec_policy_fallback_uses_strongest_decision(self):
        self.assertIs(strongest_decision((Decision.ALLOW, Decision.PROMPT)), Decision.PROMPT)
        self.assertIs(strongest_decision(("allow", "forbidden", "prompt")), Decision.FORBIDDEN)
        with self.assertRaises(ValueError):
            strongest_decision(())

        self.assertIs(
            render_intercepted_exec_policy_decision(
                "/bin/bash",
                ["not-bash", "-lc", "ls && rm -rf /important/data"],
                _context(approval_policy=AskForApproval.ON_REQUEST),
                enable_shell_wrapper_parsing=True,
            ),
            Decision.PROMPT,
        )

    def test_exec_approval_requirement_for_decision_maps_policy_result(self):
        allowed = exec_approval_requirement_for_decision(Decision.ALLOW, forbidden_reason="blocked")
        prompt = exec_approval_requirement_for_decision("prompt", forbidden_reason="blocked", prompt_reason="needs review")
        forbidden = exec_approval_requirement_for_decision(Decision.FORBIDDEN, forbidden_reason="blocked")

        self.assertEqual(allowed.type, "skip")
        self.assertEqual(prompt.type, "needs_approval")
        self.assertEqual(prompt.reason, "needs review")
        self.assertEqual(forbidden.type, "forbidden")
        self.assertEqual(forbidden.reason, "blocked")

    def test_derive_requested_execpolicy_amendment_filters_empty_and_banned_prefix_rules(self):
        self.assertIsNone(derive_requested_execpolicy_amendment_from_prefix_rule(None))
        self.assertIsNone(derive_requested_execpolicy_amendment_from_prefix_rule(()))

        for prefix_rule in (
            ("python", "-c"),
            ("py",),
            ("py", "-3"),
            ("pythonw",),
            ("pyw",),
            ("pypy",),
            ("pypy3",),
            ("bash", "-lc"),
            ("sh", "-c"),
            ("sh", "-lc"),
            ("zsh", "-lc"),
            ("/bin/bash", "-lc"),
            ("/bin/zsh", "-lc"),
            ("pwsh",),
            ("pwsh", "-Command"),
            ("pwsh", "-c"),
            ("powershell",),
            ("powershell", "-Command"),
            ("powershell", "-c"),
            ("powershell.exe",),
            ("powershell.exe", "-Command"),
            ("powershell.exe", "-c"),
        ):
            with self.subTest(prefix_rule=prefix_rule):
                self.assertIsNone(derive_requested_execpolicy_amendment_from_prefix_rule(prefix_rule))

    def test_derive_requested_execpolicy_amendment_allows_non_exact_banned_match(self):
        prefix_rule = ("python", "-c", "print('hi')")

        self.assertEqual(
            derive_requested_execpolicy_amendment_from_prefix_rule(prefix_rule),
            ExecPolicyAmendment.new(list(prefix_rule)),
        )

    def test_derive_requested_execpolicy_amendment_skips_policy_matches_and_partial_prefixes(self):
        prefix_rule = ("cargo", "install")

        self.assertIsNone(
            derive_requested_execpolicy_amendment_from_prefix_rule(
                prefix_rule,
                matched_rules=({"prefixRuleMatch": {"matchedPrefix": ["cargo"], "decision": "prompt"}},),
            )
        )
        self.assertIsNone(
            derive_requested_execpolicy_amendment_from_prefix_rule(
                prefix_rule,
                commands=(("cargo", "install", "ripgrep"), ("git", "status")),
            )
        )
        self.assertEqual(
            derive_requested_execpolicy_amendment_from_prefix_rule(
                prefix_rule,
                commands=(("cargo", "install", "ripgrep"),),
            ),
            ExecPolicyAmendment.new(["cargo", "install"]),
        )
        self.assertTrue(prefix_rule_would_approve_all_commands(prefix_rule, (("cargo", "install", "ripgrep"),)))
        self.assertFalse(prefix_rule_would_approve_all_commands(prefix_rule, (("cargo", "build"),)))

    def test_create_exec_approval_requirement_for_command_proposes_requested_prefix_rule(self):
        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "cargo install ripgrep"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.read_only(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_cwd=Path("/repo"),
                prefix_rule=("cargo", "install"),
            )
        )

        self.assertEqual(requirement.type, "needs_approval")
        self.assertEqual(
            requirement.proposed_execpolicy_amendment,
            ExecPolicyAmendment.new(["cargo", "install"]),
        )

    def test_create_exec_approval_requirement_for_command_honors_prompt_rule_reason(self):
        matched_rules = (
            {
                "prefixRuleMatch": {
                    "matchedPrefix": ["cargo"],
                    "decision": "prompt",
                    "justification": "review toolchain changes",
                }
            },
            {
                "prefixRuleMatch": {
                    "matchedPrefix": ["cargo", "install"],
                    "decision": "prompt",
                }
            },
        )

        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "cargo install ripgrep"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.workspace_write(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
                sandbox_cwd=Path("/repo"),
                matched_rules=matched_rules,
            )
        )

        self.assertEqual(requirement.type, "needs_approval")
        self.assertEqual(requirement.reason, "`bash -lc cargo install ripgrep` requires approval by policy")
        self.assertIsNone(requirement.proposed_execpolicy_amendment)
        self.assertEqual(
            derive_prompt_reason(("bash", "-lc", "cargo install ripgrep"), matched_rules),
            "`bash -lc cargo install ripgrep` requires approval by policy",
        )

    def test_match_exec_policy_rules_for_command_matches_shell_wrapped_prefix_rules(self):
        rules = (
            ExecPolicyPrefixRule.new(["cargo", "install"], "prompt", "review installs"),
            ExecPolicyPrefixRule.new([["npm", "pnpm"], "publish"], "forbidden"),
        )

        cargo_matches = match_exec_policy_rules_for_command(("bash", "-lc", "cargo install ripgrep"), rules)
        npm_matches = match_exec_policy_rules_for_command(("bash", "-lc", "npm publish"), rules)

        self.assertEqual(
            cargo_matches,
            (
                {
                    "prefixRuleMatch": {
                        "matchedPrefix": ["cargo", "install"],
                        "decision": "prompt",
                        "justification": "review installs",
                    }
                },
            ),
        )
        self.assertEqual(
            npm_matches,
            (
                {
                    "prefixRuleMatch": {
                        "matchedPrefix": ["npm", "publish"],
                        "decision": "forbidden",
                    }
                },
            ),
        )
        self.assertEqual(match_exec_policy_rules_for_command(("bash", "-lc", "git status"), rules), ())

    def test_create_exec_approval_requirement_for_command_honors_forbidden_rule_reason(self):
        matched_rules = (
            {
                "prefixRuleMatch": {
                    "matchedPrefix": ["rm"],
                    "decision": "forbidden",
                    "justification": "destructive cleanup is blocked",
                }
            },
        )

        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "rm -rf /important/data"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.workspace_write(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
                sandbox_cwd=Path("/repo"),
                matched_rules=matched_rules,
            )
        )

        self.assertEqual(requirement.type, "forbidden")
        self.assertEqual(requirement.reason, "`bash -lc rm -rf /important/data` rejected: destructive cleanup is blocked")
        self.assertEqual(
            derive_forbidden_reason(("bash", "-lc", "rm -rf /important/data"), matched_rules),
            "`bash -lc rm -rf /important/data` rejected: destructive cleanup is blocked",
        )

    def test_create_exec_approval_requirement_for_command_filters_banned_requested_prefix_and_heredoc(self):
        banned = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("python", "-c", "print(1)"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.read_only(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_cwd=Path("/repo"),
                prefix_rule=("python", "-c"),
            )
        )
        heredoc = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("zsh", "-lc", "python3 <<'PY'\nprint('hello')\nPY"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.read_only(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_cwd=Path("/repo"),
                prefix_rule=("python3", "script.py"),
            )
        )

        self.assertEqual(banned.type, "needs_approval")
        self.assertEqual(
            banned.proposed_execpolicy_amendment,
            ExecPolicyAmendment.new(["python", "-c", "print(1)"]),
        )
        self.assertEqual(heredoc.type, "needs_approval")
        self.assertIsNone(heredoc.proposed_execpolicy_amendment)

    def test_create_exec_approval_requirement_for_command_honors_prompt_policy_rejection(self):
        requirement = create_exec_approval_requirement_for_command(
            {
                "command": ("rm", "-rf", "/important/data"),
                "approval_policy": AskForApproval.NEVER,
                "permission_profile": PermissionProfile.read_only(),
                "file_system_sandbox_policy": FileSystemSandboxPolicy.default(),
                "sandbox_cwd": Path("/repo"),
                "prefix_rule": ("rm",),
            }
        )

        self.assertEqual(requirement.type, "forbidden")
        self.assertEqual(requirement.reason, "`rm -rf /important/data` rejected: blocked by policy")

    @unittest.skipUnless(os.name == "nt", "PowerShell exec-policy parsing is Windows-specific upstream")
    def test_commands_for_exec_policy_parses_powershell_wrapper_on_windows(self):
        command = ["powershell.exe", "-NoProfile", "-Command", "echo blocked"]

        self.assertEqual(
            commands_for_exec_policy(command),
            ExecPolicyCommands((("echo", "blocked"),), False, ExecPolicyCommandOrigin.POWERSHELL),
        )

    def test_profile_is_managed_read_only_detects_windows_unsandboxed_read_only(self):
        read_only_profile = PermissionProfile.read_only()
        read_only_policy = read_only_profile.file_system_sandbox_policy()
        workspace_policy = FileSystemSandboxPolicy.workspace_write(())

        self.assertTrue(profile_is_managed_read_only(read_only_profile, read_only_policy, Path("/repo")))
        self.assertFalse(profile_is_managed_read_only(PermissionProfile.workspace_write(), workspace_policy, Path("/repo")))
        self.assertFalse(
            profile_is_managed_read_only(PermissionProfile.disabled(), FileSystemSandboxPolicy.unrestricted(), Path("/repo"))
        )

    def test_render_decision_for_known_safe_unmatched_command(self):
        self.assertIs(
            render_decision_for_unmatched_command(
                ["ls"],
                _context(approval_policy=AskForApproval.UNLESS_TRUSTED),
            ),
            Decision.ALLOW,
        )

    def test_render_decision_prompts_for_sandbox_override_under_on_request(self):
        self.assertIs(
            render_decision_for_unmatched_command(
                ["python", "--version"],
                _context(
                    approval_policy=AskForApproval.ON_REQUEST,
                    permission_profile=PermissionProfile.workspace_write(),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
                    sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
                ),
            ),
            Decision.PROMPT,
        )

    def test_render_decision_allows_unmatched_non_dangerous_in_unrestricted_on_request(self):
        self.assertIs(
            render_decision_for_unmatched_command(
                ["python", "--version"],
                _context(
                    approval_policy=AskForApproval.ON_REQUEST,
                    permission_profile=PermissionProfile.disabled(),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(),
                ),
            ),
            Decision.ALLOW,
        )

    def test_render_decision_for_dangerous_command(self):
        self.assertIs(
            render_decision_for_unmatched_command(
                ["rm", "-rf", "/important/data"],
                _context(approval_policy=AskForApproval.ON_REQUEST),
            ),
            Decision.PROMPT,
        )
        self.assertIs(
            render_decision_for_unmatched_command(
                ["rm", "-rf", "/important/data"],
                _context(approval_policy=AskForApproval.NEVER),
            ),
            Decision.FORBIDDEN,
        )
        self.assertIs(
            render_decision_for_unmatched_command(
                ["rm", "-rf", "/important/data"],
                _context(
                    approval_policy=AskForApproval.NEVER,
                    permission_profile=PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.external_sandbox(),
                ),
            ),
            Decision.ALLOW,
        )


def _context(
    *,
    approval_policy=AskForApproval.ON_REQUEST,
    permission_profile: PermissionProfile | None = None,
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None,
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT,
    used_complex_parsing: bool = False,
    command_origin: ExecPolicyCommandOrigin = ExecPolicyCommandOrigin.GENERIC,
) -> UnmatchedCommandContext:
    if permission_profile is None:
        permission_profile = PermissionProfile.read_only()
    if file_system_sandbox_policy is None:
        file_system_sandbox_policy = permission_profile.file_system_sandbox_policy()
    return UnmatchedCommandContext(
        approval_policy=approval_policy,
        permission_profile=permission_profile,
        file_system_sandbox_policy=file_system_sandbox_policy,
        sandbox_cwd=Path("/repo"),
        sandbox_permissions=sandbox_permissions,
        used_complex_parsing=used_complex_parsing,
        command_origin=command_origin,
    )


if __name__ == "__main__":
    unittest.main()
