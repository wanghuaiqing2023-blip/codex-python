import unittest

from pycodex.core import (
    ApprovalPreset,
    builtin_approval_presets,
    builtin_permission_profile_for_active_permission_profile,
)
from pycodex.protocol import (
    BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
    ActivePermissionProfile,
    AskForApproval,
    PermissionProfile,
)


class ApprovalPresetsTests(unittest.TestCase):
    def test_builtin_approval_presets_match_upstream_order_and_ids(self) -> None:
        presets = builtin_approval_presets()

        self.assertEqual(tuple(preset.id for preset in presets), ("read-only", "auto", "full-access"))
        self.assertTrue(all(isinstance(preset, ApprovalPreset) for preset in presets))

    def test_approval_preset_rejects_non_rust_shapes(self) -> None:
        active = ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_READ_ONLY)
        profile = PermissionProfile.read_only()

        with self.assertRaisesRegex(TypeError, "id must be a string"):
            ApprovalPreset(123, "Read Only", "desc", AskForApproval.ON_REQUEST, active, profile)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "label must be a string"):
            ApprovalPreset("read-only", 123, "desc", AskForApproval.ON_REQUEST, active, profile)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "description must be a string"):
            ApprovalPreset("read-only", "Read Only", 123, AskForApproval.ON_REQUEST, active, profile)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "approval must be an AskForApproval"):
            ApprovalPreset("read-only", "Read Only", "desc", object(), active, profile)  # type: ignore[arg-type]
        self.assertIs(
            ApprovalPreset("read-only", "Read Only", "desc", "on-request", active, profile).approval,
            AskForApproval.ON_REQUEST,
        )
        with self.assertRaisesRegex(TypeError, "active_permission_profile must be an ActivePermissionProfile"):
            ApprovalPreset("read-only", "Read Only", "desc", AskForApproval.ON_REQUEST, "read-only", profile)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "permission_profile must be a PermissionProfile"):
            ApprovalPreset("read-only", "Read Only", "desc", AskForApproval.ON_REQUEST, active, "read-only")  # type: ignore[arg-type]

    def test_read_only_preset_pairs_on_request_with_read_only_profile(self) -> None:
        preset = builtin_approval_presets()[0]

        self.assertEqual(preset.label, "Read Only")
        self.assertIn("Approval is required to edit files", preset.description)
        self.assertIs(preset.approval, AskForApproval.ON_REQUEST)
        self.assertEqual(
            preset.active_permission_profile,
            ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_READ_ONLY),
        )
        self.assertEqual(preset.permission_profile, PermissionProfile.read_only())

    def test_auto_preset_pairs_on_request_with_workspace_profile(self) -> None:
        preset = builtin_approval_presets()[1]

        self.assertEqual(preset.label, "Default")
        self.assertIn("Identical to Agent mode", preset.description)
        self.assertIs(preset.approval, AskForApproval.ON_REQUEST)
        self.assertEqual(
            preset.active_permission_profile,
            ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_WORKSPACE),
        )
        self.assertEqual(preset.permission_profile, PermissionProfile.workspace_write())

    def test_full_access_preset_pairs_never_with_disabled_profile(self) -> None:
        preset = builtin_approval_presets()[2]

        self.assertEqual(preset.label, "Full Access")
        self.assertIn("without asking for approval", preset.description)
        self.assertIs(preset.approval, AskForApproval.NEVER)
        self.assertEqual(
            preset.active_permission_profile,
            ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS),
        )
        self.assertEqual(preset.permission_profile, PermissionProfile.disabled())

    def test_builtin_permission_profile_for_active_permission_profile(self) -> None:
        self.assertEqual(
            builtin_permission_profile_for_active_permission_profile(
                ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_READ_ONLY)
            ),
            PermissionProfile.read_only(),
        )
        self.assertEqual(
            builtin_permission_profile_for_active_permission_profile(
                ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_WORKSPACE)
            ),
            PermissionProfile.workspace_write(),
        )
        self.assertEqual(
            builtin_permission_profile_for_active_permission_profile(
                ActivePermissionProfile.new(BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS)
            ),
            PermissionProfile.disabled(),
        )

    def test_extended_or_unknown_active_profile_has_no_builtin_permission_profile(self) -> None:
        self.assertIsNone(
            builtin_permission_profile_for_active_permission_profile(
                ActivePermissionProfile("custom", BUILT_IN_PERMISSION_PROFILE_WORKSPACE)
            )
        )
        self.assertIsNone(
            builtin_permission_profile_for_active_permission_profile(
                ActivePermissionProfile.new("custom")
            )
        )
        with self.assertRaisesRegex(TypeError, "active_permission_profile must be an ActivePermissionProfile"):
            builtin_permission_profile_for_active_permission_profile("read-only")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
