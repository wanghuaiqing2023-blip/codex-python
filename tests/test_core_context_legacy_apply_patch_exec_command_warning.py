import unittest

from pycodex.core.context import LegacyApplyPatchExecCommandWarning
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class LegacyApplyPatchExecCommandWarningTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/legacy_apply_patch_exec_command_warning.rs

    def test_legacy_apply_patch_warning_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = LegacyApplyPatchExecCommandWarning()
        old_warning = (
            "  Warning: apply_patch was requested via exec_command. "
            "Use the apply_patch tool instead of exec_command.\n"
        )

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), "")
        self.assertEqual(fragment.render(), "")
        self.assertTrue(LegacyApplyPatchExecCommandWarning.matches_text(old_warning))
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
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(""),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(""),)),
        )


if __name__ == "__main__":
    unittest.main()
