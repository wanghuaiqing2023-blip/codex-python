"""Memory citation parser from Rust ``citation.rs``."""

from enum import Enum

from .inline_hidden_tag import InlineHiddenTagParser, InlineTagSpec
from .stream_text import StreamTextChunk

class _CitationTag(Enum):
    CITATION = "citation"


CITATION_OPEN = "<oai-mem-citation>"
CITATION_CLOSE = "</oai-mem-citation>"


class CitationStreamParser:
    def __init__(self) -> None:
        self._inner = InlineHiddenTagParser(
            [InlineTagSpec(tag=_CitationTag.CITATION, open=CITATION_OPEN, close=CITATION_CLOSE)]
        )

    def push_str(self, chunk: str) -> StreamTextChunk[str]:
        inner = self._inner.push_str(chunk)
        return StreamTextChunk(
            visible_text=inner.visible_text,
            extracted=[tag.content for tag in inner.extracted],
        )

    def finish(self) -> StreamTextChunk[str]:
        inner = self._inner.finish()
        return StreamTextChunk(
            visible_text=inner.visible_text,
            extracted=[tag.content for tag in inner.extracted],
        )


def strip_citations(text: str) -> tuple[str, list[str]]:
    parser = CitationStreamParser()
    out = parser.push_str(text)
    tail = parser.finish()
    out.visible_text += tail.visible_text
    out.extracted.extend(tail.extracted)
    return out.visible_text, out.extracted


