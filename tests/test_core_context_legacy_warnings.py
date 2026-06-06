import unittest

from pycodex.core.context import (
    LegacyApplyPatchExecCommandWarning,
    LegacyModelMismatchWarning,
    LegacyUnifiedExecProcessLimitWarning,
    is_standard_contextual_user_text,
)


class CoreContextLegacyWarningsTests(unittest.TestCase):
    # Rust source contracts:
    # - codex/codex-rs/core/src/context/legacy_apply_patch_exec_command_warning.rs
    # - codex/codex-rs/core/src/context/legacy_model_mismatch_warning.rs
    # - codex/codex-rs/core/src/context/legacy_unified_exec_process_limit_warning.rs
    # - codex/codex-rs/core/src/context/fragment.rs

    def test_legacy_apply_patch_exec_command_warning_matches_only_full_shape(self):
        warning = (
            "Warning: apply_patch was requested via exec_command. "
            "Use the apply_patch tool instead of exec_command."
        )

        self.assertEqual(LegacyApplyPatchExecCommandWarning.role(), "user")
        self.assertEqual(LegacyApplyPatchExecCommandWarning().markers(), ("", ""))
        self.assertEqual(LegacyApplyPatchExecCommandWarning.type_markers(), ("", ""))
        self.assertEqual(LegacyApplyPatchExecCommandWarning().body(), "")
        self.assertEqual(LegacyApplyPatchExecCommandWarning().render(), "")
        self.assertTrue(LegacyApplyPatchExecCommandWarning.matches_text(f"\n{warning}\n"))
        self.assertTrue(is_standard_contextual_user_text(warning))
        self.assertFalse(
            LegacyApplyPatchExecCommandWarning.matches_text(
                "Warning: apply_patch was requested via exec_command."
            )
        )
        self.assertFalse(
            LegacyApplyPatchExecCommandWarning.matches_text(
                "Use the apply_patch tool instead of exec_command."
            )
        )

    def test_legacy_model_mismatch_warning_matches_trimmed_prefix(self):
        warning = (
            "Warning: Your account was flagged for potentially high-risk cyber activity "
            "and a legacy model warning was inserted."
        )

        self.assertEqual(LegacyModelMismatchWarning.role(), "user")
        self.assertEqual(LegacyModelMismatchWarning().markers(), ("", ""))
        self.assertEqual(LegacyModelMismatchWarning.type_markers(), ("", ""))
        self.assertEqual(LegacyModelMismatchWarning().body(), "")
        self.assertTrue(LegacyModelMismatchWarning.matches_text(f"  {warning}\n"))
        self.assertTrue(is_standard_contextual_user_text(warning))
        self.assertFalse(
            LegacyModelMismatchWarning.matches_text(
                "Warning: Your account was flagged for regular account activity"
            )
        )

    def test_legacy_unified_exec_process_limit_warning_matches_trimmed_prefix(self):
        warning = (
            "Warning: The maximum number of unified exec processes you can keep open is "
            "3. Close one before starting another."
        )

        self.assertEqual(LegacyUnifiedExecProcessLimitWarning.role(), "user")
        self.assertEqual(LegacyUnifiedExecProcessLimitWarning().markers(), ("", ""))
        self.assertEqual(LegacyUnifiedExecProcessLimitWarning.type_markers(), ("", ""))
        self.assertEqual(LegacyUnifiedExecProcessLimitWarning().body(), "")
        self.assertTrue(LegacyUnifiedExecProcessLimitWarning.matches_text(f"\t{warning} "))
        self.assertTrue(is_standard_contextual_user_text(warning))
        self.assertFalse(
            LegacyUnifiedExecProcessLimitWarning.matches_text(
                "Warning: The maximum number of regular exec processes you can keep open is 3."
            )
        )


if __name__ == "__main__":
    unittest.main()
