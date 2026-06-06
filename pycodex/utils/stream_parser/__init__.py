"""Incremental streamed text parsers aligned with Rust `codex-utils-stream-parser`.

This package currently ports the core hidden-inline-tag and UTF-8 byte-stream
modules. Proposed-plan and assistant-text parsing remain separate follow-up
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Iterable, Protocol, TypeVar

T = TypeVar("T")


@dataclass
class StreamTextChunk(Generic[T]):
    visible_text: str = ""
    extracted: list[T] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.visible_text and not self.extracted


class StreamTextParser(Protocol[T]):
    def push_str(self, chunk: str) -> StreamTextChunk[T]:
        ...

    def finish(self) -> StreamTextChunk[T]:
        ...


@dataclass(frozen=True)
class ExtractedInlineTag(Generic[T]):
    tag: T
    content: str


@dataclass(frozen=True)
class InlineTagSpec(Generic[T]):
    tag: T
    open: str
    close: str


@dataclass
class _ActiveTag(Generic[T]):
    tag: T
    close: str
    content: str = ""


class InlineHiddenTagParser(Generic[T]):
    """Hide configured literal inline tags and extract their contents."""

    def __init__(self, specs: Iterable[InlineTagSpec[T]]) -> None:
        self._specs = list(specs)
        if not self._specs:
            raise AssertionError("InlineHiddenTagParser requires at least one tag spec")
        for spec in self._specs:
            if not spec.open:
                raise AssertionError("InlineHiddenTagParser requires non-empty open delimiters")
            if not spec.close:
                raise AssertionError("InlineHiddenTagParser requires non-empty close delimiters")
        self._pending = ""
        self._active: _ActiveTag[T] | None = None

    def _find_next_open(self) -> tuple[int, int] | None:
        best: tuple[int, int, int] | None = None
        for idx, spec in enumerate(self._specs):
            pos = self._pending.find(spec.open)
            if pos < 0:
                continue
            candidate = (pos, -len(spec.open), idx)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            return None
        return best[0], best[2]

    def _max_open_prefix_suffix_len(self) -> int:
        return max((_longest_suffix_prefix_len(self._pending, spec.open) for spec in self._specs), default=0)

    def _drain_visible_to_suffix_match(
        self,
        out: StreamTextChunk[ExtractedInlineTag[T]],
        keep_suffix_len: int,
    ) -> None:
        take = max(len(self._pending) - keep_suffix_len, 0)
        if take == 0:
            return
        out.visible_text += self._pending[:take]
        self._pending = self._pending[take:]

    def push_str(self, chunk: str) -> StreamTextChunk[ExtractedInlineTag[T]]:
        if not isinstance(chunk, str):
            raise TypeError("chunk must be a string")

        self._pending += chunk
        out: StreamTextChunk[ExtractedInlineTag[T]] = StreamTextChunk()

        while True:
            if self._active is not None:
                close = self._active.close
                close_idx = self._pending.find(close)
                if close_idx >= 0:
                    active = self._active
                    active.content += self._pending[:close_idx]
                    out.extracted.append(ExtractedInlineTag(tag=active.tag, content=active.content))
                    self._pending = self._pending[close_idx + len(close) :]
                    self._active = None
                    continue

                keep = _longest_suffix_prefix_len(self._pending, close)
                take = max(len(self._pending) - keep, 0)
                if take > 0:
                    self._active.content += self._pending[:take]
                    self._pending = self._pending[take:]
                break

            found = self._find_next_open()
            if found is not None:
                open_idx, spec_idx = found
                out.visible_text += self._pending[:open_idx]
                spec = self._specs[spec_idx]
                self._pending = self._pending[open_idx + len(spec.open) :]
                self._active = _ActiveTag(tag=spec.tag, close=spec.close)
                continue

            keep = self._max_open_prefix_suffix_len()
            self._drain_visible_to_suffix_match(out, keep)
            break

        return out

    def finish(self) -> StreamTextChunk[ExtractedInlineTag[T]]:
        out: StreamTextChunk[ExtractedInlineTag[T]] = StreamTextChunk()

        if self._active is not None:
            active = self._active
            if self._pending:
                active.content += self._pending
                self._pending = ""
            out.extracted.append(ExtractedInlineTag(tag=active.tag, content=active.content))
            self._active = None
            return out

        if self._pending:
            out.visible_text = self._pending
            self._pending = ""
        return out


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


class Utf8StreamParserErrorKind(Enum):
    INVALID_UTF8 = "invalid_utf8"
    INCOMPLETE_UTF8_AT_EOF = "incomplete_utf8_at_eof"


@dataclass(frozen=True)
class Utf8StreamParserError(Exception):
    kind: Utf8StreamParserErrorKind
    valid_up_to: int | None = None
    error_len: int | None = None

    @classmethod
    def invalid_utf8(cls, valid_up_to: int, error_len: int) -> "Utf8StreamParserError":
        return cls(Utf8StreamParserErrorKind.INVALID_UTF8, valid_up_to, error_len)

    @classmethod
    def incomplete_utf8_at_eof(cls) -> "Utf8StreamParserError":
        return cls(Utf8StreamParserErrorKind.INCOMPLETE_UTF8_AT_EOF)

    def __str__(self) -> str:
        if self.kind is Utf8StreamParserErrorKind.INVALID_UTF8:
            return (
                "invalid UTF-8 in streamed bytes at offset "
                f"{self.valid_up_to} (error length {self.error_len})"
            )
        return "incomplete UTF-8 code point at end of stream"


P = TypeVar("P", bound=StreamTextParser[object])


class Utf8StreamParser(Generic[P]):
    def __init__(self, inner: P) -> None:
        self._inner = inner
        self._pending_utf8 = bytearray()

    def push_bytes(self, chunk: bytes | bytearray | memoryview) -> StreamTextChunk[object]:
        chunk_bytes = bytes(chunk)
        old_len = len(self._pending_utf8)
        self._pending_utf8.extend(chunk_bytes)

        try:
            text = self._pending_utf8.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason != "unexpected end of data":
                self._pending_utf8 = self._pending_utf8[:old_len]
                raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None

            valid_up_to = err.start
            if valid_up_to == 0:
                return StreamTextChunk()

            try:
                text = bytes(self._pending_utf8[:valid_up_to]).decode("utf-8")
            except UnicodeDecodeError as prefix_err:
                self._pending_utf8 = self._pending_utf8[:old_len]
                raise Utf8StreamParserError.invalid_utf8(
                    prefix_err.start,
                    max(prefix_err.end - prefix_err.start, 0),
                ) from None

            out = self._inner.push_str(text)
            del self._pending_utf8[:valid_up_to]
            return out

        out = self._inner.push_str(text)
        self._pending_utf8.clear()
        return out

    def finish(self) -> StreamTextChunk[object]:
        if self._pending_utf8:
            try:
                text = self._pending_utf8.decode("utf-8")
            except UnicodeDecodeError as err:
                if err.reason != "unexpected end of data":
                    raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None
                raise Utf8StreamParserError.incomplete_utf8_at_eof() from None

            out = self._inner.push_str(text)
            self._pending_utf8.clear()
        else:
            out = StreamTextChunk()

        tail = self._inner.finish()
        out.visible_text += tail.visible_text
        out.extracted.extend(tail.extracted)
        return out

    def into_inner(self) -> P:
        if not self._pending_utf8:
            return self._inner
        try:
            self._pending_utf8.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason != "unexpected end of data":
                raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None
            raise Utf8StreamParserError.incomplete_utf8_at_eof() from None
        return self._inner

    def into_inner_lossy(self) -> P:
        return self._inner


def _longest_suffix_prefix_len(s: str, needle: str) -> int:
    max_len = min(len(s), max(len(needle) - 1, 0))
    for length in range(max_len, 0, -1):
        if s.endswith(needle[:length]):
            return length
    return 0


@dataclass(frozen=True)
class _TagSpec(Generic[T]):
    open: str
    close: str
    tag: T


class _TaggedLineSegmentKind(Enum):
    NORMAL = "normal"
    TAG_START = "tag_start"
    TAG_DELTA = "tag_delta"
    TAG_END = "tag_end"


@dataclass(frozen=True)
class _TaggedLineSegment(Generic[T]):
    kind: _TaggedLineSegmentKind
    tag: T | None = None
    text: str = ""

    @classmethod
    def normal(cls, text: str) -> "_TaggedLineSegment[T]":
        return cls(_TaggedLineSegmentKind.NORMAL, text=text)

    @classmethod
    def tag_start(cls, tag: T) -> "_TaggedLineSegment[T]":
        return cls(_TaggedLineSegmentKind.TAG_START, tag=tag)

    @classmethod
    def tag_delta(cls, tag: T, text: str) -> "_TaggedLineSegment[T]":
        return cls(_TaggedLineSegmentKind.TAG_DELTA, tag=tag, text=text)

    @classmethod
    def tag_end(cls, tag: T) -> "_TaggedLineSegment[T]":
        return cls(_TaggedLineSegmentKind.TAG_END, tag=tag)


class _TaggedLineParser(Generic[T]):
    def __init__(self, specs: Iterable[_TagSpec[T]]) -> None:
        self._specs = list(specs)
        self._active_tag: T | None = None
        self._detect_tag = True
        self._line_buffer = ""

    def parse(self, delta: str) -> list[_TaggedLineSegment[T]]:
        segments: list[_TaggedLineSegment[T]] = []
        run = ""

        for ch in delta:
            if self._detect_tag:
                if run:
                    self._push_text(run, segments)
                    run = ""
                self._line_buffer += ch
                if ch == "\n":
                    self._finish_line(segments)
                    continue
                slug = self._line_buffer.lstrip()
                if not slug or self._is_tag_prefix(slug):
                    continue
                buffered = self._line_buffer
                self._line_buffer = ""
                self._detect_tag = False
                self._push_text(buffered, segments)
                continue

            run += ch
            if ch == "\n":
                self._push_text(run, segments)
                run = ""
                self._detect_tag = True

        if run:
            self._push_text(run, segments)

        return segments

    def finish(self) -> list[_TaggedLineSegment[T]]:
        segments: list[_TaggedLineSegment[T]] = []
        if self._line_buffer:
            buffered = self._line_buffer
            self._line_buffer = ""
            without_newline = buffered[:-1] if buffered.endswith("\n") else buffered
            slug = without_newline.lstrip().rstrip()

            open_tag = self._match_open(slug)
            close_tag = self._match_close(slug)
            if open_tag is not None and self._active_tag is None:
                _push_tagged_line_segment(segments, _TaggedLineSegment.tag_start(open_tag))
                self._active_tag = open_tag
            elif close_tag is not None and self._active_tag == close_tag:
                _push_tagged_line_segment(segments, _TaggedLineSegment.tag_end(close_tag))
                self._active_tag = None
            else:
                self._push_text(buffered, segments)

        if self._active_tag is not None:
            tag = self._active_tag
            self._active_tag = None
            _push_tagged_line_segment(segments, _TaggedLineSegment.tag_end(tag))
        self._detect_tag = True
        return segments

    def _finish_line(self, segments: list[_TaggedLineSegment[T]]) -> None:
        line = self._line_buffer
        self._line_buffer = ""
        without_newline = line[:-1] if line.endswith("\n") else line
        slug = without_newline.lstrip().rstrip()

        open_tag = self._match_open(slug)
        if open_tag is not None and self._active_tag is None:
            _push_tagged_line_segment(segments, _TaggedLineSegment.tag_start(open_tag))
            self._active_tag = open_tag
            self._detect_tag = True
            return

        close_tag = self._match_close(slug)
        if close_tag is not None and self._active_tag == close_tag:
            _push_tagged_line_segment(segments, _TaggedLineSegment.tag_end(close_tag))
            self._active_tag = None
            self._detect_tag = True
            return

        self._detect_tag = True
        self._push_text(line, segments)

    def _push_text(self, text: str, segments: list[_TaggedLineSegment[T]]) -> None:
        if self._active_tag is not None:
            _push_tagged_line_segment(segments, _TaggedLineSegment.tag_delta(self._active_tag, text))
        else:
            _push_tagged_line_segment(segments, _TaggedLineSegment.normal(text))

    def _is_tag_prefix(self, slug: str) -> bool:
        slug = slug.rstrip()
        return any(spec.open.startswith(slug) or spec.close.startswith(slug) for spec in self._specs)

    def _match_open(self, slug: str) -> T | None:
        for spec in self._specs:
            if spec.open == slug:
                return spec.tag
        return None

    def _match_close(self, slug: str) -> T | None:
        for spec in self._specs:
            if spec.close == slug:
                return spec.tag
        return None


def _push_tagged_line_segment(
    segments: list[_TaggedLineSegment[T]],
    segment: _TaggedLineSegment[T],
) -> None:
    if segment.kind is _TaggedLineSegmentKind.NORMAL:
        if not segment.text:
            return
        if segments and segments[-1].kind is _TaggedLineSegmentKind.NORMAL:
            previous = segments[-1]
            segments[-1] = _TaggedLineSegment.normal(previous.text + segment.text)
            return
        segments.append(segment)
        return

    if segment.kind is _TaggedLineSegmentKind.TAG_DELTA:
        if not segment.text:
            return
        if (
            segments
            and segments[-1].kind is _TaggedLineSegmentKind.TAG_DELTA
            and segments[-1].tag == segment.tag
        ):
            previous = segments[-1]
            segments[-1] = _TaggedLineSegment.tag_delta(segment.tag, previous.text + segment.text)  # type: ignore[arg-type]
            return
        segments.append(segment)
        return

    segments.append(segment)


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
        self._parser = _TaggedLineParser(
            [_TagSpec(open=PROPOSED_PLAN_OPEN, close=PROPOSED_PLAN_CLOSE, tag=_PlanTag.PROPOSED_PLAN)]
        )

    def push_str(self, chunk: str) -> StreamTextChunk[ProposedPlanSegment]:
        return _map_proposed_plan_segments(self._parser.parse(chunk))

    def finish(self) -> StreamTextChunk[ProposedPlanSegment]:
        return _map_proposed_plan_segments(self._parser.finish())


def _map_proposed_plan_segments(
    segments: list[_TaggedLineSegment[_PlanTag]],
) -> StreamTextChunk[ProposedPlanSegment]:
    out: StreamTextChunk[ProposedPlanSegment] = StreamTextChunk()
    for segment in segments:
        if segment.kind is _TaggedLineSegmentKind.NORMAL:
            mapped = ProposedPlanSegment.normal(segment.text)
            out.visible_text += segment.text
        elif segment.kind is _TaggedLineSegmentKind.TAG_START:
            mapped = ProposedPlanSegment.proposed_plan_start()
        elif segment.kind is _TaggedLineSegmentKind.TAG_DELTA:
            mapped = ProposedPlanSegment.proposed_plan_delta(segment.text)
        elif segment.kind is _TaggedLineSegmentKind.TAG_END:
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


__all__ = [
    "AssistantTextChunk",
    "AssistantTextStreamParser",
    "CITATION_CLOSE",
    "CITATION_OPEN",
    "CitationStreamParser",
    "ExtractedInlineTag",
    "InlineHiddenTagParser",
    "InlineTagSpec",
    "PROPOSED_PLAN_CLOSE",
    "PROPOSED_PLAN_OPEN",
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
