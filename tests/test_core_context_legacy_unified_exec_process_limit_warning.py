import unittest

from pycodex.core.context import LegacyUnifiedExecProcessLimitWarning
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class LegacyUnifiedExecProcessLimitWarningTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/legacy_unified_exec_process_limit_warning.rs

    def test_legacy_unified_exec_process_limit_warning_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = LegacyUnifiedExecProcessLimitWarning()
        old_warning = (
            "  Warning: The maximum number of unified exec processes you can keep open is "
            "4. Close one process before opening another.\n"
        )

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), "")
        self.assertEqual(fragment.render(), "")
        self.assertTrue(LegacyUnifiedExecProcessLimitWarning.matches_text(old_warning))
        self.assertFalse(
            LegacyUnifiedExecProcessLimitWarning.matches_text(
                "The maximum number of unified exec processes you can keep open is 4."
            )
        )
        self.assertFalse(
            LegacyUnifiedExecProcessLimitWarning.matches_text(
                "Warning: The maximum number of exec processes you can keep open is 4."
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
