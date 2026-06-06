from __future__ import annotations

import unittest

from pycodex.utils.template import (
    Template,
    TemplateError,
    TemplateParseError,
    TemplateParseErrorKind,
    TemplateRenderError,
    TemplateRenderErrorKind,
    render,
)


class TemplateTests(unittest.TestCase):
    def test_render_replaces_placeholders_with_and_without_whitespace(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust crate: codex-utils-template
        # Rust test: tests::render_replaces_placeholders_with_and_without_whitespace
        rendered = render(
            "Hello, {{ name }}. You are in {{place}}. {{ name }} is repeated.",
            (("name", "Codex"), ("place", "codex-rs")),
        )

        self.assertEqual(rendered, "Hello, Codex. You are in codex-rs. Codex is repeated.")

    def test_parsed_templates_can_be_reused(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::parsed_templates_can_be_reused
        template = Template.parse("{{greeting}}, {{ name }}!")

        self.assertEqual(
            template.render((("greeting", "Hello"), ("name", "Codex"))),
            "Hello, Codex!",
        )
        self.assertEqual(
            template.render((("greeting", "Hi"), ("name", "builder"))),
            "Hi, builder!",
        )

    def test_placeholders_are_sorted_and_unique(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::placeholders_are_sorted_and_unique
        template = Template.parse("{{ b }} {{ a }} {{ b }}")

        self.assertEqual(template.placeholders(), ("a", "b"))

    def test_render_supports_multiline_templates_and_adjacent_placeholders(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_supports_multiline_templates_and_adjacent_placeholders
        rendered = render(
            "Line 1: {{first}}{{second}}\nLine 2: {{ third }}",
            (("first", "A"), ("second", "B"), ("third", "C")),
        )

        self.assertEqual(rendered, "Line 1: AB\nLine 2: C")

    def test_render_supports_literal_delimiter_escapes(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_supports_literal_delimiter_escapes
        rendered = render(
            "literal open: {{{{, literal close: }}}}, value: {{ name }}",
            (("name", "Codex"),),
        )

        self.assertEqual(rendered, "literal open: {{, literal close: }}, value: Codex")

    def test_parse_errors_when_placeholder_is_empty(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::parse_errors_when_placeholder_is_empty
        with self.assertRaises(TemplateParseError) as captured:
            Template.parse("Hello, {{   }}.")

        self.assertEqual(captured.exception, TemplateParseError(TemplateParseErrorKind.EMPTY_PLACEHOLDER, 7))
        self.assertEqual(str(captured.exception), "template placeholder at byte 7 is empty")

    def test_parse_errors_when_placeholder_is_unterminated(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::parse_errors_when_placeholder_is_unterminated
        with self.assertRaises(TemplateParseError) as captured:
            Template.parse("Hello, {{ name.")

        self.assertEqual(captured.exception, TemplateParseError(TemplateParseErrorKind.UNTERMINATED_PLACEHOLDER, 7))
        self.assertEqual(str(captured.exception), "template placeholder starting at byte 7 is missing `}}`")

    def test_parse_errors_when_placeholder_is_nested(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::parse_errors_when_placeholder_is_nested
        with self.assertRaises(TemplateParseError) as captured:
            Template.parse("Hello, {{ outer {{ inner }} }}.")

        self.assertEqual(captured.exception, TemplateParseError(TemplateParseErrorKind.NESTED_PLACEHOLDER, 7))
        self.assertEqual(str(captured.exception), "template placeholder starting at byte 7 contains a nested `{{`")

    def test_parse_errors_when_closing_delimiter_is_unmatched(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::parse_errors_when_closing_delimiter_is_unmatched
        with self.assertRaises(TemplateParseError) as captured:
            Template.parse("Hello, }} world.")

        self.assertEqual(captured.exception, TemplateParseError(TemplateParseErrorKind.UNMATCHED_CLOSING_DELIMITER, 7))
        self.assertEqual(str(captured.exception), "template contains an unmatched `}}` at byte 7")

    def test_parse_error_offsets_are_utf8_byte_offsets(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Contract: Rust reports byte offsets, not Unicode scalar indices.
        with self.assertRaises(TemplateParseError) as captured:
            Template.parse("é {{")

        self.assertEqual(captured.exception, TemplateParseError(TemplateParseErrorKind.UNTERMINATED_PLACEHOLDER, 3))

    def test_render_errors_when_placeholder_is_missing(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_errors_when_placeholder_is_missing
        template = Template.parse("Hello, {{ name }}.")

        with self.assertRaises(TemplateRenderError) as captured:
            template.render(())

        self.assertEqual(captured.exception, TemplateRenderError(TemplateRenderErrorKind.MISSING_VALUE, "name"))
        self.assertEqual(str(captured.exception), "template placeholder `name` is missing a value")

    def test_render_errors_when_extra_value_is_provided(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_errors_when_extra_value_is_provided
        template = Template.parse("Hello, {{ name }}.")

        with self.assertRaises(TemplateRenderError) as captured:
            template.render((("name", "Codex"), ("unused", "extra")))

        self.assertEqual(captured.exception, TemplateRenderError(TemplateRenderErrorKind.EXTRA_VALUE, "unused"))
        self.assertEqual(str(captured.exception), "template value `unused` is not used by this template")

    def test_render_errors_when_duplicate_value_is_provided(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_errors_when_duplicate_value_is_provided
        template = Template.parse("Hello, {{ name }}.")

        with self.assertRaises(TemplateRenderError) as captured:
            template.render((("name", "Codex"), ("name", "other")))

        self.assertEqual(captured.exception, TemplateRenderError(TemplateRenderErrorKind.DUPLICATE_VALUE, "name"))
        self.assertEqual(str(captured.exception), "template value `name` was provided more than once")

    def test_render_function_wraps_parse_errors(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_function_wraps_parse_errors
        with self.assertRaises(TemplateError) as captured:
            render("Hello, }} world.", (("name", "Codex"),))

        self.assertEqual(
            captured.exception,
            TemplateError.from_parse(TemplateParseError(TemplateParseErrorKind.UNMATCHED_CLOSING_DELIMITER, 7)),
        )

    def test_render_function_wraps_render_errors(self) -> None:
        # Source: codex/codex-rs/utils/template/src/lib.rs
        # Rust test: tests::render_function_wraps_render_errors
        with self.assertRaises(TemplateError) as captured:
            render("Hello, {{ name }}.", (("extra", "Codex"),))

        self.assertEqual(
            captured.exception,
            TemplateError.from_render(TemplateRenderError(TemplateRenderErrorKind.MISSING_VALUE, "name")),
        )


if __name__ == "__main__":
    unittest.main()
