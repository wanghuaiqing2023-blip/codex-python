import unittest

from pycodex.core.context import HookAdditionalContext, is_standard_contextual_user_text
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class HookAdditionalContextTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/hook_additional_context.rs

    def test_hook_additional_context_empty_markers_do_not_match_arbitrary_text(self) -> None:
        text = "hook supplied this context"

        self.assertFalse(HookAdditionalContext.matches_text(text))
        self.assertFalse(is_standard_contextual_user_text(text))

    def test_hook_additional_context_matches_rust_contextual_fragment_contract(self) -> None:
        fragment = HookAdditionalContext.new("hook supplied this context")
        expected_body = "hook supplied this context"

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
