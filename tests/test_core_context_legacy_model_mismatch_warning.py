import unittest

from pycodex.core.context import LegacyModelMismatchWarning
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class LegacyModelMismatchWarningTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/legacy_model_mismatch_warning.rs

    def test_legacy_model_mismatch_warning_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = LegacyModelMismatchWarning()
        old_warning = (
            "  Warning: Your account was flagged for potentially high-risk cyber activity "
            "and this request was routed to gpt-5.2 as a fallback.\n"
        )

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), "")
        self.assertEqual(fragment.render(), "")
        self.assertTrue(LegacyModelMismatchWarning.matches_text(old_warning))
        self.assertFalse(
            LegacyModelMismatchWarning.matches_text(
                "Your account was flagged for potentially high-risk cyber activity"
            )
        )
        self.assertFalse(
            LegacyModelMismatchWarning.matches_text(
                "Warning: Your account was flagged for high-risk cyber activity"
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
