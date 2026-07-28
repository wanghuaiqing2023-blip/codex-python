"""Proposed-plan parser from Rust ``proposed_plan.rs``."""

from dataclasses import dataclass
from enum import Enum

from .stream_text import StreamTextChunk
from .tagged_line_parser import TagSpec, TaggedLineParser, TaggedLineSegment, TaggedLineSegmentKind

class _PlanTag(Enum):
    PROPOSED_PLAN = "proposed_plan"


PROPOSED_PLAN_OPEN = "<proposed_plan>"
PROPOSED_PLAN_CLOSE = "</proposed_plan>"


class ProposedPlanSegmentKind(Enum):
    NORMAL = "normal"
    PROPOSED_PLAN_START = "proposed_plan_start"
    PROPOSED_PLAN_DELTA = "proposed_plan_delta"
    PROPOSED_PLAN_END = "proposed_plan_end"


@dataclass(frozen=True)
class ProposedPlanSegment:
    kind: ProposedPlanSegmentKind
    text: str = ""

    @classmethod
    def normal(cls, text: str) -> "ProposedPlanSegment":
        return cls(ProposedPlanSegmentKind.NORMAL, text)

    @classmethod
    def proposed_plan_start(cls) -> "ProposedPlanSegment":
        return cls(ProposedPlanSegmentKind.PROPOSED_PLAN_START)

    @classmethod
    def proposed_plan_delta(cls, text: str) -> "ProposedPlanSegment":
        return cls(ProposedPlanSegmentKind.PROPOSED_PLAN_DELTA, text)

    @classmethod
    def proposed_plan_end(cls) -> "ProposedPlanSegment":
        return cls(ProposedPlanSegmentKind.PROPOSED_PLAN_END)


class ProposedPlanParser:
    """Parser for `<proposed_plan>` blocks emitted in plan mode."""

    def __init__(self) -> None:
        self._parser = TaggedLineParser(
            [TagSpec(open=PROPOSED_PLAN_OPEN, close=PROPOSED_PLAN_CLOSE, tag=_PlanTag.PROPOSED_PLAN)]
        )

    def push_str(self, chunk: str) -> StreamTextChunk[ProposedPlanSegment]:
        return _map_proposed_plan_segments(self._parser.parse(chunk))

    def finish(self) -> StreamTextChunk[ProposedPlanSegment]:
        return _map_proposed_plan_segments(self._parser.finish())


def _map_proposed_plan_segments(
    segments: list[TaggedLineSegment[_PlanTag]],
) -> StreamTextChunk[ProposedPlanSegment]:
    out: StreamTextChunk[ProposedPlanSegment] = StreamTextChunk()
    for segment in segments:
        if segment.kind is TaggedLineSegmentKind.NORMAL:
            mapped = ProposedPlanSegment.normal(segment.text)
            out.visible_text += segment.text
        elif segment.kind is TaggedLineSegmentKind.TAG_START:
            mapped = ProposedPlanSegment.proposed_plan_start()
        elif segment.kind is TaggedLineSegmentKind.TAG_DELTA:
            mapped = ProposedPlanSegment.proposed_plan_delta(segment.text)
        elif segment.kind is TaggedLineSegmentKind.TAG_END:
            mapped = ProposedPlanSegment.proposed_plan_end()
        else:  # pragma: no cover - defensive for future enum variants.
            continue
        out.extracted.append(mapped)
    return out


def strip_proposed_plan_blocks(text: str) -> str:
    parser = ProposedPlanParser()
    out = parser.push_str(text).visible_text
    out += parser.finish().visible_text
    return out


def extract_proposed_plan_text(text: str) -> str | None:
    parser = ProposedPlanParser()
    plan_text = ""
    saw_plan_block = False
    segments = parser.push_str(text).extracted + parser.finish().extracted
    for segment in segments:
        if segment.kind is ProposedPlanSegmentKind.PROPOSED_PLAN_START:
            saw_plan_block = True
            plan_text = ""
        elif segment.kind is ProposedPlanSegmentKind.PROPOSED_PLAN_DELTA:
            plan_text += segment.text
    return plan_text if saw_plan_block else None
