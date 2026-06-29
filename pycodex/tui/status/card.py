"""Semantic slice for Rust ``codex-tui::status::card``.

This module keeps the status-card data shaping behavior testable without
replicating ratatui history-cell rendering or upstream protocol classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from urllib.parse import urlsplit, urlunsplit

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..version import CODEX_CLI_VERSION
from .account import StatusAccountDisplay
from .format import FieldFormatter, line_display_width, push_label, truncate_line_to_width
from .helpers import format_directory_display, format_tokens_compact
from .rate_limits import (
    RateLimitSnapshotDisplay,
    StatusRateLimitData,
    StatusRateLimitRow,
    StatusRateLimitValue,
    compose_rate_limit_data,
    compose_rate_limit_data_many,
    format_status_limit_summary,
    render_status_limit_progress_bar,
)
from .remote_connection import RemoteConnectionStatus

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status::card",
    source="codex/codex-rs/tui/src/status/card.rs",
    status="complete",
)

CHATGPT_USAGE_URL = "https://chatgpt.com/codex/settings/usage"
DIM_STYLE = {"dim": True}
BOLD_STYLE = {"bold": True}
CYAN_STYLE = {"fg": "cyan"}
UNDERLINED_CYAN_STYLE = {"fg": "cyan", "underlined": True}


@dataclass(frozen=True)
class StatusContextWindowData:
    percent_remaining: int
    tokens_in_context: int
    window: int


@dataclass(frozen=True)
class StatusTokenUsageData:
    total: int
    input: int
    output: int
    context_window: Optional[StatusContextWindowData] = None


@dataclass
class StatusRateLimitState:
    rate_limits: StatusRateLimitData
    refreshing_rate_limits: bool = False


@dataclass(frozen=True)
class CompositeStatusOutput:
    command_lines: Tuple[Line, ...]
    card: "StatusHistoryCell"

    def display_lines(self, width: int) -> Tuple[Line, ...]:
        return (*self.command_lines, *self.card.display_lines(width))


@dataclass
class StatusHistoryHandle:
    rate_limit_state: StatusRateLimitState

    def finish_rate_limit_refresh(self, rate_limits: Iterable[RateLimitSnapshotDisplay], now: datetime) -> None:
        snapshots = tuple(rate_limits)
        self.rate_limit_state.rate_limits = (
            compose_rate_limit_data(snapshots[0] if snapshots else None, now)
            if len(snapshots) <= 1
            else compose_rate_limit_data_many(snapshots, now)
        )
        self.rate_limit_state.refreshing_rate_limits = False


@dataclass
class StatusHistoryCell:
    model_name: str
    model_details: Tuple[str, ...] = ()
    directory: Path = field(default_factory=lambda: Path.cwd())
    permissions: str = "<unknown>"
    agents_summary: str = "<none>"
    collaboration_mode: Optional[str] = None
    model_provider: Optional[str] = None
    remote_connection: Optional[RemoteConnectionStatus] = None
    show_chatgpt_usage_link: bool = False
    account: Optional[StatusAccountDisplay] = None
    thread_name: Optional[str] = None
    session_id: Optional[str] = None
    forked_from: Optional[str] = None
    token_usage: StatusTokenUsageData = field(default_factory=lambda: StatusTokenUsageData(0, 0, 0))
    rate_limit_state: StatusRateLimitState = field(default_factory=lambda: StatusRateLimitState(StatusRateLimitData.missing()))

    @classmethod
    def new(
        cls,
        *,
        model_name: str,
        model_details: Iterable[str] = (),
        directory: Optional[Union[str, Path]] = None,
        permissions: str = "<unknown>",
        agents_summary: str = "<none>",
        collaboration_mode: Optional[str] = None,
        model_provider: Optional[str] = None,
        remote_connection: Optional[RemoteConnectionStatus] = None,
        show_chatgpt_usage_link: bool = False,
        account: Optional[StatusAccountDisplay] = None,
        thread_name: Optional[str] = None,
        session_id: Optional[str] = None,
        forked_from: Optional[str] = None,
        token_usage: Optional[StatusTokenUsageData] = None,
        rate_limits: Iterable[RateLimitSnapshotDisplay] = (),
        now: Optional[datetime] = None,
        refreshing_rate_limits: bool = False,
    ) -> Tuple["StatusHistoryCell", StatusHistoryHandle]:
        snapshots = tuple(rate_limits)
        now = now or datetime.now().astimezone()
        rate_limit_data = (
            compose_rate_limit_data(snapshots[0] if snapshots else None, now)
            if len(snapshots) <= 1
            else compose_rate_limit_data_many(snapshots, now)
        )
        state = StatusRateLimitState(rate_limit_data, refreshing_rate_limits)
        cell = cls(
            model_name=str(model_name),
            model_details=tuple(str(item) for item in model_details),
            directory=Path.cwd() if directory is None else Path(directory),
            permissions=str(permissions),
            agents_summary=str(agents_summary),
            collaboration_mode=collaboration_mode,
            model_provider=model_provider,
            remote_connection=remote_connection,
            show_chatgpt_usage_link=show_chatgpt_usage_link,
            account=account,
            thread_name=thread_name,
            session_id=session_id,
            forked_from=forked_from,
            token_usage=token_usage or StatusTokenUsageData(0, 0, 0),
            rate_limit_state=state,
        )
        return cell, StatusHistoryHandle(state)

    def token_usage_spans(self) -> Tuple[Span, ...]:
        total_fmt = format_tokens_compact(self.token_usage.total)
        input_fmt = format_tokens_compact(self.token_usage.input)
        output_fmt = format_tokens_compact(self.token_usage.output)
        return (
            Span(total_fmt),
            Span(" total "),
            Span(" (", DIM_STYLE),
            Span(input_fmt, DIM_STYLE),
            Span(" input", DIM_STYLE),
            Span(" + ", DIM_STYLE),
            Span(output_fmt, DIM_STYLE),
            Span(" output", DIM_STYLE),
            Span(")", DIM_STYLE),
        )

    def context_window_spans(self) -> Optional[Tuple[Span, ...]]:
        context = self.token_usage.context_window
        if context is None:
            return None
        return (
            Span(f"{context.percent_remaining}% left"),
            Span(" (", DIM_STYLE),
            Span(format_tokens_compact(context.tokens_in_context), DIM_STYLE),
            Span(" used / ", DIM_STYLE),
            Span(format_tokens_compact(context.window), DIM_STYLE),
            Span(")", DIM_STYLE),
        )

    def rate_limit_lines(self, state: StatusRateLimitState, available_inner_width: int, formatter: FieldFormatter) -> List[Line]:
        data = state.rate_limits
        if data.kind == "available":
            if not data.rows:
                return [formatter.line("Limits", [Span("not available for this account", DIM_STYLE)])]
            return self.rate_limit_row_lines(data.rows, available_inner_width, formatter)
        if data.kind == "stale":
            lines = self.rate_limit_row_lines(data.rows, available_inner_width, formatter)
            warning = "limits may be stale - run /status again shortly." if state.refreshing_rate_limits else "limits may be stale - start new turn to refresh."
            lines.append(formatter.line("Warning", [Span(warning, DIM_STYLE)]))
            return lines
        if data.kind == "unavailable":
            return [formatter.line("Limits", [Span("not available for this account", DIM_STYLE)])]
        message = "refresh requested; run /status again shortly." if state.refreshing_rate_limits else "data not available yet"
        return [formatter.line("Limits", [Span(message, DIM_STYLE)])]

    def rate_limit_row_lines(self, rows: Iterable[StatusRateLimitRow], available_inner_width: int, formatter: FieldFormatter) -> List[Line]:
        lines: List[Line] = []
        for row in rows:
            value = row.value
            if value.kind == "window":
                percent_used = value.percent_used or 0.0
                percent_remaining = min(max(100.0 - percent_used, 0.0), 100.0)
                summary = format_status_limit_summary(percent_remaining)
                full_value_spans = [Span(render_status_limit_progress_bar(percent_remaining)), Span(" "), Span(summary)]
                value_spans = full_value_spans if line_display_width(Line.from_spans(full_value_spans)) <= formatter.value_width(available_inner_width) else [Span(summary)]
                base_spans = formatter.full_spans(row.label, value_spans)
                base_line = Line.from_spans(base_spans)
                if value.resets_at:
                    inline_spans = (*base_spans, Span(" ", DIM_STYLE), Span(f"(resets {value.resets_at})", DIM_STYLE))
                    if line_display_width(Line.from_spans(inline_spans)) <= available_inner_width:
                        lines.append(Line.from_spans(inline_spans))
                    else:
                        lines.append(base_line)
                        reset_width = max(formatter.value_width(available_inner_width), 1)
                        for part in _word_wrap(f"(resets {value.resets_at})", reset_width):
                            lines.append(formatter.continuation([Span(part, DIM_STYLE)]))
                else:
                    lines.append(base_line)
            else:
                lines.append(Line.from_spans(formatter.full_spans(row.label, [Span(value.text or "")])) )
        return lines

    def collect_rate_limit_labels(self, state: StatusRateLimitState, seen: Set[str], labels: List[str]) -> None:
        data = state.rate_limits
        if data.kind == "available":
            if not data.rows:
                push_label(labels, seen, "Limits")
            else:
                for row in data.rows:
                    push_label(labels, seen, row.label)
        elif data.kind == "stale":
            for row in data.rows:
                push_label(labels, seen, row.label)
            push_label(labels, seen, "Warning")
        else:
            push_label(labels, seen, "Limits")

    def display_lines(self, width: int) -> Tuple[Line, ...]:
        available_inner_width = max(int(width) - 4, 0)
        if available_inner_width == 0:
            return ()
        labels = ["Model", "Directory", "Permissions", "Agents.md"]
        seen = set(labels)
        if self.model_provider:
            push_label(labels, seen, "Model provider")
        account_value = self.account_value()
        if account_value:
            push_label(labels, seen, "Account")
        if self.thread_name:
            push_label(labels, seen, "Thread name")
        if self.session_id:
            push_label(labels, seen, "Session")
        if self.session_id and self.forked_from:
            push_label(labels, seen, "Forked from")
        if self.collaboration_mode:
            push_label(labels, seen, "Collaboration mode")
        push_label(labels, seen, "Token usage")
        if self.token_usage.context_window:
            push_label(labels, seen, "Context window")
        self.collect_rate_limit_labels(self.rate_limit_state, seen, labels)

        formatter = FieldFormatter.from_labels(labels)
        value_width = formatter.value_width(available_inner_width)
        lines: List[Line] = [Line.from_spans([Span(f"{FieldFormatter.INDENT}>_ ", DIM_STYLE), Span("OpenAI Codex", BOLD_STYLE), Span(" ", DIM_STYLE), Span(f"(v{CODEX_CLI_VERSION})", DIM_STYLE)]), Line(())]
        if self.show_chatgpt_usage_link:
            lines.append(Line.from_spans([Span("Visit ", CYAN_STYLE), Span(CHATGPT_USAGE_URL, UNDERLINED_CYAN_STYLE), Span(" for up-to-date", CYAN_STYLE)]))
            lines.append(Line.from_spans([Span("information on rate limits and credits", CYAN_STYLE)]))
            lines.append(Line(()))
        if self.remote_connection:
            lines.append(formatter.line("Remote", [Span(f"{self.remote_connection.address} ({self.remote_connection.version})")]))
            lines.append(Line(()))

        model_spans = [Span(self.model_name)]
        if self.model_details:
            model_spans.extend([Span(" (", DIM_STYLE), Span(", ".join(self.model_details), DIM_STYLE), Span(")", DIM_STYLE)])
        lines.append(formatter.line("Model", model_spans))
        if self.model_provider:
            lines.append(formatter.line("Model provider", [Span(self.model_provider)]))
        lines.append(formatter.line("Directory", [Span(format_directory_display(self.directory, value_width))]))
        lines.append(formatter.line("Permissions", [Span(self.permissions)]))
        lines.append(formatter.line("Agents.md", [Span(self.agents_summary)]))
        if account_value:
            lines.append(formatter.line("Account", [Span(account_value)]))
        if self.thread_name:
            lines.append(formatter.line("Thread name", [Span(self.thread_name)]))
        if self.collaboration_mode:
            lines.append(formatter.line("Collaboration mode", [Span(self.collaboration_mode)]))
        if self.session_id:
            lines.append(formatter.line("Session", [Span(self.session_id)]))
        if self.session_id and self.forked_from:
            lines.append(formatter.line("Forked from", [Span(self.forked_from)]))
        lines.append(Line(()))
        if not _is_chatgpt_account(self.account):
            lines.append(formatter.line("Token usage", self.token_usage_spans()))
        context_spans = self.context_window_spans()
        if context_spans:
            lines.append(formatter.line("Context window", context_spans))
        lines.extend(self.rate_limit_lines(self.rate_limit_state, available_inner_width, formatter))

        content_width = min(max((line_display_width(line) for line in lines), default=0), available_inner_width)
        return tuple(truncate_line_to_width(line, content_width) for line in lines)

    def raw_lines(self) -> Tuple[Line, ...]:
        return self.display_lines(2**16 - 1)

    def display_hyperlink_lines(self, width: int) -> Tuple[Dict[str, Any], ...]:
        out = []
        for line in self.display_lines(width):
            text = "".join(span.content for span in line.spans)
            hyperlinks = []
            start = text.find(CHATGPT_USAGE_URL)
            if start >= 0:
                hyperlinks.append({"columns": range(start, start + len(CHATGPT_USAGE_URL)), "destination": CHATGPT_USAGE_URL})
            out.append({"line": line, "hyperlinks": hyperlinks})
        return tuple(out)

    def transcript_hyperlink_lines(self, width: int) -> Tuple[Dict[str, Any], ...]:
        return self.display_hyperlink_lines(width)

    def account_value(self) -> Optional[str]:
        account = self.account
        if account is None:
            return None
        kind = getattr(account, "kind", None)
        if kind == "api_key" or account == StatusAccountDisplay.api_key():
            return "API key configured (run codex login to use ChatGPT)"
        email = getattr(account, "email", None)
        plan = getattr(account, "plan", None)
        if email and plan:
            return f"{email} ({plan})"
        if email:
            return str(email)
        if plan:
            return str(plan)
        return "ChatGPT"


def new_status_output(*args: Any, **kwargs: Any) -> CompositeStatusOutput:
    cell, _handle = new_status_output_with_rate_limits_handle(*args, **kwargs)
    return cell


def new_status_output_with_rate_limits(*args: Any, **kwargs: Any) -> CompositeStatusOutput:
    cell, _handle = new_status_output_with_rate_limits_handle(*args, **kwargs)
    return cell


def new_status_output_with_rate_limits_handle(**kwargs: Any) -> Tuple[CompositeStatusOutput, StatusHistoryHandle]:
    cell, handle = StatusHistoryCell.new(**kwargs)
    command = Line.from_spans([Span("/status", {"fg": "magenta"})])
    return CompositeStatusOutput((command,), cell), handle


def status_permission_summary(summary: str, *_args: Any, **_kwargs: Any) -> str:
    text = str(summary)
    if text.startswith("read-only"):
        return "read-only with network access" if "(network access enabled)" in text else "read-only"
    if text.startswith("workspace-write"):
        return "workspace with network access" if "(network access enabled)" in text else "workspace"
    if text == "custom permissions (network access enabled)":
        return "custom permissions with network access"
    return text


def workspace_root_suffix(workspace_roots: Iterable[Union[str, Path]], cwd: Union[str, Path]) -> Optional[str]:
    cwd_text = str(cwd)
    extra = [str(root) for root in workspace_roots if str(root) != cwd_text]
    return f" [{', '.join(extra)}]" if extra else None


def status_permissions_label(
    active_permission_profile: Any,
    permission_profile: Any,
    approval_policy: str,
    sandbox: str,
    approval: str,
    workspace_root_suffix: Optional[str] = None,
) -> str:
    active_id = _active_profile_id(active_permission_profile)
    approval_policy = _display_scalar(approval_policy)
    approval = _display_scalar(approval)
    if active_id == "read-only":
        label = "Read Only with network access" if sandbox == "read-only with network access" else "Read Only"
        return f"{label} ({approval})"
    if active_id == "workspace-write":
        if sandbox == "workspace":
            return f"Workspace{workspace_root_suffix or ''} ({approval})"
        if sandbox == "workspace with network access":
            return f"Workspace with network access{workspace_root_suffix or ''} ({approval})"
    if active_id == "danger-full-access" and _permission_profile_disabled(permission_profile):
        return "Full Access" if approval_policy == "never" else f"No Sandbox ({approval})"
    if active_id:
        decorated = decorate_workspace_sandbox_label(sandbox, workspace_root_suffix)
        return f"Profile {active_id} ({decorated}, {approval})"
    if sandbox == "read-only":
        return f"Read Only ({approval})"
    if approval_policy == "on-request" and sandbox == "workspace":
        return f"Workspace{workspace_root_suffix or ''} ({approval})"
    if approval_policy == "never" and _permission_profile_disabled(permission_profile):
        return "Full Access"
    decorated = decorate_workspace_sandbox_label(sandbox, workspace_root_suffix)
    return f"Custom ({decorated}, {approval})"


def _display_scalar(value: Any) -> str:
    for method_name in ("as_str", "to_json"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, str):
                return result
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)


def decorate_workspace_sandbox_label(sandbox: str, workspace_root_suffix: Optional[str]) -> str:
    if workspace_root_suffix and str(sandbox).startswith("workspace"):
        return f"{sandbox}{workspace_root_suffix}"
    return str(sandbox)


def status_approval_label(approval_policy: str, approvals_reviewer: str, approval: str) -> str:
    approval_policy = _display_scalar(approval_policy)
    approvals_reviewer = _display_scalar(approvals_reviewer)
    approval = _display_scalar(approval)
    return "auto-review" if approval_policy == "on-request" and approvals_reviewer == "auto-review" else approval


def display_lines(cell: StatusHistoryCell, width: int) -> Tuple[Line, ...]:
    return cell.display_lines(width)


def raw_lines(cell: StatusHistoryCell) -> Tuple[Line, ...]:
    return cell.raw_lines()


def display_hyperlink_lines(cell: StatusHistoryCell, width: int) -> Tuple[Dict[str, Any], ...]:
    return cell.display_hyperlink_lines(width)


def transcript_hyperlink_lines(cell: StatusHistoryCell, width: int) -> Tuple[Dict[str, Any], ...]:
    return cell.transcript_hyperlink_lines(width)


def format_model_provider(config: Any, runtime_base_url: Optional[str] = None) -> Optional[str]:
    provider = getattr(config, "model_provider", config)
    provider_name = str(getattr(provider, "name", "") or getattr(config, "model_provider_id", "")).strip()
    base_url = sanitize_base_url(runtime_base_url) if runtime_base_url is not None else None
    is_openai = bool(getattr(provider, "is_openai", lambda: False)()) if callable(getattr(provider, "is_openai", None)) else bool(getattr(provider, "openai", False))
    if is_openai and base_url is None:
        return None
    return f"{provider_name} - {base_url}" if base_url else provider_name


def sanitize_base_url(raw: str) -> Optional[str]:
    trimmed = str(raw).strip()
    if not trimmed:
        return None
    parts = urlsplit(trimmed)
    if not parts.scheme or not parts.netloc:
        return None
    hostname = parts.hostname or ""
    if not hostname:
        return None
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    sanitized = urlunsplit((parts.scheme, netloc, parts.path, "", "")).rstrip("/")
    return sanitized or None


def _word_wrap(text: str, width: int) -> List[str]:
    words = text.split(" ")
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _active_profile_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return getattr(value, "id", None)


def _permission_profile_disabled(value: Any) -> bool:
    return value is None or str(value).lower() in {"disabled", "none", "false"} or getattr(value, "kind", None) == "disabled"


def _is_chatgpt_account(account: Any) -> bool:
    return account is not None and getattr(account, "kind", None) == "chatgpt"


__all__ = [
    "CHATGPT_USAGE_URL",
    "CompositeStatusOutput",
    "RUST_MODULE",
    "StatusContextWindowData",
    "StatusHistoryCell",
    "StatusHistoryHandle",
    "StatusRateLimitState",
    "StatusTokenUsageData",
    "decorate_workspace_sandbox_label",
    "display_hyperlink_lines",
    "display_lines",
    "format_model_provider",
    "new_status_output",
    "new_status_output_with_rate_limits",
    "new_status_output_with_rate_limits_handle",
    "raw_lines",
    "sanitize_base_url",
    "status_approval_label",
    "status_permission_summary",
    "status_permissions_label",
    "transcript_hyperlink_lines",
    "workspace_root_suffix",
]
