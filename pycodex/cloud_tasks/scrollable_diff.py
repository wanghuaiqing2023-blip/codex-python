"""Port of Rust ``codex-cloud-tasks/src/scrollable_diff.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
import unicodedata


SOFT_BREAK_CHARS = {",", ";", ".", ":", ")", "]", "}", "|", "/", "?", "!", "-", "_"}


@dataclass
class ScrollViewState:
    scroll: int = 0
    viewport_h: int = 0
    content_h: int = 0

    def clamp(self) -> None:
        max_scroll = max(0, self.content_h - self.viewport_h)
        if self.scroll > max_scroll:
            self.scroll = max_scroll


@dataclass
class ScrollableDiff:
    _raw: list[str] = field(default_factory=list)
    _wrapped: list[str] = field(default_factory=list)
    _wrapped_src_idx: list[int] = field(default_factory=list)
    _wrap_cols: int | None = None
    state: ScrollViewState = field(default_factory=ScrollViewState)

    @classmethod
    def new(cls) -> "ScrollableDiff":
        return cls()

    def set_content(self, lines: list[str]) -> None:
        self._raw = list(lines)
        self._wrapped.clear()
        self._wrapped_src_idx.clear()
        self.state.content_h = 0
        self._wrap_cols = None

    def set_width(self, width: int) -> None:
        width = max(0, int(width))
        if self._wrap_cols == width:
            return
        self._wrap_cols = width
        self._rewrap(width)
        self.state.clamp()

    def set_viewport(self, height: int) -> None:
        self.state.viewport_h = max(0, int(height))
        self.state.clamp()

    def wrapped_lines(self) -> list[str]:
        return self._wrapped

    def wrapped_src_indices(self) -> list[int]:
        return self._wrapped_src_idx

    def raw_line_at(self, idx: int) -> str:
        if 0 <= idx < len(self._raw):
            return self._raw[idx]
        return ""

    def scroll_by(self, delta: int) -> None:
        scroll = self.state.scroll + int(delta)
        self.state.scroll = min(max(scroll, 0), self._max_scroll())

    def page_by(self, delta: int) -> None:
        self.scroll_by(delta)

    def scroll_to_top(self) -> None:
        self.state.scroll = 0

    def scroll_to_bottom(self) -> None:
        self.state.scroll = self._max_scroll()

    def percent_scrolled(self) -> int | None:
        if self.state.content_h == 0 or self.state.viewport_h == 0:
            return None
        if self.state.content_h <= self.state.viewport_h:
            return None
        visible_bottom = self.state.scroll + self.state.viewport_h
        pct = round(visible_bottom / self.state.content_h * 100)
        return int(min(max(pct, 0), 100))

    def _max_scroll(self) -> int:
        return max(0, self.state.content_h - self.state.viewport_h)

    def _rewrap(self, width: int) -> None:
        if width == 0:
            self._wrapped = list(self._raw)
            self.state.content_h = len(self._wrapped)
            return

        max_cols = int(width)
        out: list[str] = []
        out_idx: list[int] = []
        for raw_idx, raw_line in enumerate(self._raw):
            raw = raw_line.replace("\t", "    ")
            if raw == "":
                out.append("")
                out_idx.append(raw_idx)
                continue

            line = ""
            line_cols = 0
            last_soft_idx: int | None = None
            for ch in raw:
                if ch == "\n":
                    out.append(line)
                    out_idx.append(raw_idx)
                    line = ""
                    line_cols = 0
                    last_soft_idx = None
                    continue

                width_ch = _char_width(ch)
                if line_cols + width_ch > max_cols:
                    if last_soft_idx is not None:
                        prefix = line[:last_soft_idx]
                        rest = line[last_soft_idx:]
                        out.append(prefix.rstrip())
                        out_idx.append(raw_idx)
                        line = rest.lstrip()
                        last_soft_idx = None
                    elif line:
                        out.append(line)
                        out_idx.append(raw_idx)
                        line = ""

                if ch.isspace() or ch in SOFT_BREAK_CHARS:
                    last_soft_idx = len(line)
                line += ch
                line_cols = _display_width(line)

            if line:
                out.append(line)
                out_idx.append(raw_idx)

        self._wrapped = out
        self._wrapped_src_idx = out_idx
        self.state.content_h = len(self._wrapped)


def _display_width(value: str) -> int:
    return sum(_char_width(ch) for ch in value)


def _char_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    category = unicodedata.category(ch)
    if category in {"Cc", "Cf"}:
        return 0
    if unicodedata.east_asian_width(ch) in {"F", "W"}:
        return 2
    return 1


__all__ = ["ScrollViewState", "ScrollableDiff"]
