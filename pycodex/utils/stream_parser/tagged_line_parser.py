"""Line tag parser from Rust ``tagged_line_parser.rs``."""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class TagSpec(Generic[T]):
    open: str
    close: str
    tag: T


class TaggedLineSegmentKind(Enum):
    NORMAL = "normal"
    TAG_START = "tag_start"
    TAG_DELTA = "tag_delta"
    TAG_END = "tag_end"


@dataclass(frozen=True)
class TaggedLineSegment(Generic[T]):
    kind: TaggedLineSegmentKind
    tag: T | None = None
    text: str = ""

    @classmethod
    def normal(cls, text: str) -> "TaggedLineSegment[T]":
        return cls(TaggedLineSegmentKind.NORMAL, text=text)

    @classmethod
    def tag_start(cls, tag: T) -> "TaggedLineSegment[T]":
        return cls(TaggedLineSegmentKind.TAG_START, tag=tag)

    @classmethod
    def tag_delta(cls, tag: T, text: str) -> "TaggedLineSegment[T]":
        return cls(TaggedLineSegmentKind.TAG_DELTA, tag=tag, text=text)

    @classmethod
    def tag_end(cls, tag: T) -> "TaggedLineSegment[T]":
        return cls(TaggedLineSegmentKind.TAG_END, tag=tag)


class TaggedLineParser(Generic[T]):
    def __init__(self, specs: Iterable[TagSpec[T]]) -> None:
        self._specs = list(specs)
        self._active_tag: T | None = None
        self._detect_tag = True
        self._line_buffer = ""

    def parse(self, delta: str) -> list[TaggedLineSegment[T]]:
        segments: list[TaggedLineSegment[T]] = []
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

    def finish(self) -> list[TaggedLineSegment[T]]:
        segments: list[TaggedLineSegment[T]] = []
        if self._line_buffer:
            buffered = self._line_buffer
            self._line_buffer = ""
            without_newline = buffered[:-1] if buffered.endswith("\n") else buffered
            slug = without_newline.lstrip().rstrip()

            open_tag = self._match_open(slug)
            close_tag = self._match_close(slug)
            if open_tag is not None and self._active_tag is None:
                _push_tagged_line_segment(segments, TaggedLineSegment.tag_start(open_tag))
                self._active_tag = open_tag
            elif close_tag is not None and self._active_tag == close_tag:
                _push_tagged_line_segment(segments, TaggedLineSegment.tag_end(close_tag))
                self._active_tag = None
            else:
                self._push_text(buffered, segments)

        if self._active_tag is not None:
            tag = self._active_tag
            self._active_tag = None
            _push_tagged_line_segment(segments, TaggedLineSegment.tag_end(tag))
        self._detect_tag = True
        return segments

    def _finish_line(self, segments: list[TaggedLineSegment[T]]) -> None:
        line = self._line_buffer
        self._line_buffer = ""
        without_newline = line[:-1] if line.endswith("\n") else line
        slug = without_newline.lstrip().rstrip()

        open_tag = self._match_open(slug)
        if open_tag is not None and self._active_tag is None:
            _push_tagged_line_segment(segments, TaggedLineSegment.tag_start(open_tag))
            self._active_tag = open_tag
            self._detect_tag = True
            return

        close_tag = self._match_close(slug)
        if close_tag is not None and self._active_tag == close_tag:
            _push_tagged_line_segment(segments, TaggedLineSegment.tag_end(close_tag))
            self._active_tag = None
            self._detect_tag = True
            return

        self._detect_tag = True
        self._push_text(line, segments)

    def _push_text(self, text: str, segments: list[TaggedLineSegment[T]]) -> None:
        if self._active_tag is not None:
            _push_tagged_line_segment(segments, TaggedLineSegment.tag_delta(self._active_tag, text))
        else:
            _push_tagged_line_segment(segments, TaggedLineSegment.normal(text))

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
    segments: list[TaggedLineSegment[T]],
    segment: TaggedLineSegment[T],
) -> None:
    if segment.kind is TaggedLineSegmentKind.NORMAL:
        if not segment.text:
            return
        if segments and segments[-1].kind is TaggedLineSegmentKind.NORMAL:
            previous = segments[-1]
            segments[-1] = TaggedLineSegment.normal(previous.text + segment.text)
            return
        segments.append(segment)
        return

    if segment.kind is TaggedLineSegmentKind.TAG_DELTA:
        if not segment.text:
            return
        if (
            segments
            and segments[-1].kind is TaggedLineSegmentKind.TAG_DELTA
            and segments[-1].tag == segment.tag
        ):
            previous = segments[-1]
            segments[-1] = TaggedLineSegment.tag_delta(segment.tag, previous.text + segment.text)  # type: ignore[arg-type]
            return
        segments.append(segment)
        return

    segments.append(segment)


