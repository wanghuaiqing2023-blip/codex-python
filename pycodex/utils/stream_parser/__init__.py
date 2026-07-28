"""Public re-exports matching Rust ``stream-parser/src/lib.rs``."""

from .assistant_text import AssistantTextChunk, AssistantTextStreamParser
from .citation import CitationStreamParser, strip_citations
from .inline_hidden_tag import ExtractedInlineTag, InlineHiddenTagParser, InlineTagSpec
from .proposed_plan import (
    ProposedPlanParser,
    ProposedPlanSegment,
    ProposedPlanSegmentKind,
    extract_proposed_plan_text,
    strip_proposed_plan_blocks,
)
from .stream_text import StreamTextChunk, StreamTextParser
from .utf8_stream import (
    Utf8StreamParser,
    Utf8StreamParserError,
    Utf8StreamParserErrorKind,
)

__all__ = [
    "AssistantTextChunk",
    "AssistantTextStreamParser",
    "CitationStreamParser",
    "ExtractedInlineTag",
    "InlineHiddenTagParser",
    "InlineTagSpec",
    "ProposedPlanParser",
    "ProposedPlanSegment",
    "ProposedPlanSegmentKind",
    "StreamTextChunk",
    "StreamTextParser",
    "Utf8StreamParser",
    "Utf8StreamParserError",
    "Utf8StreamParserErrorKind",
    "extract_proposed_plan_text",
    "strip_citations",
    "strip_proposed_plan_blocks",
]
