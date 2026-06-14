"""Incremental live row wrapping for ``codex-tui::live_wrap``.

Rust source: ``codex/codex-rs/tui/src/live_wrap.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._porting import RustTuiModule
from .line_truncation import _display_width

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="live_wrap",
    source="codex/codex-rs/tui/src/live_wrap.rs",
)


@dataclass(eq=True)
class Row:
    text: str
    explicit_break: bool

    def width(self) -> int:
        return _display_width(self.text)


@dataclass
class RowBuilder:
    target_width: int
    current_line: str = ""
    _rows: list[Row] = field(default_factory=list)

    @classmethod
    def new(cls, target_width: int) -> "RowBuilder":
        return cls(target_width=max(1, int(target_width)))

    def width(self) -> int:
        return self.target_width

    def set_width(self, width: int) -> None:
        self.target_width = max(1, int(width))
        all_text = ""
        for row in self._rows:
            all_text += row.text
            if row.explicit_break:
                all_text += "\n"
        all_text += self.current_line
        self._rows.clear()
        self.current_line = ""
        self.push_fragment(all_text)

    def push_fragment(self, fragment: str) -> None:
        if fragment == "":
            return
        start = 0
        for index, ch in enumerate(fragment):
            if ch == "\n":
                if start < index:
                    self.current_line += fragment[start:index]
                self.flush_current_line(True)
                start = index + 1
        if start < len(fragment):
            self.current_line += fragment[start:]
            self.wrap_current_line()

    def end_line(self) -> None:
        self.flush_current_line(True)

    def rows(self) -> list[Row]:
        return list(self._rows)

    def display_rows(self) -> list[Row]:
        out = list(self._rows)
        if self.current_line:
            out.append(Row(self.current_line, False))
        return out

    def drain_commit_ready(self, max_keep: int) -> list[Row]:
        display_count = len(self._rows) + (0 if self.current_line == "" else 1)
        if display_count <= max_keep:
            return []
        to_commit = display_count - max_keep
        commit_count = min(to_commit, len(self._rows))
        drained = self._rows[:commit_count]
        del self._rows[:commit_count]
        return drained

    def flush_current_line(self, explicit_break: bool) -> None:
        self.wrap_current_line()
        if explicit_break:
            if self.current_line == "":
                self._rows.append(Row("", True))
            else:
                self._rows.append(Row(self.current_line, True))
        self.current_line = ""

    def wrap_current_line(self) -> None:
        while self.current_line:
            prefix, suffix, taken = take_prefix_by_width(self.current_line, self.target_width)
            if taken == 0:
                first = self.current_line[0]
                self._rows.append(Row(first, False))
                self.current_line = self.current_line[1:]
                continue
            if suffix == "":
                break
            self._rows.append(Row(prefix, False))
            self.current_line = suffix


def take_prefix_by_width(text: str, max_cols: int) -> tuple[str, str, int]:
    if max_cols == 0 or text == "":
        return "", text, 0
    cols = 0
    end_idx = 0
    for idx, ch in enumerate(text):
        ch_width = _display_width(ch)
        if cols + ch_width > max_cols:
            break
        cols += ch_width
        end_idx = idx + 1
        if cols == max_cols:
            break
    return text[:end_idx], text[end_idx:], cols


__all__ = [
    "RUST_MODULE",
    "Row",
    "RowBuilder",
    "take_prefix_by_width",
]
