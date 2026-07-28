"""Inline hidden-tag parser from Rust ``inline_hidden_tag.rs``."""

from dataclasses import dataclass
from typing import Generic, Iterable, TypeVar

from .stream_text import StreamTextChunk

T = TypeVar("T")


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



def _longest_suffix_prefix_len(s: str, needle: str) -> int:
    max_len = min(len(s), max(len(needle) - 1, 0))
    for length in range(max_len, 0, -1):
        if s.endswith(needle[:length]):
            return length
    return 0
