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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: prompt_is_rejected_by_policy. Policy-rule prompts
        # use granular.rules while sandbox/escalation prompts use
        # granular.sandbox_approval; AskForApproval::Never rejects both.
        granular = GranularApprovalConfig(
            sandbox_approval=False,
            rules=False,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=True,
        )

        self.assertEqual(prompt_is_rejected_by_policy(AskForApproval.NEVER, False), PROMPT_CONFLICT_REASON)
        self.assertEqual(prompt_is_rejected_by_policy(AskForApproval.NEVER, True), PROMPT_CONFLICT_REASON)
        self.assertEqual(prompt_is_rejected_by_policy(granular, False), REJECT_SANDBOX_APPROVAL_REASON)
        self.assertEqual(prompt_is_rejected_by_policy(granular, True), REJECT_RULES_APPROVAL_REASON)
        self.assertIsNone(prompt_is_rejected_by_policy(AskForApproval.ON_FAILURE, False))
        self.assertIsNone(prompt_is_rejected_by_policy(AskForApproval.ON_REQUEST, True))
        self.assertIsNone(prompt_is_rejected_by_policy(AskForApproval.UNLESS_TRUSTED, True))
        self.assertIsNone(
            prompt_is_rejected_by_policy(
                GranularApprovalConfig(True, True, mcp_elicitations=True),
                True,
            )
        )
        self.assertIsNone(
            prompt_is_rejected_by_policy(
                GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=False,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                ),
                False,
            )
        )

    def test_commands_for_exec_policy_parses_plain_shell_wrappers(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: commands_for_exec_policy delegates shell -lc/-c
        # wrappers to plain-command parsing before exec-policy matching.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust tests: empty_bash_lc_script_falls_back_to_original_command and
        # whitespace_bash_lc_script_falls_back_to_original_command.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust tests: omits_auto_amendment_for_heredoc_fallback_prompts and
        # heredoc fallback prompt tests. The parsed command uses complex parsing
        # so auto-amendment suggestions are suppressed downstream.
        command = ["zsh", "-lc", "python3 <<'PY'\nprint('hello')\nPY"]

        self.assertEqual(
            commands_for_exec_policy(command),
            ExecPolicyCommands((("python3",),), True, ExecPolicyCommandOrigin.GENERIC),
        )

    def test_commands_for_intercepted_exec_policy_honors_shell_wrapper_parsing_flag(self):
        # Rust source: codex-rs/core/src/exec_policy.rs plus shell runtime
        # intercepted-command candidate parsing. This Python adapter keeps the
        # same exec-policy candidate shape while allowing tests to toggle shell
        # wrapper parsing.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: each parsed candidate command is rendered through
        # render_decision_for_unmatched_command before taking the strongest decision.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: multi-command exec-policy evaluation uses the strongest
        # decision so forbidden > prompt > allow.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: derive_requested_execpolicy_amendment_from_prefix_rule
        # filters empty and exact banned prefix-rule suggestions.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: banned prefix filtering is exact; extending a banned
        # prefix with a concrete command remains eligible.
        prefix_rule = ("python", "-c", "print('hi')")

        self.assertEqual(
            derive_requested_execpolicy_amendment_from_prefix_rule(prefix_rule),
            ExecPolicyAmendment.new(list(prefix_rule)),
        )

    def test_derive_requested_execpolicy_amendment_skips_policy_matches_and_partial_prefixes(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust behavior anchors: derive_requested_execpolicy_amendment_from_prefix_rule
        # and prefix_rule_would_approve_all_commands.
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
        self.assertTrue(
            prefix_rule_would_approve_all_commands(
                prefix_rule,
                (("cargo", "install", "ripgrep"), ("cargo", "install", "cargo-insta")),
            )
        )
        self.assertFalse(prefix_rule_would_approve_all_commands(prefix_rule, (("cargo", "build"),)))
        self.assertFalse(
            prefix_rule_would_approve_all_commands(
                prefix_rule,
                (("cargo", "install", "ripgrep"), ("rm", "-rf", "/tmp/codex")),
            )
        )

    def test_create_exec_approval_requirement_for_command_proposes_requested_prefix_rule(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: request_rule_uses_prefix_rule.
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

    def test_create_exec_approval_requirement_for_command_falls_back_when_prefix_rule_is_partial(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: request_rule_falls_back_when_prefix_rule_does_not_approve_all_commands.
        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "cargo install cargo-insta && rm -rf /tmp/codex"),
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.disabled(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(),
                sandbox_cwd=Path("/repo"),
                sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
                prefix_rule=("cargo", "install"),
            )
        )

        self.assertEqual(requirement.type, "needs_approval")
        self.assertEqual(
            requirement.proposed_execpolicy_amendment,
            ExecPolicyAmendment.new(["rm", "-rf", "/tmp/codex"]),
        )

    def test_create_exec_approval_requirement_for_command_honors_prompt_rule_reason(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchors: derive_prompt_reason and prompt-rule match precedence.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: match_exec_policy_rules_for_command parses shell
        # wrappers and returns Rust-shaped prefixRuleMatch payloads.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchors: derive_forbidden_reason and forbidden prefix-rule
        # justification rendering.
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
        self.assertEqual(
            derive_forbidden_reason(
                ("rm",),
                ({"prefixRuleMatch": {"matchedPrefix": ["rm"], "decision": "forbidden"}},),
            ),
            "`rm` rejected: policy forbids commands starting with `rm`",
        )

    def test_create_exec_approval_requirement_for_command_filters_banned_requested_prefix_and_heredoc(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchors: banned requested prefix suggestions and complex
        # shell parsing suppress auto-amendment suggestions.
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
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: create_exec_approval_requirement_for_command rejects
        # a fallback prompt when AskForApproval::Never disallows prompting.
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

    def test_create_exec_approval_requirement_for_command_rejects_policy_rule_prompt_when_never(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: exec_approval_requirement_respects_approval_policy.
        requirement = create_exec_approval_requirement_for_command(
            {
                "command": ("rm",),
                "approval_policy": AskForApproval.NEVER,
                "permission_profile": PermissionProfile.disabled(),
                "file_system_sandbox_policy": FileSystemSandboxPolicy.unrestricted(),
                "sandbox_cwd": Path("/repo"),
                "matched_rules": (
                    {
                        "prefixRuleMatch": {
                            "matchedPrefix": ["rm"],
                            "decision": "prompt",
                        }
                    },
                ),
            }
        )

        self.assertEqual(requirement.type, "forbidden")
        self.assertEqual(requirement.reason, PROMPT_CONFLICT_REASON)

    def test_create_exec_approval_requirement_for_command_rejects_mixed_policy_prompt_when_rules_disabled(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: mixed_rule_and_sandbox_prompt_rejects_when_granular_rules_are_disabled.
        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "git status && madeup-cmd"),
                approval_policy=GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=False,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                ),
                permission_profile=PermissionProfile.read_only(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_cwd=Path("/repo"),
                sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
                matched_rules=(
                    {
                        "prefixRuleMatch": {
                            "matchedPrefix": ["git"],
                            "decision": "prompt",
                        }
                    },
                ),
            )
        )

        self.assertEqual(requirement.type, "forbidden")
        self.assertEqual(requirement.reason, REJECT_RULES_APPROVAL_REASON)

    def test_create_exec_approval_requirement_for_command_policy_allow_does_not_make_sandbox_prompt_rule_prompt(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: create_exec_approval_requirement_for_command only
        # treats a prompt as rule-driven when a matched policy rule has
        # Decision::Prompt; allow rules beside a sandbox prompt still use the
        # sandbox approval gate.
        requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=("bash", "-lc", "git status && madeup-cmd"),
                approval_policy=GranularApprovalConfig(
                    sandbox_approval=True,
                    rules=False,
                    skill_approval=True,
                    request_permissions=True,
                    mcp_elicitations=True,
                ),
                permission_profile=PermissionProfile.read_only(),
                file_system_sandbox_policy=FileSystemSandboxPolicy.default(),
                sandbox_cwd=Path("/repo"),
                sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
                matched_rules=(
                    {
                        "prefixRuleMatch": {
                            "matchedPrefix": ["git"],
                            "decision": "allow",
                        }
                    },
                ),
            )
        )

        self.assertEqual(requirement.type, "needs_approval")
        self.assertIsNone(requirement.reason)

    @unittest.skipUnless(os.name == "nt", "PowerShell exec-policy parsing is Windows-specific upstream")
    def test_commands_for_exec_policy_parses_powershell_wrapper_on_windows(self):
        command = ["powershell.exe", "-NoProfile", "-Command", "echo blocked"]

        self.assertEqual(
            commands_for_exec_policy(command),
            ExecPolicyCommands((("echo", "blocked"),), False, ExecPolicyCommandOrigin.POWERSHELL),
        )

    def test_profile_is_managed_read_only_detects_windows_unsandboxed_read_only(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: profile_is_managed_read_only.
        read_only_profile = PermissionProfile.read_only()
        read_only_policy = read_only_profile.file_system_sandbox_policy()
        workspace_policy = FileSystemSandboxPolicy.workspace_write(())

        self.assertTrue(profile_is_managed_read_only(read_only_profile, read_only_policy, Path("/repo")))
        self.assertFalse(profile_is_managed_read_only(PermissionProfile.workspace_write(), workspace_policy, Path("/repo")))
        self.assertFalse(
            profile_is_managed_read_only(PermissionProfile.disabled(), FileSystemSandboxPolicy.unrestricted(), Path("/repo"))
        )

    def test_render_decision_for_known_safe_unmatched_command(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: render_decision_for_unmatched_command allows known-safe
        # unmatched commands under UnlessTrusted only when parsing was simple.
        self.assertIs(
            render_decision_for_unmatched_command(
                ["ls"],
                _context(approval_policy=AskForApproval.UNLESS_TRUSTED),
            ),
            Decision.ALLOW,
        )
        self.assertIs(
            render_decision_for_unmatched_command(
                ["ls"],
                _context(
                    approval_policy=AskForApproval.UNLESS_TRUSTED,
                    used_complex_parsing=True,
                ),
            ),
            Decision.PROMPT,
        )

    def test_render_decision_allows_non_dangerous_under_never_and_on_failure(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: unmatched non-dangerous commands are allowed for
        # Never and OnFailure, relying on sandbox protections.
        for policy in (AskForApproval.NEVER, AskForApproval.ON_FAILURE):
            with self.subTest(policy=policy):
                self.assertIs(
                    render_decision_for_unmatched_command(
                        ["cargo", "build"],
                        _context(
                            approval_policy=policy,
                            permission_profile=PermissionProfile.workspace_write(),
                            file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
                        ),
                    ),
                    Decision.ALLOW,
                )

    def test_render_decision_prompts_for_sandbox_override_under_on_request(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: unmatched_on_request_uses_split_filesystem_policy_for_escalation_prompts.
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

    def test_render_decision_granular_mirrors_on_request_for_unmatched_commands(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Rust test: unmatched_granular_policy_still_prompts_for_restricted_sandbox_escalation.
        granular = GranularApprovalConfig(
            sandbox_approval=True,
            rules=True,
            skill_approval=True,
            request_permissions=True,
            mcp_elicitations=True,
        )

        self.assertIs(
            render_decision_for_unmatched_command(
                ["python", "--version"],
                _context(
                    approval_policy=granular,
                    permission_profile=PermissionProfile.workspace_write(),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.workspace_write(()),
                    sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
                ),
            ),
            Decision.PROMPT,
        )
        self.assertIs(
            render_decision_for_unmatched_command(
                ["python", "--version"],
                _context(
                    approval_policy=granular,
                    permission_profile=PermissionProfile.disabled(),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(),
                ),
            ),
            Decision.ALLOW,
        )

    def test_render_decision_allows_unmatched_non_dangerous_in_unrestricted_on_request(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: OnRequest allows unmatched non-dangerous commands in
        # unrestricted or external sandbox environments.
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
        self.assertIs(
            render_decision_for_unmatched_command(
                ["python", "--version"],
                _context(
                    approval_policy=AskForApproval.ON_REQUEST,
                    permission_profile=PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.external_sandbox(),
                ),
            ),
            Decision.ALLOW,
        )

    def test_render_decision_for_dangerous_command(self):
        # Rust source: codex-rs/core/src/exec_policy.rs
        # Behavior anchor: dangerous unmatched commands prompt unless prompting
        # is disabled; explicit disabled/external sandbox profiles allow Never.
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
        self.assertIs(
            render_decision_for_unmatched_command(
                ["rm", "-rf", "/important/data"],
                _context(
                    approval_policy=AskForApproval.NEVER,
                    permission_profile=PermissionProfile.disabled(),
                    file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(),
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
