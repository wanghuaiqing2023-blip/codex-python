"""Composable renderable layout primitives for ``codex-tui::render::renderable``.

Rust uses ratatui ``Rect``/``Buffer`` and trait implementations.  Python keeps
the same behavior contract with semantic ``Rect`` objects, a simple recording
``Buffer``, and duck-typed renderables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Protocol, Tuple, Union, runtime_checkable

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..ratatui_bridge import Buffer, Paragraph, Rect
from ..ratatui_bridge.text import Line as BridgeLine
from ..ratatui_bridge.text import Span as BridgeSpan
from ..ratatui_bridge.text import Text as BridgeText

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="render::renderable",
    source="codex/codex-rs/tui/src/render/renderable.rs",
)

DEFAULT_CURSOR_STYLE = "DefaultUserShape"


@dataclass(frozen=True)
class Insets:
    top: int = 0
    left: int = 0
    bottom: int = 0
    right: int = 0

    @classmethod
    def tlbr(cls, top: int, left: int, bottom: int, right: int) -> "Insets":
        return cls(top=top, left=left, bottom=bottom, right=right)

    @classmethod
    def vh(cls, v: int, h: int) -> "Insets":
        return cls(top=v, left=h, bottom=v, right=h)


@runtime_checkable
class Renderable(Protocol):
    def render(self, area: Rect, buf: Buffer) -> None: ...
    def desired_height(self, width: int) -> int: ...
    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]: ...
    def cursor_style(self, area: Rect) -> Any: ...


class EmptyRenderable:
    def render(self, area: Rect, buf: Buffer) -> None:
        return None

    def desired_height(self, width: int) -> int:
        return 0

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return None

    def cursor_style(self, area: Rect) -> Any:
        return DEFAULT_CURSOR_STYLE


@dataclass
class TextRenderable:
    value: Union[str, Span, Line, BridgeSpan, BridgeLine]

    def render(self, area: Rect, buf: Buffer) -> None:
        if area.is_empty():
            return
        if isinstance(self.value, BridgeSpan):
            buf.set_span(area.x, area.y, self.value, max_width=area.width)
        elif isinstance(self.value, BridgeLine):
            buf.set_line(area.x, area.y, self.value, max_width=area.width)
        else:
            buf.set_line(area.x, area.y, BridgeLine.raw(_plain(self.value)), max_width=area.width)

    def desired_height(self, width: int) -> int:
        return 1

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return None

    def cursor_style(self, area: Rect) -> Any:
        return DEFAULT_CURSOR_STYLE


@dataclass
class ParagraphRenderable:
    lines: Tuple[str, ...]
    wrap: bool = True

    @classmethod
    def from_text(cls, text: str, *, wrap: bool = True) -> "ParagraphRenderable":
        return cls(tuple(text.splitlines() or [""]), wrap=wrap)

    def render(self, area: Rect, buf: Buffer) -> None:
        if area.is_empty():
            return
        for offset, line in enumerate(_wrap_lines(self.lines, area.width, self.wrap)[: area.height]):
            buf.set_line(area.x, area.y + offset, BridgeLine.raw(line), max_width=area.width)

    def desired_height(self, width: int) -> int:
        if width <= 0:
            return len(self.lines)
        if not self.wrap:
            return len(self.lines)
        height = 0
        for line in self.lines:
            height += max(1, (len(line) + width - 1) // width)
        return height

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return None

    def cursor_style(self, area: Rect) -> Any:
        return DEFAULT_CURSOR_STYLE


@dataclass
class BridgeParagraphRenderable:
    paragraph: Paragraph

    def render(self, area: Rect, buf: Buffer) -> None:
        self.paragraph.render(area, buf)

    def desired_height(self, width: int) -> int:
        text_area = Rect.new(0, 0, width, 65535)
        if self.paragraph.block is not None:
            text_area = self.paragraph.block.inner(text_area)
        if text_area.width <= 0:
            return 0
        probe = Buffer.empty(text_area)
        self.paragraph.render(text_area, probe)
        lines = probe.to_plain_text(trim_end=True).splitlines()
        while lines and lines[-1] == "":
            lines.pop()
        return len(lines)

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return None

    def cursor_style(self, area: Rect) -> Any:
        return DEFAULT_CURSOR_STYLE


@dataclass
class RenderableItem:
    child: Any
    owned: bool = True

    @classmethod
    def Owned(cls, child: Any) -> "RenderableItem":
        return cls(as_renderable(child), owned=True)

    @classmethod
    def Borrowed(cls, child: Any) -> "RenderableItem":
        return cls(as_renderable(child), owned=False)

    def render(self, area: Rect, buf: Buffer) -> None:
        self.child.render(area, buf)

    def desired_height(self, width: int) -> int:
        return self.child.desired_height(width)

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return self.child.cursor_pos(area)

    def cursor_style(self, area: Rect) -> Any:
        return self.child.cursor_style(area)


def as_renderable(value: Any) -> Renderable:
    if value is None:
        return EmptyRenderable()
    if isinstance(value, RenderableItem):
        return value
    if hasattr(value, "render") and hasattr(value, "desired_height"):
        if not hasattr(value, "cursor_pos"):
            value.cursor_pos = lambda area: None
        if not hasattr(value, "cursor_style"):
            value.cursor_style = lambda area: DEFAULT_CURSOR_STYLE
        return value
    if isinstance(value, Paragraph):
        return BridgeParagraphRenderable(value)
    if isinstance(value, BridgeText):
        return ParagraphRenderable(tuple(line.plain for line in value.lines))
    if isinstance(value, (str, Span, Line, BridgeSpan, BridgeLine)):
        return TextRenderable(value)
    raise TypeError(f"object is not renderable: {type(value).__name__}")


def render(value: Any, area: Rect, buf: Buffer) -> None:
    as_renderable(value).render(area, buf)


def desired_height(value: Any, width: int) -> int:
    return as_renderable(value).desired_height(width)


def cursor_pos(value: Any, area: Rect) -> Optional[Tuple[int, int]]:
    return as_renderable(value).cursor_pos(area)


def cursor_style(value: Any, area: Rect) -> Any:
    return as_renderable(value).cursor_style(area)


def from_(value: Any) -> RenderableItem:
    return RenderableItem.Owned(value)


@dataclass
class ColumnRenderable:
    children: List[RenderableItem] = field(default_factory=list)

    @classmethod
    def new(cls) -> "ColumnRenderable":
        return cls()

    @classmethod
    def with_(cls, children: Iterable[Any]) -> "ColumnRenderable":
        return cls([child if isinstance(child, RenderableItem) else RenderableItem.Owned(child) for child in children])

    def push(self, child: Any) -> None:
        self.children.append(RenderableItem.Owned(child))

    def render(self, area: Rect, buf: Buffer) -> None:
        y = area.y
        for child in self.children:
            child_area = Rect.new(area.x, y, area.width, child.desired_height(area.width)).intersection(area)
            if not child_area.is_empty():
                child.render(child_area, buf)
            y += child_area.height

    def desired_height(self, width: int) -> int:
        return sum(child.desired_height(width) for child in self.children)

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        y = area.y
        for child in self.children:
            child_area = Rect.new(area.x, y, area.width, child.desired_height(area.width)).intersection(area)
            if not child_area.is_empty():
                pos = child.cursor_pos(child_area)
                if pos is not None:
                    return pos
            y += child_area.height
        return None

    def cursor_style(self, area: Rect) -> Any:
        y = area.y
        for child in self.children:
            child_area = Rect.new(area.x, y, area.width, child.desired_height(area.width)).intersection(area)
            if not child_area.is_empty() and child.cursor_pos(child_area) is not None:
                return child.cursor_style(child_area)
            y += child_area.height
        return DEFAULT_CURSOR_STYLE


@dataclass
class FlexChild:
    flex: int
    child: RenderableItem


@dataclass
class FlexRenderable:
    children: List[FlexChild] = field(default_factory=list)

    @classmethod
    def new(cls) -> "FlexRenderable":
        return cls()

    def push(self, flex: int, child: Any) -> None:
        item = child if isinstance(child, RenderableItem) else RenderableItem.Owned(child)
        self.children.append(FlexChild(flex=flex, child=item))

    def allocate(self, area: Rect) -> List[Rect]:
        child_sizes = [0 for _ in self.children]
        allocated_size = 0
        total_flex = 0
        last_flex_child_idx = 0
        max_size = area.height

        for i, child in enumerate(self.children):
            if child.flex > 0:
                total_flex += child.flex
                last_flex_child_idx = i
            else:
                size = min(child.child.desired_height(area.width), max(0, max_size - allocated_size))
                child_sizes[i] = size
                allocated_size += size

        free_space = max(0, max_size - allocated_size)
        allocated_flex_space = 0
        if total_flex > 0:
            space_per_flex = free_space // total_flex
            for i, child in enumerate(self.children):
                if child.flex > 0:
                    max_child_extent = (
                        free_space - allocated_flex_space
                        if i == last_flex_child_idx
                        else space_per_flex * child.flex
                    )
                    size = min(child.child.desired_height(area.width), max_child_extent)
                    child_sizes[i] = size
                    allocated_flex_space += size

        rects: List[Rect] = []
        y = area.y
        for size in child_sizes:
            rect = Rect.new(area.x, y, area.width, size)
            rects.append(rect)
            y += rect.height
        return rects

    def render(self, area: Rect, buf: Buffer) -> None:
        for rect, child in zip(self.allocate(area), self.children):
            child.child.render(rect, buf)

    def desired_height(self, width: int) -> int:
        allocated = self.allocate(Rect.new(0, 0, width, 65535))
        return allocated[-1].bottom() if allocated else 0

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        for rect, child in zip(self.allocate(area), self.children):
            pos = child.child.cursor_pos(rect)
            if pos is not None:
                return pos
        return None

    def cursor_style(self, area: Rect) -> Any:
        for rect, child in zip(self.allocate(area), self.children):
            if child.child.cursor_pos(rect) is not None:
                return child.child.cursor_style(rect)
        return DEFAULT_CURSOR_STYLE


@dataclass
class RowRenderable:
    children: List[Tuple[int, RenderableItem]] = field(default_factory=list)

    @classmethod
    def new(cls) -> "RowRenderable":
        return cls()

    def push(self, width: int, child: Any) -> None:
        self.children.append((width, RenderableItem.Owned(child)))

    def render(self, area: Rect, buf: Buffer) -> None:
        x = area.x
        for width, child in self.children:
            available_width = max(0, area.width - (x - area.x))
            child_area = Rect.new(x, area.y, min(width, available_width), area.height)
            if child_area.is_empty():
                break
            child.render(child_area, buf)
            x += width

    def desired_height(self, width: int) -> int:
        max_height = 0
        width_remaining = width
        for child_width, child in self.children:
            w = min(child_width, width_remaining)
            if w == 0:
                break
            max_height = max(max_height, child.desired_height(w))
            width_remaining = max(0, width_remaining - w)
        return max_height

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        x = area.x
        for width, child in self.children:
            available_width = max(0, area.width - (x - area.x))
            child_area = Rect.new(x, area.y, min(width, available_width), area.height)
            if not child_area.is_empty():
                pos = child.cursor_pos(child_area)
                if pos is not None:
                    return pos
            x += width
        return None

    def cursor_style(self, area: Rect) -> Any:
        x = area.x
        for width, child in self.children:
            available_width = max(0, area.width - (x - area.x))
            child_area = Rect.new(x, area.y, min(width, available_width), area.height)
            if not child_area.is_empty() and child.cursor_pos(child_area) is not None:
                return child.cursor_style(child_area)
            x += width
        return DEFAULT_CURSOR_STYLE


@dataclass
class InsetRenderable:
    child: RenderableItem
    insets: Insets

    @classmethod
    def new(cls, child: Any, insets: Insets) -> "InsetRenderable":
        item = child if isinstance(child, RenderableItem) else RenderableItem.Owned(child)
        return cls(child=item, insets=insets)

    def render(self, area: Rect, buf: Buffer) -> None:
        self.child.render(area.inset(self.insets), buf)

    def desired_height(self, width: int) -> int:
        inner_width = max(0, width - self.insets.left - self.insets.right)
        return self.child.desired_height(inner_width) + self.insets.top + self.insets.bottom

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return self.child.cursor_pos(area.inset(self.insets))

    def cursor_style(self, area: Rect) -> Any:
        return self.child.cursor_style(area.inset(self.insets))


class RenderableExt(Protocol):
    def inset(self, insets: Insets) -> RenderableItem: ...


def inset(value: Any, insets: Insets) -> RenderableItem:
    return RenderableItem.Owned(InsetRenderable.new(value, insets))


def _plain(value: Any) -> str:
    if hasattr(value, "plain"):
        plain = getattr(value, "plain")
        return plain() if callable(plain) else str(plain)
    if hasattr(value, "content"):
        return str(getattr(value, "content"))
    return str(value)


def _wrap_lines(lines: Iterable[str], width: int, wrap: bool) -> List[str]:
    if width <= 0:
        return ["" for _ in lines]
    wrapped: List[str] = []
    for line in lines:
        if not wrap:
            wrapped.append(line[:width])
            continue
        if not line:
            wrapped.append("")
            continue
        for start in range(0, len(line), width):
            wrapped.append(line[start : start + width])
    return wrapped


__all__ = [
    "Buffer",
    "ColumnRenderable",
    "DEFAULT_CURSOR_STYLE",
    "EmptyRenderable",
    "FlexChild",
    "FlexRenderable",
    "InsetRenderable",
    "Insets",
    "ParagraphRenderable",
    "RUST_MODULE",
    "Rect",
    "Renderable",
    "RenderableExt",
    "RenderableItem",
    "RowRenderable",
    "TextRenderable",
    "as_renderable",
    "cursor_pos",
    "cursor_style",
    "desired_height",
    "from_",
    "inset",
    "render",
]
