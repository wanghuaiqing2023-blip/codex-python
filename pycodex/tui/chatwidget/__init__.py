"""Semantic root facade for Rust ``codex-tui::chatwidget``.

Rust source: ``codex/codex-rs/tui/src/chatwidget.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import re

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget", source="codex/codex-rs/tui/src/chatwidget.rs", status="complete")

DEFAULT_MODEL_DISPLAY_NAME = "loading"
MULTI_AGENT_ENABLE_TITLE = "Enable subagents?"
MULTI_AGENT_ENABLE_YES = "Yes, enable"
MULTI_AGENT_ENABLE_NO = "Not now"
MULTI_AGENT_ENABLE_NOTICE = "Subagents will be enabled in the next session."
TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING = (
    "Your conversations have multiple flags for possible cybersecurity risk. Responses may take longer "
    "because extra safety checks are on. To get authorized for security work, join the Trusted Access "
    "for Cyber program: https://chatgpt.com/cyber"
)
MEMORIES_DOC_URL = "https://developers.openai.com/codex/memories"
MEMORIES_ENABLE_TITLE = "Enable memories?"
MEMORIES_ENABLE_YES = "Yes, enable"
MEMORIES_ENABLE_NO = "Not now"
MEMORIES_ENABLE_NOTICE = "Memories will be enabled in the next session."
PLAN_MODE_REASONING_SCOPE_TITLE = "Apply reasoning change"
PLAN_MODE_REASONING_SCOPE_PLAN_ONLY = "Apply to Plan mode override"
PLAN_MODE_REASONING_SCOPE_ALL_MODES = "Apply to global default and Plan mode override"
CONNECTORS_SELECTION_VIEW_ID = "connectors-selection"
PET_SELECTION_LOADING_VIEW_ID = "pet-selection-loading"
AMBIENT_PET_WRAP_GAP_COLUMNS = 2
TUI_STUB_MESSAGE = "Not available in TUI yet."
USER_SHELL_COMMAND_HELP_TITLE = "Run a shell command"
USER_SHELL_COMMAND_HELP_HINT = "Type a shell command to run in the workspace."
AUTO_REVIEW_DESCRIPTION = "Review changes automatically."
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_STATUS_LINE_ITEMS = ("model", "approval", "sandbox")
MAX_AGENT_COPY_HISTORY = 20
PLACEHOLDERS = ("Thinking", "Working", "Reading")
SIDE_PLACEHOLDERS = ("Side conversation",)


class ExternalEditorState(Enum):
    Closed = "closed"
    Opening = "opening"
    Open = "open"


class CodexOpTarget(Enum):
    Active = "active"
    New = "new"


class InterruptedTurnNoticeMode(Enum):
    Hidden = "hidden"
    Inline = "inline"


class ReplayKind(Enum):
    Full = "full"
    Compact = "compact"


class SessionConfiguredDisplay(Enum):
    None_ = "none"
    Active = "active"


class PlanModeNudgeScope(Enum):
    PlanOnly = "plan_only"
    AllModes = "all_modes"


class TurnAbortReason(Enum):
    Interrupted = "interrupted"
    Error = "error"


class ThreadItemRenderSource(Enum):
    Live = "live"
    Replay = "replay"


@dataclass(frozen=True)
class ChatWidgetInit:
    config: Any = None
    thread_id: str | None = None
    thread_name: str | None = None
    rollout_path: str | None = None


@dataclass(frozen=True)
class ActiveCellTranscriptKey:
    kind: str
    revision: int = 0


@dataclass
class ChatWidget:
    init: ChatWidgetInit | None = None
    history: list[Any] = field(default_factory=list)
    info_messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    composer_text: str = ""
    remote_urls: list[str] = field(default_factory=list)
    pending_approvals_value: list[Any] = field(default_factory=list)
    token_info: Any = None
    pre_review_token_info: Any = None
    raw_mode: bool = False
    active_cell: Any = None
    active_cell_revision: int = 0
    task_running: bool = False
    redraw_requests: int = 0
    thread_rename_block_message: str | None = None
    collab_metadata: Any = None
    memory_settings: Any = None

    def set_collab_agent_metadata(self, metadata: Any) -> None:
        self.collab_metadata = metadata

    def collab_agent_metadata(self) -> Any:
        return self.collab_metadata

    def realtime_conversation_enabled(self) -> bool:
        return bool(_get(self.init, "realtime_conversation", False))

    def realtime_audio_device_selection_enabled(self) -> bool:
        return bool(_get(self.init, "realtime_audio_device_selection", False))

    def restore_retry_status_header_if_present(self) -> bool:
        return False

    def record_agent_markdown(self, markdown: str) -> None:
        self.history.append({"role": "assistant", "markdown": markdown})

    def record_visible_user_turn_for_copy(self, text: str) -> None:
        self.history.append({"role": "user", "text": text})

    def open_feedback_note(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"view": "feedback_note", "args": args, "kwargs": kwargs}

    def show_feedback_note(self, note: str = "") -> None:
        self.info_messages.append(note)

    def open_app_link_view(self, params: Any = None) -> dict[str, Any]:
        return {"view": "app_link", "params": params}

    def dismiss_app_server_request(self, request: Any) -> bool:
        self.history.append({"dismissed_request": request})
        return True

    def open_feedback_consent(self) -> dict[str, str]:
        return {"view": "feedback_consent"}

    def open_multi_agent_enable_prompt(self) -> dict[str, str]:
        return {"title": MULTI_AGENT_ENABLE_TITLE, "yes": MULTI_AGENT_ENABLE_YES, "no": MULTI_AGENT_ENABLE_NO}

    def open_memories_popup(self) -> dict[str, str]:
        return {"view": "memories", "url": MEMORIES_DOC_URL}

    def open_memories_enable_prompt(self) -> dict[str, str]:
        return {"title": MEMORIES_ENABLE_TITLE, "yes": MEMORIES_ENABLE_YES, "no": MEMORIES_ENABLE_NO}

    def set_memory_settings(self, settings: Any) -> None:
        self.memory_settings = settings

    def set_token_info(self, info: Any) -> None:
        self.token_info = info

    def apply_token_info(self, info: Any) -> None:
        self.set_token_info(info)

    def context_remaining_percent(self) -> int | None:
        remaining = _get(self.token_info, "context_remaining_percent", None)
        return None if remaining is None else int(remaining)

    def context_used_tokens(self) -> int | None:
        used = _get(self.token_info, "context_used_tokens", _get(self.token_info, "used_tokens", None))
        return None if used is None else int(used)

    def restore_pre_review_token_info(self) -> None:
        self.token_info = self.pre_review_token_info

    def handle_history_entry_response(self, response: Any) -> None:
        self.history.append(response)

    def pre_draw_tick(self) -> bool:
        return self.task_running

    def flush_active_cell(self) -> Any:
        cell = self.active_cell
        if cell is not None:
            self.history.append(cell)
            self.active_cell = None
        return cell

    def add_to_history(self, cell: Any) -> None:
        self.history.append(cell)

    def add_boxed_history(self, cell: Any) -> None:
        self.add_to_history({"boxed": cell})

    def enter_review_mode_with_hint(self, hint: str = "") -> None:
        self.info_messages.append(hint or "Review mode")

    def exit_review_mode_after_item(self) -> None:
        self.info_messages.append("Exited review mode")

    def on_committed_user_message(self, text: str) -> None:
        self.record_visible_user_turn_for_copy(text)

    def on_user_message_display(self, text: str) -> None:
        self.history.append({"display_user": text})

    def request_immediate_exit(self) -> dict[str, str]:
        return {"exit": "immediate"}

    def request_quit_without_confirmation(self) -> dict[str, str]:
        return {"exit": "quit"}

    def show_shutdown_in_progress(self) -> None:
        self.info_messages.append("Shutdown in progress")

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def bump_active_cell_revision(self) -> int:
        self.active_cell_revision += 1
        return self.active_cell_revision

    def finalize_active_cell_as_failed(self, message: str = "failed") -> None:
        if self.active_cell is not None:
            self.history.append({"failed": self.active_cell, "message": message})
            self.active_cell = None

    def set_pending_thread_approvals(self, approvals: list[Any]) -> None:
        self.pending_approvals_value = list(approvals)

    def clear_thread_rename_block(self) -> None:
        self.thread_rename_block_message = None

    def set_thread_rename_block_message(self, message: str) -> None:
        self.thread_rename_block_message = message

    def set_interrupted_turn_notice_mode(self, mode: InterruptedTurnNoticeMode) -> None:
        self.info_messages.append(mode.value)

    def add_diff_in_progress(self, diff: Any = None) -> None:
        self.active_cell = {"diff_in_progress": diff}

    def on_diff_complete(self, diff: Any = None) -> None:
        self.history.append({"diff_complete": diff})
        self.active_cell = None

    def add_debug_config_output(self, text: str) -> None:
        self.add_info_message(text)

    def add_ps_output(self, text: str) -> None:
        self.add_plain_history_lines([text])

    def clean_background_terminals(self) -> int:
        return 0

    def plugins_for_mentions(self) -> list[Any]:
        return list(_get(self.init, "plugins", []))

    def placeholder_session_header_cell(self) -> dict[str, str]:
        return {"session_header": DEFAULT_MODEL_DISPLAY_NAME}

    def apply_session_info_cell(self, info: Any) -> None:
        self.history.append({"session_info": info})

    def add_info_message(self, message: str) -> None:
        self.info_messages.append(str(message))

    def add_memories_enable_notice(self) -> None:
        self.add_info_message(MEMORIES_ENABLE_NOTICE)

    def add_plain_history_lines(self, lines: list[str]) -> None:
        self.history.extend(lines)

    def add_warning_message(self, message: str) -> None:
        self.warnings.append(str(message))

    def add_error_message(self, message: str) -> None:
        self.errors.append(str(message))

    def add_app_server_stub_message(self) -> None:
        self.add_info_message(TUI_STUB_MESSAGE)

    def rename_confirmation_cell(self, name: str) -> dict[str, str]:
        return {"rename": name}

    def add_mcp_output(self, output: Any) -> None:
        self.history.append({"mcp": output})

    def clear_mcp_inventory_loading(self) -> None:
        pass

    def apply_file_search_result(self, result: Any) -> None:
        self.history.append({"file_search": result})

    def current_stream_width(self) -> int:
        return int(_get(self.init, "stream_width", 80))

    def raw_output_mode(self) -> bool:
        return self.raw_mode

    def history_render_mode(self) -> str:
        return "raw" if self.raw_mode else "markdown"

    def set_raw_output_mode(self, enabled: bool) -> None:
        self.raw_mode = bool(enabled)

    def raw_output_mode_notice(self) -> str:
        return "Raw output mode enabled" if self.raw_mode else "Raw output mode disabled"

    def set_raw_output_mode_and_notify(self, enabled: bool) -> str:
        self.set_raw_output_mode(enabled)
        notice = self.raw_output_mode_notice()
        self.add_info_message(notice)
        return notice

    def toggle_raw_output_mode_and_notify(self) -> str:
        return self.set_raw_output_mode_and_notify(not self.raw_mode)

    def on_terminal_resize(self, width: int) -> None:
        if self.init is not None:
            object.__setattr__(self.init, "stream_width", width)

    def has_active_agent_stream(self) -> bool:
        return bool(_get(self.active_cell, "agent_stream", False))

    def has_active_plan_stream(self) -> bool:
        return bool(_get(self.active_cell, "plan_stream", False))

    def is_plan_streaming_in_tui(self) -> bool:
        return self.has_active_plan_stream()

    def composer_is_empty(self) -> bool:
        return self.composer_text == ""

    def is_task_running_for_test(self) -> bool:
        return self.task_running

    def toggle_vim_mode_and_notify(self) -> str:
        state = not bool(_get(self, "vim_enabled", False))
        setattr(self, "vim_enabled", state)
        notice = "Vim mode enabled" if state else "Vim mode disabled"
        self.add_info_message(notice)
        return notice

    def is_normal_backtrack_mode(self) -> bool:
        return False

    def should_handle_vim_insert_escape(self, event: Any) -> bool:
        return bool(_get(self, "vim_enabled", False)) and str(event).lower() == "esc"

    def insert_str(self, text: str) -> None:
        self.composer_text += str(text)

    def set_composer_text(self, text: str) -> None:
        self.composer_text = str(text)

    def set_remote_image_urls(self, urls: list[str]) -> None:
        self.remote_urls = list(urls)

    def take_remote_image_urls(self) -> list[str]:
        urls = list(self.remote_urls)
        self.remote_urls.clear()
        return urls

    def remote_image_urls(self) -> list[str]:
        return list(self.remote_urls)

    def pending_thread_approvals(self) -> list[Any]:
        return list(self.pending_approvals_value)

    def has_active_view(self) -> bool:
        return self.active_cell is not None

    def show_esc_backtrack_hint(self) -> None:
        self.add_info_message("Esc again to backtrack")

    def clear_esc_backtrack_hint(self) -> None:
        self.info_messages = [m for m in self.info_messages if "backtrack" not in m.lower()]

    def refresh_skills_for_current_cwd(self) -> dict[str, str]:
        return {"refresh": "skills"}

    def submit_op(self, op: Any) -> None:
        self.history.append({"op": op})

    def append_message_history_entry(self, entry: Any) -> None:
        self.history.append(entry)

    def prepare_local_op_submission(self, op: Any) -> dict[str, Any]:
        return {"op": op, "composer_text": self.composer_text}

    def on_list_skills(self, response: Any) -> None:
        self.history.append({"skills": response})

    def refresh_plugin_mentions(self) -> dict[str, str]:
        return {"refresh": "plugin_mentions"}

    def on_plugin_mentions_loaded(self, mentions: Any) -> None:
        self.history.append({"plugin_mentions": mentions})

    def sync_plugin_mentions_config(self) -> dict[str, str]:
        return {"sync": "plugin_mentions"}

    def token_usage(self) -> Any:
        return self.token_info

    def thread_id(self) -> str | None:
        return _get(self.init, "thread_id", None)

    def thread_name(self) -> str | None:
        return _get(self.init, "thread_name", None)

    def rollout_path(self) -> str | None:
        return _get(self.init, "rollout_path", None)

    def active_cell_transcript_key(self) -> ActiveCellTranscriptKey | None:
        if self.active_cell is None:
            return None
        return ActiveCellTranscriptKey(type(self.active_cell).__name__, self.active_cell_revision)

    def active_cell_transcript_hyperlink_lines(self) -> list[Any]:
        return self.active_cell_transcript_lines()

    def active_cell_transcript_lines(self) -> list[Any]:
        if self.active_cell is None:
            return []
        if isinstance(self.active_cell, list):
            return self.active_cell
        return [self.active_cell]

    def config_ref(self) -> Any:
        return _get(self.init, "config", None)

    def status_line_text(self) -> str:
        return " ".join(str(item) for item in DEFAULT_STATUS_LINE_ITEMS)

    def clear_token_usage(self) -> None:
        self.token_info = None

    def update_recording_meter_in_place(self, value: Any) -> None:
        self.active_cell = {"recording_meter": value}

    def remove_recording_meter_placeholder(self) -> None:
        if _get(self.active_cell, "recording_meter", None) is not None:
            self.active_cell = None


def queued_message_edit_binding_for_terminal(terminal: Any = None) -> str:
    name = str(_get(terminal, "name", terminal) or "").lower()
    multiplexer = str(_get(terminal, "multiplexer", "") or "").lower()
    if any(part in name for part in ("apple", "warp", "vscode")) or multiplexer == "tmux":
        return "shift-left"
    return "alt-up"


def queued_message_edit_hint_binding(terminal: Any = None) -> str:
    return queued_message_edit_binding_for_terminal(terminal).replace("-", "+")


def contains_plan_keyword(text: str) -> bool:
    return bool(re.search(r"\b(plan|规划|计划)\b", str(text), re.IGNORECASE))


def exec_approval_request_from_params(params: Any) -> dict[str, Any]:
    return {"kind": "exec", "command": _get(params, "command", None), "params": params}


def patch_approval_request_from_params(params: Any) -> dict[str, Any]:
    return {"kind": "patch", "changes": _get(params, "changes", None), "params": params}


def request_permissions_from_params(params: Any) -> dict[str, Any]:
    return {"kind": "permissions", "permissions": _get(params, "permissions", []), "params": params}


def token_usage_info_from_app_server(value: Any) -> dict[str, int | None]:
    return {
        "input_tokens": _maybe_int(_get(value, "input_tokens", None)),
        "output_tokens": _maybe_int(_get(value, "output_tokens", None)),
        "total_tokens": _maybe_int(_get(value, "total_tokens", None)),
    }


def has_websocket_timing_metrics(value: Any) -> bool:
    metrics = _get(value, "websocket_timing_metrics", _get(value, "timing_metrics", None))
    return bool(metrics)


def drop(widget: ChatWidget | None = None) -> None:
    if widget is not None:
        widget.flush_active_cell()


def extract_first_bold(markdown: str) -> str | None:
    match = re.search(r"\*\*([^*]+)\*\*", str(markdown))
    return None if match is None else match.group(1)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _maybe_int(value: Any) -> int | None:
    return None if value is None else int(value)


__all__ = [
    "AMBIENT_PET_WRAP_GAP_COLUMNS",
    "AUTO_REVIEW_DESCRIPTION",
    "ActiveCellTranscriptKey",
    "CONNECTORS_SELECTION_VIEW_ID",
    "ChatWidget",
    "ChatWidgetInit",
    "CodexOpTarget",
    "DEFAULT_MODEL_DISPLAY_NAME",
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_STATUS_LINE_ITEMS",
    "ExternalEditorState",
    "InterruptedTurnNoticeMode",
    "MAX_AGENT_COPY_HISTORY",
    "MEMORIES_DOC_URL",
    "MEMORIES_ENABLE_NO",
    "MEMORIES_ENABLE_NOTICE",
    "MEMORIES_ENABLE_TITLE",
    "MEMORIES_ENABLE_YES",
    "MULTI_AGENT_ENABLE_NO",
    "MULTI_AGENT_ENABLE_NOTICE",
    "MULTI_AGENT_ENABLE_TITLE",
    "MULTI_AGENT_ENABLE_YES",
    "PET_SELECTION_LOADING_VIEW_ID",
    "PLACEHOLDERS",
    "PLAN_MODE_REASONING_SCOPE_ALL_MODES",
    "PLAN_MODE_REASONING_SCOPE_PLAN_ONLY",
    "PLAN_MODE_REASONING_SCOPE_TITLE",
    "PlanModeNudgeScope",
    "RUST_MODULE",
    "ReplayKind",
    "SIDE_PLACEHOLDERS",
    "SessionConfiguredDisplay",
    "TRUSTED_ACCESS_FOR_CYBER_VERIFICATION_WARNING",
    "TUI_STUB_MESSAGE",
    "ThreadItemRenderSource",
    "TurnAbortReason",
    "USER_SHELL_COMMAND_HELP_HINT",
    "USER_SHELL_COMMAND_HELP_TITLE",
    "contains_plan_keyword",
    "drop",
    "exec_approval_request_from_params",
    "extract_first_bold",
    "has_websocket_timing_metrics",
    "patch_approval_request_from_params",
    "queued_message_edit_binding_for_terminal",
    "queued_message_edit_hint_binding",
    "request_permissions_from_params",
    "token_usage_info_from_app_server",
]
