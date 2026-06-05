from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from pycodex.apply_patch import ApplyPatchAction, ApplyPatchFileChange
from pycodex.core.safety import (
    PATCH_REJECTED_OUTSIDE_PROJECT_REASON,
    PATCH_REJECTED_READ_ONLY_REASON,
    SafetyCheck,
    assess_patch_safety,
    is_write_patch_constrained_to_writable_paths,
)
from pycodex.core.sandbox_tags import SandboxType, get_platform_sandbox
from pycodex.protocol import (
    AskForApproval,
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    GranularApprovalConfig,
    NetworkSandboxPolicy,
    PermissionProfile,
    WindowsSandboxLevel,
)


class SafetyTests(unittest.TestCase):
    def test_empty_patch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)

            self.assertEqual(
                assess_patch_safety(
                    ApplyPatchAction({}),
                    AskForApproval.ON_REQUEST,
                    profile,
                    profile.file_system_sandbox_policy(),
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.reject("empty patch"),
            )

    def test_writable_roots_constraint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            parent = cwd.parent
            policy = FileSystemSandboxPolicy.workspace_write(
                exclude_tmpdir_env_var=True,
                exclude_slash_tmp=True,
            )

            self.assertTrue(
                is_write_patch_constrained_to_writable_paths(
                    ApplyPatchAction.new_add_for_test(cwd / "inner.txt", ""),
                    policy,
                    cwd,
                )
            )
            self.assertFalse(
                is_write_patch_constrained_to_writable_paths(
                    ApplyPatchAction.new_add_for_test(parent / "outside.txt", ""),
                    policy,
                    cwd,
                )
            )

            parent_policy = FileSystemSandboxPolicy.workspace_write(
                (parent,),
                exclude_tmpdir_env_var=True,
                exclude_slash_tmp=True,
            )
            self.assertTrue(
                is_write_patch_constrained_to_writable_paths(
                    ApplyPatchAction.new_add_for_test(parent / "outside.txt", ""),
                    parent_policy,
                    cwd,
                )
            )

    def test_update_move_path_must_also_be_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            parent = cwd.parent
            policy = FileSystemSandboxPolicy.workspace_write(
                exclude_tmpdir_env_var=True,
                exclude_slash_tmp=True,
            )
            action = ApplyPatchAction(
                {
                    cwd / "inside.txt": ApplyPatchFileChange.update(
                        "@@ -1 +1 @@\n-old\n+new\n",
                        move_path=parent / "outside.txt",
                    )
                }
            )

            self.assertFalse(is_write_patch_constrained_to_writable_paths(action, policy, cwd))

    def test_external_sandbox_auto_approves_inside_writable_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            action = ApplyPatchAction.new_add_for_test(cwd / "inner.txt", "")
            profile = PermissionProfile.external(NetworkSandboxPolicy.ENABLED)
            policy = FileSystemSandboxPolicy.external_sandbox()

            self.assertEqual(
                assess_patch_safety(
                    action,
                    AskForApproval.ON_REQUEST,
                    profile,
                    policy,
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.auto_approve(SandboxType.NONE),
            )

    def test_granular_sandbox_approval_false_rejects_out_of_root_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            parent = cwd.parent
            action = ApplyPatchAction.new_add_for_test(parent / "outside.txt", "")
            profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
            policy = profile.file_system_sandbox_policy()

            self.assertEqual(
                assess_patch_safety(
                    action,
                    GranularApprovalConfig(
                        sandbox_approval=False,
                        rules=True,
                        skill_approval=True,
                        request_permissions=True,
                        mcp_elicitations=True,
                    ),
                    profile,
                    policy,
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.reject(PATCH_REJECTED_OUTSIDE_PROJECT_REASON),
            )

    def test_read_only_policy_rejects_with_read_only_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            action = ApplyPatchAction.new_add_for_test(cwd / "inside.txt", "")
            profile = PermissionProfile.read_only()
            policy = profile.file_system_sandbox_policy()

            self.assertFalse(is_write_patch_constrained_to_writable_paths(action, policy, cwd))
            self.assertEqual(
                assess_patch_safety(
                    action,
                    AskForApproval.NEVER,
                    profile,
                    policy,
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.reject(PATCH_REJECTED_READ_ONLY_REASON),
            )

    def test_unless_trusted_asks_user_before_auto_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            profile = PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)

            self.assertEqual(
                assess_patch_safety(
                    ApplyPatchAction.new_add_for_test(cwd / "inside.txt", ""),
                    AskForApproval.UNLESS_TRUSTED,
                    profile,
                    FileSystemSandboxPolicy.external_sandbox(),
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.ask_user(),
            )

    def test_explicit_unreadable_paths_prevent_auto_approval_for_external_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            blocked = cwd / "blocked.txt"
            action = ApplyPatchAction.new_add_for_test(blocked, "")
            profile = PermissionProfile.external(NetworkSandboxPolicy.RESTRICTED)
            policy = FileSystemSandboxPolicy.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                    FileSystemSandboxEntry(
                        FileSystemPath.explicit_path(blocked),
                        FileSystemAccessMode.DENY,
                    ),
                )
            )

            self.assertFalse(is_write_patch_constrained_to_writable_paths(action, policy, cwd))
            self.assertEqual(
                assess_patch_safety(
                    action,
                    AskForApproval.ON_REQUEST,
                    profile,
                    policy,
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                ),
                SafetyCheck.ask_user(),
            )


    def test_safety_public_models_reject_implicit_coercions(self) -> None:
        with self.assertRaises(ValueError):
            SafetyCheck("unknown")
        with self.assertRaises(TypeError):
            SafetyCheck.auto_approve(SandboxType.NONE, user_explicitly_approved=1)
        with self.assertRaises(TypeError):
            SafetyCheck.reject(123)

        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
            action = ApplyPatchAction.new_add_for_test(cwd / "inside.txt", "")
            with self.assertRaises(TypeError):
                assess_patch_safety(
                    action,
                    "on-request",
                    profile,
                    profile.file_system_sandbox_policy(),
                    cwd,
                    WindowsSandboxLevel.DISABLED,
                )
            with self.assertRaises(TypeError):
                assess_patch_safety(
                    action,
                    AskForApproval.ON_REQUEST,
                    profile,
                    profile.file_system_sandbox_policy(),
                    123,
                    WindowsSandboxLevel.DISABLED,
                )
            with self.assertRaises(TypeError):
                is_write_patch_constrained_to_writable_paths(
                    action,
                    profile.file_system_sandbox_policy(),
                    123,
                )

    def test_managed_inside_patch_uses_platform_sandbox_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = Path(tmpdir)
            profile = PermissionProfile.workspace_write(exclude_tmpdir_env_var=True, exclude_slash_tmp=True)
            expected_sandbox = get_platform_sandbox(
                sys.platform == "win32"
                and WindowsSandboxLevel.RESTRICTED_TOKEN is not WindowsSandboxLevel.DISABLED
            )
            if expected_sandbox is None:
                self.skipTest("platform sandbox unavailable in this environment")

            self.assertEqual(
                assess_patch_safety(
                    ApplyPatchAction.new_add_for_test(cwd / "inside.txt", ""),
                    AskForApproval.ON_REQUEST,
                    profile,
                    profile.file_system_sandbox_policy(),
                    cwd,
                    WindowsSandboxLevel.RESTRICTED_TOKEN,
                ),
                SafetyCheck.auto_approve(expected_sandbox),
            )


if __name__ == "__main__":
    unittest.main()
