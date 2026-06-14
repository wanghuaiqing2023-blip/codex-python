"""Semantic port of Rust ``bottom_pane/title_setup.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::title_setup",
    source="codex/codex-rs/tui/src/bottom_pane/title_setup.rs",
)

ACTION_REQUIRED_PREVIEW_PREFIX = "[ ! ] Action Required"


class TerminalTitleItem(Enum):
    APP_NAME = "app-name"
    PROJECT = "project-name"
    CURRENT_DIR = "current-dir"
    SPINNER = "activity"
    STATUS = "run-state"
    THREAD = "thread-title"
    GIT_BRANCH = "git-branch"
    CONTEXT_REMAINING = "context-remaining"
    CONTEXT_USED = "context-used"
    FIVE_HOUR_LIMIT = "five-hour-limit"
    WEEKLY_LIMIT = "weekly-limit"
    CODEX_VERSION = "codex-version"
    USED_TOKENS = "used-tokens"
    TOTAL_INPUT_TOKENS = "total-input-tokens"
    TOTAL_OUTPUT_TOKENS = "total-output-tokens"
    SESSION_ID = "session-id"
    FAST_MODE = "fast-mode"
    MODEL = "model"
    MODEL_WITH_REASONING = "model-with-reasoning"
    TASK_PROGRESS = "task-progress"

    @classmethod
    def from_id(cls, value: Any) -> "TerminalTitleItem":
        text = str(value)
        legacy = {
            "project": cls.PROJECT,
            "spinner": cls.SPINNER,
            "status": cls.STATUS,
            "thread": cls.THREAD,
            "context-usage": cls.CONTEXT_USED,
            "session-id": cls.SESSION_ID,
            "model-name": cls.MODEL,
        }
        if text in legacy:
            return legacy[text]
        return cls(text)

    def __str__(self) -> str:
        return self.value

    def description(self) -> str:
        return _DESCRIPTIONS[self]

    def preview_item(self) -> str | None:
        return _PREVIEW_ITEMS.get(self)

    def separator_from_previous(self, previous: "TerminalTitleItem | None") -> str:
        if previous is None:
            return ""
        if previous is TerminalTitleItem.SPINNER or self is TerminalTitleItem.SPINNER:
            return " "
        return " | "


_DESCRIPTIONS: dict[TerminalTitleItem, str] = {
    TerminalTitleItem.APP_NAME: "Codex app name",
    TerminalTitleItem.PROJECT: "Project name (falls back to current directory name)",
    TerminalTitleItem.CURRENT_DIR: "Current working directory",
    TerminalTitleItem.SPINNER: "Spinner while working, action-required message while blocked.",
    TerminalTitleItem.STATUS: "Compact session run-state text (Ready, Working, Thinking)",
    TerminalTitleItem.THREAD: "Current thread title, or thread identifier when unnamed",
    TerminalTitleItem.GIT_BRANCH: "Current Git branch (omitted when unavailable)",
    TerminalTitleItem.CONTEXT_REMAINING: "Percentage of context window remaining (omitted when unknown)",
    TerminalTitleItem.CONTEXT_USED: "Percentage of context window used (omitted when unknown)",
    TerminalTitleItem.FIVE_HOUR_LIMIT: "Remaining usage on the primary usage limit (omitted when unavailable)",
    TerminalTitleItem.WEEKLY_LIMIT: "Remaining usage on the secondary usage limit (omitted when unavailable)",
    TerminalTitleItem.CODEX_VERSION: "Codex application version",
    TerminalTitleItem.USED_TOKENS: "Total tokens used in session (omitted when zero)",
    TerminalTitleItem.TOTAL_INPUT_TOKENS: "Total input tokens used in session",
    TerminalTitleItem.TOTAL_OUTPUT_TOKENS: "Total output tokens used in session",
    TerminalTitleItem.SESSION_ID: "Current thread identifier (omitted until thread starts)",
    TerminalTitleItem.FAST_MODE: "Whether Fast mode is currently active",
    TerminalTitleItem.MODEL: "Current model name",
    TerminalTitleItem.MODEL_WITH_REASONING: "Current model name with reasoning level",
    TerminalTitleItem.TASK_PROGRESS: "Latest task progress from update_plan (omitted until available)",
}


_PREVIEW_ITEMS: dict[TerminalTitleItem, str] = {
    TerminalTitleItem.APP_NAME: "AppName",
    TerminalTitleItem.PROJECT: "ProjectName",
    TerminalTitleItem.CURRENT_DIR: "CurrentDir",
    TerminalTitleItem.STATUS: "Status",
    TerminalTitleItem.THREAD: "ThreadTitle",
    TerminalTitleItem.GIT_BRANCH: "GitBranch",
    TerminalTitleItem.CONTEXT_REMAINING: "ContextRemaining",
    TerminalTitleItem.CONTEXT_USED: "ContextUsed",
    TerminalTitleItem.FIVE_HOUR_LIMIT: "FiveHourLimit",
    TerminalTitleItem.WEEKLY_LIMIT: "WeeklyLimit",
    TerminalTitleItem.CODEX_VERSION: "CodexVersion",
    TerminalTitleItem.USED_TOKENS: "UsedTokens",
    TerminalTitleItem.TOTAL_INPUT_TOKENS: "TotalInputTokens",
    TerminalTitleItem.TOTAL_OUTPUT_TOKENS: "TotalOutputTokens",
    TerminalTitleItem.SESSION_ID: "SessionId",
    TerminalTitleItem.FAST_MODE: "FastMode",
    TerminalTitleItem.MODEL: "Model",
    TerminalTitleItem.MODEL_WITH_REASONING: "ModelWithReasoning",
    TerminalTitleItem.TASK_PROGRESS: "TaskProgress",
}


@dataclass(frozen=True)
class MultiSelectItem:
    id: str
    name: str
    description: str | None
    enabled: bool
    orderable: bool = True
    section_break_after: bool = False


def preview_line_for_title_items(items: Iterable[TerminalTitleItem | str], preview_data: Any) -> str | None:
    parsed = [item if isinstance(item, TerminalTitleItem) else TerminalTitleItem.from_id(item) for item in items]
    if TerminalTitleItem.SPINNER in parsed:
        return _preview_with_action_required(parsed, preview_data)

    previous: TerminalTitleItem | None = None
    parts: list[str] = []
    for item in parsed:
        value = _preview_value(preview_data, item)
        if value is None:
            continue
        parts.append(item.separator_from_previous(previous) + value)
        previous = item
    preview = "".join(parts)
    return preview or None


def parse_terminal_title_items(ids: Iterable[Any]) -> list[TerminalTitleItem] | None:
    result: list[TerminalTitleItem] = []
    try:
        for item_id in ids:
            result.append(TerminalTitleItem.from_id(item_id))
    except ValueError:
        return None
    return result


def _preview_with_action_required(items: list[TerminalTitleItem], preview_data: Any) -> str:
    parts = [ACTION_REQUIRED_PREVIEW_PREFIX]
    for item in items:
        if item is TerminalTitleItem.SPINNER:
            continue
        value = _preview_value(preview_data, item)
        if value is None:
            continue
        parts.append(value)
    return " | ".join(parts)


def _preview_value(preview_data: Any, item: TerminalTitleItem) -> str | None:
    preview_item = item.preview_item()
    if preview_item is None:
        return None
    if isinstance(preview_data, dict):
        value = preview_data.get(preview_item)
        if value is None:
            value = preview_data.get(item.value)
        return None if value is None else str(value)
    value_for = getattr(preview_data, "value_for", None)
    if callable(value_for):
        value = value_for(preview_item)
        return None if value is None else str(value)
    value = getattr(preview_data, preview_item, None)
    return None if value is None else str(value)


@dataclass
class TerminalTitleSetupView:
    items: list[MultiSelectItem]
    preview_data: Any
    emitted_events: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = False

    @classmethod
    def new(
        cls,
        title_items: Iterable[str] | None = None,
        preview_data: Any | None = None,
        app_event_tx: Any = None,
        list_keymap: Any = None,
    ) -> "TerminalTitleSetupView":
        del app_event_tx, list_keymap
        preview_data = {} if preview_data is None else preview_data
        selected: list[TerminalTitleItem] = []
        seen: set[TerminalTitleItem] = set()
        for item_id in title_items or []:
            try:
                item = TerminalTitleItem.from_id(item_id)
            except ValueError:
                continue
            if item not in seen:
                selected.append(item)
                seen.add(item)
        items = [cls.title_select_item(item, True, preview_data) for item in selected]
        items.extend(
            cls.title_select_item(item, False, preview_data)
            for item in TerminalTitleItem
            if item not in seen
        )
        return cls(items=items, preview_data=preview_data)

    @staticmethod
    def title_select_item(item: TerminalTitleItem | str, enabled: bool, preview_data: Any) -> MultiSelectItem:
        parsed = item if isinstance(item, TerminalTitleItem) else TerminalTitleItem.from_id(item)
        default_name = parsed.value
        default_description = parsed.description()
        name = _rate_limit_item_name(preview_data, parsed.preview_item(), default_name)
        description = _rate_limit_item_description(preview_data, parsed.preview_item(), default_description)
        return MultiSelectItem(
            id=parsed.value,
            name=name,
            description=description,
            enabled=enabled,
            orderable=True,
            section_break_after=False,
        )

    def preview(self) -> str | None:
        items = parse_terminal_title_items(item.id for item in self.items if item.enabled)
        if items is None:
            return None
        return preview_line_for_title_items(items, self.preview_data)

    def confirm(self) -> None:
        items = parse_terminal_title_items(item.id for item in self.items if item.enabled)
        if items is None:
            return
        self.emitted_events.append({"type": "TerminalTitleSetup", "items": items})
        self.complete = True

    def cancel(self) -> None:
        self.emitted_events.append({"type": "TerminalTitleSetupCancelled"})
        self.complete = True

    def handle_key_event(self, key_event: Any) -> None:
        if str(key_event).lower() in {"esc", "ctrl-c", "ctrl_c"}:
            self.cancel()

    def is_complete(self) -> bool:
        return self.complete

    def on_ctrl_c(self) -> str:
        self.cancel()
        return "Handled"

    def render_lines(self) -> list[str]:
        lines = ["Configure Terminal Title", "Select which items to display in the terminal title."]
        preview = self.preview()
        if preview:
            lines.append(preview)
        lines.extend(
            f"[{'x' if item.enabled else ' '}] {item.name} - {item.description or ''}"
            for item in self.items
        )
        return lines

    def render(self, area: Any = None, buf: Any = None) -> list[str]:
        del area
        lines = self.render_lines()
        if isinstance(buf, list):
            buf.extend(lines)
        return lines

    def desired_height(self, width: int) -> int:
        del width
        return len(self.render_lines())


def _rate_limit_item_name(preview_data: Any, preview_item: str | None, default: str) -> str:
    if preview_item not in {"FiveHourLimit", "WeeklyLimit"}:
        return default
    getter = getattr(preview_data, "rate_limit_item_name", None)
    if callable(getter):
        return str(getter(preview_item, default))
    if isinstance(preview_data, dict):
        return str(preview_data.get(f"{preview_item}.name", default))
    return default


def _rate_limit_item_description(preview_data: Any, preview_item: str | None, default: str) -> str:
    if preview_item not in {"FiveHourLimit", "WeeklyLimit"}:
        return default
    getter = getattr(preview_data, "rate_limit_item_description", None)
    if callable(getter):
        return str(getter(preview_item, default))
    if isinstance(preview_data, dict):
        return str(preview_data.get(f"{preview_item}.description", default))
    return default


def handle_key_event(view: TerminalTitleSetupView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: TerminalTitleSetupView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: TerminalTitleSetupView) -> str:
    return view.on_ctrl_c()


def render(view: TerminalTitleSetupView, area: Any = None, buf: Any = None) -> list[str]:
    return view.render(area, buf)


def desired_height(view: TerminalTitleSetupView, width: int) -> int:
    return view.desired_height(width)


def render_lines(view: TerminalTitleSetupView, width: int | None = None) -> str:
    del width
    return "\n".join(view.render_lines())


__all__ = [
    "ACTION_REQUIRED_PREVIEW_PREFIX",
    "MultiSelectItem",
    "RUST_MODULE",
    "TerminalTitleItem",
    "TerminalTitleSetupView",
    "desired_height",
    "handle_key_event",
    "is_complete",
    "on_ctrl_c",
    "parse_terminal_title_items",
    "preview_line_for_title_items",
    "render",
    "render_lines",
]
