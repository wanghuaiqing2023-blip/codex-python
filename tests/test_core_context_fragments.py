import unittest

from pycodex.core.context import (
    AdditionalContextDeveloperFragment,
    AdditionalContextUserFragment,
    ADDITIONAL_CONTEXT_END_MARKER_SUFFIX,
    ADDITIONAL_CONTEXT_START_MARKER_PREFIX,
    CONTEXTUAL_USER_FRAGMENT_TYPES,
    MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS,
    is_standard_contextual_user_text,
)
from pycodex.core import (
    ADDITIONAL_CONTEXT_END_MARKER_SUFFIX as CORE_ADDITIONAL_CONTEXT_END_MARKER_SUFFIX,
    ADDITIONAL_CONTEXT_START_MARKER_PREFIX as CORE_ADDITIONAL_CONTEXT_START_MARKER_PREFIX,
    MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS as CORE_MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS,
)
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class AdditionalContextFragmentsTests(unittest.TestCase):
    # Rust source contract:
    # - codex/codex-rs/core/src/context/fragments.rs
    # - codex/codex-rs/core/src/context/contextual_user_message.rs

    def test_additional_context_user_fragment_matches_rust_contract(self) -> None:
        fragment = AdditionalContextUserFragment.new("browser_info", "tab one")
        expected_render = "<external_browser_info>tab one</external_browser_info>"

        self.assertEqual(fragment.role(), "user")
        self.assertEqual(fragment.markers(), ("<external_", ">"))
        self.assertEqual(fragment.type_markers(), ("<external_", ">"))
        self.assertEqual(fragment.body(), "browser_info>tab one</external_browser_info")
        self.assertEqual(fragment.render(), expected_render)
        self.assertTrue(AdditionalContextUserFragment.matches_text(expected_render))
        self.assertTrue(
            AdditionalContextUserFragment.matches_text(f"  {expected_render}\n")
        )
        self.assertFalse(
            AdditionalContextUserFragment.matches_text(
                "<EXTERNAL_browser_info>tab one</external_browser_info>"
            )
        )
        self.assertFalse(
            AdditionalContextUserFragment.matches_text(
                "<external_browser_info>tab one</external_terminal_info>"
            )
        )
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("user", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("user", (ContentItem.input_text(expected_render),)),
        )

    def test_additional_context_constants_match_rust_module_contract(self) -> None:
        self.assertEqual(ADDITIONAL_CONTEXT_START_MARKER_PREFIX, "<external_")
        self.assertEqual(ADDITIONAL_CONTEXT_END_MARKER_SUFFIX, ">")
        self.assertEqual(MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS, 1_000)
        self.assertEqual(CORE_ADDITIONAL_CONTEXT_START_MARKER_PREFIX, ADDITIONAL_CONTEXT_START_MARKER_PREFIX)
        self.assertEqual(CORE_ADDITIONAL_CONTEXT_END_MARKER_SUFFIX, ADDITIONAL_CONTEXT_END_MARKER_SUFFIX)
        self.assertEqual(CORE_MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS, MAX_ADDITIONAL_CONTEXT_VALUE_TOKENS)

    def test_additional_context_developer_fragment_matches_rust_contract(self) -> None:
        fragment = AdditionalContextDeveloperFragment.new("app", "state")
        expected_render = "<app>state</app>"

        self.assertEqual(fragment.role(), "developer")
        self.assertEqual(fragment.markers(), ("", ""))
        self.assertEqual(fragment.type_markers(), ("", ""))
        self.assertEqual(fragment.body(), expected_render)
        self.assertEqual(fragment.render(), expected_render)
        self.assertFalse(AdditionalContextDeveloperFragment.matches_text(expected_render))
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(expected_render),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(expected_render),)),
        )

    def test_additional_context_user_fragment_is_registered_for_standard_user_detection(self) -> None:
        self.assertIn(AdditionalContextUserFragment, CONTEXTUAL_USER_FRAGMENT_TYPES)
        self.assertTrue(
            is_standard_contextual_user_text(
                "<external_browser_info>tab one</external_browser_info>"
            )
        )

    def test_additional_context_values_are_truncated_with_token_budget(self) -> None:
        fragment = AdditionalContextUserFragment.new("browser_info", "x" * 5000)
        rendered = fragment.render()

        self.assertIn("tokens truncated", rendered)
        self.assertTrue(rendered.startswith("<external_browser_info>"))
        self.assertTrue(rendered.endswith("</external_browser_info>"))


if __name__ == "__main__":
    unittest.main()
