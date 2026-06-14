"""Status output and setup controls for ``ChatWidget``.

Semantic port of Rust ``codex-tui::chatwidget::status_controls``.  Rendering,
async git lookup, and full status-output history cells stay in neighboring
modules/runtime boundaries; this module owns the mutable state transitions and
small formatting helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule, not_ported
from .status_state import STATUS_DETAILS_DEFAULT_MAX_LINES, StatusIndicatorState, StatusState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::status_controls",
    source="codex/codex-rs/tui/src/chatwidget/status_controls.rs",
    status="complete_slice",
)


class StatusDetailsCapitalization(str, Enum):
    CapitalizeFirst = "capitalize_first"
    Preserve = "preserve"


class ReasoningEffortConfig(str, Enum):
    Minimal = "minimal"
    Low = "low"
    Medium = "medium"
    High = "high"
    XHigh = "xhigh"
    None_ = "none"


@dataclass(eq=True)
class TokenUsage:
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def percent_of_context_window_remaining(self, context_window: int) -> int:
        if context_window <= 0:
            return 100
        used = max(0, self.total_tokens)
        remaining = round((max(0, context_window - used) / context_window) * 100)
        return int(remaining)


@dataclass(eq=True)
class TokenInfo:
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
    last_token_usage: TokenUsage = field(default_factory=TokenUsage)
    model_context_window: int | None = None


@dataclass(eq=True)
class RateLimitWindowDisplay:
    used_percent: float


@dataclass(eq=True)
class StatusControlsConfig:
    tui_terminal_title: list[str] | None = None
    tui_status_line: list[str] | None = None
    tui_status_line_use_colors: bool = False
    model_context_window: int | None = None
    model_reasoning_effort: ReasoningEffortConfig | str | None = None


@dataclass(eq=True)
class BottomPaneRecorder:
    status_updates: list[tuple[str, str | None, StatusDetailsCapitalization, int]] = field(default_factory=list)
    status_line: Any | None = None
    status_line_hyperlink: str | None = None
    active_agent_label: str | None = None

    def update_status(
        self,
        header: str,
        details: str | None,
        details_capitalization: StatusDetailsCapitalization,
        details_max_lines: int,
    ) -> None:
        self.status_updates.append((header, details, details_capitalization, details_max_lines))

    def set_status_line(self, status_line: Any | None) -> None:
        self.status_line = status_line

    def set_status_line_hyperlink(self, url: str | None) -> None:
        self.status_line_hyperlink = url

    def set_active_agent_label(self, active_agent_label: str | None) -> None:
        self.active_agent_label = active_agent_label


@dataclass(eq=True)
class StatusControlsState:
    status_state: StatusState = field(default_factory=StatusState)
    bottom_pane: BottomPaneRecorder = field(default_factory=BottomPaneRecorder)
    config: StatusControlsConfig = field(default_factory=StatusControlsConfig)
    terminal_title_setup_original_items: list[str] | None | object = None
    status_line_branch_cwd: Path | None = None
    status_line_branch: str | None = None
    status_line_branch_pending: bool = False
    status_line_branch_lookup_complete: bool = False
    status_line_git_summary_cwd: Path | None = None
    status_line_git_summary: Any | None = None
    status_line_git_summary_pending: bool = False
    status_line_git_summary_lookup_complete: bool = False
    token_info: TokenInfo | None = None
    refreshed_status_surfaces: int = 0
    refreshed_terminal_title: int = 0
    refreshed_status_line: int = 0

    def refresh_status_surfaces(self) -> None:
        self.refreshed_status_surfaces += 1

    def refresh_terminal_title(self) -> None:
        self.refreshed_terminal_title += 1

    def refresh_status_line(self) -> None:
        self.refreshed_status_line += 1


def _capitalize_first(value: str) -> str:
    if not value:
        return value
    return value[0].upper() + value[1:]


def set_status(
    state: StatusControlsState,
    header: str,
    details: str | None,
    details_capitalization: StatusDetailsCapitalization,
    details_max_lines: int,
) -> None:
    detail_value: str | None = None
    if details is not None and details != "":
        trimmed = details.lstrip()
        if details_capitalization is StatusDetailsCapitalization.CapitalizeFirst:
            detail_value = _capitalize_first(trimmed)
        else:
            detail_value = trimmed

    state.status_state.set_status(StatusIndicatorState(header, detail_value, details_max_lines))
    state.bottom_pane.update_status(
        header,
        detail_value,
        StatusDetailsCapitalization.Preserve,
        details_max_lines,
    )
    title_items = state.config.tui_terminal_title or []
    if any(item in {"run-state", "status"} for item in title_items):
        state.refresh_status_surfaces()


def set_status_header(state: StatusControlsState, header: str) -> None:
    set_status(
        state,
        header,
        None,
        StatusDetailsCapitalization.CapitalizeFirst,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )


def set_status_line(state: StatusControlsState, status_line: Any | None) -> None:
    state.bottom_pane.set_status_line(status_line)


def set_status_line_hyperlink(state: StatusControlsState, url: str | None) -> None:
    state.bottom_pane.set_status_line_hyperlink(url)


def set_active_agent_label(state: StatusControlsState, active_agent_label: str | None) -> None:
    state.bottom_pane.set_active_agent_label(active_agent_label)


def setup_status_line(state: StatusControlsState, items: list[Any], use_theme_colors: bool) -> None:
    state.config.tui_status_line = [str(item) for item in items]
    state.config.tui_status_line_use_colors = use_theme_colors
    state.refresh_status_line()


def preview_terminal_title(state: StatusControlsState, items: list[Any]) -> None:
    if state.terminal_title_setup_original_items is None:
        current = state.config.tui_terminal_title
        state.terminal_title_setup_original_items = None if current is None else list(current)
    state.config.tui_terminal_title = [str(item) for item in items]
    state.refresh_terminal_title()


def revert_terminal_title_setup_preview(state: StatusControlsState) -> None:
    original = state.terminal_title_setup_original_items
    if original is None:
        return
    state.terminal_title_setup_original_items = None
    state.config.tui_terminal_title = None if original is None else list(original)  # type: ignore[arg-type]
    state.refresh_terminal_title()


def cancel_terminal_title_setup(state: StatusControlsState) -> None:
    revert_terminal_title_setup_preview(state)


def setup_terminal_title(state: StatusControlsState, items: list[Any]) -> None:
    state.terminal_title_setup_original_items = None
    state.config.tui_terminal_title = [str(item) for item in items]
    state.refresh_terminal_title()


def set_status_line_branch(state: StatusControlsState, cwd: Any, branch: str | None) -> None:
    path = Path(cwd)
    if state.status_line_branch_cwd != path:
        state.status_line_branch_pending = False
        return
    state.status_line_branch = branch
    state.status_line_branch_pending = False
    state.status_line_branch_lookup_complete = True
    state.refresh_status_surfaces()


def set_status_line_git_summary(state: StatusControlsState, cwd: Any, summary: Any) -> None:
    path = Path(cwd)
    if state.status_line_git_summary_cwd != path:
        state.status_line_git_summary_pending = False
        return
    state.status_line_git_summary = summary
    state.status_line_git_summary_pending = False
    state.status_line_git_summary_lookup_complete = True
    state.refresh_status_surfaces()


def status_line_context_window_size(state: StatusControlsState) -> int | None:
    if state.token_info is not None and state.token_info.model_context_window is not None:
        return state.token_info.model_context_window
    return state.config.model_context_window


def status_line_context_remaining_percent(state: StatusControlsState) -> int | None:
    context_window = status_line_context_window_size(state)
    if context_window is None:
        return 100
    usage = state.token_info.last_token_usage if state.token_info is not None else TokenUsage()
    return max(0, min(100, usage.percent_of_context_window_remaining(context_window)))


def status_line_context_used_percent(state: StatusControlsState) -> int | None:
    remaining = status_line_context_remaining_percent(state)
    if remaining is None:
        remaining = 100
    return max(0, min(100, 100 - remaining))


def status_line_total_usage(state: StatusControlsState) -> TokenUsage:
    if state.token_info is None:
        return TokenUsage()
    return state.token_info.total_token_usage


def status_line_limit_display(window: RateLimitWindowDisplay | None, label: str) -> str | None:
    if window is None:
        return None
    remaining = max(0.0, min(100.0, 100.0 - window.used_percent))
    return f"{label} {remaining:.0f}% left"


def status_line_reasoning_effort_label(effort: ReasoningEffortConfig | str | None) -> str:
    if effort is None:
        return "default"
    value = effort.value if isinstance(effort, ReasoningEffortConfig) else str(effort).lower()
    return {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "none": "default",
    }.get(value, "default")


def add_status_output(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("chatwidget::status_controls::add_status_output requires status history-cell rendering")


def open_status_line_setup(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("chatwidget::status_controls::open_status_line_setup requires BottomPane view runtime")


__all__ = [
    "BottomPaneRecorder",
    "RateLimitWindowDisplay",
    "ReasoningEffortConfig",
    "RUST_MODULE",
    "StatusControlsConfig",
    "StatusControlsState",
    "StatusDetailsCapitalization",
    "TokenInfo",
    "TokenUsage",
    "add_status_output",
    "cancel_terminal_title_setup",
    "open_status_line_setup",
    "preview_terminal_title",
    "revert_terminal_title_setup_preview",
    "set_active_agent_label",
    "set_status",
    "set_status_header",
    "set_status_line",
    "set_status_line_branch",
    "set_status_line_git_summary",
    "set_status_line_hyperlink",
    "setup_status_line",
    "setup_terminal_title",
    "status_line_context_remaining_percent",
    "status_line_context_used_percent",
    "status_line_context_window_size",
    "status_line_limit_display",
    "status_line_reasoning_effort_label",
    "status_line_total_usage",
]
