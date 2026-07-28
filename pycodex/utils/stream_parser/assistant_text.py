"""Assistant text parser from Rust ``assistant_text.rs``."""

from dataclasses import dataclass, field

from .citation import CitationStreamParser
from .proposed_plan import ProposedPlanParser, ProposedPlanSegment


@dataclass
class AssistantTextChunk:
    visible_text: str = ""
    citations: list[str] = field(default_factory=list)
    plan_segments: list[ProposedPlanSegment] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.visible_text and not self.citations and not self.plan_segments


class AssistantTextStreamParser:
    """Parse assistant text streaming markup in one pass."""

    def __init__(self, plan_mode: bool) -> None:
        self._plan_mode = bool(plan_mode)
        self._citations = CitationStreamParser()
        self._plan = ProposedPlanParser()

    def push_str(self, chunk: str) -> AssistantTextChunk:
        citation_chunk = self._citations.push_str(chunk)
        out = self._parse_visible_text(citation_chunk.visible_text)
        out.citations = citation_chunk.extracted
        return out

    def finish(self) -> AssistantTextChunk:
        citation_chunk = self._citations.finish()
        out = self._parse_visible_text(citation_chunk.visible_text)
        if self._plan_mode:
            tail = self._plan.finish()
            if not tail.is_empty():
                out.visible_text += tail.visible_text
                out.plan_segments.extend(tail.extracted)
        out.citations = citation_chunk.extracted
        return out

    def _parse_visible_text(self, visible_text: str) -> AssistantTextChunk:
        if not self._plan_mode:
            return AssistantTextChunk(visible_text=visible_text)
        plan_chunk = self._plan.push_str(visible_text)
        return AssistantTextChunk(
            visible_text=plan_chunk.visible_text,
            plan_segments=plan_chunk.extracted,
        )


