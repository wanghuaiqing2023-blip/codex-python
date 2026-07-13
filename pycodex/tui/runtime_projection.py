"""Runtime display projections shared by the terminal TUI.

Rust ownership:
- ``codex-tui::chatwidget::status_surfaces`` owns status/footer projections.
- ``codex-tui::history_cell::session`` owns startup session notices.
- ``codex-tui::app`` owns runtime/thread identity routing.

This module is the neutral place for turning a ``TuiAppRuntime`` into
display-ready values.  It must not own widget behavior.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pycodex.utils.sandbox_summary import summarize_permission_profile

from .app.runtime import ActiveThreadRuntime, TuiAppRuntime
from .bottom_pane.status_line_setup import StatusLineItem
from .chatwidget.status_surfaces import DEFAULT_STATUS_LINE_ITEMS
from .history_cell.session import has_yolo_permissions
from .status.card import (
    StatusContextWindowData,
    StatusTokenUsageData,
    status_approval_label,
    status_permission_summary,
    status_permissions_label,
    workspace_root_suffix,
)
from .status.helpers import compose_agents_summary, compose_model_display, format_tokens_compact
from .tooltips import APP_TOOLTIP


def configure_app_runtime_thread_identity(
    app_runtime: TuiAppRuntime,
    active_thread_runtime: ActiveThreadRuntime,
) -> None:
    """Mirror the app/thread identity bridge used by the terminal projection path."""

    thread_id = _runtime_thread_id(active_thread_runtime)
    if thread_id is not None and str(thread_id).strip():
        app_runtime.thread_id = thread_id
        app_runtime.routing_state.active_thread_id = thread_id
        primary_thread_id = _runtime_primary_thread_id(active_thread_runtime) or thread_id
        app_runtime.routing_state.primary_thread_id = primary_thread_id
        app_runtime.upsert_agent_picker_thread(thread_id)
    else:
        app_runtime.sync_active_agent_label()
    for entry in _runtime_agent_navigation_entries(active_thread_runtime):
        entry_thread_id = entry.get("thread_id")
        if entry_thread_id is None:
            continue
        app_runtime.upsert_agent_picker_thread(
            str(entry_thread_id),
            agent_nickname=_optional_text(entry.get("agent_nickname") or entry.get("nickname")),
            agent_role=_optional_text(entry.get("agent_role") or entry.get("role")),
            is_closed=bool(entry.get("is_closed") or entry.get("closed")),
        )
    active_agent_label = _runtime_active_agent_label(active_thread_runtime)
    if active_agent_label is not None and getattr(app_runtime.chat_widget, "active_agent_label", None) is None:
        app_runtime.chat_widget.set_active_agent_label(active_agent_label)
    rollout_path = getattr(active_thread_runtime, "rollout_path", None)
    if rollout_path is not None:
        try:
            app_runtime.rollout_path = Path(rollout_path)
        except TypeError:
            pass
    cwd = getattr(active_thread_runtime, "cwd", None)
    config = getattr(active_thread_runtime, "session_config", None)
    if cwd is None:
        cwd = getattr(config, "cwd", None)
    if cwd is not None:
        try:
            app_runtime.cwd = Path(cwd)
        except TypeError:
            pass


def _runtime_thread_id(active_thread_runtime: ActiveThreadRuntime) -> str | None:
    model_client = getattr(active_thread_runtime, "model_client", None)
    model_client_state = getattr(model_client, "state", None)
    for source in (active_thread_runtime, model_client, model_client_state):
        value = _runtime_first_value(source, names=("thread_id", "conversation_id", "session_id"))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _runtime_primary_thread_id(active_thread_runtime: ActiveThreadRuntime) -> str | None:
    for name in ("primary_thread_id", "main_thread_id"):
        value = getattr(active_thread_runtime, name, None)
        value = value() if callable(value) else value
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _runtime_active_agent_label(active_thread_runtime: ActiveThreadRuntime) -> str | None:
    label = getattr(active_thread_runtime, "active_agent_label", None)
    label = label() if callable(label) else label
    if label is None:
        chat_widget = getattr(active_thread_runtime, "chat_widget", None)
        label = getattr(chat_widget, "active_agent_label", None)
        label = label() if callable(label) else label
    return None if label is None or not str(label).strip() else str(label).strip()


def _runtime_agent_navigation_entries(active_thread_runtime: ActiveThreadRuntime) -> list[dict[str, object]]:
    raw = getattr(active_thread_runtime, "agent_navigation_entries", None)
    raw = raw() if callable(raw) else raw
    if raw is None:
        raw = getattr(active_thread_runtime, "agent_threads", None)
        raw = raw() if callable(raw) else raw
    if raw is None:
        return []
    entries: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            entries.append(dict(item))
            continue
        thread_id = getattr(item, "thread_id", None)
        if thread_id is None:
            continue
        entries.append(
            {
                "thread_id": thread_id,
                "agent_nickname": getattr(item, "agent_nickname", None),
                "agent_role": getattr(item, "agent_role", None),
                "is_closed": getattr(item, "is_closed", False),
            }
        )
    return entries


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display_version() -> str:
    try:
        from pycodex import __version__  # type: ignore

        value = str(__version__).strip()
        return value or "0.1.0"
    except Exception:
        return "0.1.0"


def _display_directory_for_path(path: Path | str) -> str:
    cwd = Path(path)
    home = Path.home()
    try:
        rel = cwd.relative_to(home)
        return "~" if str(rel) == "." else f"~{os.sep}{rel}"
    except ValueError:
        return str(cwd)


def _runtime_display_model(app_runtime: TuiAppRuntime) -> str:
    chat_widget = getattr(app_runtime, "chat_widget", None)
    for source in (
        chat_widget,
        getattr(chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        for name in ("selected_model", "model", "model_slug", "requested_model"):
            value = getattr(source, name, None)
            value = value() if callable(value) else value
            if value is not None and str(value).strip():
                return str(value).strip()
    return (os.environ.get("PYCODEX_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.5").strip() or "gpt-5.5"


def _runtime_model_with_reasoning(app_runtime: TuiAppRuntime) -> str:
    model = _runtime_display_model(app_runtime)
    effort = _runtime_header_reasoning_effort(app_runtime)
    parts = [model]
    if effort is not None:
        label = str(getattr(effort, "value", effort)).replace("_", "-").lower()
        if label and label != "default":
            parts.append(label)
    if _runtime_show_fast_status(app_runtime):
        parts.append("fast")
    return " ".join(parts)


def _runtime_header_reasoning_effort(app_runtime: TuiAppRuntime) -> str | None:
    details = _runtime_model_details(app_runtime)
    for detail in details:
        normalized = str(detail).strip().lower().replace("-", "_")
        if normalized.startswith("reasoning "):
            normalized = normalized.removeprefix("reasoning ").strip().replace("-", "_")
        elif normalized.startswith("summaries "):
            continue
        if normalized and normalized != "fast":
            return normalized
    for source in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        for name in ("effective_reasoning_effort", "model_reasoning_effort", "reasoning_effort"):
            effort = getattr(source, name, None)
            effort = effort() if callable(effort) else effort
            if effort is not None and str(effort).strip():
                label = str(getattr(effort, "value", effort)).replace("-", "_").lower()
                return label if label and label != "default" else None
    return None


def _runtime_show_fast_status(app_runtime: TuiAppRuntime) -> bool:
    return any(str(detail).strip().lower() == "fast" for detail in _runtime_model_details(app_runtime))


def _runtime_model_details(app_runtime: TuiAppRuntime) -> tuple[str, ...]:
    details = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("model_details", "status_model_details"),
    )
    if isinstance(details, str):
        return (details,)
    if isinstance(details, Iterable):
        return tuple(str(item) for item in details if str(item))
    if details is not None:
        return (str(details),)
    config_entries: list[tuple[str, str]] = []
    effort = _runtime_reasoning_effort_for_status(app_runtime)
    if effort:
        config_entries.append(("reasoning effort", effort))
    summary = _runtime_reasoning_summary_for_status(app_runtime)
    if summary:
        config_entries.append(("reasoning summaries", summary))
    if not config_entries:
        return ()
    _model_name, composed_details = compose_model_display(_runtime_display_model(app_runtime), config_entries)
    return tuple(composed_details)


def _runtime_reasoning_effort_for_status(app_runtime: TuiAppRuntime) -> str | None:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        getattr(app_runtime.active_thread_runtime, "model_info", None),
        names=("effective_reasoning_effort", "model_reasoning_effort", "reasoning_effort", "default_reasoning_level"),
    )
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip().replace("_", "-").lower()
    return text or None


def _runtime_reasoning_summary_for_status(app_runtime: TuiAppRuntime) -> str | None:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        getattr(app_runtime.active_thread_runtime, "model_info", None),
        names=("model_reasoning_summary", "reasoning_summary", "default_reasoning_summary"),
    )
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip().replace("_", "-").lower()
    if text in {"", "default"}:
        return None
    return text


def _runtime_agents_summary(app_runtime: TuiAppRuntime) -> str:
    sources = (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
    )
    value = _runtime_first_value(*sources, names=("agents_summary", "agents_md_summary", "agents"))
    if value is None:
        paths = _runtime_first_value(
            *sources,
            names=("instruction_source_paths", "instruction_sources", "agents_md_paths", "instructions_paths"),
        )
        if paths is not None and not isinstance(paths, str):
            try:
                return compose_agents_summary(getattr(app_runtime.active_thread_runtime, "session_config", None), paths)  # type: ignore[arg-type]
            except (TypeError, ValueError, OSError):
                pass
    return str(value) if value is not None and str(value).strip() else "<none>"


def _runtime_header_yolo_mode(app_runtime: TuiAppRuntime) -> bool:
    sources = (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
    )
    approval_policy = _runtime_first_value(*sources, names=("approval_policy", "ask_for_approval"))
    permission_profile = _runtime_first_value(*sources, names=("permission_profile", "permissions_profile"))
    return has_yolo_permissions(approval_policy, permission_profile)


def _runtime_permissions_label(app_runtime: TuiAppRuntime) -> str:
    sources = (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
    )
    active_profile = _runtime_first_value(*sources, names=("active_permission_profile", "permission_profile_id"))
    permission_profile = _runtime_first_value(*sources, names=("permission_profile", "permissions_profile"))
    approval_policy = _runtime_first_value(*sources, names=("approval_policy", "ask_for_approval")) or "never"
    approvals_reviewer = _runtime_first_value(*sources, names=("approvals_reviewer", "approval_reviewer")) or approval_policy
    workspace_roots = _runtime_workspace_roots(app_runtime)
    if permission_profile is not None:
        # Fixed Rust baseline 1c7832f, codex-tui::status::card:
        # status_permission_summary always derives the displayed sandbox from
        # the current canonical PermissionProfile.  A legacy sandbox_mode may
        # describe startup state and must not override a later /permissions
        # selection.
        sandbox_text = status_permission_summary(
            summarize_permission_profile(permission_profile, app_runtime.cwd, workspace_roots)
        )
    else:
        sandbox_summary = _runtime_first_value(*sources, names=("sandbox_summary", "sandbox", "sandbox_mode"))
        sandbox_text = status_permission_summary(str(sandbox_summary or "read-only"))
    suffix = workspace_root_suffix(workspace_roots, app_runtime.cwd)
    return status_permissions_label(
        active_profile,
        permission_profile,
        approval_policy,
        sandbox_text,
        status_approval_label(approval_policy, approvals_reviewer, approval_policy),
        suffix,
    )


def _runtime_workspace_roots(app_runtime: TuiAppRuntime) -> tuple[Path, ...]:
    raw = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("workspace_roots", "runtime_workspace_roots"),
    )
    if raw is None:
        return (Path(app_runtime.cwd),)
    if isinstance(raw, (str, Path)):
        return (Path(raw),)
    if isinstance(raw, Iterable):
        return tuple(Path(value) for value in raw)
    return (Path(app_runtime.cwd),)


def _runtime_status_token_usage(app_runtime: TuiAppRuntime) -> StatusTokenUsageData:
    token_info = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("token_info", "latest_token_info"),
    )
    usage = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("token_usage", "latest_token_usage", "total_token_usage"),
    )
    if usage is None and token_info is not None:
        usage = getattr(token_info, "total_token_usage", None)
    context_window = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("model_context_window", "context_window"),
    )
    if context_window is None and token_info is not None:
        context_window = getattr(token_info, "model_context_window", None)
    if context_window is None:
        model_info = _runtime_first_value(
            app_runtime.active_thread_runtime,
            getattr(app_runtime.active_thread_runtime, "session_config", None),
            names=("model_info",),
        )
        if model_info is None:
            model_info = getattr(app_runtime.active_thread_runtime, "model_info", None)
        for name in ("model_context_window", "context_window", "max_context_window"):
            context_window = _runtime_value(model_info, name, None)
            if context_window is not None:
                break
        if context_window is None:
            resolved = getattr(model_info, "resolved_context_window", None)
            if callable(resolved):
                try:
                    context_window = resolved()
                except Exception:
                    context_window = None
    total = int(
        _call_numeric(usage, "blended_total")
        or _runtime_value(usage, "total_tokens", 0)
        or _runtime_value(usage, "total", 0)
        or 0
    )
    input_tokens = int(
        _call_numeric(usage, "non_cached_input")
        or _runtime_value(usage, "input_tokens", 0)
        or _runtime_value(usage, "input", 0)
        or 0
    )
    output_tokens = int(_runtime_value(usage, "output_tokens", 0) or _runtime_value(usage, "output", 0) or 0)
    context_data = None
    if context_window:
        window = int(context_window)
        context_usage = getattr(token_info, "last_token_usage", None) if token_info is not None else usage
        tokens_in_context = int(
            _call_numeric(context_usage, "tokens_in_context_window")
            or _runtime_value(context_usage, "total_tokens", 0)
            or _runtime_value(context_usage, "total", 0)
            or total
        )
        percent_remaining = _call_numeric(context_usage, "percent_of_context_window_remaining", window)
        if percent_remaining is None:
            remaining = max(window - tokens_in_context, 0)
            percent_remaining = 100 if window <= 0 else round((remaining / window) * 100)
        context_data = StatusContextWindowData(int(percent_remaining), tokens_in_context, window)
    return StatusTokenUsageData(total, input_tokens, output_tokens, context_data)


def _runtime_status_line_item_ids(app_runtime: TuiAppRuntime) -> tuple[Any, ...]:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("tui_status_line", "status_line_items", "status_line"),
    )
    if value is None:
        return tuple(DEFAULT_STATUS_LINE_ITEMS)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _runtime_status_line_value(app_runtime: TuiAppRuntime, item: StatusLineItem, status: str) -> str | None:
    if item == StatusLineItem.MODEL_NAME:
        return _runtime_display_model(app_runtime)
    if item == StatusLineItem.MODEL_WITH_REASONING:
        return _runtime_model_with_reasoning(app_runtime)
    if item == StatusLineItem.CURRENT_DIR:
        return _display_directory_for_path(app_runtime.cwd)
    if item == StatusLineItem.STATUS:
        return status
    if item == StatusLineItem.CONTEXT_REMAINING:
        return _runtime_context_remaining_text(app_runtime)
    if item == StatusLineItem.CONTEXT_USED:
        usage = _runtime_status_token_usage(app_runtime)
        context = usage.context_window
        percent_used = 0 if context is None else max(0, 100 - int(context.percent_remaining))
        return f"Context {percent_used}% used"
    if item == StatusLineItem.CONTEXT_WINDOW_SIZE:
        context = _runtime_status_token_usage(app_runtime).context_window
        if context is None:
            return None
        return f"{format_tokens_compact(context.window)} window"
    if item == StatusLineItem.USED_TOKENS:
        total = _runtime_status_token_usage(app_runtime).total
        return None if total <= 0 else f"{format_tokens_compact(total)} used"
    if item == StatusLineItem.TOTAL_INPUT_TOKENS:
        return f"{format_tokens_compact(_runtime_status_token_usage(app_runtime).input)} in"
    if item == StatusLineItem.TOTAL_OUTPUT_TOKENS:
        return f"{format_tokens_compact(_runtime_status_token_usage(app_runtime).output)} out"
    if item == StatusLineItem.SESSION_ID:
        thread_id = getattr(app_runtime, "thread_id", None) or getattr(app_runtime.active_thread_runtime, "thread_id", None)
        return None if thread_id is None else str(thread_id)
    if item == StatusLineItem.FAST_MODE:
        text = _runtime_model_with_reasoning(app_runtime)
        return "fast" if " fast" in text else None
    if item == StatusLineItem.RAW_OUTPUT:
        raw = bool(getattr(getattr(app_runtime, "chat_widget", None), "raw_mode", False))
        return "raw" if raw else None
    if item == StatusLineItem.THREAD_TITLE:
        return getattr(app_runtime, "thread_name", None) or getattr(app_runtime, "thread_id", None)
    agent_label = getattr(getattr(app_runtime, "chat_widget", None), "active_agent_label", None)
    if agent_label and item == StatusLineItem.TASK_PROGRESS:
        return str(agent_label)
    return None


def _runtime_context_remaining_text(app_runtime: TuiAppRuntime) -> str | None:
    usage = _runtime_status_token_usage(app_runtime)
    context = usage.context_window
    if context is None:
        return None
    return f"Context {context.percent_remaining}% left"


def _runtime_startup_tooltip(app_runtime: TuiAppRuntime) -> str | None:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("startup_tooltip_override", "startup_tooltip"),
    )
    if value is not None and str(value).strip():
        return str(value)
    show_tooltips = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("show_tooltips",),
    )
    if show_tooltips is False:
        return None
    return APP_TOOLTIP


def _runtime_startup_warnings(app_runtime: TuiAppRuntime) -> tuple[str, ...]:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("startup_warnings", "startupWarnings"),
    )
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _runtime_cwd(app_runtime: TuiAppRuntime) -> Path:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    for candidate in (
        _runtime_value(runtime, "cwd", None),
        _runtime_value(_runtime_value(runtime, "session_config", None), "cwd", None),
        getattr(app_runtime, "cwd", None),
    ):
        if candidate:
            return Path(candidate)
    return Path.cwd()


def _runtime_first_value(*sources: object, names: tuple[str, ...]) -> object | None:
    for source in sources:
        if source is None:
            continue
        for name in names:
            value = _runtime_value(source, name, None)
            if value is not None:
                return value
    return None


def _runtime_value(source: object, name: str, default: object | None = None) -> object | None:
    if isinstance(source, dict):
        return source.get(name, default)
    value = getattr(source, name, default)
    return value() if callable(value) else value


def _call_numeric(source: object, name: str, *args: object) -> int | None:
    if source is None:
        return None
    value = getattr(source, name, None)
    if not callable(value):
        return None
    try:
        result = value(*args)
    except Exception:
        return None
    if isinstance(result, bool) or result is None:
        return None
    try:
        return int(result)
    except (TypeError, ValueError):
        return None


__all__ = [
    "configure_app_runtime_thread_identity",
    "_display_version",
    "_runtime_agents_summary",
    "_runtime_cwd",
    "_runtime_display_model",
    "_runtime_header_reasoning_effort",
    "_runtime_header_yolo_mode",
    "_runtime_model_with_reasoning",
    "_runtime_permissions_label",
    "_runtime_show_fast_status",
    "_runtime_startup_tooltip",
    "_runtime_startup_warnings",
    "_runtime_status_line_item_ids",
    "_runtime_status_line_value",
]
