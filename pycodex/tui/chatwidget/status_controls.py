"""Status output and setup controls for ``ChatWidget``.

Semantic port of Rust ``codex-tui::chatwidget::status_controls``.

The Rust module mutates ``ChatWidget`` state and delegates rendering to
neighboring modules. Python mirrors those state transitions with lightweight
semantic records instead of ratatui widgets, async tasks, or concrete history
cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from .status_state import STATUS_DETAILS_DEFAULT_MAX_LINES, StatusIndicatorState, StatusState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::status_controls",
    source="codex/codex-rs/tui/src/chatwidget/status_controls.rs",
    status="complete",
)


_NO_TERMINAL_TITLE_SETUP = object()


class StatusDetailsCapitalization(str, Enum):
    CapitalizeFirst = "capitalize_first"
    Preserve = "preserve"


class ReasoningEffortConfig(str, Enum):
    Minimal = "minimal"
    Low = "low"
    Medium = "medium"
    High = "high"
    XHigh = "xhigh"
    Max = "max"
    Ultra = "ultra"
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
        remaining = round((max(0, context_window - used) / float(context_window)) * 100)
        return int(remaining)


@dataclass(eq=True)
class TokenInfo:
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
    last_token_usage: TokenUsage = field(default_factory=TokenUsage)
    model_context_window: Optional[int] = None


@dataclass(eq=True)
class RateLimitWindowDisplay:
    used_percent: float


@dataclass(eq=True)
class StatusControlsConfig:
    tui_terminal_title: Optional[List[str]] = None
    tui_status_line: Optional[List[str]] = None
    tui_status_line_use_colors: bool = False
    model_context_window: Optional[int] = None
    model_reasoning_effort: Optional[Any] = None


@dataclass(eq=True)
class StatusSurfacePreviewData:
    live_values: Dict[Any, Any] = field(default_factory=dict)
    suppressed_placeholders: List[Any] = field(default_factory=list)

    @classmethod
    def from_iter(cls, values: Iterable[Tuple[Any, Any]]) -> "StatusSurfacePreviewData":
        return cls(dict(values), [])

    def set_live(self, item: Any, value: Any) -> None:
        self.live_values[item] = value

    def suppress_placeholder(self, item: Any) -> None:
        if item not in self.suppressed_placeholders:
            self.suppressed_placeholders.append(item)


@dataclass(eq=True)
class SetupViewRequest:
    kind: str
    configured_items: Optional[List[Any]]
    use_theme_colors: Optional[bool]
    preview_data: StatusSurfacePreviewData
    keymap: Any = None


@dataclass(eq=True)
class StatusOutputCell:
    refreshing_rate_limits: bool
    request_id: Optional[int]
    token_info: Optional[TokenInfo]
    total_usage: TokenUsage
    rate_limit_snapshots: List[Any]
    model: Optional[str]
    collaboration_mode: Optional[str]
    reasoning_effort_override: Any = None


@dataclass(eq=True)
class StatusOutputHandle:
    cell: StatusOutputCell
    finished_rate_limit_snapshots: Optional[List[Any]] = None
    finished_at: Any = None

    def finish_rate_limit_refresh(self, snapshots: Iterable[Any], now: Any) -> None:
        self.finished_rate_limit_snapshots = list(snapshots)
        self.finished_at = now


@dataclass(eq=True)
class BottomPaneRecorder:
    status_updates: List[Tuple[str, Optional[str], StatusDetailsCapitalization, int]] = field(default_factory=list)
    status_line: Any = None
    status_line_hyperlink: Optional[str] = None
    active_agent_label: Optional[str] = None
    shown_views: List[SetupViewRequest] = field(default_factory=list)
    keymap: Any = None

    def update_status(
        self,
        header: str,
        details: Optional[str],
        details_capitalization: StatusDetailsCapitalization,
        details_max_lines: int,
    ) -> None:
        self.status_updates.append((header, details, details_capitalization, details_max_lines))

    def set_status_line(self, status_line: Any) -> None:
        self.status_line = status_line

    def set_status_line_hyperlink(self, url: Optional[str]) -> None:
        self.status_line_hyperlink = url

    def set_active_agent_label(self, active_agent_label: Optional[str]) -> None:
        self.active_agent_label = active_agent_label

    def show_view(self, view: SetupViewRequest) -> None:
        self.shown_views.append(view)

    def list_keymap(self) -> Any:
        return self.keymap


@dataclass(eq=True)
class StatusControlsState:
    status_state: StatusState = field(default_factory=StatusState)
    bottom_pane: BottomPaneRecorder = field(default_factory=BottomPaneRecorder)
    config: StatusControlsConfig = field(default_factory=StatusControlsConfig)
    terminal_title_setup_original_items: Optional[List[Any]] = None
    terminal_title_setup_active: bool = False
    status_line_branch_cwd: Optional[Path] = None
    status_line_branch: Optional[str] = None
    status_line_branch_pending: bool = False
    status_line_branch_lookup_complete: bool = False
    status_line_git_summary_cwd: Optional[Path] = None
    status_line_git_summary: Any = None
    status_line_git_summary_pending: bool = False
    status_line_git_summary_lookup_complete: bool = False
    token_info: Optional[TokenInfo] = None
    rate_limit_snapshots_by_limit_id: Dict[str, Any] = field(default_factory=dict)
    refreshing_status_outputs: List[Tuple[int, StatusOutputHandle]] = field(default_factory=list)
    history: List[StatusOutputCell] = field(default_factory=list)
    preview_values: Dict[Any, Any] = field(default_factory=dict)
    terminal_title_values: Dict[Any, Any] = field(default_factory=dict)
    configured_status_line_item_values: Optional[List[Any]] = None
    configured_terminal_title_item_values: Optional[List[Any]] = None
    model: Optional[str] = None
    collaboration_mode: Optional[str] = None
    reasoning_effort_override: Any = None
    refreshed_status_surfaces: int = 0
    refreshed_terminal_title: int = 0
    redraw_requests: int = 0

    def refresh_status_surfaces(self) -> None:
        self.refreshed_status_surfaces += 1

    def refresh_terminal_title(self) -> None:
        self.refreshed_terminal_title += 1

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def add_to_history(self, cell: StatusOutputCell) -> None:
        self.history.append(cell)

    def configured_status_line_items(self) -> List[Any]:
        if self.configured_status_line_item_values is not None:
            return list(self.configured_status_line_item_values)
        return list(self.config.tui_status_line or [])

    def configured_terminal_title_items(self) -> List[Any]:
        if self.configured_terminal_title_item_values is not None:
            return list(self.configured_terminal_title_item_values)
        return list(self.config.tui_terminal_title or [])


@dataclass(frozen=True)
class TerminalStatusCommandController:
    """Run terminal ``/status`` through Rust's status refresh lifecycle."""

    app_runtime: Any
    status_writer: Any

    def run(self) -> Any:
        from ..app_event import AppEvent, RateLimitRefreshOrigin
        from ..status.card import terminal_status_output_from_runtime

        if not terminal_should_prefetch_rate_limits(self.app_runtime):
            return self.status_writer.run()

        request_id = self.app_runtime.next_status_rate_limit_request_id()
        output, handle = terminal_status_output_from_runtime(
            self.app_runtime,
            refreshing_rate_limits=True,
        )
        self.app_runtime.register_status_rate_limit_handle(request_id, handle)
        self.app_runtime.handle_app_event(
            AppEvent.refresh_rate_limits(RateLimitRefreshOrigin.status_command(request_id))
        )
        return self.status_writer.write_output(output)


def terminal_should_prefetch_rate_limits(app_runtime: Any) -> bool:
    """Match Rust's provider-auth and ChatGPT-account refresh guard."""

    active = getattr(app_runtime, "active_thread_runtime", None)
    provider = getattr(active, "provider", None)
    requires_openai_auth = getattr(provider, "requires_openai_auth", True)
    if not bool(requires_openai_auth):
        return False
    if not callable(getattr(active, "fetch_account_rate_limits", None)):
        return False
    for auth in (getattr(active, "auth", None), getattr(active, "original_auth", None)):
        if _is_chatgpt_auth(auth):
            return True
    return False


def _is_chatgpt_auth(auth: Any) -> bool:
    if auth is None:
        return False
    predicate = getattr(auth, "is_chatgpt", None)
    if callable(predicate):
        try:
            if bool(predicate()):
                return True
        except TypeError:
            pass
    mode = auth.get("auth_mode") if isinstance(auth, dict) else getattr(auth, "auth_mode", None)
    if callable(mode):
        try:
            mode = mode()
        except TypeError:
            mode = None
    normalized = str(getattr(mode, "value", mode) or "").replace("_", "").replace("-", "").lower()
    return normalized in {"chatgpt", "chatgptauthtokens"}


def _capitalize_first(value: str) -> str:
    if not value:
        return value
    return value[0].upper() + value[1:]


def set_status(
    state: StatusControlsState,
    header: str,
    details: Optional[str],
    details_capitalization: StatusDetailsCapitalization,
    details_max_lines: int,
) -> None:
    detail_value = None
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
    if any(item in ("run-state", "status") for item in title_items):
        state.refresh_status_surfaces()


def set_status_header(state: StatusControlsState, header: str) -> None:
    set_status(
        state,
        header,
        None,
        StatusDetailsCapitalization.CapitalizeFirst,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )


def set_status_line(state: StatusControlsState, status_line: Any) -> None:
    state.bottom_pane.set_status_line(status_line)


def set_status_line_hyperlink(state: StatusControlsState, url: Optional[str]) -> None:
    state.bottom_pane.set_status_line_hyperlink(url)


def set_active_agent_label(state: StatusControlsState, active_agent_label: Optional[str]) -> None:
    state.bottom_pane.set_active_agent_label(active_agent_label)


def refresh_status_line(state: StatusControlsState) -> None:
    state.refresh_status_surfaces()


def cancel_status_line_setup(state: StatusControlsState) -> None:
    del state


def setup_status_line(state: StatusControlsState, items: Iterable[Any], use_theme_colors: bool) -> None:
    state.config.tui_status_line = [str(item) for item in items]
    state.config.tui_status_line_use_colors = use_theme_colors
    refresh_status_line(state)


def preview_terminal_title(state: StatusControlsState, items: Iterable[Any]) -> None:
    if not state.terminal_title_setup_active:
        current = state.config.tui_terminal_title
        state.terminal_title_setup_original_items = None if current is None else list(current)
        state.terminal_title_setup_active = True
    state.config.tui_terminal_title = [str(item) for item in items]
    state.refresh_terminal_title()


def revert_terminal_title_setup_preview(state: StatusControlsState) -> None:
    if not state.terminal_title_setup_active:
        return
    original = state.terminal_title_setup_original_items
    state.terminal_title_setup_active = False
    state.terminal_title_setup_original_items = None
    state.config.tui_terminal_title = None if original is None else list(original)
    state.refresh_terminal_title()


def cancel_terminal_title_setup(state: StatusControlsState) -> None:
    revert_terminal_title_setup_preview(state)


def setup_terminal_title(state: StatusControlsState, items: Iterable[Any]) -> None:
    state.terminal_title_setup_active = False
    state.terminal_title_setup_original_items = None
    state.config.tui_terminal_title = [str(item) for item in items]
    state.refresh_terminal_title()


def set_status_line_branch(state: StatusControlsState, cwd: Any, branch: Optional[str]) -> None:
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


def add_status_output(
    state: StatusControlsState,
    refreshing_rate_limits: bool,
    request_id: Optional[int] = None,
) -> StatusOutputCell:
    default_usage = TokenUsage()
    token_info = state.token_info
    total_usage = token_info.total_token_usage if token_info is not None else default_usage
    snapshots = list(state.rate_limit_snapshots_by_limit_id.values())
    cell = StatusOutputCell(
        refreshing_rate_limits=refreshing_rate_limits,
        request_id=request_id,
        token_info=token_info,
        total_usage=total_usage,
        rate_limit_snapshots=snapshots,
        model=state.model,
        collaboration_mode=state.collaboration_mode,
        reasoning_effort_override=state.reasoning_effort_override,
    )
    if request_id is not None:
        state.refreshing_status_outputs.append((request_id, StatusOutputHandle(cell)))
    state.add_to_history(cell)
    return cell


def finish_status_rate_limit_refresh(state: StatusControlsState, request_id: int, now: Any = None) -> None:
    if not state.refreshing_status_outputs:
        return
    snapshots = list(state.rate_limit_snapshots_by_limit_id.values())
    remaining = []
    updated_any = False
    for pending_request_id, handle in state.refreshing_status_outputs:
        if pending_request_id == request_id:
            updated_any = True
            handle.finish_rate_limit_refresh(snapshots, now)
        else:
            remaining.append((pending_request_id, handle))
    state.refreshing_status_outputs = remaining
    if updated_any:
        state.request_redraw()


def status_surface_preview_data(state: StatusControlsState) -> StatusSurfacePreviewData:
    preview_data = StatusSurfacePreviewData.from_iter(state.preview_values.items())
    if "codex" in state.rate_limit_snapshots_by_limit_id:
        for item in ("five_hour_limit", "weekly_limit"):
            if item not in preview_data.live_values:
                preview_data.suppress_placeholder(item)
    return preview_data


def terminal_title_preview_data(state: StatusControlsState) -> StatusSurfacePreviewData:
    preview_data = status_surface_preview_data(state)
    for item, value in state.terminal_title_values.items():
        preview_data.set_live(item, value)
    return preview_data


def open_status_line_setup(state: StatusControlsState) -> SetupViewRequest:
    view = SetupViewRequest(
        kind="status_line",
        configured_items=state.configured_status_line_items(),
        use_theme_colors=state.config.tui_status_line_use_colors,
        preview_data=status_surface_preview_data(state),
        keymap=state.bottom_pane.list_keymap(),
    )
    state.bottom_pane.show_view(view)
    return view


def open_terminal_title_setup(state: StatusControlsState) -> SetupViewRequest:
    current = state.config.tui_terminal_title
    state.terminal_title_setup_original_items = None if current is None else list(current)
    state.terminal_title_setup_active = True
    view = SetupViewRequest(
        kind="terminal_title",
        configured_items=state.configured_terminal_title_items(),
        use_theme_colors=None,
        preview_data=terminal_title_preview_data(state),
        keymap=state.bottom_pane.list_keymap(),
    )
    state.bottom_pane.show_view(view)
    return view


def status_line_context_window_size(state: StatusControlsState) -> Optional[int]:
    if state.token_info is not None and state.token_info.model_context_window is not None:
        return state.token_info.model_context_window
    return state.config.model_context_window


def status_line_context_remaining_percent(state: StatusControlsState) -> Optional[int]:
    context_window = status_line_context_window_size(state)
    if context_window is None:
        return 100
    usage = state.token_info.last_token_usage if state.token_info is not None else TokenUsage()
    return max(0, min(100, usage.percent_of_context_window_remaining(context_window)))


def status_line_context_used_percent(state: StatusControlsState) -> Optional[int]:
    remaining = status_line_context_remaining_percent(state)
    if remaining is None:
        remaining = 100
    return max(0, min(100, 100 - remaining))


def status_line_total_usage(state: StatusControlsState) -> TokenUsage:
    if state.token_info is None:
        return TokenUsage()
    return state.token_info.total_token_usage


def status_line_limit_display(window: Optional[RateLimitWindowDisplay], label: str) -> Optional[str]:
    if window is None:
        return None
    remaining = max(0.0, min(100.0, 100.0 - window.used_percent))
    return "%s %.0f%% left" % (label, remaining)


def status_line_reasoning_effort_label(effort: Optional[Any]) -> str:
    if effort is None:
        return "default"
    value = effort.value if isinstance(effort, ReasoningEffortConfig) else str(effort).lower()
    return {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "max": "max",
        "ultra": "ultra",
        "none": "default",
    }.get(value, "default")


__all__ = [
    "BottomPaneRecorder",
    "RateLimitWindowDisplay",
    "ReasoningEffortConfig",
    "RUST_MODULE",
    "SetupViewRequest",
    "StatusControlsConfig",
    "StatusControlsState",
    "TerminalStatusCommandController",
    "StatusDetailsCapitalization",
    "StatusOutputCell",
    "StatusOutputHandle",
    "StatusSurfacePreviewData",
    "TokenInfo",
    "TokenUsage",
    "add_status_output",
    "cancel_status_line_setup",
    "cancel_terminal_title_setup",
    "finish_status_rate_limit_refresh",
    "open_status_line_setup",
    "open_terminal_title_setup",
    "preview_terminal_title",
    "refresh_status_line",
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
    "status_surface_preview_data",
    "terminal_title_preview_data",
    "terminal_should_prefetch_rate_limits",
]
