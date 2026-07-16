'''Parity tests for codex-core::context::fragment.'''

from dataclasses import dataclass

from pycodex.core.context.fragment import ContextualUserFragmentBase, FragmentRegistrationProxy, matches_marked_text


@dataclass(frozen=True)
class ExampleFragment(ContextualUserFragmentBase):
    value: str

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return '<example>', '</example>'

    def body(self) -> str:
        return self.value


def test_marked_text_matching_uses_ascii_case_insensitive_trimmed_markers() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/fragment.rs::matches_marked_text
    # Contract: context.fragment.marked_text_matching
    assert matches_marked_text('<example>', '</example>', '  <EXAMPLE>value</EXAMPLE>\n')
    assert not matches_marked_text('<example>', '</example>', '<example>value</different>')
    assert not matches_marked_text('', '</example>', '<example>value</example>')


def test_fragment_renders_exact_markers_and_projects_user_input_item() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/fragment.rs::ContextualUserFragment
    # Contract: context.fragment.render_and_response_projection
    fragment = ExampleFragment('body')

    assert fragment.render() == '<example>body</example>'
    assert fragment.into_response_input_item().role == 'user'
    assert fragment.into_response_input_item().content[0].text == '<example>body</example>'


def test_fragment_proxy_matches_without_constructing_a_payload() -> None:
    # Rust crate: codex-core
    # Rust module: src/context/fragment.rs::FragmentRegistrationProxy
    # Contract: context.fragment.type_erased_registration
    registration = FragmentRegistrationProxy.new(ExampleFragment)

    assert registration.matches_text('<example>payload</example>')
    assert not registration.matches_text('unrelated')
