import unittest
from pathlib import Path

from pycodex.core.guardian.approval_request import (
    GuardianApprovalRequest,
    GuardianMcpAnnotations,
    GuardianNetworkAccessTrigger,
    format_guardian_action_pretty,
    guardian_approval_request_to_json,
    guardian_assessment_action,
    guardian_request_target_item_id,
    guardian_request_turn_id,
    guardian_reviewed_action,
)
from pycodex.protocol import NetworkApprovalProtocol, SandboxPermissions
from pycodex.protocol.request_permissions import RequestPermissionProfile


class GuardianApprovalRequestTests(unittest.TestCase):
    # Rust source:
    # - codex/codex-rs/core/src/guardian/approval_request.rs
    # - codex/codex-rs/core/src/guardian/tests.rs

    def test_shell_and_exec_command_json_match_rust_action_shapes(self) -> None:
        shell = GuardianApprovalRequest.shell(
            id="shell-1",
            command=("git", "push"),
            cwd=Path("/repo"),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
            justification="Need to push the reviewed docs fix.",
        )
        exec_command = GuardianApprovalRequest.exec_command(
            id="exec-1",
            command=("pwd",),
            cwd=Path("/repo"),
            sandbox_permissions=SandboxPermissions.REQUIRE_ESCALATED,
            tty=True,
        )

        self.assertEqual(
            guardian_approval_request_to_json(shell),
            {
                "tool": "shell",
                "command": ["git", "push"],
                "cwd": "/repo",
                "sandbox_permissions": "use_default",
                "justification": "Need to push the reviewed docs fix.",
            },
        )
        self.assertEqual(
            guardian_approval_request_to_json(exec_command),
            {
                "tool": "exec_command",
                "command": ["pwd"],
                "cwd": "/repo",
                "sandbox_permissions": "require_escalated",
                "tty": True,
            },
        )

    def test_apply_patch_json_and_assessment_redacts_patch_text(self) -> None:
        action = GuardianApprovalRequest.apply_patch(
            id="patch-1",
            cwd=Path("/tmp"),
            files=(Path("/tmp/guardian.txt"),),
            patch="*** Begin Patch\n*** Update File: guardian.txt\n@@\n+secret\n*** End Patch",
        )

        self.assertEqual(
            guardian_approval_request_to_json(action),
            {
                "tool": "apply_patch",
                "cwd": "/tmp",
                "files": ["/tmp/guardian.txt"],
                "patch": "*** Begin Patch\n*** Update File: guardian.txt\n@@\n+secret\n*** End Patch",
            },
        )
        self.assertEqual(
            guardian_assessment_action(action),
            {
                "type": "apply_patch",
                "cwd": "/tmp",
                "files": ["/tmp/guardian.txt"],
            },
        )

    def test_network_access_json_renders_trigger_with_camel_case_fields(self) -> None:
        trigger = GuardianNetworkAccessTrigger(
            "call-1",
            "shell",
            ("curl", "https://example.com"),
            Path("/repo"),
            SandboxPermissions.USE_DEFAULT,
            justification="Fetch the release metadata.",
        )
        action = GuardianApprovalRequest.network_access(
            id="network-1",
            turn_id="turn-1",
            target="https://example.com:443",
            host="example.com",
            protocol=NetworkApprovalProtocol.HTTPS,
            port=443,
            trigger=trigger,
        )

        self.assertEqual(
            guardian_approval_request_to_json(action),
            {
                "tool": "network_access",
                "target": "https://example.com:443",
                "host": "example.com",
                "protocol": "https",
                "port": 443,
                "trigger": {
                    "callId": "call-1",
                    "toolName": "shell",
                    "command": ["curl", "https://example.com"],
                    "cwd": "/repo",
                    "sandboxPermissions": "use_default",
                    "justification": "Fetch the release metadata.",
                },
            },
        )

    def test_target_item_and_turn_id_follow_rust_network_access_rules(self) -> None:
        network_access = GuardianApprovalRequest.network_access(
            id="network-1",
            turn_id="owner-turn",
            target="https://example.com:443",
            host="example.com",
            protocol="https",
            port=443,
        )
        apply_patch = GuardianApprovalRequest.apply_patch(
            id="patch-1",
            cwd=Path("/tmp"),
            files=(Path("/tmp/guardian.txt"),),
            patch="patch",
        )

        self.assertIsNone(guardian_request_target_item_id(network_access))
        self.assertEqual(guardian_request_target_item_id(apply_patch), "patch-1")
        self.assertEqual(guardian_request_turn_id(network_access, "fallback-turn"), "owner-turn")
        self.assertEqual(guardian_request_turn_id(apply_patch, "fallback-turn"), "fallback-turn")

    def test_assessment_and_reviewed_actions_match_rust_tagged_shapes(self) -> None:
        shell = GuardianApprovalRequest.shell(
            id="shell-1",
            command=("git", "push"),
            cwd=Path("/repo"),
            sandbox_permissions=SandboxPermissions.USE_DEFAULT,
        )
        request_permissions = GuardianApprovalRequest.request_permissions(
            id="perm-1",
            turn_id="turn-1",
            reason="Need network access.",
            permissions=RequestPermissionProfile(),
        )

        self.assertEqual(
            guardian_assessment_action(shell),
            {
                "type": "command",
                "source": "shell",
                "command": "git push",
                "cwd": "/repo",
            },
        )
        self.assertEqual(
            guardian_reviewed_action(shell),
            {
                "type": "shell",
                "sandbox_permissions": "use_default",
                "additional_permissions": None,
            },
        )
        self.assertEqual(
            guardian_approval_request_to_json(request_permissions),
            {
                "tool": "request_permissions",
                "turn_id": "turn-1",
                "permissions": {},
                "reason": "Need network access.",
            },
        )
        self.assertEqual(
            guardian_assessment_action(request_permissions),
            {
                "type": "request_permissions",
                "reason": "Need network access.",
                "permissions": {},
            },
        )

    def test_mcp_tool_call_shape_is_available_as_deferred_compatibility_surface(self) -> None:
        action = GuardianApprovalRequest.mcp_tool_call(
            id="call-1",
            server="mcp_server",
            tool_name="browser_navigate",
            arguments={"url": "https://example.com"},
            connector_name="Playwright",
            tool_title="Navigate",
            annotations=GuardianMcpAnnotations(destructive_hint=True, read_only_hint=False),
        )

        self.assertEqual(
            guardian_approval_request_to_json(action),
            {
                "tool": "mcp_tool_call",
                "server": "mcp_server",
                "tool_name": "browser_navigate",
                "arguments": {"url": "https://example.com"},
                "connector_name": "Playwright",
                "tool_title": "Navigate",
                "annotations": {
                    "destructive_hint": True,
                    "read_only_hint": False,
                },
            },
        )

    def test_pretty_format_truncates_large_string_fields(self) -> None:
        action = GuardianApprovalRequest.apply_patch(
            id="patch-1",
            cwd=Path("/tmp"),
            files=(),
            patch="line\n" * 100_000,
        )

        rendered = format_guardian_action_pretty(action)

        self.assertIn('"tool": "apply_patch"', rendered.text)
        self.assertIn('<truncated omitted_approx_tokens=', rendered.text)
        self.assertTrue(rendered.truncated)
        self.assertLess(len(rendered.text), len("line\n" * 100_000))


if __name__ == "__main__":
    unittest.main()
