import unittest
from dataclasses import dataclass

from pycodex.core.context import (
    ContextualUserFragmentBase,
    FragmentRegistrationProxy,
    matches_marked_text,
)
from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


@dataclass(frozen=True)
class DemoFragment(ContextualUserFragmentBase):
    text: str

    @classmethod
    def role(cls) -> str:
        return "developer"

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<demo_fragment>", "</demo_fragment>"

    def body(self) -> str:
        return f"\n{self.text}\n"


@dataclass(frozen=True)
class UnmarkedFragment(ContextualUserFragmentBase):
    text: str

    def body(self) -> str:
        return self.text


class ContextFragmentTests(unittest.TestCase):
    # Rust source:
    # - codex/codex-rs/core/src/context/fragment.rs
    # Related Rust test anchors:
    # - codex/codex-rs/core/src/context/contextual_user_message_tests.rs

    def test_marked_fragment_render_and_response_items_match_rust_trait_defaults(self) -> None:
        fragment = DemoFragment("hello")

        self.assertEqual(fragment.render(), "<demo_fragment>\nhello\n</demo_fragment>")
        self.assertEqual(
            fragment.into_response_item(),
            ResponseItem.message("developer", (ContentItem.input_text(fragment.render()),)),
        )
        self.assertEqual(
            fragment.into_response_input_item(),
            ResponseInputItem.message("developer", (ContentItem.input_text(fragment.render()),)),
        )

    def test_matches_marked_text_trims_edges_and_ignores_marker_case(self) -> None:
        self.assertTrue(
            matches_marked_text(
                "<demo_fragment>",
                "</demo_fragment>",
                "  <DEMO_FRAGMENT>\nhello\n</DEMO_FRAGMENT>\n",
            )
        )
        self.assertFalse(matches_marked_text("<demo_fragment>", "</demo_fragment>", "<demo_fragment>hello"))
        self.assertFalse(matches_marked_text("", "</demo_fragment>", "</demo_fragment>"))
        self.assertFalse(matches_marked_text("<demo_fragment>", "", "<demo_fragment>"))

    def test_unmarked_fragment_renders_body_and_never_matches_arbitrary_text(self) -> None:
        fragment = UnmarkedFragment("plain body")

        self.assertEqual(fragment.render(), "plain body")
        self.assertFalse(UnmarkedFragment.matches_text("plain body"))

    def test_fragment_registration_proxy_matches_using_fragment_type(self) -> None:
        registration = FragmentRegistrationProxy.new(DemoFragment)

        self.assertTrue(registration.matches_text(" <demo_fragment>hello</demo_fragment> "))
        self.assertFalse(registration.matches_text("hello"))
        with self.assertRaises(TypeError):
            FragmentRegistrationProxy.new(object())
        with self.assertRaises(TypeError):
            registration.matches_text(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
