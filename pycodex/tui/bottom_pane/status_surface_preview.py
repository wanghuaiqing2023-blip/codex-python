"""Preview data for configurable status surfaces.

Python port of Rust ``codex-tui::bottom_pane::status_surface_preview``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .status_line_style import StyledLine
from .status_line_style import status_line_from_segments

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::status_surface_preview",
    source="codex/codex-rs/tui/src/bottom_pane/status_surface_preview.rs",
    status="complete",
)


class StatusSurfacePreviewItem(Enum):
    APP_NAME = "AppName"
    PROJECT_NAME = "ProjectName"
    PROJECT_ROOT = "ProjectRoot"
    CURRENT_DIR = "CurrentDir"
    STATUS = "Status"
    THREAD_TITLE = "ThreadTitle"
    GIT_BRANCH = "GitBranch"
    PULL_REQUEST_NUMBER = "PullRequestNumber"
    BRANCH_CHANGES = "BranchChanges"
    PERMISSIONS = "Permissions"
    APPROVAL_MODE = "ApprovalMode"
    CONTEXT_REMAINING = "ContextRemaining"
    CONTEXT_USED = "ContextUsed"
    FIVE_HOUR_LIMIT = "FiveHourLimit"
    WEEKLY_LIMIT = "WeeklyLimit"
    CODEX_VERSION = "CodexVersion"
    CONTEXT_WINDOW_SIZE = "ContextWindowSize"
    USED_TOKENS = "UsedTokens"
    TOTAL_INPUT_TOKENS = "TotalInputTokens"
    TOTAL_OUTPUT_TOKENS = "TotalOutputTokens"
    SESSION_ID = "SessionId"
    FAST_MODE = "FastMode"
    RAW_OUTPUT = "RawOutput"
    MODEL = "Model"
    MODEL_WITH_REASONING = "ModelWithReasoning"
    TASK_PROGRESS = "TaskProgress"

    @classmethod
    def iter(cls) -> Tuple["StatusSurfacePreviewItem", ...]:
        return tuple(cls)

    def placeholder(self) -> str:
        return _PLACEHOLDERS[self]


_PLACEHOLDERS = {
    StatusSurfacePreviewItem.APP_NAME: "codex",
    StatusSurfacePreviewItem.PROJECT_NAME: "my-project",
    StatusSurfacePreviewItem.PROJECT_ROOT: "my-project",
    StatusSurfacePreviewItem.CURRENT_DIR: "~/my-project/subdir",
    StatusSurfacePreviewItem.STATUS: "Working",
    StatusSurfacePreviewItem.THREAD_TITLE: "thread title",
    StatusSurfacePreviewItem.GIT_BRANCH: "feat/awesome-feature",
    StatusSurfacePreviewItem.PULL_REQUEST_NUMBER: "PR #123",
    StatusSurfacePreviewItem.BRANCH_CHANGES: "+12 -3",
    StatusSurfacePreviewItem.PERMISSIONS: "Workspace",
    StatusSurfacePreviewItem.APPROVAL_MODE: "on-request",
    StatusSurfacePreviewItem.CONTEXT_REMAINING: "Context 0% left",
    StatusSurfacePreviewItem.CONTEXT_USED: "Context 0% used",
    StatusSurfacePreviewItem.FIVE_HOUR_LIMIT: "primary 0%",
    StatusSurfacePreviewItem.WEEKLY_LIMIT: "secondary 0%",
    StatusSurfacePreviewItem.CODEX_VERSION: "0.0.0",
    StatusSurfacePreviewItem.CONTEXT_WINDOW_SIZE: "0 window",
    StatusSurfacePreviewItem.USED_TOKENS: "0 used",
    StatusSurfacePreviewItem.TOTAL_INPUT_TOKENS: "0 in",
    StatusSurfacePreviewItem.TOTAL_OUTPUT_TOKENS: "0 out",
    StatusSurfacePreviewItem.SESSION_ID: "550e8400-e29b-41d4",
    StatusSurfacePreviewItem.FAST_MODE: "Fast on",
    StatusSurfacePreviewItem.RAW_OUTPUT: "raw output",
    StatusSurfacePreviewItem.MODEL: "gpt-5.2-codex",
    StatusSurfacePreviewItem.MODEL_WITH_REASONING: "gpt-5.2-codex medium",
    StatusSurfacePreviewItem.TASK_PROGRESS: "Tasks 0/0",
}


@dataclass(frozen=True)
class PreviewValue:
    text: str
    is_placeholder: bool


@dataclass
class StatusSurfacePreviewData:
    values: Dict[StatusSurfacePreviewItem, PreviewValue]

    def __init__(
        self,
        values: Optional[Dict[StatusSurfacePreviewItem, PreviewValue]] = None,
    ) -> None:
        self.values = values if values is not None else {}
        if values is None:
            for item in StatusSurfacePreviewItem.iter():
                self.set_placeholder(item, item.placeholder())

    @classmethod
    def from_iter(cls, values: Iterable[Tuple[Any, Any]]) -> "StatusSurfacePreviewData":
        data = cls()
        for item, value in values:
            data.set_live(item, value)
        return data

    def set_live(self, item: Any, value: Any) -> None:
        self.values[_preview_item(item)] = PreviewValue(str(value), False)

    def set_placeholder(self, item: Any, value: Any) -> None:
        key = _preview_item(item)
        existing = self.values.get(key)
        if existing is not None and not existing.is_placeholder:
            return
        self.values[key] = PreviewValue(str(value), True)

    def suppress_placeholder(self, item: Any) -> None:
        key = _preview_item(item)
        existing = self.values.get(key)
        if existing is not None and existing.is_placeholder:
            del self.values[key]

    def rate_limit_item_name(self, item: Any, fallback: str) -> str:
        copy = rate_limit_preview_copy(self.live_value_for(item) or "")
        return copy.name if copy is not None else fallback

    def rate_limit_item_description(self, item: Any, fallback: str) -> str:
        copy = rate_limit_preview_copy(self.live_value_for(item) or "")
        return copy.description if copy is not None else fallback

    def value_for(self, item: Any) -> Optional[str]:
        value = self.values.get(_preview_item(item))
        return value.text if value is not None else None

    def live_value_for(self, item: Any) -> Optional[str]:
        value = self.values.get(_preview_item(item))
        if value is None or value.is_placeholder:
            return None
        return value.text

    def status_line_for_items(self, items: Iterable[Any], use_theme_colors: bool) -> Optional[StyledLine]:
        segments: List[Tuple[Any, str]] = []
        for item in items:
            value = self.value_for(_status_line_item_to_preview_item(item))
            if value is not None:
                segments.append((item, value))
        return status_line_from_segments(segments, use_theme_colors)


def default() -> StatusSurfacePreviewData:
    return StatusSurfacePreviewData()


@dataclass(frozen=True)
class RateLimitPreviewCopy:
    name: str
    description: str


def rate_limit_preview_copy(value: str) -> Optional[RateLimitPreviewCopy]:
    value = value.lstrip()
    for prefix, name, description in _RATE_LIMIT_COPIES:
        if value.startswith(prefix):
            return RateLimitPreviewCopy(name, description)
    return None


_RATE_LIMIT_COPIES = (
    (
        "secondary usage ",
        "secondary-usage-limit",
        "Remaining usage on the secondary usage limit (omitted when unavailable)",
    ),
    (
        "usage ",
        "usage-limit",
        "Remaining usage on the primary usage limit (omitted when unavailable)",
    ),
    (
        "5h ",
        "five-hour-limit",
        "Remaining usage on the 5-hour usage limit (omitted when unavailable)",
    ),
    (
        "daily ",
        "daily-limit",
        "Remaining usage on the daily usage limit (omitted when unavailable)",
    ),
    (
        "weekly ",
        "weekly-limit",
        "Remaining usage on the weekly usage limit (omitted when unavailable)",
    ),
    (
        "monthly ",
        "monthly-limit",
        "Remaining usage on the monthly usage limit (omitted when unavailable)",
    ),
    (
        "annual ",
        "annual-limit",
        "Remaining usage on the annual usage limit (omitted when unavailable)",
    ),
)


_STATUS_ITEM_TO_PREVIEW = {
    "ModelName": StatusSurfacePreviewItem.MODEL,
    "ModelWithReasoning": StatusSurfacePreviewItem.MODEL_WITH_REASONING,
    "CurrentDir": StatusSurfacePreviewItem.CURRENT_DIR,
    "ProjectRoot": StatusSurfacePreviewItem.PROJECT_ROOT,
    "GitBranch": StatusSurfacePreviewItem.GIT_BRANCH,
    "PullRequestNumber": StatusSurfacePreviewItem.PULL_REQUEST_NUMBER,
    "BranchChanges": StatusSurfacePreviewItem.BRANCH_CHANGES,
    "Status": StatusSurfacePreviewItem.STATUS,
    "Permissions": StatusSurfacePreviewItem.PERMISSIONS,
    "ApprovalMode": StatusSurfacePreviewItem.APPROVAL_MODE,
    "ContextRemaining": StatusSurfacePreviewItem.CONTEXT_REMAINING,
    "ContextUsed": StatusSurfacePreviewItem.CONTEXT_USED,
    "FiveHourLimit": StatusSurfacePreviewItem.FIVE_HOUR_LIMIT,
    "WeeklyLimit": StatusSurfacePreviewItem.WEEKLY_LIMIT,
    "CodexVersion": StatusSurfacePreviewItem.CODEX_VERSION,
    "ContextWindowSize": StatusSurfacePreviewItem.CONTEXT_WINDOW_SIZE,
    "UsedTokens": StatusSurfacePreviewItem.USED_TOKENS,
    "TotalInputTokens": StatusSurfacePreviewItem.TOTAL_INPUT_TOKENS,
    "TotalOutputTokens": StatusSurfacePreviewItem.TOTAL_OUTPUT_TOKENS,
    "SessionId": StatusSurfacePreviewItem.SESSION_ID,
    "FastMode": StatusSurfacePreviewItem.FAST_MODE,
    "RawOutput": StatusSurfacePreviewItem.RAW_OUTPUT,
    "ThreadTitle": StatusSurfacePreviewItem.THREAD_TITLE,
    "TaskProgress": StatusSurfacePreviewItem.TASK_PROGRESS,
}


def _preview_item(item: Any) -> StatusSurfacePreviewItem:
    if isinstance(item, StatusSurfacePreviewItem):
        return item
    name = _rust_name(item)
    try:
        return StatusSurfacePreviewItem(name)
    except ValueError:
        upper_name = _snake_to_enum_name(name)
        if upper_name in StatusSurfacePreviewItem.__members__:
            return StatusSurfacePreviewItem[upper_name]
        if name in _STATUS_ITEM_TO_PREVIEW:
            return _STATUS_ITEM_TO_PREVIEW[name]
        raise ValueError(f"unknown StatusSurfacePreviewItem: {item!r}") from None


def _status_line_item_to_preview_item(item: Any) -> StatusSurfacePreviewItem:
    preview_item = getattr(item, "preview_item", None)
    if callable(preview_item):
        return _preview_item(preview_item())
    name = _rust_name(item)
    if name in _STATUS_ITEM_TO_PREVIEW:
        return _STATUS_ITEM_TO_PREVIEW[name]
    return _preview_item(item)


def _rust_name(item: Any) -> str:
    if isinstance(item, str):
        return _normalize_rust_case(item)
    name = getattr(item, "name", None)
    if isinstance(name, str):
        return _normalize_rust_case(name)
    value = getattr(item, "value", None)
    if isinstance(value, str):
        return _normalize_rust_case(value)
    return _normalize_rust_case(str(item))


def _normalize_rust_case(name: str) -> str:
    if "_" in name or "-" in name:
        return "".join(part[:1].upper() + part[1:].lower() for part in name.replace("-", "_").split("_") if part)
    return name[:1].upper() + name[1:] if name and name[0].islower() else name


def _snake_to_enum_name(name: str) -> str:
    chars: List[str] = []
    for idx, ch in enumerate(name):
        if ch.isupper() and idx > 0:
            chars.append("_")
        chars.append(ch.upper())
    return "".join(chars)


__all__ = [
    "PreviewValue",
    "RUST_MODULE",
    "RateLimitPreviewCopy",
    "StatusSurfacePreviewData",
    "StatusSurfacePreviewItem",
    "default",
    "rate_limit_preview_copy",
]

