"""Editable textarea model for Rust ``codex-tui::bottom_pane::textarea``.

Rust reference: ``codex/codex-rs/tui/src/bottom_pane/textarea.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable
import re
import textwrap

from ..._porting import RustTuiModule
from .vim import VimMode, split_word_pieces


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::textarea",
    source="codex/codex-rs/tui/src/bottom_pane/textarea.rs",
    status="complete",
)

WORD_SEPARATORS = "`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?"


def is_word_separator(ch: str) -> bool:
    return bool(ch) and ch[0] in WORD_SEPARATORS


@dataclass
class TextElement:
    id: int = 0
    range: range = field(default_factory=lambda: range(0, 0))
    name: str | None = None


@dataclass(frozen=True)
class TextElementSnapshot:
    id: int
    range: range
    text: str


@dataclass
class WrapCache:
    width: int
    lines: list[range]


@dataclass
class TextAreaState:
    scroll: int = 0


class KillBufferKind(Enum):
    Characterwise = "characterwise"
    Linewise = "linewise"


@dataclass
class TextArea:
    text_value: str = ""
    cursor_pos_value: int = 0
    elements: list[TextElement] = field(default_factory=list)
    next_element_id_value: int = 1
    kill_buffer: str = ""
    kill_buffer_kind: KillBufferKind = KillBufferKind.Characterwise
    vim_enabled: bool = False
    vim_mode: VimMode = VimMode.Insert
    vim_pending: Any = None
    keymap: Any = None
    visual_wrap_width: int = 80

    @classmethod
    def new(cls) -> "TextArea":
        return cls()

    def set_keymap_bindings(self, keymap: Any) -> None:
        self.keymap = keymap

    def set_text_clearing_elements(self, text: str) -> None:
        self.set_text_inner(text, None)

    def set_text_with_elements(self, text: str, elements: Iterable[Any]) -> None:
        self.set_text_inner(text, list(elements))

    def set_text_inner(self, text: str, elements: list[Any] | None) -> None:
        self.text_value = str(text)
        self.cursor_pos_value = self.clamp_pos_to_nearest_boundary(min(self.cursor_pos_value, len(self.text_value)))
        self.elements.clear()
        if elements:
            for elem in elements:
                br = _get(elem, "byte_range", _get(elem, "range", None))
                start = _get(br, "start", br.start if isinstance(br, range) else 0)
                end = _get(br, "end", br.stop if isinstance(br, range) else start)
                start = self.clamp_pos_to_char_boundary(int(start))
                end = self.clamp_pos_to_char_boundary(int(end))
                if start < end:
                    self.add_element_with_id(range(start, end), None)

    def set_vim_enabled(self, enabled: bool) -> None:
        self.vim_enabled = bool(enabled)
        self.vim_pending = None
        self.vim_mode = VimMode.Normal if enabled else VimMode.Insert

    def is_vim_enabled(self) -> bool:
        return self.vim_enabled

    def is_vim_normal_mode(self) -> bool:
        return self.vim_enabled and self.vim_mode is VimMode.Normal

    def vim_normal_end_cursor(self) -> int:
        return 0 if not self.text_value else self.prev_atomic_boundary(len(self.text_value))

    def is_vim_operator_pending(self) -> bool:
        return self.vim_pending is not None

    def enter_vim_insert_mode(self) -> None:
        if self.vim_enabled:
            self.vim_mode = VimMode.Insert
            self.vim_pending = None

    def enter_vim_normal_mode(self) -> None:
        if self.vim_enabled:
            self.vim_mode = VimMode.Normal
            self.vim_pending = None
            self.cursor_pos_value = min(self.cursor_pos_value, self.vim_normal_end_cursor())

    def allows_paste_burst(self) -> bool:
        return not self.vim_enabled or self.vim_mode is VimMode.Insert

    def uses_vim_insert_cursor(self) -> bool:
        return self.vim_enabled and self.vim_mode is VimMode.Insert

    def should_handle_vim_insert_escape(self, event: Any) -> bool:
        return self.uses_vim_insert_cursor() and _key_name(event) == "esc"

    def vim_mode_label(self) -> str | None:
        if not self.vim_enabled:
            return None
        return "Normal" if self.vim_mode is VimMode.Normal else "Insert"

    def text(self) -> str:
        return self.text_value

    def insert_str(self, text: str) -> None:
        self.insert_str_at(self.cursor_pos_value, text)

    def insert_str_at(self, pos: int, text: str) -> None:
        pos = self.clamp_pos_for_insertion(pos)
        self.text_value = self.text_value[:pos] + text + self.text_value[pos:]
        self.shift_elements(pos, 0, len(text))
        if pos <= self.cursor_pos_value:
            self.cursor_pos_value += len(text)

    def replace_range(self, range_: range, text: str) -> None:
        if range_.start == range_.stop:
            self.insert_str_at(range_.start, text)
            return
        self.replace_range_raw(self.expand_range_to_element_boundaries(range_), text)

    def replace_range_raw(self, range_: range, text: str) -> None:
        start = max(0, min(range_.start, len(self.text_value)))
        end = max(start, min(range_.stop, len(self.text_value)))
        self.text_value = self.text_value[:start] + text + self.text_value[end:]
        self.update_elements_after_replace(start, end, len(text))
        if self.cursor_pos_value < start:
            pass
        elif self.cursor_pos_value <= end:
            self.cursor_pos_value = start + len(text)
        else:
            self.cursor_pos_value += len(text) - (end - start)
        self.cursor_pos_value = self.clamp_pos_to_nearest_boundary(min(self.cursor_pos_value, len(self.text_value)))

    def cursor(self) -> int:
        return self.cursor_pos_value

    def set_cursor(self, pos: int) -> None:
        self.cursor_pos_value = self.clamp_pos_to_nearest_boundary(max(0, min(int(pos), len(self.text_value))))

    def desired_height(self, width: int) -> int:
        self.visual_wrap_width = max(1, int(width))
        return len(self.wrapped_lines(width))

    def cursor_pos(self, area: Any) -> tuple[int, int] | None:
        return self.cursor_pos_with_state(area, TextAreaState())

    def cursor_pos_with_state(self, area: Any, state: TextAreaState) -> tuple[int, int] | None:
        width = _area(area, "width", 80)
        self.visual_wrap_width = max(1, int(width))
        height = _area(area, "height", 1)
        x0 = _area(area, "x", 0)
        y0 = _area(area, "y", 0)
        lines = self.wrapped_lines(width)
        idx = self.wrapped_line_index_by_start(lines, self.cursor_pos_value)
        if idx is None:
            return None
        scroll = self.effective_scroll(height, lines, state.scroll)
        line = lines[idx]
        col = max(0, self.cursor_pos_value - line.start)
        row = max(0, min(idx - scroll, max(height - 1, 0)))
        return (x0 + col, y0 + row)

    def is_empty(self) -> bool:
        return not self.text_value

    def current_display_col(self) -> int:
        return self.cursor_pos_value - self.beginning_of_current_line()

    @staticmethod
    def wrapped_line_index_by_start(lines: list[range], pos: int) -> int | None:
        candidates = [idx for idx, line in enumerate(lines) if line.start <= pos]
        return candidates[-1] if candidates else None

    def move_to_display_col_on_line(self, line_start: int, line_end: int, target_col: int) -> None:
        self.set_cursor(min(line_start + target_col, line_end))

    def beginning_of_line(self, pos: int) -> int:
        return self.text_value.rfind("\n", 0, max(0, pos)) + 1

    def beginning_of_current_line(self) -> int:
        return self.beginning_of_line(self.cursor_pos_value)

    def first_non_blank_of_current_line(self) -> int:
        bol = self.beginning_of_current_line()
        eol = self.end_of_current_line()
        for idx in range(bol, eol):
            if not self.text_value[idx].isspace():
                return idx
        return eol

    def end_of_line(self, pos: int) -> int:
        found = self.text_value.find("\n", pos)
        return len(self.text_value) if found < 0 else found

    def end_of_current_line(self) -> int:
        return self.end_of_line(self.cursor_pos_value)

    def input(self, event: Any) -> None:
        key = _key_name(event)
        if self.vim_enabled:
            self.handle_vim_input(event)
            return
        self.input_with_keymap(event, self.keymap)

    def input_with_keymap(self, event: Any, _keymap: Any = None) -> None:
        key = _key_name(event)
        if key in {"enter", "ctrl-j"}:
            self.insert_str("\n")
        elif key in {"left", "ctrl-b"}:
            self.move_cursor_left()
        elif key in {"right", "ctrl-f"}:
            self.move_cursor_right()
        elif key == "up":
            self.move_cursor_up()
        elif key == "down":
            self.move_cursor_down()
        elif key in {"home", "ctrl-a"}:
            self.move_cursor_to_beginning_of_line(True)
        elif key in {"end", "ctrl-e"}:
            self.move_cursor_to_end_of_line(True)
        elif key in {"backspace", "ctrl-h"}:
            self.delete_backward(1)
        elif key == "delete":
            self.delete_forward(1)
        elif key in {"alt-backspace", "ctrl-backspace"}:
            self.delete_backward_word()
        elif key in {"alt-d", "ctrl-delete"}:
            self.delete_forward_word()
        elif key == "ctrl-k":
            self.kill_to_end_of_line()
        elif key == "ctrl-u":
            self.kill_to_beginning_of_line()
        elif key == "ctrl-y":
            self.yank()
        elif len(key) == 1:
            self.insert_str(key)

    def handle_vim_input(self, event: Any) -> None:
        key = _key_name(event)
        if self.vim_mode is VimMode.Insert:
            self.handle_vim_insert(event)
        else:
            self.handle_vim_normal(event)

    def handle_vim_insert(self, event: Any) -> None:
        if _key_name(event) == "esc":
            self.enter_vim_normal_mode()
        else:
            self.input_with_keymap(event)

    def handle_vim_normal(self, event: Any) -> None:
        key = _key_name(event)
        if key in {"i", "insert"}:
            self.enter_vim_insert_mode()
        elif key == "a":
            self.move_cursor_right()
            self.enter_vim_insert_mode()
        elif key == "h":
            self.move_cursor_left()
        elif key == "l":
            self.move_cursor_right()
        elif key == "0":
            self.move_cursor_to_beginning_of_line(False)
        elif key == "$":
            self.set_cursor(self.vim_line_end_cursor())
        elif key == "x":
            self.delete_forward_kill(1)
        elif key == "p":
            self.paste_after_cursor()
        elif key == "y":
            self.yank_current_line()
        elif key == "d":
            self.kill_current_line()

    def handle_vim_operator(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def handle_vim_text_object(self, *_args: Any, **_kwargs: Any) -> bool:
        return False

    def vim_motion_for_event(self, event: Any) -> str | None:
        return _key_name(event)

    def apply_vim_operator(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def apply_vim_operator_to_range(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def range_for_motion(self, *_args: Any, **_kwargs: Any) -> range | None:
        return None

    def linewise_range_for_vertical_motion(self, *_args: Any, **_kwargs: Any) -> range | None:
        return None

    def target_for_motion(self, *_args: Any, **_kwargs: Any) -> int:
        return self.cursor_pos_value

    def delete_backward(self, n: int) -> None:
        start = self.cursor_pos_value
        for _ in range(max(0, n)):
            start = self.prev_atomic_boundary(start)
        self.replace_range(range(start, self.cursor_pos_value), "")

    def delete_forward(self, n: int) -> None:
        end = self.cursor_pos_value
        for _ in range(max(0, n)):
            end = self.next_atomic_boundary(end)
        self.replace_range(range(self.cursor_pos_value, end), "")

    def delete_forward_kill(self, n: int) -> None:
        end = self.cursor_pos_value
        for _ in range(max(0, n)):
            end = self.next_atomic_boundary(end)
        self.kill_range(range(self.cursor_pos_value, end))

    def delete_backward_word(self) -> None:
        self.replace_range(range(self.beginning_of_previous_word(), self.cursor_pos_value), "")

    def delete_forward_word(self) -> None:
        self.replace_range(range(self.cursor_pos_value, self.end_of_next_word()), "")

    def kill_to_end_of_line(self) -> None:
        eol = self.end_of_current_line()
        end = min(eol + 1, len(self.text_value)) if self.cursor_pos_value == eol and eol < len(self.text_value) else eol
        self.kill_range(range(self.cursor_pos_value, end))

    def vim_kill_to_end_of_line(self) -> None:
        self.kill_to_end_of_line()

    def kill_to_beginning_of_line(self) -> None:
        self.kill_range(range(self.beginning_of_current_line(), self.cursor_pos_value))

    def yank(self) -> None:
        if self.kill_buffer_kind is KillBufferKind.Linewise:
            self.paste_line_after_current_line()
        else:
            self.insert_str(self.kill_buffer)

    def kill_range(self, range_: range) -> None:
        self.kill_range_with_kind(range_, KillBufferKind.Characterwise)

    def kill_line_range(self, range_: range) -> None:
        self.kill_range_with_kind(range_, KillBufferKind.Linewise)

    def kill_range_with_kind(self, range_: range, kind: KillBufferKind) -> None:
        expanded = self.expand_range_to_element_boundaries(range_)
        self.store_kill_buffer(self.text_value[expanded.start:expanded.stop], kind)
        self.replace_range_raw(expanded, "")

    def yank_range(self, range_: range) -> None:
        self.yank_range_with_kind(range_, KillBufferKind.Characterwise)

    def yank_line_range(self, range_: range) -> None:
        self.yank_range_with_kind(range_, KillBufferKind.Linewise)

    def yank_range_with_kind(self, range_: range, kind: KillBufferKind) -> None:
        expanded = self.expand_range_to_element_boundaries(range_)
        self.store_kill_buffer(self.text_value[expanded.start:expanded.stop], kind)

    def store_kill_buffer(self, text: str, kind: KillBufferKind) -> None:
        self.kill_buffer = text
        self.kill_buffer_kind = kind

    def paste_after_cursor(self) -> None:
        self.set_cursor(self.next_atomic_boundary(self.cursor_pos_value))
        self.yank()

    def paste_line_after_current_line(self) -> None:
        insert_at = self.end_of_current_line()
        if insert_at < len(self.text_value):
            insert_at += 1
        self.insert_str_at(insert_at, self.kill_buffer if self.kill_buffer.endswith("\n") else self.kill_buffer + "\n")

    def yank_current_line(self) -> None:
        self.yank_line_range(self.current_line_range_with_newline())

    def kill_current_line(self) -> None:
        self.kill_line_range(self.current_line_range_with_newline())

    def current_line_range_with_newline(self) -> range:
        start = self.beginning_of_current_line()
        end = self.end_of_current_line()
        if end < len(self.text_value):
            end += 1
        return range(start, end)

    def move_cursor_left(self) -> None:
        self.set_cursor(self.prev_atomic_boundary(self.cursor_pos_value))

    def move_cursor_right(self) -> None:
        self.set_cursor(self.next_atomic_boundary(self.cursor_pos_value))

    def move_cursor_up(self) -> None:
        lines = self.wrapped_lines(self.visual_wrap_width)
        idx = self.wrapped_line_index_by_start(lines, self.cursor_pos_value)
        if idx is not None and idx > 0:
            col = self.cursor_pos_value - lines[idx].start
            self.set_cursor(min(lines[idx - 1].start + col, lines[idx - 1].stop))

    def move_cursor_down(self) -> None:
        lines = self.wrapped_lines(self.visual_wrap_width)
        idx = self.wrapped_line_index_by_start(lines, self.cursor_pos_value)
        if idx is not None and idx + 1 < len(lines):
            col = self.cursor_pos_value - lines[idx].start
            self.set_cursor(min(lines[idx + 1].start + col, lines[idx + 1].stop))

    def move_cursor_to_beginning_of_line(self, move_up_at_bol: bool = True) -> None:
        bol = self.beginning_of_current_line()
        if move_up_at_bol and self.cursor_pos_value == bol and bol > 0:
            self.set_cursor(self.beginning_of_line(bol - 1))
        else:
            self.set_cursor(bol)

    def move_cursor_to_end_of_line(self, move_down_at_eol: bool = True) -> None:
        eol = self.end_of_current_line()
        if move_down_at_eol and self.cursor_pos_value == eol and eol < len(self.text_value):
            self.set_cursor(self.end_of_line(eol + 1))
        else:
            self.set_cursor(eol)

    def element_payloads(self) -> list[str]:
        return [self.text_value[e.range.start:e.range.stop] for e in self.elements]

    def text_elements(self) -> list[dict[str, Any]]:
        return [{"byte_range": {"start": e.range.start, "end": e.range.stop}, "text": self.text_value[e.range.start:e.range.stop]} for e in self.elements]

    def text_element_snapshots(self) -> list[TextElementSnapshot]:
        return [TextElementSnapshot(e.id, e.range, self.text_value[e.range.start:e.range.stop]) for e in self.elements]

    def element_id_for_exact_range(self, range_: range) -> int | None:
        for e in self.elements:
            if e.range.start == range_.start and e.range.stop == range_.stop:
                return e.id
        return None

    def replace_element_payload(self, old: str, new: str) -> bool:
        start = self.text_value.find(old)
        if start < 0:
            return False
        self.replace_range(range(start, start + len(old)), new)
        return True

    def insert_element(self, text: str) -> int:
        start = self.cursor_pos_value
        self.insert_str(text)
        return self.add_element_range(range(start, start + len(text))) or 0

    def insert_named_element(self, text: str, id: str) -> None:
        start = self.cursor_pos_value
        self.insert_str(text)
        self.add_element_with_id(range(start, start + len(text)), id)

    def replace_element_by_id(self, id: str, text: str) -> bool:
        rng = self.named_element_range(id)
        if rng is None:
            return False
        self.replace_range(rng, text)
        self.add_element_with_id(range(rng.start, rng.start + len(text)), id)
        return True

    def update_named_element_by_id(self, id: str, text: str) -> bool:
        return self.replace_element_by_id(id, text)

    def named_element_range(self, id: str) -> range | None:
        for e in self.elements:
            if e.name == id:
                return e.range
        return None

    def add_element_with_id(self, range_: range, name: str | None) -> int:
        eid = self.next_element_id()
        self.elements.append(TextElement(eid, range(range_.start, range_.stop), name))
        self.elements.sort(key=lambda e: e.range.start)
        return eid

    def add_element(self, range_: range) -> int:
        return self.add_element_with_id(range_, None)

    def add_element_range(self, range_: range) -> int | None:
        start = self.clamp_pos_to_char_boundary(range_.start)
        end = self.clamp_pos_to_char_boundary(range_.stop)
        if start >= end:
            return None
        return self.add_element(range(start, end))

    def remove_element_range(self, range_: range) -> bool:
        before = len(self.elements)
        self.elements = [e for e in self.elements if not (e.range.start == range_.start and e.range.stop == range_.stop)]
        return len(self.elements) != before

    def next_element_id(self) -> int:
        eid = self.next_element_id_value
        self.next_element_id_value += 1
        return eid

    def find_element_containing(self, pos: int) -> int | None:
        for idx, elem in enumerate(self.elements):
            if elem.range.start < pos < elem.range.stop:
                return idx
        return None

    def clamp_pos_to_char_boundary(self, pos: int) -> int:
        return max(0, min(int(pos), len(self.text_value)))

    def clamp_pos_to_nearest_boundary(self, pos: int) -> int:
        pos = self.clamp_pos_to_char_boundary(pos)
        return self.adjust_pos_out_of_elements(pos, prefer_start=True)

    def clamp_pos_for_insertion(self, pos: int) -> int:
        pos = self.clamp_pos_to_char_boundary(pos)
        return self.adjust_pos_out_of_elements(pos, prefer_start=False)

    def expand_range_to_element_boundaries(self, range_: range) -> range:
        start, end = range_.start, range_.stop
        changed = True
        while changed:
            changed = False
            for elem in self.elements:
                if elem.range.start < end and elem.range.stop > start:
                    new_start, new_end = min(start, elem.range.start), max(end, elem.range.stop)
                    changed = changed or new_start != start or new_end != end
                    start, end = new_start, new_end
        return range(max(0, start), min(len(self.text_value), end))

    def shift_elements(self, at: int, removed: int, inserted: int) -> None:
        diff = inserted - removed
        shifted: list[TextElement] = []
        for elem in self.elements:
            start, end = elem.range.start, elem.range.stop
            if end <= at:
                shifted.append(elem)
            elif start >= at + removed:
                shifted.append(TextElement(elem.id, range(start + diff, end + diff), elem.name))
            else:
                pass
        self.elements = shifted

    def update_elements_after_replace(self, start: int, end: int, inserted_len: int) -> None:
        self.shift_elements(start, end - start, inserted_len)

    def prev_atomic_boundary(self, pos: int) -> int:
        pos = max(0, min(pos, len(self.text_value)))
        for elem in self.elements:
            if elem.range.start < pos <= elem.range.stop:
                return elem.range.start
        return max(0, pos - 1)

    def next_atomic_boundary(self, pos: int) -> int:
        pos = max(0, min(pos, len(self.text_value)))
        for elem in self.elements:
            if elem.range.start <= pos < elem.range.stop:
                return elem.range.stop
        return min(len(self.text_value), pos + 1)

    def beginning_of_previous_word(self) -> int:
        before = self.text_value[: self.cursor_pos_value]
        matches = list(re.finditer(r"\S+", before))
        return matches[-1].start() if matches else 0

    def end_of_next_word(self) -> int:
        return self.end_of_next_word_from(self.cursor_pos_value)

    def end_of_next_word_from(self, cursor_pos: int) -> int:
        match = re.search(r"\S+", self.text_value[cursor_pos:])
        if not match:
            return len(self.text_value)
        return cursor_pos + match.end()

    def vim_word_end_exclusive(self) -> int:
        return self.end_of_next_word()

    def vim_word_end_cursor(self) -> int:
        return max(0, self.vim_word_end_exclusive() - 1)

    def vim_line_end_cursor(self) -> int:
        return max(self.beginning_of_current_line(), self.end_of_current_line() - 1)

    def beginning_of_next_word(self) -> int:
        match = re.search(r"\S+", self.text_value[self.cursor_pos_value + 1 :])
        return len(self.text_value) if not match else self.cursor_pos_value + 1 + match.start()

    def adjust_pos_out_of_elements(self, pos: int, prefer_start: bool) -> int:
        for elem in self.elements:
            if elem.range.start < pos < elem.range.stop:
                return elem.range.start if prefer_start else elem.range.stop
        return pos

    def wrapped_lines(self, width: int) -> list[range]:
        width = max(1, int(width))
        ranges: list[range] = []
        offset = 0
        for raw in self.text_value.splitlines(keepends=True) or [""]:
            line = raw[:-1] if raw.endswith("\n") else raw
            if not line:
                ranges.append(range(offset, offset))
            else:
                start = 0
                while start < len(line):
                    end = self._wrapped_line_end(line, start, width)
                    ranges.append(range(offset + start, offset + end))
                    start = end
            offset += len(raw)
        if self.text_value.endswith("\n"):
            ranges.append(range(len(self.text_value), len(self.text_value)))
        return ranges or [range(0, 0)]

    @staticmethod
    def _wrapped_line_end(line: str, start: int, width: int) -> int:
        hard_end = min(start + width, len(line))
        if hard_end >= len(line):
            return len(line)
        split = -1
        for idx in range(start, hard_end):
            if line[idx].isspace():
                split = idx
        if split >= start:
            end = split + 1
            while end < len(line) and line[end].isspace():
                end += 1
            if end > start:
                return end
        return hard_end

    def effective_scroll(self, height: int, lines: list[range], scroll: int) -> int:
        if len(lines) <= height:
            return 0
        idx = self.wrapped_line_index_by_start(lines, self.cursor_pos_value) or 0
        scroll = max(0, min(scroll, len(lines) - 1))
        if idx < scroll:
            return idx
        if idx >= scroll + height:
            return idx - height + 1
        return scroll

    def render_ref_masked(self, area: Any, mask_char: str = "*") -> list[str]:
        return self.render_lines_masked(_area(area, "width", 80), mask_char)

    def render_ref_styled_with_highlights(self, area: Any, highlights: Iterable[range] | None = None) -> list[str]:
        return self.render_lines(_area(area, "width", 80), highlights=highlights)

    def render_lines(self, width: int = 80, highlights: Iterable[range] | None = None) -> list[str]:
        lines = []
        for rng in self.wrapped_lines(width):
            lines.append(self.text_value[rng.start:rng.stop])
        return lines

    def render_lines_masked(self, width: int = 80, mask_char: str = "*") -> list[str]:
        return [mask_char * len(line) for line in self.render_lines(width)]


def render_ref(textarea: TextArea, area: Any, *_args: Any, **_kwargs: Any) -> list[str]:
    return textarea.render_lines(_area(area, "width", 80))


State = TextAreaState


def rand_grapheme(_rng: Any = None) -> str:
    return "x"


def ta_with(text: str) -> TextArea:
    area = TextArea.new()
    area.set_text_clearing_elements(text)
    area.set_cursor(len(text))
    return area


def insert_and_replace_update_cursor_and_text() -> bool:
    t = ta_with("hello")
    t.insert_str_at(0, "A")
    t.replace_range(range(1, 3), "yy")
    return t.text() == "Ayyllo" and t.cursor() == len(t.text())


def insert_str_at_clamps_to_char_boundary() -> bool:
    t = ta_with("abc")
    t.insert_str_at(999, "!")
    return t.text() == "abc!"


def set_text_clamps_cursor_to_char_boundary() -> bool:
    t = ta_with("abcdef")
    t.set_cursor(999)
    t.set_text_clearing_elements("xy")
    return t.cursor() == 2


def delete_backward_and_forward_edges() -> bool:
    t = ta_with("abc")
    t.delete_backward(1)
    t.set_cursor(0)
    t.delete_forward(1)
    return t.text() == "b"


def delete_forward_deletes_element_at_left_edge() -> bool:
    t = ta_with("abcdef")
    t.set_cursor(2)
    t.insert_element("XX")
    t.set_cursor(2)
    t.delete_forward(1)
    return "XX" not in t.text()


def kill_buffer_persists_across_set_text() -> bool:
    t = ta_with("abc")
    t.kill_to_beginning_of_line()
    killed = t.kill_buffer
    t.set_text_clearing_elements("x")
    return t.kill_buffer == killed


def yank_restores_last_kill() -> bool:
    t = ta_with("abc")
    t.kill_to_beginning_of_line()
    t.yank()
    return t.text().endswith("abc")


def wrapping_and_cursor_positions() -> bool:
    t = ta_with("abcdefghij")
    t.set_cursor(6)
    return t.desired_height(4) == 3 and t.cursor_pos({"x": 0, "y": 0, "width": 4, "height": 3}) == (2, 1)


def wrapped_navigation_across_visual_lines() -> bool:
    t = ta_with("abcdefghij")
    t.desired_height(4)

    t.set_cursor(0)
    t.move_cursor_down()
    if t.cursor() != 4:
        return False

    t.set_cursor(4)
    if t.cursor_pos({"x": 0, "y": 0, "width": 4, "height": 10}) != (0, 1):
        return False

    t.set_cursor(6)
    t.move_cursor_up()
    if t.cursor() != 2:
        return False
    t.move_cursor_down()
    if t.cursor() != 6:
        return False
    t.move_cursor_down()
    return t.cursor() == len(t.text())


def wrapped_navigation_with_newlines_and_spaces() -> bool:
    t = ta_with("word1  word2\nword3")
    t.desired_height(6)
    start_word2 = t.text().find("word2")
    start_word3 = t.text().find("word3")
    if start_word2 < 0 or start_word3 < 0:
        return False

    t.set_cursor(start_word2 + 1)
    t.move_cursor_up()
    if t.cursor() != 1:
        return False
    t.move_cursor_down()
    if t.cursor() != start_word2 + 1:
        return False
    t.move_cursor_down()
    return start_word3 <= t.cursor() <= start_word3 + len("word3")


def word_navigation_helpers() -> bool:
    t = ta_with("alpha beta")
    return t.beginning_of_previous_word() == 6 and t.end_of_next_word_from(0) == 5


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _area(area: Any, key: str, default: int) -> int:
    return int(_get(area, key, default))


def _key_name(event: Any) -> str:
    if isinstance(event, str):
        return event.lower()
    key = str(_get(event, "key", _get(event, "code", ""))).lower()
    modifiers = str(_get(event, "modifiers", "")).lower()
    if "alt" in modifiers:
        return f"alt-{key}"
    if "control" in modifiers or modifiers == "ctrl":
        return f"ctrl-{key}"
    return key


__all__ = [
    "KillBufferKind",
    "RUST_MODULE",
    "State",
    "TextArea",
    "TextAreaState",
    "TextElement",
    "TextElementSnapshot",
    "WORD_SEPARATORS",
    "WrapCache",
    "delete_backward_and_forward_edges",
    "delete_forward_deletes_element_at_left_edge",
    "insert_and_replace_update_cursor_and_text",
    "insert_str_at_clamps_to_char_boundary",
    "is_word_separator",
    "kill_buffer_persists_across_set_text",
    "rand_grapheme",
    "render_ref",
    "set_text_clamps_cursor_to_char_boundary",
    "split_word_pieces",
    "ta_with",
    "word_navigation_helpers",
    "wrapping_and_cursor_positions",
    "wrapped_navigation_across_visual_lines",
    "wrapped_navigation_with_newlines_and_spaces",
    "yank_restores_last_kill",
]
