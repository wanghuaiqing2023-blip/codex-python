from __future__ import annotations

import unittest

from pycodex.utils.stream_parser import (
    AssistantTextChunk,
    AssistantTextStreamParser,
    CitationStreamParser,
    ExtractedInlineTag,
    InlineHiddenTagParser,
    InlineTagSpec,
    ProposedPlanParser,
    ProposedPlanSegment,
    StreamTextChunk,
    Utf8StreamParser,
    Utf8StreamParserError,
    Utf8StreamParserErrorKind,
    extract_proposed_plan_text,
    strip_citations,
    strip_proposed_plan_blocks,
)


def collect_text_chunks(parser, chunks: list[str]):
    out = StreamTextChunk()
    for chunk in chunks:
        next_out = parser.push_str(chunk)
        out.visible_text += next_out.visible_text
        out.extracted.extend(next_out.extracted)
    tail = parser.finish()
    out.visible_text += tail.visible_text
    out.extracted.extend(tail.extracted)
    return out


def collect_byte_chunks(parser, chunks: list[bytes]):
    out = StreamTextChunk()
    for chunk in chunks:
        next_out = parser.push_bytes(chunk)
        out.visible_text += next_out.visible_text
        out.extracted.extend(next_out.extracted)
    tail = parser.finish()
    out.visible_text += tail.visible_text
    out.extracted.extend(tail.extracted)
    return out


class StreamParserTest(unittest.TestCase):
    # Rust crate/module: codex-utils-stream-parser::citation.
    # Rust test: citation_parser_streams_across_chunk_boundaries.
    def test_citation_parser_streams_across_chunk_boundaries(self) -> None:
        parser = CitationStreamParser()

        out = collect_text_chunks(
            parser,
            [
                "Hello <oai-mem-",
                "citation>source A</oai-mem-",
                "citation> world",
            ],
        )

        self.assertEqual(out.visible_text, "Hello  world")
        self.assertEqual(out.extracted, ["source A"])

    # Rust crate/module: codex-utils-stream-parser::citation.
    # Rust tests: partial opener buffering and EOF handling.
    def test_citation_parser_buffers_and_flushes_partial_open_tags(self) -> None:
        parser = CitationStreamParser()

        first = parser.push_str("abc <oai-mem-")
        self.assertEqual(first.visible_text, "abc ")
        self.assertEqual(first.extracted, [])

        second = parser.push_str("citation>x</oai-mem-citation>z")
        tail = parser.finish()

        self.assertEqual(second.visible_text, "z")
        self.assertEqual(second.extracted, ["x"])
        self.assertTrue(tail.is_empty())

        out = collect_text_chunks(CitationStreamParser(), ["hello <oai-mem-"])
        self.assertEqual(out.visible_text, "hello <oai-mem-")
        self.assertEqual(out.extracted, [])

    # Rust crate/module: codex-utils-stream-parser::citation.
    # Rust tests: strip_citations_collects_all_citations and non-nested behavior.
    def test_strip_citations_collects_and_does_not_nest(self) -> None:
        visible, citations = strip_citations(
            "a<oai-mem-citation>one</oai-mem-citation>"
            "b<oai-mem-citation>two</oai-mem-citation>c"
        )
        self.assertEqual(visible, "abc")
        self.assertEqual(citations, ["one", "two"])

        visible, citations = strip_citations(
            "a<oai-mem-citation>x<oai-mem-citation>y</oai-mem-citation>z</oai-mem-citation>b"
        )
        self.assertEqual(visible, "az</oai-mem-citation>b")
        self.assertEqual(citations, ["x<oai-mem-citation>y"])

    # Rust crate/module: codex-utils-stream-parser::citation.
    # Rust test: strip_citations_auto_closes_unterminated_citation_at_eof.
    def test_strip_citations_auto_closes_unterminated_citation_at_eof(self) -> None:
        visible, citations = strip_citations("x<oai-mem-citation>y")

        self.assertEqual(visible, "x")
        self.assertEqual(citations, ["y"])

    # Rust crate/module: codex-utils-stream-parser::inline_hidden_tag.
    # Rust tests: multiple tag types and longest opener preference.
    def test_inline_hidden_tag_parser_multiple_tags_and_longest_opener(self) -> None:
        parser = InlineHiddenTagParser(
            [
                InlineTagSpec(tag="A", open="<a>", close="</a>"),
                InlineTagSpec(tag="B", open="<b>", close="</b>"),
            ]
        )

        out = collect_text_chunks(parser, ["1<a>x</a>2<b>y</b>3"])
        self.assertEqual(out.visible_text, "123")
        self.assertEqual(
            out.extracted,
            [ExtractedInlineTag("A", "x"), ExtractedInlineTag("B", "y")],
        )

        parser = InlineHiddenTagParser(
            [
                InlineTagSpec(tag="A", open="<a>", close="</a>"),
                InlineTagSpec(tag="B", open="<ab>", close="</ab>"),
            ]
        )
        out = collect_text_chunks(parser, ["x<ab>y</ab>z"])
        self.assertEqual(out.visible_text, "xz")
        self.assertEqual(out.extracted, [ExtractedInlineTag("B", "y")])

    # Rust crate/module: codex-utils-stream-parser::inline_hidden_tag.
    # Rust test: generic_inline_parser_supports_non_ascii_tag_delimiters.
    def test_inline_hidden_tag_parser_supports_non_ascii_tag_delimiters(self) -> None:
        parser = InlineHiddenTagParser([InlineTagSpec(tag="A", open="<\u00e9>", close="</\u00e9>")])

        out = collect_text_chunks(parser, ["a<", "\u00e9>\u4e2d</", "\u00e9>b"])

        self.assertEqual(out.visible_text, "ab")
        self.assertEqual(out.extracted, [ExtractedInlineTag("A", "\u4e2d")])

    # Rust crate/module: codex-utils-stream-parser::inline_hidden_tag.
    # Rust tests: constructor panics for empty specs/delimiters.
    def test_inline_hidden_tag_parser_rejects_empty_specs_and_delimiters(self) -> None:
        with self.assertRaisesRegex(AssertionError, "at least one tag spec"):
            InlineHiddenTagParser([])
        with self.assertRaisesRegex(AssertionError, "non-empty open delimiters"):
            InlineHiddenTagParser([InlineTagSpec(tag="A", open="", close="</a>")])
        with self.assertRaisesRegex(AssertionError, "non-empty close delimiters"):
            InlineHiddenTagParser([InlineTagSpec(tag="A", open="<a>", close="")])

    # Rust crate/module: codex-utils-stream-parser::utf8_stream.
    # Rust test: utf8_stream_parser_handles_split_code_points_across_chunks.
    def test_utf8_stream_parser_handles_split_code_points_across_chunks(self) -> None:
        chunks = [
            b"A\xc3",
            b"\xa9<oai-mem-citation>\xe4",
            b"\xb8\xad</oai-mem-citation>Z",
        ]

        parser = Utf8StreamParser(CitationStreamParser())
        out = collect_byte_chunks(parser, chunks)

        self.assertEqual(out.visible_text, "AéZ")
        self.assertEqual(out.extracted, ["中"])

    # Rust crate/module: codex-utils-stream-parser::utf8_stream.
    # Rust test: utf8_stream_parser_rolls_back_on_invalid_utf8_chunk.
    def test_utf8_stream_parser_rolls_back_on_invalid_utf8_chunk(self) -> None:
        parser = Utf8StreamParser(CitationStreamParser())

        first = parser.push_bytes(bytes([0xC3]))
        self.assertTrue(first.is_empty())

        with self.assertRaises(Utf8StreamParserError) as captured:
            parser.push_bytes(bytes([0x28]))
        self.assertEqual(
            captured.exception,
            Utf8StreamParserError(Utf8StreamParserErrorKind.INVALID_UTF8, 0, 1),
        )
        self.assertEqual(str(captured.exception), "invalid UTF-8 in streamed bytes at offset 0 (error length 1)")

        second = parser.push_bytes(bytes([0xA9, ord("x")]))
        tail = parser.finish()
        self.assertEqual(second.visible_text, "éx")
        self.assertEqual(second.extracted, [])
        self.assertTrue(tail.is_empty())

    # Rust crate/module: codex-utils-stream-parser::utf8_stream.
    # Rust test: rollback entire chunk when invalid byte follows valid prefix.
    def test_utf8_stream_parser_rolls_back_entire_invalid_chunk(self) -> None:
        parser = Utf8StreamParser(CitationStreamParser())

        with self.assertRaises(Utf8StreamParserError) as captured:
            parser.push_bytes(b"ok\xff")

        self.assertEqual(
            captured.exception,
            Utf8StreamParserError(Utf8StreamParserErrorKind.INVALID_UTF8, 2, 1),
        )

        next_out = parser.push_bytes(b"!")
        self.assertEqual(next_out.visible_text, "!")
        self.assertEqual(next_out.extracted, [])

    # Rust crate/module: codex-utils-stream-parser::utf8_stream.
    # Rust tests: EOF/into_inner partial UTF-8 behavior.
    def test_utf8_stream_parser_errors_on_incomplete_code_point_at_eof(self) -> None:
        parser = Utf8StreamParser(CitationStreamParser())

        out = parser.push_bytes(bytes([0xE2, 0x82]))
        self.assertTrue(out.is_empty())

        with self.assertRaises(Utf8StreamParserError) as captured:
            parser.finish()
        self.assertEqual(captured.exception, Utf8StreamParserError.incomplete_utf8_at_eof())
        self.assertEqual(str(captured.exception), "incomplete UTF-8 code point at end of stream")

        parser = Utf8StreamParser(CitationStreamParser())
        self.assertTrue(parser.push_bytes(bytes([0xC3])).is_empty())
        with self.assertRaises(Utf8StreamParserError):
            parser.into_inner()

        parser = Utf8StreamParser(CitationStreamParser())
        self.assertTrue(parser.push_bytes(bytes([0xC3])).is_empty())
        inner = parser.into_inner_lossy()
        self.assertTrue(inner.finish().is_empty())

    # Rust crate/module: codex-utils-stream-parser::proposed_plan.
    # Rust test: streams_proposed_plan_segments_and_visible_text.
    def test_proposed_plan_parser_streams_segments_and_visible_text(self) -> None:
        parser = ProposedPlanParser()

        out = collect_text_chunks(
            parser,
            [
                "Intro text\n<prop",
                "osed_plan>\n- step 1\n",
                "</proposed_plan>\nOutro",
            ],
        )

        self.assertEqual(out.visible_text, "Intro text\nOutro")
        self.assertEqual(
            out.extracted,
            [
                ProposedPlanSegment.normal("Intro text\n"),
                ProposedPlanSegment.proposed_plan_start(),
                ProposedPlanSegment.proposed_plan_delta("- step 1\n"),
                ProposedPlanSegment.proposed_plan_end(),
                ProposedPlanSegment.normal("Outro"),
            ],
        )

    # Rust crate/module: codex-utils-stream-parser::proposed_plan and tagged_line_parser.
    # Rust tests: preserves_non_tag_lines and rejects_tag_lines_with_extra_text.
    def test_proposed_plan_parser_preserves_non_tag_lines(self) -> None:
        parser = ProposedPlanParser()

        out = collect_text_chunks(parser, ["  <proposed_plan> extra\n"])

        self.assertEqual(out.visible_text, "  <proposed_plan> extra\n")
        self.assertEqual(out.extracted, [ProposedPlanSegment.normal("  <proposed_plan> extra\n")])

    # Rust crate/module: codex-utils-stream-parser::proposed_plan.
    # Rust test: closes_unterminated_plan_block_on_finish.
    def test_proposed_plan_parser_closes_unterminated_block_on_finish(self) -> None:
        parser = ProposedPlanParser()

        out = collect_text_chunks(parser, ["<proposed_plan>\n- step 1\n"])

        self.assertEqual(out.visible_text, "")
        self.assertEqual(
            out.extracted,
            [
                ProposedPlanSegment.proposed_plan_start(),
                ProposedPlanSegment.proposed_plan_delta("- step 1\n"),
                ProposedPlanSegment.proposed_plan_end(),
            ],
        )

    # Rust crate/module: codex-utils-stream-parser::tagged_line_parser.
    # Rust test: buffers_prefix_until_tag_is_decided.
    def test_proposed_plan_parser_buffers_prefix_until_tag_is_decided(self) -> None:
        parser = ProposedPlanParser()

        segments = parser.push_str("<prop")
        self.assertTrue(segments.is_empty())

        out = parser.push_str("osed_plan>\nline\n</proposed_plan>\n")
        tail = parser.finish()
        out.visible_text += tail.visible_text
        out.extracted.extend(tail.extracted)

        self.assertEqual(out.visible_text, "")
        self.assertEqual(
            out.extracted,
            [
                ProposedPlanSegment.proposed_plan_start(),
                ProposedPlanSegment.proposed_plan_delta("line\n"),
                ProposedPlanSegment.proposed_plan_end(),
            ],
        )

    # Rust crate/module: codex-utils-stream-parser::proposed_plan.
    # Rust tests: strip_proposed_plan_blocks_from_text and extracts_proposed_plan_text.
    def test_proposed_plan_helpers_strip_and_extract(self) -> None:
        text = "before\n<proposed_plan>\n- step\n</proposed_plan>\nafter"

        self.assertEqual(strip_proposed_plan_blocks(text), "before\nafter")
        self.assertEqual(extract_proposed_plan_text(text), "- step\n")
        self.assertIsNone(extract_proposed_plan_text("plain text only"))

    # Rust crate/module: codex-utils-stream-parser::proposed_plan.
    # Source contract: extract_proposed_plan_text clears text on every block start.
    def test_extract_proposed_plan_text_returns_last_plan_block(self) -> None:
        text = (
            "<proposed_plan>\nfirst\n</proposed_plan>\n"
            "middle\n"
            "<proposed_plan>\nsecond\n</proposed_plan>\n"
        )

        self.assertEqual(extract_proposed_plan_text(text), "second\n")

    # Rust crate/module: codex-utils-stream-parser::assistant_text.
    # Rust test: parses_citations_across_seed_and_delta_boundaries.
    def test_assistant_text_parser_parses_citations_across_seed_and_delta_boundaries(self) -> None:
        parser = AssistantTextStreamParser(plan_mode=False)

        seeded = parser.push_str("hello <oai-mem-citation>doc")
        parsed = parser.push_str("1</oai-mem-citation> world")
        tail = parser.finish()

        self.assertEqual(seeded.visible_text, "hello ")
        self.assertEqual(seeded.citations, [])
        self.assertEqual(seeded.plan_segments, [])
        self.assertEqual(parsed.visible_text, " world")
        self.assertEqual(parsed.citations, ["doc1"])
        self.assertEqual(parsed.plan_segments, [])
        self.assertEqual(tail, AssistantTextChunk())
        self.assertTrue(tail.is_empty())

    # Rust crate/module: codex-utils-stream-parser::assistant_text.
    # Rust test: parses_plan_segments_after_citation_stripping.
    def test_assistant_text_parser_parses_plan_segments_after_citation_stripping(self) -> None:
        parser = AssistantTextStreamParser(plan_mode=True)

        seeded = parser.push_str("Intro\n<proposed")
        parsed = parser.push_str("_plan>\n- step <oai-mem-citation>doc</oai-mem-citation>\n")
        tail = parser.push_str("</proposed_plan>\nOutro")
        finish = parser.finish()

        self.assertEqual(seeded.visible_text, "Intro\n")
        self.assertEqual(seeded.citations, [])
        self.assertEqual(seeded.plan_segments, [ProposedPlanSegment.normal("Intro\n")])
        self.assertEqual(parsed.visible_text, "")
        self.assertEqual(parsed.citations, ["doc"])
        self.assertEqual(
            parsed.plan_segments,
            [
                ProposedPlanSegment.proposed_plan_start(),
                ProposedPlanSegment.proposed_plan_delta("- step \n"),
            ],
        )
        self.assertEqual(tail.visible_text, "Outro")
        self.assertEqual(tail.citations, [])
        self.assertEqual(
            tail.plan_segments,
            [
                ProposedPlanSegment.proposed_plan_end(),
                ProposedPlanSegment.normal("Outro"),
            ],
        )
        self.assertTrue(finish.is_empty())

    # Rust crate/module: codex-utils-stream-parser::assistant_text.
    # Source contract: plan parsing is bypassed unless plan_mode is enabled.
    def test_assistant_text_parser_leaves_plan_tags_visible_when_plan_mode_is_disabled(self) -> None:
        parser = AssistantTextStreamParser(plan_mode=False)

        out = parser.push_str("<proposed_plan>\n- step\n</proposed_plan>")
        tail = parser.finish()
        out.visible_text += tail.visible_text
        out.citations.extend(tail.citations)
        out.plan_segments.extend(tail.plan_segments)

        self.assertEqual(out.visible_text, "<proposed_plan>\n- step\n</proposed_plan>")
        self.assertEqual(out.citations, [])
        self.assertEqual(out.plan_segments, [])


if __name__ == "__main__":
    unittest.main()
