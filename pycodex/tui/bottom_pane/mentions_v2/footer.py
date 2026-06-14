"""Footer rendering semantics for Rust bottom_pane/mentions_v2/footer.rs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..._porting import RustTuiModule
from .search_mode import SearchMode

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::footer",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/footer.rs",
)


@dataclass(frozen=True)
class FooterSpan:
    text: str
    style: tuple[str, ...] = ()


@dataclass(frozen=True)
class FooterLine:
    spans: tuple[FooterSpan, ...] = field(default_factory=tuple)

    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    def width(self) -> int:
        return len(self.text())


@dataclass(frozen=True)
class RenderedFooter:
    width: int
    left_width: int
    gap: int
    left: FooterLine
    right: FooterLine
    text: str


def render_footer(area: Any, buf: Any = None, search_mode: SearchMode = SearchMode.RESULTS) -> RenderedFooter:
    width = _area_width(area)
    right_line = search_mode_indicator_line(search_mode)
    right_width = right_line.width()
    gap = 1 if right_width > 0 else 0
    left_width = max(width - right_width - gap, 0)
    left_line = truncate_line_with_ellipsis_if_overflow(footer_hint_line(), left_width)
    right_text = right_line.text() if right_width > 0 and right_width <= width else ""
    if right_text:
        combined = left_line.text().ljust(left_width) + (" " if gap else "") + right_text
    else:
        combined = left_line.text().ljust(width)
    combined = combined[:width]
    rendered = RenderedFooter(width=width, left_width=left_width, gap=gap, left=left_line, right=right_line, text=combined)
    if isinstance(buf, list):
        buf.append(rendered)
    elif hasattr(buf, "append"):
        buf.append(rendered)
    return rendered


def footer_hint_line() -> FooterLine:
    return FooterLine(
        (
            FooterSpan("Enter"),
            FooterSpan(" insert | ", ("dim",)),
            FooterSpan("Esc"),
            FooterSpan(" close | ", ("dim",)),
            FooterSpan("Left"),
            FooterSpan("/", ("dim",)),
            FooterSpan("Right"),
            FooterSpan(" switch search modes", ("dim",)),
        )
    )


def search_mode_indicator_line(active_search_mode: SearchMode) -> FooterLine:
    active = SearchMode(active_search_mode)
    spans: list[FooterSpan] = []
    for index, mode in enumerate((SearchMode.RESULTS, SearchMode.FILESYSTEM_ONLY, SearchMode.TOOLS)):
        if index > 0:
            spans.append(FooterSpan("  ", ("dim",)))
        if mode is active:
            color = "magenta" if mode is SearchMode.TOOLS else "cyan"
            spans.append(FooterSpan(f"[{mode.label()}]", (color, "bold")))
        else:
            spans.append(FooterSpan(f" {mode.label()} ", ("dim",)))
    return FooterLine(tuple(spans))


def truncate_line_with_ellipsis_if_overflow(line: FooterLine, width: int) -> FooterLine:
    width = max(int(width), 0)
    if line.width() <= width:
        return line
    if width == 0:
        return FooterLine(())
    if width == 1:
        return FooterLine((FooterSpan("..."[:1], ("dim",)),))
    text = line.text()
    truncated = text[: max(width - 1, 0)] + "..."[:1]
    return FooterLine((FooterSpan(truncated),))


def line_text(line: FooterLine) -> str:
    return line.text()


def _area_width(area: Any) -> int:
    if isinstance(area, int):
        return max(area, 0)
    if isinstance(area, dict):
        return max(int(area.get("width", 0)), 0)
    return max(int(getattr(area, "width", 0)), 0)


__all__ = [
    "FooterLine",
    "FooterSpan",
    "RenderedFooter",
    "RUST_MODULE",
    "footer_hint_line",
    "line_text",
    "render_footer",
    "search_mode_indicator_line",
    "truncate_line_with_ellipsis_if_overflow",
]
