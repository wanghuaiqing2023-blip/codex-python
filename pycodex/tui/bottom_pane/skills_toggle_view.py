"""Skills enable/disable popup view.

Python port of Rust ``codex-tui::bottom_pane::skills_toggle_view``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::skills_toggle_view",
    source="codex/codex-rs/tui/src/bottom_pane/skills_toggle_view.rs",
)

SEARCH_PLACEHOLDER = "Type to search skills"
SEARCH_PROMPT_PREFIX = "> "
SKILL_NAME_TRUNCATE_LEN = 21


@dataclass
class SkillsToggleItem:
    name: str
    skill_name: str
    description: str
    enabled: bool
    path: Any


@dataclass(frozen=True)
class DisplayRow:
    name: str
    description: str | None = None
    selected: bool = False


@dataclass(frozen=True)
class DisplayLine:
    text: str
    style: str = "plain"


@dataclass
class SkillsToggleView:
    items: list[SkillsToggleItem]
    app_event_tx: Any = None
    keymap: Any = None
    selected_idx: int | None = None
    scroll_top: int = 0
    complete: bool = False
    search_query: str = ""
    filtered_indices: list[int] = field(default_factory=list)
    header: tuple[str, str] = (
        "Enable/Disable Skills",
        "Turn skills on or off. Your changes are saved automatically.",
    )
    footer_hint: str = field(default_factory=lambda: skills_toggle_hint_line())

    @classmethod
    def new(
        cls,
        items: Iterable[SkillsToggleItem],
        app_event_tx: Any = None,
        keymap: Any = None,
    ) -> "SkillsToggleView":
        view = cls(list(items), app_event_tx=app_event_tx, keymap=keymap)
        view.footer_hint = skills_toggle_hint_line(keymap)
        view.apply_filter()
        return view

    def visible_len(self) -> int:
        return len(self.filtered_indices)

    @staticmethod
    def max_visible_rows(length: int) -> int:
        return min(MAX_POPUP_ROWS, max(1, int(length)))

    def apply_filter(self) -> None:
        previous_actual = None
        if self.selected_idx is not None and 0 <= self.selected_idx < len(self.filtered_indices):
            previous_actual = self.filtered_indices[self.selected_idx]

        filter_text = self.search_query.strip()
        if not filter_text:
            self.filtered_indices = list(range(len(self.items)))
        else:
            matches: list[tuple[int, int]] = []
            for idx, item in enumerate(self.items):
                match = match_skill(filter_text, item.name, item.skill_name)
                if match is not None:
                    _indices, score = match
                    matches.append((idx, score))
            matches.sort(key=lambda pair: (pair[1], self.items[pair[0]].name))
            self.filtered_indices = [idx for idx, _score in matches]

        length = len(self.filtered_indices)
        if previous_actual is not None and previous_actual in self.filtered_indices:
            self.selected_idx = self.filtered_indices.index(previous_actual)
        else:
            self.selected_idx = 0 if length > 0 else None
        self._clamp_selection()
        self._ensure_visible()

    def build_rows(self) -> list[DisplayRow]:
        rows: list[DisplayRow] = []
        for visible_idx, actual_idx in enumerate(self.filtered_indices):
            item = self.items[actual_idx]
            selected = self.selected_idx == visible_idx
            prefix = "›" if selected else " "
            marker = "x" if item.enabled else " "
            rows.append(
                DisplayRow(
                    name=f"{prefix} [{marker}] {truncate_skill_name(item.name)}",
                    description=item.description,
                    selected=selected,
                )
            )
        return rows

    def move_up(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current - 1) % length
        self._ensure_visible()

    def move_down(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = (current + 1) % length
        self._ensure_visible()

    def page_up(self) -> None:
        length = self.visible_len()
        visible = self.max_visible_rows(length)
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = max(0, current - visible)
        self._ensure_visible()

    def page_down(self) -> None:
        length = self.visible_len()
        visible = self.max_visible_rows(length)
        if length == 0:
            return
        current = self.selected_idx if self.selected_idx is not None else 0
        self.selected_idx = min(length - 1, current + visible)
        self._ensure_visible()

    def jump_top(self) -> None:
        if self.visible_len() == 0:
            return
        self.selected_idx = 0
        self._ensure_visible()

    def jump_bottom(self) -> None:
        length = self.visible_len()
        if length == 0:
            return
        self.selected_idx = length - 1
        self._ensure_visible()

    def toggle_selected(self) -> None:
        if self.selected_idx is None:
            return
        if not (0 <= self.selected_idx < len(self.filtered_indices)):
            return
        actual_idx = self.filtered_indices[self.selected_idx]
        item = self.items[actual_idx]
        item.enabled = not item.enabled
        _send(
            self.app_event_tx,
            {"type": "SetSkillEnabled", "path": item.path, "enabled": item.enabled},
        )

    def close(self) -> None:
        if self.complete:
            return
        self.complete = True
        _send(self.app_event_tx, {"type": "ManageSkillsClosed"})
        _list_skills(self.app_event_tx, [], True)

    @staticmethod
    def rows_width(total_width: int) -> int:
        return max(0, int(total_width) - 2)

    def rows_height(self, rows: list[DisplayRow]) -> int:
        return min(MAX_POPUP_ROWS, max(1, len(rows)))

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        plain_text = _is_plain_text_key(key_event)
        if not plain_text and key in {"up", "k"}:
            self.move_up()
        elif not plain_text and key in {"down", "j"}:
            self.move_down()
        elif not plain_text and key in {"pageup", "page_up"}:
            self.page_up()
        elif not plain_text and key in {"pagedown", "page_down"}:
            self.page_down()
        elif not plain_text and key in {"home", "g"}:
            self.jump_top()
        elif not plain_text and key == "end":
            self.jump_bottom()
        elif key == "backspace":
            self.search_query = self.search_query[:-1]
            self.apply_filter()
        elif key == " ":
            self.toggle_selected()
        elif key == "enter":
            self.toggle_selected()
        elif key == "esc":
            self.on_ctrl_c()
        elif len(key) == 1 and not _has_control_or_alt(key_event):
            self.search_query += key
            self.apply_filter()

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.close()
        return "Handled"

    def desired_height(self, width: int) -> int:
        rows = self.build_rows()
        return len(self.header) + self.rows_height(rows) + 6

    def render(self, area: Any = None, buf: Any = None) -> list[DisplayLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width == 0 or height == 0:
            return []
        lines = [
            DisplayLine(self.header[0], "title"),
            DisplayLine(self.header[1], "dim"),
            DisplayLine(""),
            DisplayLine(SEARCH_PLACEHOLDER, "placeholder"),
            DisplayLine(SEARCH_PROMPT_PREFIX + self.search_query if self.search_query else SEARCH_PROMPT_PREFIX, "search"),
        ]
        rows = self.build_rows()
        if rows:
            for row in rows[self.scroll_top : self.scroll_top + self.max_visible_rows(len(rows))]:
                lines.append(DisplayLine(row.name, "selected" if row.selected else "plain"))
                if row.description:
                    lines.append(DisplayLine(row.description, "description"))
        else:
            lines.append(DisplayLine("no matches", "empty"))
        lines.append(DisplayLine(self.footer_hint, "hint"))
        return lines[:height]

    def _clamp_selection(self) -> None:
        length = self.visible_len()
        if length == 0:
            self.selected_idx = None
            self.scroll_top = 0
        elif self.selected_idx is None:
            self.selected_idx = 0
        else:
            self.selected_idx = max(0, min(self.selected_idx, length - 1))

    def _ensure_visible(self) -> None:
        length = self.visible_len()
        if self.selected_idx is None or length == 0:
            self.scroll_top = 0
            return
        visible = self.max_visible_rows(length)
        if self.selected_idx < self.scroll_top:
            self.scroll_top = self.selected_idx
        elif self.selected_idx >= self.scroll_top + visible:
            self.scroll_top = self.selected_idx + 1 - visible
        self.scroll_top = max(0, min(self.scroll_top, max(0, length - visible)))


def truncate_skill_name(name: str) -> str:
    text = str(name)
    if len(text) <= SKILL_NAME_TRUNCATE_LEN:
        return text
    if SKILL_NAME_TRUNCATE_LEN <= 1:
        return "…"[:SKILL_NAME_TRUNCATE_LEN]
    return text[: SKILL_NAME_TRUNCATE_LEN - 1] + "…"


def match_skill(filter_text: str, display_name: str, skill_name: str) -> tuple[list[int] | None, int] | None:
    display = _subsequence_match_indices(filter_text, display_name)
    if display is not None:
        return display, _score(display, display_name)
    if display_name != skill_name:
        canonical = _subsequence_match_indices(filter_text, skill_name)
        if canonical is not None:
            return None, _score(canonical, skill_name)
    return None


def handle_key_event(view: SkillsToggleView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: SkillsToggleView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: SkillsToggleView) -> str:
    return view.on_ctrl_c()


def desired_height(view: SkillsToggleView, width: int) -> int:
    return view.desired_height(width)


def render(view: SkillsToggleView, area: Any = None, buf: Any = None) -> list[DisplayLine]:
    return view.render(area, buf)


def skills_toggle_hint_line(keymap: Any = None) -> str:
    accept = _primary_binding(getattr(keymap, "accept", None))
    cancel = _primary_binding(getattr(keymap, "cancel", None))
    space = "Space"
    if accept == space:
        accept = None
    if accept and cancel:
        return f"Press {space} or {accept} to toggle; {cancel} to close"
    if accept:
        return f"Press {space} or {accept} to toggle"
    if cancel:
        return f"Press {space} to toggle; {cancel} to close"
    return f"Press {space} to toggle"


def _subsequence_match_indices(needle: str, haystack: str) -> list[int] | None:
    needle = needle.lower()
    haystack_lower = haystack.lower()
    indices: list[int] = []
    pos = 0
    for ch in needle:
        found = haystack_lower.find(ch, pos)
        if found == -1:
            return None
        indices.append(found)
        pos = found + 1
    return indices


def _score(indices: list[int], haystack: str) -> int:
    if not indices:
        return 0
    spread = indices[-1] - indices[0]
    start_penalty = indices[0]
    return spread + start_penalty + len(haystack)


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event if key_event == " " else key_event.lower()
    for attr in ("key", "code", "name"):
        value = getattr(key_event, attr, None)
        if value is not None:
            text = str(value)
            return text if text == " " else text.lower()
    text = str(key_event)
    return text if text == " " else text.lower()


def _is_plain_text_key(key_event: Any) -> bool:
    key = _key_name(key_event)
    return len(key) == 1 and not _has_control_or_alt(key_event)


def _has_control_or_alt(key_event: Any) -> bool:
    if isinstance(key_event, str):
        return False
    modifiers = str(getattr(key_event, "modifiers", "")).lower()
    return "control" in modifiers or "ctrl" in modifiers or "alt" in modifiers


def _send(target: Any, event: dict[str, Any]) -> None:
    if target is None:
        return
    if hasattr(target, "send"):
        target.send(event)
    elif hasattr(target, "append"):
        target.append(event)
    elif callable(target):
        target(event)
    elif hasattr(target, "events"):
        target.events.append(event)


def _list_skills(target: Any, args: list[Any], force_reload: bool) -> None:
    if target is None:
        return
    if hasattr(target, "list_skills"):
        target.list_skills(args, force_reload)
    else:
        _send(target, {"type": "ListSkills", "args": args, "force_reload": force_reload})


def _primary_binding(bindings: Any) -> str | None:
    if not bindings:
        return None
    if isinstance(bindings, str):
        return bindings
    try:
        first = list(bindings)[0]
    except Exception:
        return str(bindings)
    return str(first)


def _area_width(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("width", 0))
    if isinstance(area, tuple) and len(area) >= 3:
        return int(area[2])
    return int(getattr(area, "width", 0))


def _area_height(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("height", 0))
    if isinstance(area, tuple) and len(area) >= 4:
        return int(area[3])
    return int(getattr(area, "height", 0))


__all__ = [
    "DisplayLine",
    "DisplayRow",
    "RUST_MODULE",
    "SEARCH_PLACEHOLDER",
    "SEARCH_PROMPT_PREFIX",
    "SKILL_NAME_TRUNCATE_LEN",
    "SkillsToggleItem",
    "SkillsToggleView",
    "desired_height",
    "handle_key_event",
    "is_complete",
    "match_skill",
    "on_ctrl_c",
    "render",
    "skills_toggle_hint_line",
    "truncate_skill_name",
]
