import unittest

from pycodex.core.context import ApprovedCommandPrefixSaved
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class ApprovedCommandPrefixSavedTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/approved_command_prefix_saved.rs

    def test_approved_command_prefix_saved_matches_rust_contextual_fragment_contract(
        self,
    ) -> None:
        fragment = ApprovedCommandPrefixSaved.new("git status\npython -m pytest")
        expected_body = "Approved command prefix saved:\ngit status\npython -m pytest"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), expected_body)
        self.assertEqual(fragment.render(), expected_body)
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_body),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_body),)),
        )


if __name__ == "__main__":
    unittest.main()
