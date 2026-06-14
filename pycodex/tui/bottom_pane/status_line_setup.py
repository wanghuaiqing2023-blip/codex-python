"""Status line setup behavior for Rust bottom_pane/status_line_setup.rs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .._porting import RustTuiModule
from .multi_select_picker import MultiSelectItem, MultiSelectPicker
from .status_surface_preview import StatusSurfacePreviewData, StatusSurfacePreviewItem

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::status_line_setup",
    source="codex/codex-rs/tui/src/bottom_pane/status_line_setup.rs",
)

STATUS_LINE_USE_THEME_COLORS_ITEM_ID = "status-line-use-theme-colors"


class StatusLineItem(Enum):
    MODEL_NAME = "model"
    MODEL_WITH_REASONING = "model-with-reasoning"
    CURRENT_DIR = "current-dir"
    PROJECT_ROOT = "project-name"
    GIT_BRANCH = "git-branch"
    PULL_REQUEST_NUMBER = "pull-request-number"
    BRANCH_CHANGES = "branch-changes"
    STATUS = "run-state"
    PERMISSIONS = "permissions"
    APPROVAL_MODE = "approval-mode"
    CONTEXT_REMAINING = "context-remaining"
    CONTEXT_USED = "context-used"
    FIVE_HOUR_LIMIT = "five-hour-limit"
    WEEKLY_LIMIT = "weekly-limit"
    CODEX_VERSION = "codex-version"
    CONTEXT_WINDOW_SIZE = "context-window-size"
    USED_TOKENS = "used-tokens"
    TOTAL_INPUT_TOKENS = "total-input-tokens"
    TOTAL_OUTPUT_TOKENS = "total-output-tokens"
    SESSION_ID = "thread-id"
    FAST_MODE = "fast-mode"
    RAW_OUTPUT = "raw-output"
    THREAD_TITLE = "thread-title"
    TASK_PROGRESS = "task-progress"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def iter(cls) -> tuple["StatusLineItem", ...]:
        return tuple(cls)

    @classmethod
    def parse(cls, value: Any) -> "StatusLineItem":
        if isinstance(value, cls):
            return value
        key = str(value)
        if key in _ALIASES:
            return _ALIASES[key]
        for item in cls:
            if item.value == key:
                return item
        raise ValueError(f"unknown status line item: {value!r}")

    def description(self) -> str:
        return _DESCRIPTIONS[self]

    def preview_item(self) -> StatusSurfacePreviewItem:
        return _PREVIEW_ITEMS[self]


_ALIASES: dict[str, StatusLineItem] = {}
_DESCRIPTIONS = {
    StatusLineItem.MODEL_NAME: "Current model name",
    StatusLineItem.MODEL_WITH_REASONING: "Current model name with reasoning level",
    StatusLineItem.CURRENT_DIR: "Current working directory",
    StatusLineItem.PROJECT_ROOT: "Project name (omitted when unavailable)",
    StatusLineItem.GIT_BRANCH: "Current Git branch (omitted when unavailable)",
    StatusLineItem.PULL_REQUEST_NUMBER: "Open pull request number for the current branch (omitted when unavailable)",
    StatusLineItem.BRANCH_CHANGES: "Committed branch changes against the default branch (omitted when unavailable)",
    StatusLineItem.STATUS: "Compact session run-state text (Ready, Working, Thinking)",
    StatusLineItem.PERMISSIONS: "Active permission profile or sandbox mode",
    StatusLineItem.APPROVAL_MODE: "Active command approval mode",
    StatusLineItem.CONTEXT_REMAINING: "Percentage of context window remaining (omitted when unknown)",
    StatusLineItem.CONTEXT_USED: "Percentage of context window used (omitted when unknown)",
    StatusLineItem.FIVE_HOUR_LIMIT: "Remaining usage on the primary usage limit (omitted when unavailable)",
    StatusLineItem.WEEKLY_LIMIT: "Remaining usage on the secondary usage limit (omitted when unavailable)",
    StatusLineItem.CODEX_VERSION: "Codex application version",
    StatusLineItem.CONTEXT_WINDOW_SIZE: "Total context window size in tokens (omitted when unknown)",
    StatusLineItem.USED_TOKENS: "Total tokens used in session (omitted when zero)",
    StatusLineItem.TOTAL_INPUT_TOKENS: "Total input tokens used in session",
    StatusLineItem.TOTAL_OUTPUT_TOKENS: "Total output tokens used in session",
    StatusLineItem.SESSION_ID: "Current thread identifier (omitted until thread starts)",
    StatusLineItem.FAST_MODE: "Whether Fast mode is currently active",
    StatusLineItem.RAW_OUTPUT: "Whether raw scrollback mode is active",
    StatusLineItem.THREAD_TITLE: "Current thread title, or thread identifier when unnamed",
    StatusLineItem.TASK_PROGRESS: "Latest task progress from update_plan (omitted until available)",
}
_PREVIEW_ITEMS = {
    StatusLineItem.MODEL_NAME: StatusSurfacePreviewItem.MODEL,
    StatusLineItem.MODEL_WITH_REASONING: StatusSurfacePreviewItem.MODEL_WITH_REASONING,
    StatusLineItem.CURRENT_DIR: StatusSurfacePreviewItem.CURRENT_DIR,
    StatusLineItem.PROJECT_ROOT: StatusSurfacePreviewItem.PROJECT_ROOT,
    StatusLineItem.GIT_BRANCH: StatusSurfacePreviewItem.GIT_BRANCH,
    StatusLineItem.PULL_REQUEST_NUMBER: StatusSurfacePreviewItem.PULL_REQUEST_NUMBER,
    StatusLineItem.BRANCH_CHANGES: StatusSurfacePreviewItem.BRANCH_CHANGES,
    StatusLineItem.STATUS: StatusSurfacePreviewItem.STATUS,
    StatusLineItem.PERMISSIONS: StatusSurfacePreviewItem.PERMISSIONS,
    StatusLineItem.APPROVAL_MODE: StatusSurfacePreviewItem.APPROVAL_MODE,
    StatusLineItem.CONTEXT_REMAINING: StatusSurfacePreviewItem.CONTEXT_REMAINING,
    StatusLineItem.CONTEXT_USED: StatusSurfacePreviewItem.CONTEXT_USED,
    StatusLineItem.FIVE_HOUR_LIMIT: StatusSurfacePreviewItem.FIVE_HOUR_LIMIT,
    StatusLineItem.WEEKLY_LIMIT: StatusSurfacePreviewItem.WEEKLY_LIMIT,
    StatusLineItem.CODEX_VERSION: StatusSurfacePreviewItem.CODEX_VERSION,
    StatusLineItem.CONTEXT_WINDOW_SIZE: StatusSurfacePreviewItem.CONTEXT_WINDOW_SIZE,
    StatusLineItem.USED_TOKENS: StatusSurfacePreviewItem.USED_TOKENS,
    StatusLineItem.TOTAL_INPUT_TOKENS: StatusSurfacePreviewItem.TOTAL_INPUT_TOKENS,
    StatusLineItem.TOTAL_OUTPUT_TOKENS: StatusSurfacePreviewItem.TOTAL_OUTPUT_TOKENS,
    StatusLineItem.SESSION_ID: StatusSurfacePreviewItem.SESSION_ID,
    StatusLineItem.FAST_MODE: StatusSurfacePreviewItem.FAST_MODE,
    StatusLineItem.RAW_OUTPUT: StatusSurfacePreviewItem.RAW_OUTPUT,
    StatusLineItem.THREAD_TITLE: StatusSurfacePreviewItem.THREAD_TITLE,
    StatusLineItem.TASK_PROGRESS: StatusSurfacePreviewItem.TASK_PROGRESS,
}
_ALIASES.update({
    "model-name": StatusLineItem.MODEL_NAME,
    "project": StatusLineItem.PROJECT_ROOT,
    "project-root": StatusLineItem.PROJECT_ROOT,
    "status": StatusLineItem.STATUS,
    "approval": StatusLineItem.APPROVAL_MODE,
    "context-usage": StatusLineItem.CONTEXT_USED,
    "session-id": StatusLineItem.SESSION_ID,
})


@dataclass
class StatusLineSetupView:
    picker: MultiSelectPicker

    @classmethod
    def new(cls, status_line_items: Iterable[str] | None, use_theme_colors: bool, preview_data: StatusSurfacePreviewData | None, app_event_tx: Any, list_keymap: Any = None) -> "StatusLineSetupView":
        preview_data = preview_data or StatusSurfacePreviewData()
        used_ids: set[str] = set()
        items = [MultiSelectItem(id=STATUS_LINE_USE_THEME_COLORS_ITEM_ID, name="Use theme colors", description="Apply colors from the active /theme", enabled=use_theme_colors, orderable=False, section_break_after=True)]
        if status_line_items is not None:
            for raw_id in status_line_items:
                try:
                    item = StatusLineItem.parse(raw_id)
                except ValueError:
                    continue
                item_id = str(item)
                if item_id in used_ids:
                    continue
                used_ids.add(item_id)
                items.append(cls.status_line_select_item(item, True, preview_data))
        for item in StatusLineItem.iter():
            item_id = str(item)
            if item_id not in used_ids:
                items.append(cls.status_line_select_item(item, False, preview_data))

        def preview_builder(current_items: list[MultiSelectItem]) -> Any | None:
            theme_colors = next((item.enabled for item in current_items if item.id == STATUS_LINE_USE_THEME_COLORS_ITEM_ID), True)
            selected = []
            for picker_item in current_items:
                if picker_item.enabled:
                    try:
                        selected.append(StatusLineItem.parse(picker_item.id))
                    except ValueError:
                        pass
            return preview_data.status_line_for_items(selected, theme_colors)

        def on_confirm(ids: list[str], app_event: Any) -> None:
            theme_colors = STATUS_LINE_USE_THEME_COLORS_ITEM_ID in ids
            selected_items = []
            for item_id in ids:
                try:
                    selected_items.append(StatusLineItem.parse(item_id))
                except ValueError:
                    pass
            _send(app_event, {"type": "StatusLineSetup", "items": selected_items, "use_theme_colors": theme_colors})

        def on_cancel(app_event: Any) -> None:
            _send(app_event, {"type": "StatusLineSetupCancelled"})

        picker = (MultiSelectPicker.builder("Configure Status Line", "Select which items to display in the status line.", app_event_tx).list_keymap(list_keymap).items(items).enable_ordering().on_preview(preview_builder).on_confirm(on_confirm).on_cancel(on_cancel).build())
        return cls(picker=picker)

    @staticmethod
    def status_line_select_item(item: Any, enabled: bool, preview_data: StatusSurfacePreviewData) -> MultiSelectItem:
        item = StatusLineItem.parse(item)
        default_name = str(item)
        default_description = item.description()
        if item in {StatusLineItem.FIVE_HOUR_LIMIT, StatusLineItem.WEEKLY_LIMIT}:
            name = preview_data.rate_limit_item_name(item.preview_item(), default_name)
            description = preview_data.rate_limit_item_description(item.preview_item(), default_description)
        else:
            name = default_name
            description = default_description
        return MultiSelectItem(id=str(item), name=name, description=description, enabled=enabled, orderable=True, section_break_after=False)

    def handle_key_event(self, key_event: Any) -> None:
        self.picker.handle_key_event(key_event)

    def is_complete(self) -> bool:
        return self.picker.complete

    def on_ctrl_c(self) -> str:
        self.picker.close()
        return "Handled"

    def desired_height(self, width: int) -> int:
        rows = self.picker.build_rows()
        preview_height = 1 if self.picker.preview_line is not None else 0
        subtitle_height = 1 if self.picker.subtitle else 0
        return 2 + subtitle_height + self.picker.rows_height(rows) + preview_height

    def render_lines(self, width: int = 80) -> str:
        lines = [self.picker.title]
        if self.picker.subtitle:
            lines.append(self.picker.subtitle)
        if self.picker.preview_line is not None:
            lines.append(line_text(self.picker.preview_line) or "")
        for row in self.picker.build_rows().rows:
            desc = f" - {row.description}" if row.description else ""
            lines.append(f"{row.name}{desc}"[:width])
        return "\n".join(lines)


def parse_status_line_item(value: Any) -> StatusLineItem:
    return StatusLineItem.parse(value)


def parse_status_line_items(values: Iterable[Any]) -> list[StatusLineItem]:
    return [StatusLineItem.parse(value) for value in values]


def status_line_select_item(item: Any, enabled: bool, preview_data: StatusSurfacePreviewData) -> MultiSelectItem:
    return StatusLineSetupView.status_line_select_item(item, enabled, preview_data)


def handle_key_event(view: StatusLineSetupView, key_event: Any) -> None:
    view.handle_key_event(key_event)


def is_complete(view: StatusLineSetupView) -> bool:
    return view.is_complete()


def on_ctrl_c(view: StatusLineSetupView) -> str:
    return view.on_ctrl_c()


def render(view: StatusLineSetupView, width: int = 80) -> str:
    return view.render_lines(width)


def desired_height(view: StatusLineSetupView, width: int) -> int:
    return view.desired_height(width)


def render_lines(view: StatusLineSetupView, width: int) -> str:
    return view.render_lines(width)


def line_text(line: Any | None) -> str | None:
    if line is None:
        return None
    if isinstance(line, str):
        return line
    if hasattr(line, "text"):
        value = line.text
        return value() if callable(value) else str(value)
    spans = getattr(line, "spans", None)
    if spans is not None:
        return "".join(str(getattr(span, "content", span)) for span in spans)
    return str(line)


def _send(target: Any, event: dict[str, Any]) -> None:
    if target is None:
        return
    if hasattr(target, "send"):
        target.send(event)
    elif callable(target):
        target(event)
    elif isinstance(target, list):
        target.append(event)


__all__ = [
    "RUST_MODULE", "STATUS_LINE_USE_THEME_COLORS_ITEM_ID", "StatusLineItem", "StatusLineSetupView", "parse_status_line_item", "parse_status_line_items", "status_line_select_item", "handle_key_event", "is_complete", "on_ctrl_c", "render", "desired_height", "render_lines", "line_text",
]
