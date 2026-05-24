import unittest
from pathlib import Path

from pycodex.core import (
    CommandPrefixPolicy,
    PermissionsInstructions,
    PermissionsPromptConfig,
    approval_text,
    granular_prompt_intro_text,
    request_permissions_tool_prompt_section,
    sandbox_text,
    writable_roots_text,
)
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    ContentItem,
    GranularApprovalConfig,
    NetworkAccess,
    NetworkSandboxPolicy,
    PermissionProfile,
    ResponseItem,
    SandboxMode,
    WritableRoot,
    format_allow_prefixes,
)


class CorePermissionsInstructionsTests(unittest.TestCase):
    def test_renders_sandbox_mode_text(self):
        self.assertEqual(
            sandbox_text(SandboxMode.WORKSPACE_WRITE, NetworkAccess.RESTRICTED),
            "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `workspace-write`: The sandbox permits reading files, and editing files in `cwd` and `writable_roots`. Editing files in other directories requires approval. Network access is restricted.",
        )
        self.assertEqual(
            sandbox_text(SandboxMode.READ_ONLY, NetworkAccess.RESTRICTED),
            "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `read-only`: The sandbox only permits reading files. Network access is restricted.",
        )
        self.assertEqual(
            sandbox_text(SandboxMode.DANGER_FULL_ACCESS, NetworkAccess.ENABLED),
            "Filesystem sandboxing defines which files can be read or written. `sandbox_mode` is `danger-full-access`: No filesystem sandboxing - all commands are permitted. Network access is enabled.",
        )

    def test_builds_permissions_with_network_access_override(self):
        instructions = PermissionsInstructions.from_permissions_with_network(
            SandboxMode.WORKSPACE_WRITE,
            NetworkAccess.ENABLED,
            PermissionsPromptConfig(
                approval_policy=AskForApproval.ON_REQUEST,
                approvals_reviewer=ApprovalsReviewer.USER,
            ),
        )

        text = instructions.body()
        self.assertTrue(text.startswith("\nFilesystem sandboxing"))
        self.assertIn("Network access is enabled.", text)
        self.assertIn("How to request escalation", text)
        self.assertEqual(instructions.role(), "developer")
        self.assertEqual(
            instructions.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(instructions.render()),)),
        )

    def test_builds_permissions_from_profile(self):
        cwd = Path("/tmp")
        writable_root = cwd / "repo"
        permission_profile = PermissionProfile.workspace_write(
            (writable_root,),
            network=NetworkSandboxPolicy.ENABLED,
            exclude_tmpdir_env_var=True,
            exclude_slash_tmp=True,
        )

        instructions = PermissionsInstructions.from_permission_profile(
            permission_profile,
            AskForApproval.UNLESS_TRUSTED,
            ApprovalsReviewer.USER,
            None,
            cwd,
        )
        text = instructions.body()
        self.assertIn("`sandbox_mode` is `workspace-write`", text)
        self.assertIn("Network access is enabled.", text)
        self.assertIn(str(writable_root), text)

    def test_includes_approved_prefixes_for_on_request(self):
        policy = CommandPrefixPolicy.empty()
        policy.add_prefix_rule(("git", "pull"))

        text = approval_text(AskForApproval.ON_REQUEST, ApprovalsReviewer.USER, policy)

        self.assertIn("prefix_rule", text)
        self.assertIn("Approved command prefixes", text)
        self.assertIn('["git", "pull"]', text)

    def test_request_permissions_tool_sections(self):
        unless_trusted = approval_text(
            AskForApproval.UNLESS_TRUSTED,
            ApprovalsReviewer.USER,
            request_permissions_tool_enabled=True,
        )
        on_request = approval_text(
            AskForApproval.ON_REQUEST,
            ApprovalsReviewer.USER,
            exec_permission_approvals_enabled=True,
            request_permissions_tool_enabled=True,
        )

        self.assertIn("`approval_policy` is `unless-trusted`", unless_trusted)
        self.assertIn("# request_permissions Tool", unless_trusted)
        self.assertIn("with_additional_permissions", on_request)
        self.assertIn(request_permissions_tool_prompt_section(), on_request)

    def test_auto_review_approval_suffix(self):
        text = approval_text(AskForApproval.ON_REQUEST, ApprovalsReviewer.AUTO_REVIEW)

        self.assertIn("`approvals_reviewer` is `auto_review`", text)
        self.assertNotIn("`approvals_reviewer` is `guardian_subagent`", text)
        self.assertIn("materially safer alternative", text)
        self.assertNotIn("`approvals_reviewer` is `auto_review`", approval_text(AskForApproval.NEVER, ApprovalsReviewer.AUTO_REVIEW))

    def test_granular_policy_lists_prompted_and_rejected_categories(self):
        text = approval_text(
            GranularApprovalConfig(
                sandbox_approval=False,
                rules=True,
                skill_approval=False,
                request_permissions=True,
                mcp_elicitations=False,
            ),
            ApprovalsReviewer.USER,
            exec_permission_approvals_enabled=True,
            request_permissions_tool_enabled=False,
        )

        self.assertEqual(
            text,
            "\n\n".join(
                (
                    granular_prompt_intro_text(),
                    "These approval categories may still prompt the user when needed:\n- `rules`",
                    "These approval categories are automatically rejected instead of prompting the user:\n- `sandbox_approval`\n- `skill_approval`\n- `mcp_elicitations`",
                )
            ),
        )

    def test_granular_policy_includes_request_permissions_tool_only_when_allowed(self):
        allowed = approval_text(
            GranularApprovalConfig(
                sandbox_approval=True,
                rules=True,
                skill_approval=True,
                request_permissions=True,
                mcp_elicitations=True,
            ),
            ApprovalsReviewer.USER,
            exec_permission_approvals_enabled=True,
            request_permissions_tool_enabled=True,
        )
        rejected = approval_text(
            GranularApprovalConfig(
                sandbox_approval=True,
                rules=True,
                skill_approval=True,
                request_permissions=False,
                mcp_elicitations=True,
            ),
            ApprovalsReviewer.USER,
            exec_permission_approvals_enabled=True,
            request_permissions_tool_enabled=True,
        )

        self.assertIn("# request_permissions Tool", allowed)
        self.assertIn("- `request_permissions`", rejected)
        self.assertNotIn("# request_permissions Tool", rejected)

    def test_writable_roots_text_and_prefix_formatting(self):
        first = WritableRoot(Path("/a"))
        second = WritableRoot(Path("/b"))
        self.assertEqual(writable_roots_text((second, first)), f" The writable roots are `{first.root}`, `{second.root}`.")

        self.assertEqual(
            format_allow_prefixes(
                [
                    ["b", "zz"],
                    ["aa"],
                    ["b"],
                    ["a", "b", "c"],
                    ["a"],
                    ["b", "a"],
                ]
            ),
            '- ["a"]\n- ["b"]\n- ["aa"]\n- ["b", "a"]\n- ["b", "zz"]\n- ["a", "b", "c"]',
        )


if __name__ == "__main__":
    unittest.main()
