"""Semantic pager overlay models for the TUI port.

Rust counterpart: ``codex-rs/tui/src/pager_overlay.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Protocol, Sequence

from .ratatui_bridge import Rect

MAX_SCROLL = 2**63 - 1


class Renderable(Protocol):
    def desired_height(self, width: int) -> int: ...
    def render_lines(self, width: int) -> list[str]: ...


@dataclass
class TextRenderable:
    lines: list[str]

    def desired_height(self, width: int) -> int:
        if width <= 0:
            return len(self.lines)
        total = 0
        for line in self.lines:
            total += max(1, (len(line) + width - 1) // width)
        return total

    def render_lines(self, width: int) -> list[str]:
        if width <= 0:
            return list(self.lines)
        out: list[str] = []
        for line in self.lines:
            if line == "":
                out.append("")
                continue
            for start in range(0, len(line), width):
                out.append(line[start : start + width])
        return out or [""]


@dataclass
class CachedRenderable:
    renderable: Renderable
    height: int | None = None
    last_width: int | None = None

    @classmethod
    def new(cls, renderable: Renderable) -> "CachedRenderable":
        return cls(renderable=renderable)

    def desired_height(self, width: int) -> int:
        if self.last_width != width:
            self.height = self.renderable.desired_height(width)
            self.last_width = width
        return self.height or 0

    def render_lines(self, width: int) -> list[str]:
        return self.renderable.render_lines(width)


@dataclass
class PagerView:
    renderables: list[Renderable]
    title: str
    scroll_offset: int = 0
    keymap: Any | None = None
    last_content_height: int | None = None
    last_rendered_height: int | None = None
    pending_scroll_chunk: int | None = None

    @classmethod
    def new(
        cls,
        renderables: Sequence[Renderable],
        title: str,
        scroll_offset: int = 0,
        keymap: Any | None = None,
    ) -> "PagerView":
        return cls(list(renderables), title, int(scroll_offset), keymap)

    def content_height(self, width: int) -> int:
        return sum(max(0, int(renderable.desired_height(width))) for renderable in self.renderables)

    def content_area(self, area: Rect) -> Rect:
        return Rect(area.x, area.y + 1, area.width, max(area.height - 2, 0))

    def update_last_content_height(self, height: int) -> None:
        self.last_content_height = max(0, int(height))

    def page_height(self, viewport_area: Rect) -> int:
        if self.last_content_height is not None:
            return self.last_content_height
        return self.content_area(viewport_area).height

    def render(self, area: Rect) -> list[str]:
        content_area = self.content_area(area)
        self.update_last_content_height(content_area.height)
        total_height = self.content_height(content_area.width)
        self.last_rendered_height = total_height
        if self.pending_scroll_chunk is not None:
            idx = self.pending_scroll_chunk
            self.pending_scroll_chunk = None
            self.ensure_chunk_visible(idx, content_area)
        max_scroll = max(total_height - content_area.height, 0)
        if self.scroll_offset >= MAX_SCROLL:
            self.scroll_offset = max_scroll
        else:
            self.scroll_offset = min(max(self.scroll_offset, 0), max_scroll)
        return self.visible_content_lines(content_area)

    def visible_content_lines(self, area: Rect) -> list[str]:
        lines: list[str] = []
        for renderable in self.renderables:
            lines.extend(renderable.render_lines(area.width))
        start = min(max(self.scroll_offset, 0), len(lines))
        visible = lines[start : start + area.height]
        if len(visible) < area.height:
            visible.extend("~" for _ in range(area.height - len(visible)))
        return visible

    def is_scrolled_to_bottom(self) -> bool:
        if self.scroll_offset >= MAX_SCROLL:
            return True
        if self.last_content_height is None:
            return False
        if not self.renderables:
            return True
        if self.last_rendered_height is None:
            return False
        if self.last_rendered_height <= self.last_content_height:
            return True
        max_scroll = max(self.last_rendered_height - self.last_content_height, 0)
        return self.scroll_offset >= max_scroll

    def scroll_chunk_into_view(self, chunk_index: int) -> None:
        self.pending_scroll_chunk = int(chunk_index)

    def ensure_chunk_visible(self, idx: int, area: Rect) -> None:
        if area.height == 0 or idx < 0 or idx >= len(self.renderables):
            return
        first = sum(self.renderables[i].desired_height(area.width) for i in range(idx))
        last = first + self.renderables[idx].desired_height(area.width)
        current_top = self.scroll_offset
        current_bottom = current_top + max(area.height - 1, 0)
        if first < current_top:
            self.scroll_offset = first
        elif last > current_bottom:
            self.scroll_offset = max(last - max(area.height - 1, 0), 0)


@dataclass(frozen=True)
class LiveTailKey:
    width: int
    revision: int
    is_stream_continuation: bool
    animation_tick: int | None = None


@dataclass
class TranscriptOverlay:
    cells: list[Renderable]
    keymap: Any | None = None
    highlight_cell: int | None = None
    live_tail_key: LiveTailKey | None = None
    live_tail: Renderable | None = None
    is_done_flag: bool = False
    view: PagerView = field(init=False)

    def __post_init__(self) -> None:
        self.view = PagerView.new(self.render_cells(self.cells, self.highlight_cell), "T R A N S C R I P T", MAX_SCROLL, self.keymap)

    @classmethod
    def new(cls, transcript_cells: Sequence[Renderable], keymap: Any | None = None) -> "TranscriptOverlay":
        return cls(list(transcript_cells), keymap=keymap)

    @staticmethod
    def render_cells(cells: Sequence[Renderable], highlight_cell: int | None = None) -> list[Renderable]:
        _ = highlight_cell
        return [CachedRenderable.new(cell) for cell in cells]

    def committed_cell_count(self) -> int:
        return len(self.cells)

    def is_done(self) -> bool:
        return self.is_done_flag

    def is_scrolled_to_bottom(self) -> bool:
        return self.view.is_scrolled_to_bottom()

    def set_highlight_cell(self, idx: int | None) -> None:
        self.highlight_cell = idx
        self.rebuild_renderables()

    def rebuild_renderables(self) -> None:
        renderables = self.render_cells(self.cells, self.highlight_cell)
        if self.live_tail is not None:
            renderables.append(self.live_tail)
        self.view.renderables = renderables

    def insert_cell(self, cell: Renderable) -> None:
        was_bottom = self.view.is_scrolled_to_bottom()
        self.cells.append(cell)
        self.rebuild_renderables()
        if was_bottom:
            self.view.scroll_offset = MAX_SCROLL

    def replace_cells(self, cells: Sequence[Renderable]) -> None:
        self.cells = list(cells)
        if self.highlight_cell is not None and self.highlight_cell >= len(self.cells):
            self.highlight_cell = None
        self.rebuild_renderables()

    def consolidate_cells(self, replacement_range: range | tuple[int, int], replacement: Renderable) -> None:
        if isinstance(replacement_range, range):
            start, stop = replacement_range.start, replacement_range.stop
        else:
            start, stop = replacement_range
        start = max(0, min(start, len(self.cells)))
        stop = max(start, min(stop, len(self.cells)))
        removed = max(stop - start, 0)
        self.cells[start:stop] = [replacement]
        if self.highlight_cell is not None:
            if start <= self.highlight_cell < stop:
                self.highlight_cell = start
            elif self.highlight_cell >= stop:
                self.highlight_cell = max(0, self.highlight_cell - max(removed - 1, 0))
        self.rebuild_renderables()

    def sync_live_tail(
        self,
        width: int,
        key: Any | None,
        build_tail: Callable[[int], Sequence[str] | Renderable | None],
    ) -> None:
        if key is None:
            self.live_tail_key = None
            self.live_tail = None
            self.rebuild_renderables()
            return
        tail_key = _coerce_live_tail_key(width, key)
        if self.live_tail_key == tail_key:
            return
        built = build_tail(width)
        self.live_tail_key = tail_key
        if built is None:
            self.live_tail = None
        elif hasattr(built, "desired_height"):
            self.live_tail = built  # type: ignore[assignment]
        else:
            self.live_tail = TextRenderable([str(line) for line in built])
        self.rebuild_renderables()

    def render(self, area: Rect) -> list[str]:
        top = Rect(area.x, area.y, area.width, max(area.height - 3, 0))
        return self.view.render(top)


@dataclass
class StaticOverlay:
    view: PagerView
    is_done_flag: bool = False

    @classmethod
    def with_title(cls, lines: Sequence[str], title: str, keymap: Any | None = None) -> "StaticOverlay":
        return cls(PagerView.new([TextRenderable([str(line) for line in lines])], title, 0, keymap))

    @classmethod
    def with_renderables(cls, renderables: Sequence[Renderable], title: str, keymap: Any | None = None) -> "StaticOverlay":
        return cls(PagerView.new(list(renderables), title, 0, keymap))

    def render(self, area: Rect) -> list[str]:
        top = Rect(area.x, area.y, area.width, max(area.height - 3, 0))
        return self.view.render(top)

    def is_done(self) -> bool:
        return self.is_done_flag


class OverlayKind(str, Enum):
    TRANSCRIPT = "transcript"
    STATIC = "static"


@dataclass
class Overlay:
    kind: OverlayKind
    inner: TranscriptOverlay | StaticOverlay

    @classmethod
    def new_transcript(cls, cells: Sequence[Renderable], keymap: Any | None = None) -> "Overlay":
        return cls(OverlayKind.TRANSCRIPT, TranscriptOverlay.new(cells, keymap))

    @classmethod
    def new_static_with_lines(cls, lines: Sequence[str], title: str, keymap: Any | None = None) -> "Overlay":
        return cls(OverlayKind.STATIC, StaticOverlay.with_title(lines, title, keymap))

    @classmethod
    def new_static_with_renderables(cls, renderables: Sequence[Renderable], title: str, keymap: Any | None = None) -> "Overlay":
        return cls(OverlayKind.STATIC, StaticOverlay.with_renderables(renderables, title, keymap))

    def is_done(self) -> bool:
        return self.inner.is_done()


def _coerce_live_tail_key(width: int, key: Any) -> LiveTailKey:
    return LiveTailKey(
        width=int(width),
        revision=int(getattr(key, "revision", key.get("revision") if isinstance(key, dict) else 0)),
        is_stream_continuation=bool(getattr(key, "is_stream_continuation", key.get("is_stream_continuation") if isinstance(key, dict) else False)),
        animation_tick=getattr(key, "animation_tick", key.get("animation_tick") if isinstance(key, dict) else None),
    )


def first_or_empty(bindings: Sequence[Any]) -> list[Any]:
    return list(bindings[:1])


def render_key_hints(pairs: Sequence[tuple[Sequence[str], str]]) -> str:
    parts: list[str] = []
    for keys, desc in pairs:
        parts.append(f"{'/'.join(str(key) for key in keys)} {desc}")
    return " " + "   ".join(parts)


def render_offset_content(renderable: Renderable, width: int, offset: int, height: int) -> list[str]:
    return renderable.render_lines(width)[offset : offset + height]


def paragraph_block(prefix: str, lines: int) -> TextRenderable:
    return TextRenderable([f"{prefix}{i}" for i in range(lines)])


def pager_view(renderables: Sequence[Renderable], title: str, scroll_offset: int = 0) -> PagerView:
    return PagerView.new(renderables, title, scroll_offset)


def transcript_overlay(cells: Sequence[Renderable]) -> TranscriptOverlay:
    return TranscriptOverlay.new(cells)


def static_overlay(lines: Sequence[str], title: str) -> StaticOverlay:
    return StaticOverlay.with_title(lines, title)


__all__ = [
    "CachedRenderable",
    "LiveTailKey",
    "MAX_SCROLL",
    "Overlay",
    "OverlayKind",
    "PagerView",
    "Rect",
    "StaticOverlay",
    "TextRenderable",
    "TranscriptOverlay",
    "first_or_empty",
    "pager_view",
    "paragraph_block",
    "render_key_hints",
    "render_offset_content",
    "static_overlay",
    "transcript_overlay",
]
