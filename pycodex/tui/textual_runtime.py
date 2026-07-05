"""Textual product runtime for Rust ``codex-tui`` composition.

Rust ownership:
- ``codex-tui::tui`` owns terminal event-loop integration.
- ``codex-tui::app`` owns user-turn routing into the active thread.
- ``codex-tui::chatwidget::protocol`` owns server-notification dispatch.
- ``codex-tui::bottom_pane::chat_composer`` owns submitted prompt input.

This module is the Python product-shell equivalent for that composition.  It
keeps model/session events on the existing ``TuiAppRuntime`` path and lets
vendored Textual own focus, input, redraw, scroll, and mouse-ready UI concerns.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pycodex.core.config.edit import (
    ConfigEditsBuilder,
    keymap_binding_clear_edit,
    keymap_bindings_edit,
)
from pycodex.features import Feature as CodexFeature
from pycodex.features import feature_for_key as codex_feature_for_key
from pycodex.core.agents_md import DEFAULT_AGENTS_MD_FILENAME
from pycodex.core.util import normalize_thread_name
from pycodex.git_utils import current_branch_name, local_git_branches, recent_commits
from pycodex.login.token_data import IdTokenInfoError, TokenData, parse_chatgpt_jwt_claims
from pycodex.protocol import (
    AltScreenMode,
    BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
    BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
    ActivePermissionProfile as ProtocolActivePermissionProfile,
    ApprovalsReviewer as ProtocolApprovalsReviewer,
    AskForApproval as ProtocolAskForApproval,
    CollaborationMode,
    PermissionProfile as ProtocolPermissionProfile,
    ReviewDecision,
    ReviewTarget,
    Settings,
)

from .app.event_dispatch import SHUTDOWN_FIRST_EXIT_TIMEOUT
from .app_event import AppEvent, KeymapEditIntent, RateLimitRefreshOrigin
from .app.resize_reflow import (
    HistoryCell as ResizeReflowHistoryCell,
    HistoryLineWrapPolicy as ResizeReflowHistoryLineWrapPolicy,
    ResizeReflowState,
    insert_history_cell_lines_plan,
)
from .app.agent_navigation import AgentNavigationDirection, format_agent_picker_item_name
from .app.runtime import ActiveThreadRuntime, TuiAppRuntime
from .app.runtime import _run_coro_blocking as _runtime_run_coro_blocking
from .app_server_session import app_server_rate_limit_snapshots
from .app.session_lifecycle import open_agent_picker_plan
from .app.thread_goal_actions import (
    ThreadGoal,
    ThreadGoalActionPlan,
    ThreadGoalSetMode,
    ThreadGoalStatus,
    UpdateExistingMode,
    clear_thread_goal_plan,
    open_thread_goal_editor_plan,
    open_thread_goal_menu_plan,
    set_thread_goal_objective_plan,
    set_thread_goal_status_plan,
)
from .app.input import EXTERNAL_EDITOR_HINT, MISSING_EDITOR_MESSAGE
from .app_command import AppCommand
from .app_backtrack import (
    BacktrackState,
    NO_PREVIOUS_MESSAGE_TO_EDIT,
    agent_cell as backtrack_agent_cell,
    apply_backtrack_rollback_state,
    apply_backtrack_selection_index,
    backtrack_selection,
    begin_overlay_backtrack_preview_state,
    close_transcript_overlay_state,
    handle_backtrack_overlay_event_state,
    info_cell as backtrack_info_cell,
    next_backtrack_selection_index,
    next_forward_backtrack_selection_index,
    user_cell as backtrack_user_cell,
    user_count as backtrack_user_count,
)
from .bottom_pane.command_popup import CommandPopup, CommandPopupFlags
from .bottom_pane.slash_commands import ServiceTierCommand
from .bottom_pane.chat_composer import ChatComposer
from .bottom_pane.chat_composer.slash_input import selected_command_completion
from .bottom_pane.chat_composer.history_search import (
    HistorySearchSession,
    HistorySearchStatus,
    history_search_footer_line,
)
from .bottom_pane.footer import (
    FooterKeyHints,
    FooterMode,
    KeyBinding as FooterKeyBinding,
    ShortcutsState,
    shortcut_overlay_lines,
    status_line_right_indicator_line,
    toggle_shortcut_mode,
)
from .bottom_pane.chat_composer_history import (
    ChatComposerHistory,
    HistoryEntry,
    HistoryEntryResponse,
    HistorySearchDirection,
    HistorySearchResult,
)
from .bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from .bottom_pane.title_setup import TerminalTitleItem
from .chatwidget import (
    MULTI_AGENT_ENABLE_NO,
    MULTI_AGENT_ENABLE_NOTICE,
    MULTI_AGENT_ENABLE_TITLE,
    MULTI_AGENT_ENABLE_YES,
    extract_first_bold,
)
from .chatwidget.input_submission import UserInput as SubmissionUserInput
from .collaboration_modes import plan_mask
from .bottom_pane.status_line_setup import StatusLineItem
from . import external_editor
from .chatwidget.model_popups import (
    ModelPopupContext,
    ModelPopupEvent,
    ModelPreset,
    ReasoningEffortConfig,
    ReasoningEffortPreset,
    open_all_models_popup,
    open_model_popup,
    open_plan_reasoning_scope_prompt,
    open_reasoning_popup,
)
from .chatwidget.permission_popups import (
    ApprovalsReviewer,
    AskForApproval,
    PermissionProfile,
    builtin_approval_presets as popup_builtin_approval_presets,
    open_full_access_confirmation,
    open_permissions_popup,
)
from .chatwidget.permissions_menu import (
    CustomPermissionProfileSummary,
    PermissionMenuConfig,
    open_permission_profiles_popup as open_permission_profiles_menu,
)
from .chatwidget.review_popups import (
    ReviewPopupAction,
    custom_review_prompt_action,
    open_review_popup,
    show_review_branch_picker,
    show_review_commit_picker,
)
from .chatwidget.settings_popups import (
    open_realtime_audio_device_selection,
    open_realtime_audio_popup,
    open_realtime_audio_restart_prompt,
)
from .chatwidget.protocol import ServerNotification, token_usage_info_from_app_server
from .chatwidget.interaction import copy_last_agent_markdown_with
from .chatwidget.keymap_picker import KeymapPickerWidgetState, KeymapView
from .chatwidget.slash_dispatch import GOAL_USAGE, GOAL_USAGE_HINT, RAW_USAGE
from .chatwidget.status_surfaces import (
    DEFAULT_STATUS_LINE_ITEMS,
    DEFAULT_TERMINAL_TITLE_ITEMS,
    parse_status_line_items_with_invalids,
    parse_terminal_title_items_with_invalids,
    terminal_title_spinner_frame_at,
    truncate_terminal_title_part,
)
from .bottom_pane.popup_consts import standard_popup_hint_line
from .resume_picker import (
    BackgroundEvent,
    PickerPage,
    PickerState,
    Row as ResumePickerRow,
    SessionPickerAction,
    SessionSelection,
    picker_footer_progress_label,
    row_from_app_server_thread,
    sort_key_label,
)
from .resume_picker.transcript import RawReasoningVisibility, TranscriptCell, thread_to_transcript_cells
from .get_git_diff import get_git_diff
from .history_cell.exec import UnifiedExecProcessDetails, new_unified_exec_processes_output
from .history_cell.messages import new_reasoning_summary_block
from .history_cell.session import SessionHeaderHistoryCell, has_yolo_permissions
from .insert_history import (
    HistoryLineWrapPolicy as InsertHistoryLineWrapPolicy,
    TerminalModel as InsertHistoryTerminalModel,
    insert_history_lines,
    insert_history_lines_with_wrap_policy,
)
from .exec_cell.model import CommandOutput as ExecCellCommandOutput
from .exec_cell.model import ExecCall as ExecCellCall
from .exec_cell.model import ExecCell
from .exec_cell.model import UNIFIED_EXEC_INTERACTION as EXEC_CELL_UNIFIED_EXEC_INTERACTION
from .exec_cell.model import USER_SHELL as EXEC_CELL_USER_SHELL
from .exec_cell.render import command_display_lines as exec_cell_command_display_lines
from .exec_cell.render import render_line_text as render_exec_cell_line_text
from .keymap import KeyBinding, RuntimeKeymap, primary_binding
from . import keymap_setup
from .keymap_setup.picker import (
    KeymapActionFilter as KeymapSetupActionFilter,
    build_keymap_picker_params_for_selected_action_with_filter as build_keymap_picker_selection_for_action,
    build_keymap_picker_params_with_filter as build_keymap_picker_selection,
)
from .slash_command import SlashCommand, built_in_slash_commands
from .status.card import (
    StatusAccountDisplay,
    StatusContextWindowData,
    StatusTokenUsageData,
    new_status_output_with_rate_limits_handle,
    status_approval_label,
    status_permissions_label,
    workspace_root_suffix,
)
from .status.helpers import compose_agents_summary, compose_model_display, plan_type_display_name
from .status.rate_limits import (
    RateLimitSnapshotDisplay,
    RateLimitWindowDisplay,
    rate_limit_snapshot_display_for_limit,
)
from .status_indicator_widget import (
    KeyBinding as StatusKeyBinding,
    StatusDetailsCapitalization,
    StatusIndicatorWidget,
)
from .text_formatting import proper_join
from .textual_compat import (
    App,
    ComposeResult,
    NoMatches,
    RichLog,
    Static,
    Text,
    TextArea,
    Vertical,
    verify_textual_runtime,
)
from .tooltips import APP_TOOLTIP
from .workspace_command import AppServerWorkspaceCommandRunner

RUST_MODULE_CRATE = "codex-tui"
RUST_MODULE = "tui::textual_runtime"
RUST_SOURCE = "codex/codex-rs/tui/src/tui.rs"
_TEXTUAL_DEFAULT_STATUS_LINE_ITEMS = tuple(DEFAULT_STATUS_LINE_ITEMS)

_INIT_PROMPT = """Generate a file named AGENTS.md that serves as a contributor guide for this repository.
Your goal is to produce a clear, concise, and well-structured document with descriptive headings and actionable explanations for each section.
Follow the outline below, but adapt as needed - add sections if relevant, and omit those that do not apply to this project.

Document Requirements

- Title the document "Repository Guidelines".
- Use Markdown headings (#, ##, etc.) for structure.
- Keep the document concise. 200-400 words is optimal.
- Keep explanations short, direct, and specific to this repository.
- Provide examples where helpful (commands, directory paths, naming patterns).
- Maintain a professional, instructional tone.

Recommended Sections

Project Structure & Module Organization

- Outline the project structure, including where the source code, tests, and assets are located.

Build, Test, and Development Commands

- List key commands for building, testing, and running locally (e.g., npm test, make build).
- Briefly explain what each command does.

Coding Style & Naming Conventions

- Specify indentation rules, language-specific style preferences, and naming patterns.
- Include any formatting or linting tools used.

Testing Guidelines

- Identify testing frameworks and coverage requirements.
- State test naming conventions and how to run tests.

Commit & Pull Request Guidelines

- Summarize commit message conventions found in the project's Git history.
- Outline pull request requirements (descriptions, linked issues, screenshots, etc.).

(Optional) Add other sections if relevant, such as Security & Configuration Tips, Architecture Overview, or Agent-Specific Instructions.
"""


def _textual_timing_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


def _plain_status_text(value: object) -> Text:
    """Render status/footer strings as literal text, not Rich markup."""

    return Text(str(value))


def should_use_textual_tui(
    *,
    stdout: Any,
    stdin: Any,
    active_thread_runtime: ActiveThreadRuntime | None,
    use_alt_screen: bool,
) -> bool:
    """Return whether the product path should enter the Textual runtime.

    Tests and non-interactive pipes temporarily keep using the old projection
    loop while their harnesses are migrated.  The product TTY path is Textual
    only so we do not keep extending two visual runtimes in parallel.
    """

    if active_thread_runtime is None:
        return False
    return _is_tty(stdout) and _is_tty(stdin)


def run_textual_tui(
    *,
    active_thread_runtime: ActiveThreadRuntime | TuiAppRuntime,
    stdout: Any | None = None,
    stdin: Any | None = None,
    use_alt_screen: bool = True,
) -> int:
    """Run the Textual-backed interactive TUI product shell."""

    if _should_use_scrollback_product_path(stdout):
        from .tui import run_terminal_tui

        return run_terminal_tui(active_thread_runtime=active_thread_runtime, stdout=stdout, stdin=stdin)

    verify_textual_runtime()
    if isinstance(active_thread_runtime, TuiAppRuntime):
        app_runtime = active_thread_runtime
        configure_app_runtime_thread_identity(app_runtime, app_runtime.active_thread_runtime)
    else:
        app_runtime = TuiAppRuntime(active_thread_runtime=active_thread_runtime)
        configure_app_runtime_thread_identity(app_runtime, active_thread_runtime)
    app = PyCodexTextualApp(app_runtime, use_alt_screen=use_alt_screen)
    result = app.run()
    code = int(result or app.exit_code)

    _write_exit_summary(sys.stdout if stdout is None else stdout, app_runtime)
    return code


def _should_use_scrollback_product_path(stdout: Any | None) -> bool:
    """Return whether real terminal sessions should use native scrollback history.

    Rust ``codex-tui`` writes finalized history into terminal scrollback and
    keeps only the bottom pane live.  Python's retained Textual transcript is
    still valuable for component tests and overlay migration, but a real TTY
    product session must not put transcript history behind a Textual widget
    because that prevents native terminal scroll/copy parity.
    """

    flag = os.environ.get("PYCODEX_TUI_FORCE_TEXTUAL", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return False
    if stdout is None:
        return True
    isatty = getattr(stdout, "isatty", None)
    if callable(isatty):
        try:
            return bool(isatty())
        except Exception:
            return False
    return False


def determine_alt_screen_mode(no_alt_screen: bool, tui_alternate_screen: Any) -> bool:
    """Mirror Rust ``codex-tui::determine_alt_screen_mode``."""

    if no_alt_screen:
        return False
    mode = tui_alternate_screen
    if not isinstance(mode, AltScreenMode):
        mode = AltScreenMode.parse(str(mode))
    return mode is not AltScreenMode.NEVER


def _write_exit_summary(writer: Any, app_runtime: TuiAppRuntime) -> None:
    """Print Rust ``codex-cli::format_exit_messages`` style exit lines."""

    _sync_exit_summary_runtime_state(app_runtime)
    lines = _exit_summary_lines(app_runtime)
    if not lines:
        return
    for line in lines:
        writer.write(f"{line}\n")
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def _exit_summary_lines(app_runtime: TuiAppRuntime) -> list[str]:
    from . import AppExitInfo
    from .main import format_exit_messages

    return format_exit_messages(
        AppExitInfo(
            token_usage=_exit_summary_token_usage(app_runtime),
            thread_id=_resumable_thread_id(app_runtime),
            thread_name=_runtime_thread_name(app_runtime),
        )
    )


def _exit_summary_token_usage(app_runtime: TuiAppRuntime) -> object:
    token_info = getattr(getattr(app_runtime, "chat_widget", None), "token_info", None)
    token_usage = getattr(token_info, "total_token_usage", None)
    if token_usage is not None:
        return token_usage
    return getattr(getattr(app_runtime, "chat_widget", None), "token_usage", None)


def _sync_exit_summary_runtime_state(app_runtime: TuiAppRuntime) -> None:
    """Refresh Rust ``AppExitInfo`` fields before printing exit messages."""

    active_thread_runtime = getattr(app_runtime, "active_thread_runtime", None)
    if active_thread_runtime is None:
        return
    configure_app_runtime_thread_identity(app_runtime, active_thread_runtime)
    waiter = getattr(active_thread_runtime, "wait_for_rollout_path", None)
    if callable(waiter) and not _rollout_path_is_resumable(getattr(app_runtime, "rollout_path", None)):
        try:
            rollout_path = waiter(_exit_summary_rollout_wait_seconds())
        except Exception:
            rollout_path = None
        if rollout_path is not None:
            app_runtime.rollout_path = Path(str(rollout_path))
    configure_app_runtime_thread_identity(app_runtime, active_thread_runtime)


def _exit_summary_rollout_wait_seconds() -> float:
    raw = os.environ.get("PYCODEX_TUI_EXIT_SUMMARY_ROLLOUT_WAIT_SECONDS")
    if raw is None:
        return 1.0
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 1.0


def _resumable_thread_id(app_runtime: TuiAppRuntime) -> str | None:
    thread_id = str(getattr(app_runtime, "thread_id", "") or "").strip()
    if not thread_id or thread_id == "primary":
        return None
    if not _rollout_path_is_resumable(getattr(app_runtime, "rollout_path", None)):
        return None
    return thread_id


def _rollout_path_is_resumable(path: object) -> bool:
    if path is None:
        return False
    try:
        rollout_path = Path(str(path))
        stat = rollout_path.stat()
    except (OSError, ValueError):
        return False
    return rollout_path.is_file() and stat.st_size > 0


def _copy_to_system_clipboard(text: str) -> Any:
    if sys.platform == "win32":
        clip = shutil.which("clip")
        if clip is None:
            raise RuntimeError("clip.exe not found")
        subprocess.run([clip], input=str(text), text=True, check=True)
        return "clip.exe"
    if sys.platform == "darwin":
        pbcopy = shutil.which("pbcopy")
        if pbcopy is None:
            raise RuntimeError("pbcopy not found")
        subprocess.run([pbcopy], input=str(text), text=True, check=True)
        return "pbcopy"
    for command in (("wl-copy",), ("xclip", "-selection", "clipboard"), ("xsel", "--clipboard", "--input")):
        executable = shutil.which(command[0])
        if executable is None:
            continue
        subprocess.run([executable, *command[1:]], input=str(text), text=True, check=True)
        return command[0]
    raise RuntimeError("clipboard command not found")


def _read_system_clipboard_text() -> str | None:
    if sys.platform == "win32":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            return None
        try:
            result = subprocess.run(
                [powershell, "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                text=True,
                capture_output=True,
                timeout=1.5,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout or None
    if sys.platform == "darwin":
        pbpaste = shutil.which("pbpaste")
        if pbpaste is None:
            return None
        try:
            result = subprocess.run([pbpaste], text=True, capture_output=True, timeout=1.5, check=False)
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout or None
    for command in (("wl-paste", "-n"), ("xclip", "-selection", "clipboard", "-out"), ("xsel", "--clipboard", "--output")):
        executable = shutil.which(command[0])
        if executable is None:
            continue
        try:
            result = subprocess.run(
                [executable, *command[1:]],
                text=True,
                capture_output=True,
                timeout=1.5,
                check=False,
            )
        except Exception:
            continue
        if result.returncode == 0:
            return result.stdout or None
    return None


class CodexTranscriptLog(RichLog):
    """Scrollable transcript pane that mirrors Rust pager offset redraws."""

    def watch_scroll_y(self, old: float, new: float) -> None:
        parent = super()
        watcher = getattr(parent, "watch_scroll_y", None)
        if callable(watcher):
            try:
                watcher(old, new)
            except TypeError:
                watcher(new)
        app = getattr(self, "app", None)
        if getattr(app, "_transcript_mode", False):
            app._render_transcript_overlay_banner()


class PyCodexTextualApp(App[int]):
    """Small Textual shell around the already ported ``TuiAppRuntime``."""

    CSS = """
    Screen {
        layout: vertical;
        background: black;
        color: white;
    }

    #transcript {
        height: 1fr;
        margin: 0 1;
        padding: 0 1;
        background: black;
        color: white;
        scrollbar-size: 0 0;
    }

    #status-line {
        height: 2;
        padding: 0 1;
        color: $text-muted;
    }

    #slash-popup {
        height: auto;
        margin: 0 1;
        color: $text-muted;
    }

    #composer-prompt {
        height: auto;
        margin: 0 1;
        color: $text-muted;
    }

    #composer {
        height: 5;
        margin: 0 1 1 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "interrupt_or_quit", "Interrupt"),
        ("escape", "interrupt_or_focus", "Interrupt"),
        ("ctrl+d", "quit", "Quit"),
    ]

    def get_driver_class(self) -> Any:
        if os.name == "nt":
            from .textual_windows_vt_driver import PyCodexWindowsVtDriver

            return PyCodexWindowsVtDriver
        return super().get_driver_class()

    def __init__(self, app_runtime: TuiAppRuntime, *, use_alt_screen: bool = True) -> None:
        super().__init__()
        self.app_runtime = app_runtime
        self._pycodex_alt_screen_enabled = bool(use_alt_screen)
        self._pycodex_alt_screen_active = False
        # Back-compat for older tests/helpers. Rust keeps "enabled" separate
        # from "active": normal chat starts inline and only overlays enter alt.
        self._pycodex_use_alt_screen = self._pycodex_alt_screen_enabled
        self.exit_code = 0
        self._blocks: list[_TranscriptBlock] = []
        self._active_codex_block: _TranscriptBlock | None = None
        self._active_reasoning_block: _TranscriptBlock | None = None
        self._active_exec_block: _TranscriptBlock | None = None
        self._active_exec_rows: dict[str, str] = {}
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._last_mcp_status_header = ""
        self._seen_mcp_warnings: set[str] = set()
        self._turn_worker: threading.Thread | None = None
        self._busy = False
        self._turn_started_at = 0.0
        self._active_turn_id: str | None = None
        self._prompt_history = ChatComposerHistory.new()
        self._prompt_history_metadata: tuple[Any, int, int] | None = None
        self._queued_prompts: list[str] = []
        self._transcript_mode = False
        self._backtrack_state = BacktrackState()
        self._active_selection: _TextualSelection | None = None
        self._active_selection_index = 0
        self._suppress_selection_enter_until = 0.0
        self._review_custom_prompt_active = False
        self._managed_terminal_title: str | None = None
        self._invalid_status_line_warned = False
        self._invalid_terminal_title_warned = False
        self._notices_ready = False
        self._session_header_configured = _runtime_session_header_configured_at_startup(app_runtime)
        self._session_header_block_index: int | None = None
        self._shutdown_requested = False
        self.copy_to_clipboard = _copy_to_system_clipboard
        self._post_submit_composer_text: str | None = None
        self._rename_prompt_active = False
        self._goal_edit_prompt: _GoalEditPromptState | None = None
        self._shortcut_overlay_mode = FooterMode.COMPOSER_EMPTY
        self._external_editor_thread: threading.Thread | None = None
        self._active_retry_status: _RetryStatus | None = None
        self.read_clipboard_text = _read_system_clipboard_text
        self._history_projection_next_index = 0
        self._terminal_scrollback_projected_until = 0
        self._last_history_projection_ansi = ""
        self._resize_reflow_state = ResizeReflowState(raw_output_mode=_raw_output_mode(app_runtime))
        self._last_insert_history_reflow_plan: Any = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            CodexTranscriptLog(id="transcript", wrap=True, highlight=False, markup=False, auto_scroll=True),
            Static(_plain_status_text(self._startup_status_line_text()), id="status-line"),
            Static("", id="slash-popup"),
            Static(_plain_status_text(self._composer_prompt_text()), id="composer-prompt"),
            CodexComposerTextArea(id="composer"),
        )

    def on_mount(self) -> None:
        self._sync_composer_history_metadata_from_runtime()
        self._refresh_terminal_title(active_progress=False)
        self._notices_ready = True
        self._ensure_session_header_block()
        self._append_startup_notices()
        self._history_projection_next_index = len(self._blocks)
        self._set_status("Ready")
        self._composer().focus()
        self._pump_app_server_events()
        self.set_interval(0.1, self._pump_app_server_events)
        self.set_interval(1.0, self._tick_status)
        self.set_timer(0.01, self._apply_startup_session_action)

    def on_unmount(self) -> None:
        self._clear_managed_terminal_title()
        self.app_runtime.close()

    def submit_composer_text(self, prompt: str) -> None:
        prepared = self._prepare_composer_submission(prompt)
        if prepared is None:
            return
        prompt, _text_elements = prepared
        composer = self._composer()
        composer.hide_command_popup()
        if self._review_custom_prompt_active:
            self._handle_review_custom_prompt_submission(prompt)
            self._clear_submission_state(composer)
            return
        if not prompt.strip():
            composer.clear_submission_state()
            return
        command = prompt.strip().lower()
        if command in {"/quit", "/exit", ":q", "q", "quit", "exit"}:
            composer.clear_submission_state()
            self._request_shutdown()
            return
        if self._rename_prompt_active:
            self._handle_rename_prompt_submission(prompt)
            self._clear_submission_state(composer)
            return
        if self._goal_edit_prompt is not None:
            self._handle_goal_edit_prompt_submission(prompt)
            self._clear_submission_state(composer)
            return
        if self._busy:
            if prompt.strip().startswith("/"):
                slash_command = _parse_slash_command(prompt)
                if slash_command is not None:
                    queued_command = prompt.strip().lower().split(maxsplit=1)[0]
                    has_queued_argument = len(prompt.strip().split(maxsplit=1)) > 1
                    if queued_command == "/compact" or (queued_command == "/review" and has_queued_argument):
                        composer.clear_submission_state()
                        self._queued_prompts.append(prompt)
                        self._append_system_notice("Queued follow-up inputs")
                        return
                    if not slash_command.available_during_task():
                        composer.clear_submission_state()
                        self._append_system_notice(
                            f"'{slash_command.command() if slash_command.command().startswith('/') else '/' + slash_command.command()}' "
                            "is disabled while a task is in progress."
                        )
                        return
                    if self._handle_local_slash_command(prompt):
                        self._guard_selection_enter_from_submit()
                        self._clear_submission_state(composer)
                        return
            composer.clear_submission_state()
            self._queued_prompts.append(prompt)
            self._append_system_notice("Queued follow-up inputs")
            return
        if self._handle_local_slash_command(prompt):
            self._guard_selection_enter_from_submit()
            self._clear_submission_state(composer)
            return
        composer.clear_submission_state()
        self._prompt_history.record_local_submission(HistoryEntry.new(prompt))
        append_history = getattr(self.app_runtime, "append_message_history_entry", None)
        if callable(append_history):
            append_history(prompt)
            self._sync_composer_history_metadata_from_runtime()
        self._submit_prompt(prompt)

    def navigate_composer_history(self, composer: "CodexComposerTextArea", direction: str) -> bool:
        self._sync_composer_history_metadata_from_runtime()
        text = composer.text
        cursor = composer.byte_cursor_offset()
        if not self._prompt_history.should_handle_navigation(text, cursor):
            return False
        previous_cursor = self._prompt_history.history_cursor
        if direction == "older":
            entry = self._prompt_history.navigate_up(self._handle_history_lookup_event)
        else:
            entry = self._prompt_history.navigate_down(self._handle_history_lookup_event)
        if entry is None:
            return self._prompt_history.history_cursor != previous_cursor
        composer.apply_history_entry(entry)
        return True

    def begin_composer_history_search(self, composer: "CodexComposerTextArea") -> None:
        self._sync_composer_history_metadata_from_runtime()
        composer.begin_history_search()
        self._set_history_search_status(composer)

    def update_composer_history_search(self, composer: "CodexComposerTextArea") -> None:
        self._search_composer_history(
            composer,
            direction=HistorySearchDirection.OLDER,
            restart=True,
        )

    def step_composer_history_search(
        self,
        composer: "CodexComposerTextArea",
        direction: HistorySearchDirection,
    ) -> None:
        self._search_composer_history(
            composer,
            direction=direction,
            restart=False,
        )

    def _search_composer_history(
        self,
        composer: "CodexComposerTextArea",
        *,
        direction: HistorySearchDirection,
        restart: bool,
    ) -> None:
        self._sync_composer_history_metadata_from_runtime()
        session = composer.history_search
        if session is None:
            return
        query = session.query
        if not query:
            composer.restore_history_search_original(keep_search=True, status=HistorySearchStatus.IDLE)
            self._set_history_search_status(composer)
            return
        result = self._prompt_history.search(query, direction, restart, self._handle_history_lookup_event)
        status = _history_search_status_for_result(result)
        entry = getattr(result, "entry", None)
        if status is HistorySearchStatus.MATCH and entry is not None:
            composer.apply_history_entry(entry)
            composer.set_history_search_status(status)
        elif status is HistorySearchStatus.NO_MATCH:
            composer.restore_history_search_original(keep_search=True, status=status)
        else:
            composer.set_history_search_status(status)
        self._set_history_search_status(composer)

    def _sync_composer_history_metadata_from_runtime(self) -> None:
        metadata = getattr(self.app_runtime.chat_widget, "bottom_history_metadata", None)
        if not metadata:
            metadata = getattr(self.app_runtime, "message_history_metadata", None)
        if metadata is None:
            return
        try:
            thread_id, log_id, entry_count = metadata
        except (TypeError, ValueError):
            thread_id = _payload_field(metadata, "thread_id", self.app_runtime.current_displayed_thread_id())
            history = _payload_field(metadata, "message_history", metadata)
            log_id = _payload_field(history, "log_id", None)
            entry_count = _payload_field(history, "entry_count", 0)
        if thread_id is None or log_id is None:
            return
        try:
            normalized = (thread_id, int(log_id), int(entry_count or 0))
        except (TypeError, ValueError):
            return
        if normalized == self._prompt_history_metadata:
            return
        self._prompt_history.set_metadata(*normalized)
        self._prompt_history_metadata = normalized

    def _handle_history_lookup_event(self, event: Any) -> None:
        if _payload_field(event, "type", None) != "LookupMessageHistoryEntry":
            return
        thread_id = _payload_field(event, "thread_id", None)
        log_id = _payload_field(event, "log_id", None)
        offset = _payload_field(event, "offset", None)
        if thread_id is None or log_id is None or offset is None:
            return
        try:
            log_id_int = int(log_id)
            offset_int = int(offset)
        except (TypeError, ValueError):
            return
        entry = self._lookup_message_history_entry(thread_id, log_id_int, offset_int)
        response = self._prompt_history.on_entry_response(
            log_id_int,
            offset_int,
            entry,
            self._handle_history_lookup_event,
        )
        self._apply_history_entry_response(response)

    def _lookup_message_history_entry(self, thread_id: Any, log_id: int, offset: int) -> str | None:
        runtime = self.app_runtime.active_thread_runtime
        for name in (
            "lookup_message_history_entry",
            "message_history_lookup",
            "lookup_history_entry",
        ):
            lookup = getattr(runtime, name, None)
            if not callable(lookup):
                continue
            for args in ((thread_id, log_id, offset), (log_id, offset), (offset,)):
                try:
                    result = lookup(*args)
                except TypeError:
                    continue
                if hasattr(result, "__await__"):
                    result = _runtime_run_coro_blocking(result)
                return _coerce_history_entry_text(result)
        return None

    def _apply_history_entry_response(self, response: HistoryEntryResponse) -> bool:
        composer = self._composer()
        if response.kind == "Found" and response.entry is not None:
            composer.apply_history_entry(response.entry)
            return True
        if response.kind == "Search" and response.search_result is not None:
            return self._apply_history_search_result(composer, response.search_result)
        return False

    def _apply_history_search_result(self, composer: "CodexComposerTextArea", result: HistorySearchResult) -> bool:
        status = _history_search_status_for_result(result)
        entry = getattr(result, "entry", None)
        if status is HistorySearchStatus.MATCH and entry is not None:
            composer.apply_history_entry(entry)
            composer.set_history_search_status(status)
            self._set_history_search_status(composer)
            return True
        if status is HistorySearchStatus.NO_MATCH:
            composer.restore_history_search_original(keep_search=True, status=status)
        else:
            composer.set_history_search_status(status)
        self._set_history_search_status(composer)
        return False

    def accept_composer_history_search(self, composer: "CodexComposerTextArea") -> bool:
        if composer.accept_history_search():
            self._set_status("Ready")
            return True
        return False

    def cancel_composer_history_search(self, composer: "CodexComposerTextArea") -> bool:
        if composer.cancel_history_search():
            self._set_status("Ready")
            return True
        return False

    def sync_command_popup(self, composer: "CodexComposerTextArea") -> None:
        if self._transcript_mode:
            self._render_transcript_overlay_banner()
            return
        if self._shortcut_overlay_mode is FooterMode.SHORTCUT_OVERLAY:
            if composer.text == "":
                self._render_shortcut_overlay()
                return
            self._clear_shortcut_overlay()
        popup = composer.sync_command_popup()
        widget = self.query_one("#slash-popup", Static)
        if popup is None:
            widget.update(_plain_status_text(""))
            return
        widget.update(_render_command_popup_text(popup))

    def clear_command_popup(self) -> None:
        if self._transcript_mode:
            self._render_transcript_overlay_banner()
            return
        self._shortcut_overlay_mode = FooterMode.COMPOSER_EMPTY
        self.query_one("#slash-popup", Static).update(_plain_status_text(""))

    def toggle_shortcut_overlay_from_composer(self, composer: "CodexComposerTextArea") -> bool:
        # Rust: bottom_pane::chat_composer::handle_shortcut_overlay_key only
        # toggles on a press event when the composer is empty and not pasting.
        if self._transcript_mode or self._active_selection is not None:
            return False
        if composer.text != "" or composer.pending_pastes:
            return False
        next_mode = toggle_shortcut_mode(
            self._shortcut_overlay_mode,
            ctrl_c_hint=False,
            is_empty=True,
        )
        changed = next_mode is not self._shortcut_overlay_mode
        self._shortcut_overlay_mode = next_mode
        if next_mode is FooterMode.SHORTCUT_OVERLAY:
            self._render_shortcut_overlay()
        else:
            self.query_one("#slash-popup", Static).update(_plain_status_text(""))
        return changed

    def _render_shortcut_overlay(self) -> None:
        self.query_one("#slash-popup", Static).update(
            _plain_status_text("\n".join(shortcut_overlay_lines(ShortcutsState(key_hints=_footer_key_hints_for_runtime(self.app_runtime)))))
        )

    def _clear_shortcut_overlay(self) -> None:
        if self._shortcut_overlay_mode is FooterMode.SHORTCUT_OVERLAY:
            self._shortcut_overlay_mode = FooterMode.COMPOSER_EMPTY
            self.query_one("#slash-popup", Static).update(_plain_status_text(""))

    def handle_selection_key(self, key: str) -> bool:
        if self._active_selection is None:
            return False
        if key == "enter" and time.monotonic() < self._suppress_selection_enter_until:
            self._suppress_selection_enter_until = 0.0
            return True
        if self._active_selection.kind in {"resume", "fork"} and isinstance(self._active_selection.context, PickerState):
            return self._handle_resume_picker_key(self._active_selection, key)
        if self._active_selection.kind == "approval" and key in {"y", "p"}:
            self._accept_exec_approval_shortcut(self._active_selection, key)
            return True
        if key == "up":
            self._active_selection_index = max(self._active_selection_index - 1, 0)
            self._render_active_selection()
            return True
        if key == "down":
            count = len(_selection_active_items(self._active_selection))
            self._active_selection_index = min(self._active_selection_index + 1, max(count - 1, 0))
            self._render_active_selection()
            return True
        if key == "tab":
            self._switch_active_selection_tab(1)
            return True
        if key in {"backtab", "shift+tab"}:
            self._switch_active_selection_tab(-1)
            return True
        if key == "backspace" and self._active_selection.search_query:
            self._active_selection.search_query = self._active_selection.search_query[:-1]
            self._active_selection_index = _first_enabled_selection_index(self._active_selection)
            self._render_active_selection()
            return True
        if _selection_accepts_search_key(self._active_selection, key):
            self._active_selection.search_query += key
            self._active_selection_index = _first_enabled_selection_index(self._active_selection)
            self._render_active_selection()
            return True
        if key in {"escape", "q"}:
            self._cancel_active_selection()
            return True
        if key == "enter":
            self._accept_active_selection()
            return True
        return False

    def _guard_selection_enter_from_submit(self) -> None:
        if self._active_selection is None:
            return
        # Rust codex-tui routes Enter through ChatComposer first, yielding an
        # InputResult::Submitted before the bottom-pane selection surface is
        # active.  Textual can deliver the same physical Enter to the newly
        # opened selection in the same event slice, so consume only that
        # immediate echo and leave subsequent user Enter presses untouched.
        self._suppress_selection_enter_until = time.monotonic() + 0.03

    def _set_history_search_status(self, composer: "CodexComposerTextArea") -> None:
        session = composer.history_search
        if session is None:
            self._set_status("Ready")
            return
        self.query_one("#status-line", Static).update(_plain_status_text(history_search_footer_line(session).text))

    def _prepare_composer_submission(self, prompt: str) -> tuple[str, list[Any]] | None:
        composer = self._composer()
        if str(prompt) != composer.text:
            composer.text = str(prompt)
        prepared, errors = composer.prepare_submission_text()
        for error in errors:
            self._append_system_notice(str(error))
        if prepared is None and self._rename_prompt_active:
            return (composer.text, [])
        if prepared is None and self._review_custom_prompt_active:
            return (composer.text, [])
        return prepared

    def action_quit(self) -> None:
        if self._transcript_mode:
            _scroll_transcript_half_page(self._transcript_log(), 1)
            return
        self._request_shutdown()

    def action_interrupt_or_focus(self) -> None:
        if self._transcript_mode:
            self._handle_transcript_pager_key("escape")
            return
        if self.cancel_composer_history_search(self._composer()):
            return
        if self._busy:
            self._interrupt_turn()
        else:
            self._composer().focus()

    def action_interrupt_or_quit(self) -> None:
        if self.cancel_composer_history_search(self._composer()):
            return
        if self._busy:
            self._interrupt_turn()
        else:
            self._request_shutdown()

    def action_open_transcript(self) -> None:
        # Rust codex-tui::app::input opens pager_overlay::TranscriptOverlay.
        # Textual's scrollable transcript pane is always present, so Ctrl-T
        # moves focus there and exposes the same pager key family.
        _textual_timing_trace("textual_open_transcript", busy=self._busy, transcript_blocks=len(self._blocks))
        self._transcript_mode = True
        transcript = self._transcript_log()
        transcript.focus()
        self._render_transcript_overlay_banner()
        self._set_status("Transcript: ↑/↓ scroll; pgup/pgdn page; home/end jump; q close")

    def action_toggle_raw_output(self) -> None:
        # Rust codex-tui::app::input handles keymap.app.toggle_raw_output with
        # apply_raw_output_mode(..., notify=false), so this is a local state
        # toggle without a transcript notice or UserTurn submission.
        enabled = not _raw_output_mode(self.app_runtime)
        self.app_runtime.apply_raw_output_mode(enabled)
        self._set_status(_raw_output_mode_notice(enabled))

    def action_clear_terminal(self) -> None:
        # Rust codex-tui::app::input handles keymap.app.clear_terminal through
        # clear_terminal_ui + reset_app_ui_state_after_clear while idle. During
        # an active task ChatWidget::can_run_ctrl_l_clear_now reports a local
        # error and leaves the transcript intact.
        if self._busy:
            self._append_system_notice("Ctrl+L is disabled while a task is in progress.")
            self._set_status("Working")
            return
        self._handle_clear_command()

    def action_toggle_vim_mode(self) -> None:
        # Rust codex-tui::app::input handles keymap.app.toggle_vim_mode by
        # calling ChatWidget::toggle_vim_mode_and_notify before the key reaches
        # the composer. Keep this aligned with the local /vim slash command.
        self._handle_vim_command()

    def action_copy_last_response(self) -> None:
        # Rust codex-tui::chatwidget::interaction consumes the configured
        # global.copy binding before normal composer input and calls
        # ChatWidget::copy_last_agent_markdown.
        if self._transcript_mode or self._active_selection is not None:
            return
        self._handle_copy_command()

    def action_open_external_editor(self) -> None:
        # Rust codex-tui::app::input requests the external editor first, then
        # AppEvent::LaunchExternalEditor performs the terminal-restored launch
        # after a frame. Textual keeps the same visible state transition and
        # runs the already-ported external_editor helper off the UI thread.
        if self._transcript_mode or self._active_selection is not None:
            return
        if self._external_editor_thread is not None and self._external_editor_thread.is_alive():
            return
        self._set_external_editor_state("Requested")
        self._set_footer_hint_override([(EXTERNAL_EDITOR_HINT, "")])
        self._set_status(EXTERNAL_EDITOR_HINT)
        seed = self._composer().text
        worker = threading.Thread(
            target=self._external_editor_worker,
            args=(seed,),
            name="pycodex-external-editor",
            daemon=True,
        )
        self._external_editor_thread = worker
        worker.start()

    def _external_editor_worker(self, seed: str) -> None:
        try:
            editor_cmd = external_editor.resolve_editor_command()
            new_text = asyncio.run(external_editor.run_editor(seed, editor_cmd))
        except external_editor.ExternalEditorError as exc:
            raw = str(exc)
            if raw == external_editor.EditorError.MISSING_EDITOR.value:
                message = MISSING_EDITOR_MESSAGE
            else:
                message = f"Failed to open editor: {raw}"
            self.call_from_thread(self._finish_external_editor, None, message)
        except Exception as exc:
            self.call_from_thread(self._finish_external_editor, None, f"Failed to open editor: {exc}")
        else:
            self.call_from_thread(self._finish_external_editor, str(new_text).rstrip(), None)

    def _finish_external_editor(self, new_text: str | None, error_message: str | None) -> None:
        self._set_external_editor_state("Closed")
        self._set_footer_hint_override(None)
        if error_message:
            self._append_system_notice(error_message)
            self._set_status("Ready")
            return
        if new_text is not None:
            composer = self._composer()
            composer.text = new_text
            composer._move_cursor_to_end()
            composer.focus()
        self._set_status("Ready")

    def _set_external_editor_state(self, state: str) -> None:
        try:
            setattr(self.app_runtime.chat_widget, "external_editor_state", state)
        except Exception:
            pass

    def _set_footer_hint_override(self, items: list[tuple[str, str]] | None) -> None:
        bottom_pane = getattr(getattr(self.app_runtime, "chat_widget", None), "bottom_pane", None)
        setter = getattr(bottom_pane, "set_footer_hint_override", None)
        if callable(setter):
            try:
                setter(items)
            except Exception:
                pass

    async def _on_key(self, event: Any) -> None:
        key = str(getattr(event, "key", "") or "")
        _textual_timing_trace(
            "textual_app_key",
            key=key,
            character=repr(getattr(event, "character", None)),
            transcript_mode=self._transcript_mode,
            focused=str(getattr(getattr(self, "focused", None), "id", None)),
        )
        if self._active_selection is not None and self._active_selection.kind == "keymap-capture":
            if key == "escape":
                event.stop()
                event.prevent_default()
                self._cancel_active_selection()
                return
            event.stop()
            event.prevent_default()
            self._handle_keymap_capture_key(self._active_selection, key)
            return
        if self._active_selection is not None and self._active_selection.kind == "keymap-debug":
            if key in {"escape", "q"}:
                event.stop()
                event.prevent_default()
                self._cancel_active_selection()
                return
            event.stop()
            event.prevent_default()
            self.query_one("#slash-popup", Static).update(_render_keymap_debug_text(self._active_selection.view, key))
            return
        if self._rename_prompt_active and key == "enter":
            event.stop()
            event.prevent_default()
            self.submit_composer_text(self._composer().text)
            return
        if self._review_custom_prompt_active:
            if key == "enter":
                event.stop()
                event.prevent_default()
                self.submit_composer_text(self._composer().text)
                return
            if key in {"escape", "q"}:
                event.stop()
                event.prevent_default()
                self._review_custom_prompt_active = False
                self._set_status("Ready")
                self._composer().focus()
                return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "open_transcript",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_open_transcript()
            return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "toggle_raw_output",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_toggle_raw_output()
            return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "open_external_editor",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_open_external_editor()
            return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "clear_terminal",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_clear_terminal()
            return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "copy",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_copy_last_response()
            return
        if not self._transcript_mode and _app_keymap_key_matches(
            self.app_runtime,
            key,
            "toggle_vim_mode",
            getattr(event, "character", None),
        ):
            event.stop()
            event.prevent_default()
            self.action_toggle_vim_mode()
            return
        if not self._transcript_mode:
            return
        if self._handle_transcript_pager_key(key):
            event.stop()
            event.prevent_default()
            return

    def _handle_transcript_pager_key(self, key: str) -> bool:
        """Route Rust ``pager_overlay::PagerView`` keys to Textual's transcript pane."""

        transcript = self._transcript_log()
        normalized = key.replace("-", "_").replace("+", "_").lower()
        if self._handle_transcript_backtrack_key(normalized):
            return True
        if normalized in {"q", "ctrl_t"}:
            self._focus_composer_from_transcript()
            return True
        handled = True
        if normalized in {"up", "k"}:
            transcript.scroll_relative(y=-1, animate=False, force=True)
        elif normalized in {"down", "j"}:
            transcript.scroll_relative(y=1, animate=False, force=True)
        elif normalized in {"pageup", "page_up", "ctrl_b"}:
            _scroll_transcript_page(transcript, -1)
        elif normalized in {"pagedown", "page_down", "ctrl_f"}:
            _scroll_transcript_page(transcript, 1)
        elif normalized == "ctrl_u":
            _scroll_transcript_half_page(transcript, -1)
        elif normalized == "ctrl_d":
            _scroll_transcript_half_page(transcript, 1)
        elif normalized == "home":
            transcript.scroll_home(animate=False, force=True)
        elif normalized == "end":
            transcript.scroll_end(animate=False, force=True)
        else:
            handled = False
        if handled:
            self.set_timer(0.01, self._render_transcript_overlay_banner)
        return handled

    def _handle_transcript_backtrack_key(self, normalized: str) -> bool:
        event_code = {
            "escape": "esc",
            "esc": "esc",
            "left": "left",
            "right": "right",
            "enter": "enter",
        }.get(normalized)
        if event_code is None:
            return False
        plan = handle_backtrack_overlay_event_state(
            self._backtrack_state,
            event_code=event_code,
            event_kind="press",
        )
        if plan.action == "forward":
            return False
        if plan.action == "begin_preview":
            self._begin_transcript_backtrack_preview()
            return True
        if plan.action == "step_backtrack":
            self._step_transcript_backtrack_preview(-1)
            return True
        if plan.action == "step_forward":
            self._step_transcript_backtrack_preview(1)
            return True
        if plan.action == "confirm":
            self._confirm_transcript_backtrack_preview()
            return True
        return False

    def _begin_transcript_backtrack_preview(self) -> None:
        cells = self._backtrack_transcript_cells()
        thread_id = self._current_thread_id_for_backtrack()
        plan = begin_overlay_backtrack_preview_state(self._backtrack_state, thread_id, cells)
        if plan.action == "no_target_close_overlay":
            self._focus_composer_from_transcript()
            self._append_system_notice(plan.info_message or NO_PREVIOUS_MESSAGE_TO_EDIT)
            return
        self._render_backtrack_preview_banner()
        self._set_status("Backtrack: Enter edit; Esc/Left older; Right newer; q close")

    def _step_transcript_backtrack_preview(self, direction: int) -> None:
        cells = self._backtrack_transcript_cells()
        total = backtrack_user_count(cells)
        if direction < 0:
            next_index = next_backtrack_selection_index(self._backtrack_state.nth_user_message, total)
        else:
            next_index = next_forward_backtrack_selection_index(self._backtrack_state.nth_user_message, total)
        apply_backtrack_selection_index(self._backtrack_state, cells, next_index)
        self._render_backtrack_preview_banner()

    def _confirm_transcript_backtrack_preview(self) -> None:
        cells = self._backtrack_transcript_cells()
        thread_id = self._current_thread_id_for_backtrack()
        selection = backtrack_selection(self._backtrack_state, thread_id, cells)
        if selection is None:
            self._focus_composer_from_transcript()
            self._append_system_notice(NO_PREVIOUS_MESSAGE_TO_EDIT)
            return
        rollback = apply_backtrack_rollback_state(self._backtrack_state, selection, cells, thread_id)
        if rollback is None:
            self._focus_composer_from_transcript()
            return
        if rollback.error_message:
            self._focus_composer_from_transcript()
            self._append_system_notice(rollback.error_message)
            return
        self.app_runtime.submit_op(AppCommand.thread_rollback(rollback.num_turns))
        composer = self._composer()
        composer.text = rollback.composer_prefill
        composer._move_cursor_to_end()
        self._focus_composer_from_transcript()

    def _render_backtrack_preview_banner(self) -> None:
        cells = self._backtrack_transcript_cells()
        selection = backtrack_selection(self._backtrack_state, self._current_thread_id_for_backtrack(), cells)
        preview = "" if selection is None else selection.prefill.strip()
        if len(preview) > 120:
            preview = f"{preview[:117]}..."
        lines = [
            _render_transcript_overlay_banner_text(self._transcript_log()),
            "",
            "B A C K T R A C K",
            "Enter to edit this message    Esc/Left older    Right newer    q close",
        ]
        if preview:
            lines.append(f"> {preview}")
        self.query_one("#slash-popup", Static).update(_plain_status_text("\n".join(lines)))

    def _backtrack_transcript_cells(self) -> list[Any]:
        cells: list[Any] = []
        for block in self._blocks:
            if block.label == "you":
                cells.append(backtrack_user_cell(block.text))
            elif block.label == "codex":
                cells.append(backtrack_agent_cell(block.text, stream_continuation=True))
            else:
                cells.append(backtrack_info_cell(block.text))
        return cells

    def _current_thread_id_for_backtrack(self) -> str:
        return self.app_runtime.current_displayed_thread_id() or self.app_runtime.thread_id

    def _focus_composer_from_transcript(self) -> None:
        close_transcript_overlay_state(self._backtrack_state)
        self._transcript_mode = False
        self.clear_command_popup()
        self._composer().focus()
        self._set_status("Working" if self._busy else "Ready")

    def _render_transcript_overlay_banner(self) -> None:
        # Rust codex-tui::pager_overlay::TranscriptOverlay renders this fixed
        # title above the transcript pager plus key hints beneath the page.
        self.query_one("#slash-popup", Static).update(
            _plain_status_text(_render_transcript_overlay_banner_text(self._transcript_log()))
        )

    async def on_mouse_scroll_down(self, event: Any) -> None:
        if self._transcript_mode:
            self.set_timer(0.01, self._render_transcript_overlay_banner)

    async def on_mouse_scroll_up(self, event: Any) -> None:
        if self._transcript_mode:
            self.set_timer(0.01, self._render_transcript_overlay_banner)

    def _open_model_picker(self) -> None:
        context = ModelPopupContext(current_model=_runtime_display_model(self.app_runtime))
        presets = _runtime_model_presets(self.app_runtime)
        result = open_model_popup(context, presets)
        if result.info_message:
            self._append_system_notice(result.info_message)
            return
        if result.view is None:
            self._append_system_notice("No model choices are available right now.")
            return
        self._mark_session_header_configured()
        self._active_selection = _TextualSelection(kind="model", view=result.view, context=context, presets=presets)
        self._active_selection_index = _initial_selection_index(self._active_selection)
        self._render_active_selection()
        self._set_status("Select Model: up/down move; Enter select; Esc/q cancel")

    def _handle_agent_command(self, argument: str) -> None:
        normalized = argument.strip().lower()
        if normalized in {"next", "n"}:
            self.app_runtime.select_adjacent_agent_thread(AgentNavigationDirection.Next)
            self._append_system_notice(_active_agent_selection_notice(self.app_runtime))
            self._set_status("Ready")
            return
        if normalized in {"previous", "prev", "p"}:
            self.app_runtime.select_adjacent_agent_thread(AgentNavigationDirection.Previous)
            self._append_system_notice(_active_agent_selection_notice(self.app_runtime))
            self._set_status("Ready")
            return
        if argument.strip():
            self.app_runtime.select_agent_thread(argument.strip())
            self._append_system_notice(_active_agent_selection_notice(self.app_runtime))
            self._set_status("Ready")
            return
        self._open_agent_picker()

    def _open_agent_picker(self) -> None:
        plan = open_agent_picker_plan(
            _agent_picker_plan_entries(self.app_runtime),
            active_thread_id=self.app_runtime.current_displayed_thread_id(),
            primary_thread_id=self.app_runtime.routing_state.primary_thread_id,
            collab_enabled=_runtime_feature_enabled(self.app_runtime, "Collab", default=True),
        )
        if plan.action == "open_multi_agent_enable_prompt":
            self._active_selection = _TextualSelection(kind="multi-agent-enable", view=_multi_agent_enable_view())
            self._active_selection_index = 0
            self._render_active_selection()
            self._set_status("Enable Subagents: up/down move; Enter select; Esc/q cancel")
            return
        if plan.action == "agent_picker_empty":
            self._append_system_notice((plan.messages or ("No agents available yet.",))[0])
            self._set_status("Ready")
            return
        view = _agent_selection_view(self.app_runtime)
        if not list(getattr(view, "items", ()) or ()):
            self._append_system_notice("No agents available yet.")
            self._set_status("Ready")
            return
        self._active_selection = _TextualSelection(kind="agent", view=view)
        self._active_selection_index = int(getattr(view, "initial_selected_idx", None) or 0)
        self._render_active_selection()
        self._set_status("Select Agent: up/down move; Enter select; Esc/q cancel")

    def _open_permissions_picker(self) -> None:
        widget = _PermissionPopupWidget(self.app_runtime)
        view = open_permissions_popup(widget)
        if view is None:
            self._append_system_notice("Permissions are not available right now.")
            self._set_status("Ready")
            return
        self._active_selection = _TextualSelection(kind="permissions", view=view, context=widget)
        self._active_selection_index = _initial_selection_index(self._active_selection)
        self._render_active_selection()
        self._set_status("Update Permissions: up/down move; Enter select; Esc/q cancel")

    def _open_exec_approval_picker(self, event: ServerNotification) -> None:
        payload = event.payload if isinstance(event.payload, Mapping) else {}
        command = str(payload.get("command", "") or "")
        reason = str(payload.get("reason", "") or "")
        approval_id = str(payload.get("id", "") or "")
        turn_id = payload.get("turn_id")
        amendment = payload.get("proposed_execpolicy_amendment")
        items = [
            SelectionItem(
                name="Yes, proceed",
                description="Run this command once.",
                actions=[ReviewDecision.approved()],
                dismiss_on_select=True,
            )
        ]
        if amendment is not None:
            items.append(
                SelectionItem(
                    name="Yes, and don't ask again for this kind of command",
                    description="Approve this command and apply the proposed exec policy amendment.",
                    actions=[
                        {
                            "approved_execpolicy_amendment": {
                                "proposed_execpolicy_amendment": amendment,
                            }
                        }
                    ],
                    dismiss_on_select=True,
                )
            )
        else:
            items.append(
                SelectionItem(
                    name="Yes, and don't ask again this session",
                    description="Approve this command for the current session.",
                    actions=[ReviewDecision.approved_for_session()],
                    dismiss_on_select=True,
                )
            )
        items.append(
            SelectionItem(
                name="No, and tell Codex what to do differently",
                description="Reject this command and return control to the model.",
                actions=[ReviewDecision.denied()],
                dismiss_on_select=True,
            )
        )
        subtitle_parts = []
        if reason:
            subtitle_parts.append(f"Reason: {reason}")
        if command:
            subtitle_parts.append(f"$ {command}")
        view = SelectionViewParams(
            title="Would you like to run the following command?",
            subtitle="\n".join(subtitle_parts) if subtitle_parts else None,
            footer_hint="Press enter to confirm or esc to go back",
            items=items,
        )
        self._active_selection = _TextualSelection(
            kind="approval",
            view=view,
            context={
                "id": approval_id,
                "turn_id": None if turn_id is None else str(turn_id),
            },
        )
        self._active_selection_index = 0
        self._render_active_selection()
        self._set_status("Command approval: up/down move; Enter select; Esc/q cancel")

    def _render_active_selection(self) -> None:
        selection = self._active_selection
        if selection is None:
            self.clear_command_popup()
            return
        if selection.kind == "keymap-capture":
            self.query_one("#slash-popup", Static).update(_render_keymap_capture_text(selection.view))
            return
        _ensure_selection_tab(selection)
        self.query_one("#slash-popup", Static).update(_render_selection_view_text(selection, self._active_selection_index))

    def _switch_active_selection_tab(self, delta: int) -> None:
        selection = self._active_selection
        if selection is None:
            return
        tabs = list(getattr(selection.view, "tabs", ()) or ())
        if not tabs:
            return
        _ensure_selection_tab(selection)
        selection.active_tab_idx = (int(selection.active_tab_idx or 0) + int(delta)) % len(tabs)
        selection.search_query = ""
        self._active_selection_index = _first_enabled_selection_index(selection)
        self._render_active_selection()
        self._set_status(_selection_status_text(selection.kind))

    def _cancel_active_selection(self) -> None:
        selection = self._active_selection
        if selection is not None and selection.kind == "approval":
            self._resolve_exec_approval_selection(selection, ReviewDecision.abort())
            return
        if selection is not None and selection.parent_views:
            selection.view = selection.parent_views.pop()
            selection.search_query = ""
            self._active_selection_index = _initial_selection_index(selection)
            self._render_active_selection()
            self._set_status(_selection_status_text(selection.kind))
            return
        kind = _selection_display_name(getattr(selection, "kind", "selection"))
        self._active_selection = None
        self.clear_command_popup()
        self._set_status("Ready")
        self._composer().focus()
        self._append_system_notice(f"{kind} selection cancelled.")

    def _accept_active_selection(self) -> None:
        selection = self._active_selection
        if selection is None:
            return
        if selection.kind == "agent":
            self._accept_agent_selection(selection)
            return
        if selection.kind == "multi-agent-enable":
            self._accept_multi_agent_enable_selection(selection)
            return
        if selection.kind == "permissions":
            self._accept_permissions_selection(selection)
            return
        if selection.kind == "approval":
            self._accept_exec_approval_selection(selection)
            return
        if selection.kind == "review":
            self._accept_review_selection(selection)
            return
        if selection.kind == "goal":
            self._accept_goal_selection(selection)
            return
        if selection.kind in {"resume", "fork"}:
            self._accept_resume_selection(selection)
            return
        if selection.kind == "settings":
            self._accept_settings_selection(selection)
            return
        if selection.kind in {"keymap", "keymap-action-menu", "keymap-replace-binding"}:
            self._accept_keymap_selection(selection)
            return
        if selection.kind in {"keymap-debug", "keymap-capture"}:
            self._cancel_active_selection()
            return
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        next_view = self._apply_model_selection_item(selection, item)
        if next_view is not None:
            selection.view = next_view
            selection.search_query = ""
            self._active_selection_index = _initial_selection_index(selection)
            self._render_active_selection()
            return
        self._active_selection = None
        self.clear_command_popup()
        self._mark_session_header_configured()
        self._set_status("Ready")
        self._composer().focus()

    def _accept_exec_approval_shortcut(self, selection: "_TextualSelection", key: str) -> None:
        items = _selection_active_items(selection)
        if not items:
            self._resolve_exec_approval_selection(selection, ReviewDecision.abort())
            return
        if key == "y":
            self._resolve_exec_approval_selection(selection, ReviewDecision.approved())
            return
        if key == "p":
            index = 1 if len(items) > 1 else 0
            action = (getattr(items[index], "actions", None) or [ReviewDecision.approved_for_session()])[0]
            self._resolve_exec_approval_selection(selection, action)

    def _accept_exec_approval_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._resolve_exec_approval_selection(selection, ReviewDecision.abort())
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        action = (getattr(item, "actions", None) or [ReviewDecision.denied()])[0]
        self._resolve_exec_approval_selection(selection, action)

    def _resolve_exec_approval_selection(self, selection: "_TextualSelection", decision: Any) -> None:
        context = selection.context if isinstance(selection.context, Mapping) else {}
        approval_id = str(context.get("id", "") or "")
        turn_id = context.get("turn_id")
        self._active_selection = None
        self.clear_command_popup()
        self._composer().focus()
        if not approval_id:
            self._append_system_notice("Approval request is missing an id.")
            return
        self.app_runtime.submit_op(AppCommand.exec_approval(approval_id, None if turn_id is None else str(turn_id), decision))
        self._set_status("Working" if self._busy else "Ready")

    def _accept_agent_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        thread_id = str((getattr(item, "actions", None) or [""])[0])
        self.app_runtime.select_agent_thread(thread_id)
        self._active_selection = None
        self.clear_command_popup()
        self._append_system_notice(_active_agent_selection_notice(self.app_runtime))
        self._set_status("Ready")
        self._composer().focus()

    def _accept_multi_agent_enable_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        action = str((getattr(item, "actions", None) or ["cancel"])[0])
        self._active_selection = None
        self.clear_command_popup()
        if action == "enable":
            _set_runtime_feature_enabled(self.app_runtime, "Collab", True)
            self._append_system_notice(MULTI_AGENT_ENABLE_NOTICE)
        else:
            self._append_system_notice("Subagents not enabled.")
        self._set_status("Ready")
        self._composer().focus()

    def _accept_goal_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        actions = list(getattr(item, "actions", ()) or ())
        self._active_selection = None
        self.clear_command_popup()
        if actions:
            event = actions[0]
            if isinstance(event, Mapping) and event.get("type") == "SetThreadGoalObjective":
                thread_id = event.get("thread_id")
                objective = str(event.get("objective") or "")
                response_goal, error = _runtime_thread_goal_set(
                    self.app_runtime,
                    thread_id,
                    objective=objective,
                    status=ThreadGoalStatus.Active,
                    replace=True,
                )
                self._apply_thread_goal_plan(
                    set_thread_goal_objective_plan(
                        thread_id,
                        objective,
                        ThreadGoalSetMode.ReplaceExisting,
                        response_goal=response_goal,
                        set_error=error,
                    )
                )
                if self._maybe_start_goal_continuation(response_goal):
                    self._composer().focus()
                    return
        else:
            self._append_system_notice("Goal update cancelled.")
        self._set_status("Ready")
        self._composer().focus()

    def _accept_permissions_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        if getattr(item, "is_disabled", False) or getattr(item, "disabled_reason", None):
            reason = getattr(item, "disabled_reason", None) or "That permissions option is disabled."
            self._append_system_notice(str(reason))
            return
        nested_view = None
        for action in getattr(item, "actions", ()) or ():
            nested_view = self._apply_permission_popup_event(selection, action) or nested_view
        if nested_view is not None:
            selection.view = nested_view
            selection.search_query = ""
            self._active_selection_index = _initial_selection_index(selection)
            self._render_active_selection()
            return
        self._active_selection = None
        self.clear_command_popup()
        self._mark_session_header_configured()
        self._set_status("Ready")
        self._composer().focus()

    def _apply_permission_popup_event(self, selection: "_TextualSelection", event: object) -> object | None:
        kind = str(getattr(event, "kind", "") or "")
        payload = getattr(event, "payload", {}) or {}
        if kind == "select_permission_profile":
            profile_selection = getattr(event, "selection", None)
            profile_id = str(getattr(profile_selection, "profile_id", "") or "")
            config = _permission_config_for_runtime(self.app_runtime)
            if (
                profile_id == ":danger-no-sandbox"
                and not bool(getattr(config.notices, "hide_full_access_warning", False))
            ):
                widget = selection.context or _PermissionPopupWidget(self.app_runtime)
                preset = _popup_approval_preset_for_profile_id(self.app_runtime, profile_id)
                if preset is not None:
                    return open_full_access_confirmation(
                        widget,
                        preset,
                        True,
                        profile_selection,
                    )
            self._apply_permission_profile_selection(profile_selection)
            return None
        if kind == "OpenFullAccessConfirmation":
            widget = selection.context or _PermissionPopupWidget(self.app_runtime)
            return open_full_access_confirmation(
                widget,
                payload.get("preset"),
                bool(payload.get("return_to_permissions")),
                payload.get("profile_selection"),
            )
        if kind in {"OpenPermissionsPopup", "OpenApprovalsPopup"}:
            widget = selection.context or _PermissionPopupWidget(self.app_runtime)
            return open_permissions_popup(widget)
        if kind == "CodexOp":
            self._submit_permission_override(payload)
            return None
        if kind == "UpdateAskForApprovalPolicy":
            self._set_permission_approval_policy(payload.get("approval", payload.get("policy")))
            return None
        if kind == "UpdateActivePermissionProfile":
            self._set_active_permission_profile(payload.get("active_permission_profile"))
            return None
        if kind == "UpdateApprovalsReviewer":
            self._set_approvals_reviewer(payload.get("approvals_reviewer", payload.get("reviewer")))
            return None
        if kind == "InsertHistoryCell":
            event = AppEvent.of(kind, **dict(payload))
            plan = self.app_runtime.handle_app_event(event)
            self._handle_insert_history_cell_dispatch_plan(plan)
            return None
        if kind == "UpdateFullAccessWarningAcknowledged":
            self._set_full_access_warning_acknowledged(bool(payload.get("acknowledged", True)))
            return None
        if kind == "PersistFullAccessWarningAcknowledged":
            self._set_full_access_warning_acknowledged(True)
            return None
        if kind == "SelectPermissionProfile":
            self._apply_permission_profile_selection(payload.get("selection"))
            return None
        if kind in {"OpenWindowsSandboxEnablePrompt", "OpenWorldWritableWarningConfirmation", "EnableWindowsSandboxForAgentMode"}:
            self._append_system_notice("That permissions flow requires the full sandbox setup prompt; keeping current permissions.")
            return None
        if kind:
            payload_map = dict(payload) if isinstance(payload, dict) else {}
            self.app_runtime.handle_app_event(AppEvent.of(kind, **payload_map))
        return None

    def _submit_permission_override(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        raw_op = payload.get("op")
        if raw_op != "override_turn_context":
            self.app_runtime.handle_app_event(AppEvent.codex_op(raw_op))
            return
        config = _permission_config_for_runtime(self.app_runtime)
        if payload.get("permission_profile") is not None:
            config.permissions.permission_profile = payload.get("permission_profile")
            _set_runtime_attr(self.app_runtime.active_thread_runtime, "permission_profile", payload.get("permission_profile"))
            _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "permission_profile", payload.get("permission_profile"))
        op = AppCommand.override_turn_context(
            approval_policy=payload.get("approval_policy"),
            approvals_reviewer=payload.get("approvals_reviewer"),
            permission_profile=payload.get("permission_profile"),
            active_permission_profile=payload.get("active_permission_profile"),
        )
        try:
            self.app_runtime.submit_op(op)
        except Exception as exc:
            self._append_system_notice(f"Permission override failed: {exc}")

    def _set_permission_approval_policy(self, value: object) -> None:
        if value is None:
            return
        config = _permission_config_for_runtime(self.app_runtime)
        config.permissions.approval_policy = value
        _set_runtime_attr(self.app_runtime.active_thread_runtime, "approval_policy", value)
        _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "approval_policy", value)

    def _set_active_permission_profile(self, value: object) -> None:
        if value is None:
            return
        config = _permission_config_for_runtime(self.app_runtime)
        config.permissions.active_permission_profile_value = value
        _set_runtime_attr(self.app_runtime.active_thread_runtime, "active_permission_profile", value)
        _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "active_permission_profile", value)

    def _set_approvals_reviewer(self, value: object) -> None:
        if value is None:
            return
        config = _permission_config_for_runtime(self.app_runtime)
        config.approvals_reviewer = value
        _set_runtime_attr(self.app_runtime.active_thread_runtime, "approvals_reviewer", value)
        _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "approvals_reviewer", value)

    def _set_full_access_warning_acknowledged(self, acknowledged: bool) -> None:
        config = _permission_config_for_runtime(self.app_runtime)
        config.notices.hide_full_access_warning = bool(acknowledged)

    def _apply_permission_profile_selection(self, selection: object) -> None:
        if selection is None:
            return
        ui_profile = getattr(selection, "profile", None)
        active_profile = getattr(selection, "active_profile", None)
        profile_id = getattr(selection, "profile_id", None)
        if profile_id is None and active_profile is not None:
            profile_id = getattr(active_profile, "id", None)
        approval_policy = _coerce_approval_policy(getattr(selection, "approval_policy", None))
        approvals_reviewer = _coerce_approvals_reviewer(getattr(selection, "approvals_reviewer", None))
        display_label = (
            getattr(selection, "display_label", None)
            or getattr(active_profile, "name", None)
            or profile_id
        )
        ui_active_permission_profile = active_profile or SimpleNamespace(id=profile_id, name=display_label)
        core_active_permission_profile = _core_active_permission_profile_for_profile_id(profile_id)
        core_permission_profile = _core_permission_profile_for_active_profile_id(profile_id)
        if ui_profile is None:
            ui_profile = _permission_profile_for_active_profile_id(self.app_runtime, profile_id)
        if approval_policy is not None:
            self._set_permission_approval_policy(approval_policy)
        if approvals_reviewer is not None:
            self._set_approvals_reviewer(approvals_reviewer)
        self._set_active_permission_profile(core_active_permission_profile or ui_active_permission_profile)
        config = _permission_config_for_runtime(self.app_runtime)
        if ui_profile is not None:
            config.permissions.permission_profile = ui_profile
        if core_permission_profile is not None:
            _set_runtime_attr(self.app_runtime.active_thread_runtime, "permission_profile", core_permission_profile)
            _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "permission_profile", core_permission_profile)
        op = AppCommand.override_turn_context(
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=core_permission_profile,
            active_permission_profile=core_active_permission_profile,
        )
        try:
            self.app_runtime.submit_op(op)
        except Exception as exc:
            self._append_system_notice(f"Permission override failed: {exc}")
        self._append_system_notice(f"Permissions updated to {display_label}")

    def _open_review_picker(self) -> None:
        view = open_review_popup(_runtime_cwd(self.app_runtime))
        self._active_selection = _TextualSelection(kind="review", view=view)
        self._active_selection_index = int(getattr(view, "initial_selected_idx", None) or 0)
        self._render_active_selection()
        self._set_status(_selection_status_text("review"))

    def _accept_review_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        nested_view = None
        for action in getattr(item, "actions", ()) or ():
            nested_view = self._apply_review_popup_action(selection, action) or nested_view
        if self._busy or self._review_custom_prompt_active:
            self._active_selection = None
            self.clear_command_popup()
            return
        if nested_view is not None:
            selection.parent_views.append(selection.view)
            selection.view = nested_view
            selection.search_query = ""
            self._active_selection_index = int(getattr(nested_view, "initial_selected_idx", None) or 0)
            self._render_active_selection()
            self._set_status(_selection_status_text("review"))
            return
        self._active_selection = None
        self.clear_command_popup()
        self._set_status("Ready")
        self._composer().focus()

    def _apply_review_popup_action(self, selection: "_TextualSelection", action: object) -> object | None:
        if not isinstance(action, ReviewPopupAction):
            return None
        if action.kind == "open_review_branch_picker":
            cwd = action.cwd or _runtime_cwd(self.app_runtime)
            return show_review_branch_picker(cwd, local_git_branches, current_branch_name)
        if action.kind == "open_review_commit_picker":
            cwd = action.cwd or _runtime_cwd(self.app_runtime)
            return show_review_commit_picker(cwd, recent_commits)
        if action.kind == "open_review_custom_prompt":
            self._active_selection = None
            self.clear_command_popup()
            self._review_custom_prompt_active = True
            composer = self._composer()
            composer.text = ""
            composer._move_cursor_to_end()
            composer.focus()
            self._set_status("Custom review instructions: type instructions and press Enter")
            return None
        if action.kind == "review_uncommitted_changes":
            self._submit_app_command(AppCommand.review(ReviewTarget.uncommitted_changes()))
            return None
        if action.kind == "review_base_branch" and action.branch:
            self._submit_app_command(AppCommand.review(ReviewTarget.base_branch(action.branch)))
            return None
        if action.kind == "review_commit" and action.sha:
            self._submit_app_command(AppCommand.review(ReviewTarget.commit(action.sha, action.title)))
            return None
        if action.kind == "review_custom" and action.instructions:
            self._submit_app_command(AppCommand.review(ReviewTarget.custom(action.instructions)))
            return None
        return None

    def _open_session_picker(self, action: SessionPickerAction) -> bool:
        rows = _runtime_resume_picker_rows(self.app_runtime)
        if not rows:
            return False
        state = _resume_picker_state_from_rows(rows, action, self.app_runtime)
        view = _resume_picker_selection_view_from_state(state)
        kind = "fork" if action is SessionPickerAction.FORK else "resume"
        self._active_selection = _TextualSelection(kind=kind, view=view, context=state, search_query=state.query)
        self._active_selection_index = state.selected
        self._render_active_selection()
        self._set_status(_selection_status_text(kind))
        return True

    def _open_resume_picker(self) -> bool:
        return self._open_session_picker(SessionPickerAction.RESUME)

    def _open_fork_picker(self) -> bool:
        return self._open_session_picker(SessionPickerAction.FORK)

    def _handle_resume_picker_key(self, selection: "_TextualSelection", key: str) -> bool:
        state = selection.context
        if not isinstance(state, PickerState):
            return False
        code = _resume_picker_textual_key(key)
        if state.overlay is not None:
            if code in {"q", "esc"}:
                state.handle_overlay_event(None, "esc")
                self._refresh_resume_picker_selection(selection)
                return True
            return True
        if code == "q" and not state.query:
            self._cancel_active_selection()
            return True
        if code == "ctrl-t":
            state.open_selected_transcript()
            self._refresh_resume_picker_selection(selection)
            state.note_transcript_loading_frame_drawn()
            state.open_pending_transcript_if_ready()
            self._refresh_resume_picker_selection(selection)
            return True
        result = _run_picker_coro_synchronously(state.handle_key(code))
        self._refresh_resume_picker_selection(selection)
        if isinstance(result, SessionSelection):
            if result.kind == "Exit":
                self._cancel_active_selection()
                return True
            if result.kind == "StartFresh":
                self._cancel_active_selection()
                return True
            if result.target is not None:
                self._accept_resume_selection(selection)
                return True
        return True

    def _refresh_resume_picker_selection(self, selection: "_TextualSelection") -> None:
        state = selection.context
        if not isinstance(state, PickerState):
            return
        selection.view = _resume_picker_selection_view_from_state(state)
        selection.search_query = state.query
        self._active_selection_index = state.selected
        if state.overlay is not None:
            self.query_one("#slash-popup", Static).update(
                _plain_status_text(_render_resume_picker_transcript_overlay(state.overlay))
            )
            self._set_status("Transcript: q/Esc close")
            return
        if state.is_transcript_loading():
            self.query_one("#slash-popup", Static).update(_plain_status_text("Transcript loading..."))
            self._set_status("Loading transcript...")
            return
        self._render_active_selection()

    def _accept_resume_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        if getattr(item, "is_disabled", False) or getattr(item, "disabled_reason", None):
            reason = getattr(item, "disabled_reason", None) or "That session cannot be resumed."
            self._append_system_notice(str(reason))
            return
        selected = next((action for action in (getattr(item, "actions", ()) or ()) if isinstance(action, SessionSelection)), None)
        if selected is None or selected.target is None:
            self._cancel_active_selection()
            return
        target = selected.target
        target_label = target.display_label()
        if selected.kind == "Resume":
            self.app_runtime.handle_app_event(AppEvent.of("ResumeSessionByIdOrName", id_or_name=target.thread_id))
            self._append_system_notice(f"Resume requested: {target_label}")
        elif selected.kind == "Fork":
            forked = self.app_runtime.fork_startup_session_target(target)
            self._mark_session_header_configured()
            if forked:
                self._append_startup_replay_history()
                self._drain_runtime_notices()
                self._append_system_notice(
                    f"Forked session from {target_label} as {self.app_runtime.startup_session_forked_thread_id}."
                )
            else:
                self._append_system_notice(f"Fork requested: {target_label}")
        self._active_selection = None
        self.clear_command_popup()
        self._set_status("Ready")
        self._composer().focus()

    def _open_settings_picker(self) -> None:
        widget = _SettingsPopupWidget(self.app_runtime, self)
        view = open_realtime_audio_popup(widget)
        self._active_selection = _TextualSelection(kind="settings", view=view, context=widget)
        self._active_selection_index = int(getattr(view, "initial_selected_idx", None) or 0)
        self._render_active_selection()
        self._set_status("Settings: up/down move; Enter select; Esc/q cancel")

    def _open_keymap_picker(self) -> None:
        widget = _keymap_picker_widget_for_runtime(self.app_runtime)
        widget.open_keymap_picker()
        for error in widget.errors:
            self._append_system_notice(str(error))
        if not widget.shown_selection_views:
            self._set_status("Ready")
            return
        view = _keymap_selection_view(widget.shown_selection_views[-1])
        self._active_selection = _TextualSelection(kind="keymap", view=view, context=widget)
        self._active_selection_index = int(getattr(view, "initial_selected_idx", None) or 0)
        self._render_active_selection()
        self._set_status(_selection_status_text("keymap"))

    def _open_keymap_debug(self) -> None:
        widget = _keymap_picker_widget_for_runtime(self.app_runtime)
        runtime_keymap = widget.runtime_keymap_from_config(widget.tui_keymap)
        if isinstance(runtime_keymap, Exception):
            self._append_system_notice(f"Invalid `tui.keymap` configuration: {runtime_keymap}")
            self._set_status("Ready")
            return
        widget.open_keymap_debug(runtime_keymap)
        view = widget.shown_views[-1] if widget.shown_views else KeymapView("debug", runtime_keymap=runtime_keymap)
        self._active_selection = _TextualSelection(kind="keymap-debug", view=view, context=widget)
        self._active_selection_index = 0
        self.query_one("#slash-popup", Static).update(_render_keymap_debug_text(view, None))
        self._set_status(_selection_status_text("keymap-debug"))

    def _accept_keymap_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        if getattr(item, "is_disabled", False) or getattr(item, "disabled_reason", None):
            reason = getattr(item, "disabled_reason", None) or "That shortcut cannot be edited."
            self._append_system_notice(str(reason))
            return
        events = _keymap_selection_item_events(item)
        if not events and getattr(item, "dismiss_on_select", False):
            self._cancel_active_selection()
            return
        for event in events:
            next_view = self._apply_keymap_event(selection, event)
            if next_view is not None:
                selection.parent_views.append(selection.view)
                selection.view = next_view
                selection.kind = _keymap_selection_kind_for_view(next_view)
                selection.search_query = ""
                self._active_selection_index = int(getattr(next_view, "initial_selected_idx", None) or 0)
                self._render_active_selection()
                self._set_status(_selection_status_text(selection.kind))
                return
        if getattr(item, "dismiss_on_select", False):
            self._cancel_active_selection()

    def _apply_keymap_event(self, selection: "_TextualSelection", event: object) -> object | None:
        event = _coerce_keymap_app_event(event)
        if event is None:
            return None
        widget = selection.context or _keymap_picker_widget_for_runtime(self.app_runtime)
        runtime_keymap = widget.runtime_keymap_from_config(widget.tui_keymap)
        if isinstance(runtime_keymap, Exception):
            self._append_system_notice(f"Invalid `tui.keymap` configuration: {runtime_keymap}")
            return None
        payload = event.payload
        if event.kind == "OpenKeymapActionMenu":
            return keymap_setup.build_keymap_action_menu_params(
                str(payload.get("context", "")),
                str(payload.get("action", "")),
                runtime_keymap,
                widget.tui_keymap,
            )
        if event.kind == "OpenKeymapReplaceBindingMenu":
            return keymap_setup.build_keymap_replace_binding_menu_params(
                str(payload.get("context", "")),
                str(payload.get("action", "")),
                runtime_keymap,
            )
        if event.kind == "OpenKeymapCapture":
            intent = payload.get("intent")
            if not isinstance(intent, KeymapEditIntent):
                intent = KeymapEditIntent.replace_all()
            return keymap_setup.build_keymap_capture_view(
                str(payload.get("context", "")),
                str(payload.get("action", "")),
                intent,
                runtime_keymap,
            )
        if event.kind == "KeymapCaptured":
            self._apply_keymap_captured(selection, widget, runtime_keymap, payload)
            return None
        if event.kind == "KeymapCleared":
            self._apply_keymap_cleared(selection, widget, payload)
            return None
        if event.kind == "OpenKeymapDebug":
            self._open_keymap_debug()
            return None
        self.app_runtime.handle_app_event(event)
        return None

    def _handle_keymap_capture_key(self, selection: "_TextualSelection", key: str) -> None:
        event = _keymap_captured_event_from_textual_key(selection.view, key)
        if event is None:
            self.query_one("#slash-popup", Static).update(_render_keymap_capture_text(selection.view))
            return
        self._apply_keymap_event(selection, event)

    def _apply_keymap_captured(
        self,
        selection: "_TextualSelection",
        widget: KeymapPickerWidgetState,
        runtime_keymap: RuntimeKeymap,
        payload: Mapping[str, object],
    ) -> None:
        context = str(payload.get("context", ""))
        action = str(payload.get("action", ""))
        key = str(payload.get("key", ""))
        intent = payload.get("intent")
        if not isinstance(intent, KeymapEditIntent):
            intent = KeymapEditIntent.replace_all()
        try:
            outcome = keymap_setup.keymap_with_edit(widget.tui_keymap, runtime_keymap, context, action, key, intent)
        except Exception as exc:
            self._append_system_notice(str(exc))
            return
        if outcome.kind == "Unchanged":
            self._append_system_notice(outcome.message)
            return
        self._commit_keymap_update(
            selection,
            widget,
            context,
            action,
            outcome.keymap_config,
            outcome.message,
            bindings=outcome.bindings,
            clear_binding=False,
        )

    def _apply_keymap_cleared(
        self,
        selection: "_TextualSelection",
        widget: KeymapPickerWidgetState,
        payload: Mapping[str, object],
    ) -> None:
        context = str(payload.get("context", ""))
        action = str(payload.get("action", ""))
        try:
            keymap_config = keymap_setup.keymap_without_custom_binding(widget.tui_keymap, context, action)
        except Exception as exc:
            self._append_system_notice(str(exc))
            return
        self._commit_keymap_update(
            selection,
            widget,
            context,
            action,
            keymap_config,
            f"Removed custom shortcut for `{context}.{action}`.",
            bindings=(),
            clear_binding=True,
        )

    def _commit_keymap_update(
        self,
        selection: "_TextualSelection",
        widget: KeymapPickerWidgetState,
        context: str,
        action: str,
        keymap_config: object,
        message: str,
        *,
        bindings: Iterable[str],
        clear_binding: bool,
    ) -> None:
        try:
            runtime_keymap = RuntimeKeymap.from_config(keymap_config or {})
        except Exception as exc:
            selection.view = keymap_setup.build_keymap_conflict_params(
                context,
                action,
                "",
                KeymapEditIntent.replace_all(),
                str(exc),
            )
            selection.kind = _keymap_selection_kind_for_view(selection.view)
            self._active_selection_index = 0
            self._render_active_selection()
            self._set_status(_selection_status_text(selection.kind))
            return
        try:
            self._persist_keymap_update(context, action, bindings, clear_binding=clear_binding)
        except BaseException as exc:
            prefix = "Failed to remove shortcut" if clear_binding else "Failed to save shortcut"
            self._append_system_notice(f"{prefix}: {exc}")
            return
        _store_runtime_keymap_config(self.app_runtime, keymap_config)
        widget.tui_keymap = keymap_config
        widget.apply_keymap_update(keymap_config, runtime_keymap)
        widget.return_to_keymap_picker(context, action, runtime_keymap)
        if widget.replace_calls:
            next_view = widget.replace_calls[-1][1]
        elif widget.shown_selection_views:
            next_view = widget.shown_selection_views[-1]
        else:
            next_view = KeymapView("picker", runtime_keymap=runtime_keymap, selected_action=(context, action))
        selection.view = _keymap_selection_view(next_view)
        selection.kind = "keymap"
        selection.parent_views.clear()
        selection.search_query = ""
        self._active_selection_index = int(getattr(selection.view, "initial_selected_idx", None) or 0)
        self._render_active_selection()
        self._append_system_notice(message)
        self._set_status(_selection_status_text("keymap"))

    def _persist_keymap_update(
        self,
        context: str,
        action: str,
        bindings: Iterable[str],
        *,
        clear_binding: bool,
    ) -> None:
        config = _config_from_app_runtime(self.app_runtime)
        if config is None:
            raise RuntimeError("missing config")
        edit = (
            keymap_binding_clear_edit(context, action)
            if clear_binding
            else keymap_bindings_edit(context, action, tuple(bindings))
        )
        ConfigEditsBuilder.for_config(config).with_edits([edit]).apply_blocking()

    def _accept_settings_selection(self, selection: "_TextualSelection") -> None:
        items = _selection_active_items(selection)
        if not items:
            self._cancel_active_selection()
            return
        item = items[min(max(self._active_selection_index, 0), len(items) - 1)]
        if getattr(item, "is_disabled", False) or getattr(item, "disabled_reason", None):
            reason = getattr(item, "disabled_reason", None) or "That settings option is disabled."
            self._append_system_notice(str(reason))
            return
        nested_view = None
        for action in getattr(item, "actions", ()) or ():
            nested_view = self._apply_settings_popup_event(selection, action) or nested_view
        if nested_view is not None:
            selection.view = nested_view
            selection.search_query = ""
            self._active_selection_index = int(getattr(nested_view, "initial_selected_idx", None) or 0)
            self._render_active_selection()
            return
        self._active_selection = None
        self.clear_command_popup()
        self._set_status("Ready")
        self._composer().focus()

    def _apply_settings_popup_event(self, selection: "_TextualSelection", event: object) -> object | None:
        kind = str(getattr(event, "kind", "") or "")
        payload = getattr(event, "payload", {}) or {}
        widget = selection.context or _SettingsPopupWidget(self.app_runtime, self)
        if kind == "OpenRealtimeAudioDeviceSelection":
            try:
                return open_realtime_audio_device_selection(widget, payload.get("kind"))
            except NotImplementedError:
                self._append_system_notice("Realtime audio device listing is not available in this runtime.")
                return None
        if kind == "PersistRealtimeAudioDeviceSelection":
            device_kind = payload.get("kind")
            name = payload.get("name")
            widget.set_realtime_audio_device_name(device_kind, name)
            self._append_system_notice(f"{getattr(device_kind, 'title', lambda: device_kind)()} set to {name or 'System default'}")
            return open_realtime_audio_restart_prompt(widget, device_kind)
        if kind == "RestartRealtimeAudioDevice":
            payload_map = dict(payload) if isinstance(payload, dict) else {}
            self.app_runtime.handle_app_event(AppEvent.of(kind, **payload_map))
            self._append_system_notice("Realtime audio restart requested.")
            return None
        if kind:
            payload_map = dict(payload) if isinstance(payload, dict) else {}
            self.app_runtime.handle_app_event(AppEvent.of(kind, **payload_map))
        return None

    def _apply_model_selection_item(self, selection: "_TextualSelection", item: object) -> object | None:
        for action in getattr(item, "actions", ()) or ():
            next_view = self._apply_model_popup_event(selection, action)
            if next_view is not None:
                return next_view
        return None

    def _apply_model_popup_event(self, selection: "_TextualSelection", event: object) -> object | None:
        if not isinstance(event, ModelPopupEvent):
            return None
        context = selection.context
        presets = selection.presets
        if event.kind == "update_model" and event.model is not None:
            self.app_runtime.handle_app_event(AppEvent.update_model(event.model))
            context.current_model = event.model
            self._mark_session_header_configured()
            self._set_status("Ready")
            return None
        if event.kind == "update_reasoning_effort":
            self.app_runtime.handle_app_event(AppEvent.update_reasoning_effort(event.effort))
            context.effective_reasoning_effort = event.effort
            return None
        if event.kind == "persist_model_selection" and event.model is not None:
            self.app_runtime.handle_app_event(AppEvent.persist_model_selection(event.model, event.effort))
            self._drain_runtime_notices()
            return None
        if event.kind == "open_all_models_popup":
            return open_all_models_popup(context, event.models).view
        if event.kind == "open_reasoning_popup" and event.model is not None:
            preset = next((candidate for candidate in presets if candidate.model == event.model), None)
            if preset is None:
                self._append_system_notice(f"Model details are not available for {event.model}.")
                return None
            result = open_reasoning_popup(context, preset)
            if result.view is not None:
                return result.view
            for followup in result.events:
                nested = self._apply_model_popup_event(selection, followup)
                if nested is not None:
                    return nested
            return None
        if event.kind == "open_plan_reasoning_scope_prompt" and event.model is not None:
            return open_plan_reasoning_scope_prompt(context, event.model, event.effort).view
        self._append_system_notice(f"Model selection action is not available: {event.kind}")
        return None

    def _submit_prompt(self, prompt: str) -> None:
        self._busy = True
        self._turn_started_at = time.monotonic()
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._reset_active_exec_state()
        self._append_block("you", prompt)
        self._set_status("Working")
        worker = threading.Thread(target=self._run_turn_worker, args=(prompt,), name="pycodex-textual-turn", daemon=True)
        self._turn_worker = worker
        worker.start()

    def _handle_local_slash_command(self, prompt: str) -> bool:
        trimmed = prompt.strip()
        if not trimmed.startswith("/"):
            return False
        command, _, arg = trimmed.partition(" ")
        normalized = command.lower()
        argument = arg.strip()
        if normalized in {"/help", "/?"}:
            self._append_system_notice(_slash_help_notice())
            self._set_status("Ready")
            return True
        if normalized in {"/transcript", "/history"}:
            self.action_open_transcript()
            return True
        if normalized in {"/raw-output", "/raw_output"}:
            normalized = "/raw"
        try:
            slash_command = SlashCommand.parse(normalized)
        except ValueError:
            self._append_system_notice(
                f"Unrecognized command '{command}'. Type '/' for a list of supported commands."
            )
            self._set_status("Ready")
            return True
        if slash_command in {SlashCommand.AGENT, SlashCommand.MULTI_AGENTS}:
            self._handle_agent_command(argument)
            return True
        if slash_command is SlashCommand.LOGOUT:
            self._handle_logout_command()
            return True
        if slash_command is SlashCommand.QUIT or slash_command is SlashCommand.EXIT:
            self._request_shutdown()
            return True
        if slash_command is SlashCommand.RESUME:
            self._handle_resume_command(argument)
            return True
        if slash_command is SlashCommand.FORK:
            self._handle_fork_command()
            return True
        if slash_command is SlashCommand.NEW:
            self._handle_new_command()
            return True
        if slash_command is SlashCommand.INIT:
            self._handle_init_command()
            return True
        if slash_command is SlashCommand.COMPACT:
            self._handle_compact_command()
            return True
        if slash_command is SlashCommand.REVIEW:
            self._handle_review_command(argument)
            return True
        if slash_command is SlashCommand.RENAME:
            self._handle_rename_command(argument)
            return True
        if slash_command is SlashCommand.PLAN:
            self._handle_plan_command(argument)
            return True
        if slash_command is SlashCommand.GOAL:
            self._handle_goal_command(argument)
            return True
        if slash_command in {SlashCommand.SIDE, SlashCommand.BTW}:
            self._handle_side_command(argument)
            return True
        if slash_command is SlashCommand.PERMISSIONS:
            self._open_permissions_picker()
            return True
        if slash_command is SlashCommand.SETTINGS:
            self._open_settings_picker()
            return True
        if slash_command is SlashCommand.KEYMAP:
            self._handle_keymap_command(argument)
            return True
        if slash_command is SlashCommand.MODEL:
            if argument:
                self.app_runtime.update_model(argument)
                self._mark_session_header_configured()
                self._append_system_notice(f"Model set to {argument}")
                self._set_status("Ready")
            else:
                self._open_model_picker()
            return True
        if slash_command is SlashCommand.STATUS:
            self._append_status_card()
            self._set_status("Ready")
            return True
        if slash_command is SlashCommand.CLEAR:
            self._handle_clear_command()
            return True
        if slash_command is SlashCommand.DIFF:
            self._handle_diff_command()
            return True
        if slash_command is SlashCommand.COPY:
            self._handle_copy_command()
            return True
        if slash_command is SlashCommand.MENTION:
            self._post_submit_composer_text = "@"
            self._set_status("Ready")
            return True
        if slash_command is SlashCommand.VIM:
            self._handle_vim_command()
            return True
        if slash_command is SlashCommand.ROLLOUT:
            self._handle_rollout_command()
            return True
        if slash_command is SlashCommand.PS:
            self._handle_ps_command()
            return True
        if slash_command is SlashCommand.STOP:
            self._handle_stop_command()
            return True
        if slash_command is SlashCommand.IDE:
            self._handle_ide_command(argument)
            return True
        if slash_command is SlashCommand.DEBUG_CONFIG:
            self._handle_debug_config_command()
            return True
        if slash_command is SlashCommand.TITLE:
            self._handle_title_setup_command()
            return True
        if slash_command is SlashCommand.STATUSLINE:
            self._handle_statusline_setup_command()
            return True
        if slash_command is SlashCommand.THEME:
            self._handle_deferred_slash_command(slash_command, "Theme picker is not available in the Textual shell yet.")
            return True
        if slash_command is SlashCommand.PETS:
            self._handle_deferred_slash_command(slash_command, "Terminal pets are not available in the Textual shell yet.")
            return True
        if slash_command is SlashCommand.MCP:
            detail = "verbose" if argument.strip().lower() == "verbose" else "summary"
            self._handle_deferred_slash_command(slash_command, f"MCP tool listing is recognized ({detail}) but MCP runtime is deferred in PyCodex.")
            return True
        if slash_command is SlashCommand.APPS:
            self._handle_deferred_slash_command(slash_command, "Apps management is recognized but deferred in PyCodex.")
            return True
        if slash_command is SlashCommand.PLUGINS:
            self._handle_deferred_slash_command(slash_command, "Plugin browsing is recognized but deferred in PyCodex.")
            return True
        if slash_command is SlashCommand.SKILLS:
            self._handle_deferred_slash_command(slash_command, "Skills menu is recognized but deferred in PyCodex.")
            return True
        if slash_command is SlashCommand.HOOKS:
            self._handle_deferred_slash_command(slash_command, "Lifecycle hooks are recognized but deferred in PyCodex.")
            return True
        if slash_command in {
            SlashCommand.ELEVATE_SANDBOX,
            SlashCommand.SANDBOX_READ_ROOT,
            SlashCommand.EXPERIMENTAL,
            SlashCommand.AUTO_REVIEW,
            SlashCommand.MEMORIES,
            SlashCommand.FEEDBACK,
            SlashCommand.PERSONALITY,
            SlashCommand.REALTIME,
            SlashCommand.TEST_APPROVAL,
            SlashCommand.MEMORY_DROP,
            SlashCommand.MEMORY_UPDATE,
        }:
            self._handle_deferred_slash_command(slash_command)
            return True
        if normalized in {"/raw", "/raw-output", "/raw_output"}:
            enabled = _parse_raw_output_arg(argument)
            if argument and enabled is None:
                self._append_system_notice(RAW_USAGE)
                self._set_status("Ready")
                return True
            if enabled is None:
                enabled = not _raw_output_mode(self.app_runtime)
            self.app_runtime.apply_raw_output_mode(enabled)
            self._append_system_notice(_raw_output_mode_notice(enabled))
            self._set_status("Ready")
            return True
        return False

    def _clear_submission_state(self, composer: "CodexComposerTextArea") -> None:
        restore_text = self._post_submit_composer_text
        self._post_submit_composer_text = None
        composer.clear_submission_state()
        if restore_text is not None:
            composer.text = restore_text
            composer._move_cursor_to_end()
            composer.focus()

    def _handle_copy_command(self) -> None:
        copy_last_agent_markdown_with(self.app_runtime.chat_widget, self.copy_to_clipboard)
        self._drain_chatwidget_history_notices()
        self._set_status("Ready")

    def _handle_logout_command(self) -> None:
        self.app_runtime.handle_app_event(AppEvent.logout())
        self._request_shutdown()

    def _handle_resume_command(self, argument: str) -> None:
        if argument:
            self.app_runtime.handle_app_event(AppEvent.of("ResumeSessionByIdOrName", id_or_name=argument))
            self._append_system_notice(f"Resume requested: {argument}")
        else:
            self.app_runtime.handle_app_event(AppEvent.of("OpenResumePicker"))
            if not self._open_resume_picker():
                self._append_system_notice("Resume picker is not available in the Textual shell yet.")
                self._set_status("Ready")
            return
        self._set_status("Ready")

    def _handle_keymap_command(self, argument: str) -> None:
        normalized = argument.strip().lower()
        if not normalized:
            self._open_keymap_picker()
            return
        if normalized == "debug":
            self._open_keymap_debug()
            return
        self._append_system_notice("Usage: /keymap [debug]")
        self._set_status("Ready")

    def _handle_goal_command(self, argument: str) -> None:
        thread_id = self.app_runtime.current_displayed_thread_id()
        if thread_id is None:
            self._append_system_notice(f"{GOAL_USAGE}\n{GOAL_USAGE_HINT}")
            self._set_status("Ready")
            return
        trimmed = argument.strip()
        if not trimmed:
            goal, error = _runtime_thread_goal_get(self.app_runtime, thread_id)
            self.app_runtime.handle_app_event(AppEvent.of("OpenThreadGoalMenu", thread_id=thread_id))
            self._apply_thread_goal_plan(open_thread_goal_menu_plan(goal, error))
            self._set_status("Ready")
            return
        normalized = trimmed.lower()
        if normalized == "clear":
            cleared, error = _runtime_thread_goal_clear(self.app_runtime, thread_id)
            self.app_runtime.handle_app_event(AppEvent.of("ClearThreadGoal", thread_id=thread_id))
            self._apply_thread_goal_plan(clear_thread_goal_plan(thread_id, cleared, error))
            self._set_status("Ready")
            return
        if normalized == "edit":
            goal, error = _runtime_thread_goal_get(self.app_runtime, thread_id)
            self.app_runtime.handle_app_event(AppEvent.of("OpenThreadGoalEditor", thread_id=thread_id))
            self._apply_thread_goal_plan(open_thread_goal_editor_plan(thread_id, goal, error))
            if self._goal_edit_prompt is None:
                self._set_status("Ready")
            return
        if normalized in {"pause", "resume"}:
            status = ThreadGoalStatus.Paused if normalized == "pause" else ThreadGoalStatus.Active
            response_goal, error = _runtime_thread_goal_set(self.app_runtime, thread_id, status=status)
            self.app_runtime.handle_app_event(AppEvent.of("SetThreadGoalStatus", thread_id=thread_id, status=status))
            self._apply_thread_goal_plan(set_thread_goal_status_plan(thread_id, status, error, response_goal))
            self._set_status("Ready")
            return
        objective = trimmed
        if not objective:
            self._append_system_notice(f"Goal objective must not be empty.\n{GOAL_USAGE}\n{GOAL_USAGE_HINT}")
            self._set_status("Ready")
            return
        existing_goal, read_error = _runtime_thread_goal_get(self.app_runtime, thread_id)
        response_goal = None
        set_error = None
        plan = set_thread_goal_objective_plan(
            thread_id,
            objective,
            ThreadGoalSetMode.ConfirmIfExists,
            existing_goal,
            read_error=read_error,
        )
        if plan.selection_view is None and read_error is None:
            response_goal, set_error = _runtime_thread_goal_set(
                self.app_runtime,
                thread_id,
                objective=objective,
                status=ThreadGoalStatus.Active,
            )
            plan = set_thread_goal_objective_plan(
                thread_id,
                objective,
                ThreadGoalSetMode.ConfirmIfExists,
                existing_goal,
                set_error=set_error,
                response_goal=response_goal,
            )
        self.app_runtime.handle_app_event(
            AppEvent.of(
                "SetThreadGoalObjective",
                thread_id=thread_id,
                objective=objective,
                mode=ThreadGoalSetMode.ConfirmIfExists,
            )
        )
        self._apply_thread_goal_plan(plan)
        if set_error is None and response_goal is not None and self._maybe_start_goal_continuation(response_goal):
            return
        self._set_status("Ready")

    def _maybe_start_goal_continuation(self, goal: ThreadGoal | None) -> bool:
        if goal is None or self._busy:
            _textual_timing_trace("goal_textual_continue_skipped", reason="missing_goal_or_busy", busy=self._busy)
            return False
        method = getattr(self.app_runtime.active_thread_runtime, "goal_continuation_op", None)
        if not callable(method):
            _textual_timing_trace("goal_textual_continue_skipped", reason="missing_runtime_method")
            return False
        try:
            op = method(goal)
        except Exception as exc:
            _textual_timing_trace("goal_textual_continue_failed", error=str(exc))
            self._append_system_notice(f"Failed to continue goal: {exc}")
            return False
        if op is None:
            _textual_timing_trace("goal_textual_continue_skipped", reason="runtime_returned_none")
            return False
        _textual_timing_trace(
            "goal_textual_continue_requested",
            objective=getattr(goal, "objective", None),
            status=getattr(getattr(goal, "status", None), "value", getattr(goal, "status", None)),
        )
        self._submit_app_command(op)
        return True

    def _apply_thread_goal_plan(self, plan: ThreadGoalActionPlan) -> None:
        if plan.selection_view is not None:
            self._active_selection = _TextualSelection(kind="goal", view=_thread_goal_selection_view(plan))
            self._active_selection_index = _initial_selection_index(self._active_selection)
            self._render_active_selection()
            self._set_status("Goal: up/down move; Enter select; Esc/q cancel")
            return
        if plan.actions == ("show_goal_summary",):
            goal, error = _runtime_thread_goal_get(self.app_runtime, plan.thread_id)
            if error is not None:
                self._append_system_notice(str(error))
            elif goal is not None:
                self._append_block("status", _thread_goal_summary_text(goal))
            else:
                self._append_system_notice(f"{GOAL_USAGE}\nNo goal is currently set.")
            return
        if plan.actions == ("show_goal_edit_prompt",):
            goal, error = _runtime_thread_goal_get(self.app_runtime, plan.thread_id)
            if error is not None:
                self._append_system_notice(str(error))
                self._set_status("Ready")
                return
            if goal is None:
                self._append_system_notice("No goal to edit.\nCreate a goal before editing it.")
                self._set_status("Ready")
                return
            self._goal_edit_prompt = _GoalEditPromptState(
                thread_id=plan.thread_id,
                status=_edited_goal_status(goal.status),
                token_budget=goal.token_budget,
            )
            self._post_submit_composer_text = goal.objective
            composer = self._composer()
            composer.text = goal.objective
            composer.focus()
            self._set_status("Edit goal: type a goal objective and press Enter")
            return
        if plan.message:
            if plan.hint:
                self._append_system_notice(f"{plan.message}\n{plan.hint}")
            else:
                self._append_system_notice(plan.message)
        else:
            self._append_system_notice("Goal updated.")

    def _handle_side_command(self, argument: str) -> None:
        parent_thread_id = self.app_runtime.current_displayed_thread_id()
        if parent_thread_id is None:
            self._append_system_notice("Side conversations require an active saved session.")
            self._set_status("Ready")
            return
        self.app_runtime.handle_app_event(
            AppEvent.start_side(parent_thread_id=parent_thread_id, user_message=argument or None)
        )
        self._append_system_notice("Side conversation requested.")
        self._set_status("Ready")

    def _handle_ide_command(self, argument: str) -> None:
        normalized = argument.strip().lower()
        if normalized and normalized not in {"on", "off", "status"}:
            self._append_system_notice("Usage: /ide [on|off|status]")
            self._set_status("Ready")
            return
        self.app_runtime.handle_app_event(AppEvent.of("IdeContextCommand", argument=normalized))
        if normalized == "off":
            self._append_system_notice("IDE context is off.")
        elif normalized == "status":
            self._append_system_notice("IDE context status is not connected.")
        else:
            self._append_system_notice("IDE context is not connected.")
        self._set_status("Ready")

    def _handle_debug_config_command(self) -> None:
        config = getattr(self.app_runtime, "config", None)
        lines = [
            "Debug config",
            f"cwd: {_runtime_cwd(self.app_runtime)}",
            f"model: {_runtime_display_model(self.app_runtime)}",
            f"config: {type(config).__name__ if config is not None else '<none>'}",
        ]
        self._append_block("status", "\n".join(lines))
        self._set_status("Ready")

    def _handle_title_setup_command(self) -> None:
        items = ", ".join(str(item) for item in _runtime_terminal_title_items(self.app_runtime))
        self._append_system_notice(f"Terminal title items: {items or '<none>'}")
        self._set_status("Ready")

    def _handle_statusline_setup_command(self) -> None:
        items = ", ".join(str(item) for item in _runtime_status_line_items(self.app_runtime))
        self._append_system_notice(f"Status line items: {items or '<none>'}")
        self._set_status("Ready")

    def _handle_deferred_slash_command(self, command: SlashCommand, message: str | None = None) -> None:
        self.app_runtime.handle_app_event(AppEvent.of("SlashCommandRecognized", command=command.command()))
        self._append_system_notice(message or f"/{command.command()} is recognized but not available in the Textual shell yet.")
        self._set_status("Ready")

    def _handle_fork_command(self) -> None:
        self.app_runtime.handle_app_event(AppEvent.of("ForkCurrentSession"))
        self._append_system_notice("Fork current session requested.")
        self._set_status("Ready")

    def _apply_startup_session_action(self) -> None:
        action = getattr(self.app_runtime, "startup_session_action", None)
        if action == "fork" and getattr(self.app_runtime, "startup_session_id", None):
            target = SessionPickerAction.FORK.selection(None, str(self.app_runtime.startup_session_id)).target
            forked = self.app_runtime.fork_startup_session_target(target) if target is not None else False
            self._mark_session_header_configured()
            if forked:
                self._append_startup_replay_history()
                self._drain_runtime_notices()
                self._append_system_notice(
                    f"Forked session from thread {self.app_runtime.startup_session_id} as {self.app_runtime.startup_session_forked_thread_id}."
                )
            else:
                self._append_system_notice(f"Fork requested: {self.app_runtime.startup_session_id}")
            self.app_runtime.startup_session_action = None
            self._set_ready_after_startup_if_idle()
            return
        if action == "resume" and getattr(self.app_runtime, "startup_session_id", None):
            self.app_runtime.handle_app_event(
                AppEvent.of("ResumeSessionByIdOrName", id_or_name=str(self.app_runtime.startup_session_id))
            )
            self._append_system_notice(f"Resume requested: {self.app_runtime.startup_session_id}")
            self.app_runtime.startup_session_action = None
            self._set_ready_after_startup_if_idle()
            return
        if action == "fork" and not getattr(self.app_runtime, "startup_session_last", False):
            if self._open_fork_picker():
                self.app_runtime.startup_session_action = None
                return
            self._append_system_notice("Fork picker is not available in the Textual shell yet.")
            self.app_runtime.startup_session_action = None
        elif action == "resume" and not getattr(self.app_runtime, "startup_session_last", False):
            if self._open_resume_picker():
                self.app_runtime.startup_session_action = None
                return
            self._append_system_notice("Resume picker is not available in the Textual shell yet.")
            self.app_runtime.startup_session_action = None
        self._set_ready_after_startup_if_idle()

    def _handle_new_command(self) -> None:
        self.app_runtime.handle_app_event(AppEvent.new_session())
        self._blocks.clear()
        self._history_projection_next_index = 0
        self._reset_insert_history_reflow_state()
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._session_header_configured = False
        self._session_header_block_index = None
        self._ensure_session_header_block()
        self._refresh_transcript()
        self._append_startup_notices()
        self._history_projection_next_index = len(self._blocks)
        self._set_status("Ready")

    def _handle_init_command(self) -> None:
        init_target = _runtime_cwd(self.app_runtime) / DEFAULT_AGENTS_MD_FILENAME
        if init_target.exists():
            self._append_system_notice(
                f"{DEFAULT_AGENTS_MD_FILENAME} already exists here. Skipping /init to avoid overwriting it."
            )
            self._set_status("Ready")
            return
        self._submit_prompt(_INIT_PROMPT)

    def _handle_compact_command(self) -> None:
        self._submit_app_command(AppCommand.compact())

    def _handle_review_command(self, argument: str) -> None:
        if not argument:
            self._open_review_picker()
            return
        self._submit_app_command(AppCommand.review(ReviewTarget.custom(argument)))

    def _handle_review_custom_prompt_submission(self, prompt: str) -> None:
        action = custom_review_prompt_action(prompt)
        self._review_custom_prompt_active = False
        if action is None:
            self._set_status("Ready")
            return
        self._apply_review_popup_action(_TextualSelection(kind="review", view=open_review_popup(_runtime_cwd(self.app_runtime))), action)

    def _handle_rename_command(self, argument: str) -> None:
        if argument:
            self._submit_thread_name(argument)
            return
        self._rename_prompt_active = True
        composer = self._composer()
        existing_name = _runtime_thread_name(self.app_runtime) or ""
        composer.text = existing_name
        self._post_submit_composer_text = existing_name
        composer._move_cursor_to_end()
        composer.focus()
        if existing_name:
            self._append_system_notice("Rename thread")
        else:
            self._append_system_notice("Name thread")
        self._set_status("Type a name and press Enter")

    def _handle_rename_prompt_submission(self, text: str) -> None:
        self._rename_prompt_active = False
        self._submit_thread_name(text)

    def _handle_goal_edit_prompt_submission(self, text: str) -> None:
        state = self._goal_edit_prompt
        self._goal_edit_prompt = None
        if state is None:
            self._set_status("Ready")
            return
        objective = text.strip()
        if not objective:
            self._append_system_notice(f"Goal objective must not be empty.\n{GOAL_USAGE}\n{GOAL_USAGE_HINT}")
            self._set_status("Ready")
            return
        response_goal, error = _runtime_thread_goal_set(
            self.app_runtime,
            state.thread_id,
            objective=objective,
            status=state.status,
            token_budget=state.token_budget,
        )
        self.app_runtime.handle_app_event(
            AppEvent.of(
                "SetThreadGoalObjective",
                thread_id=state.thread_id,
                objective=objective,
                mode=ThreadGoalSetMode.UpdateExisting,
            )
        )
        self._apply_thread_goal_plan(
            set_thread_goal_objective_plan(
                state.thread_id,
                objective,
                UpdateExistingMode(state.status, state.token_budget),
                set_error=error,
                response_goal=response_goal,
            )
        )
        if error is None and response_goal is not None and self._maybe_start_goal_continuation(response_goal):
            return
        self._set_status("Ready")

    def _submit_thread_name(self, text: str) -> None:
        name = normalize_thread_name(text)
        if name is None:
            self._append_system_notice("Thread name cannot be empty.")
            self._set_status("Ready")
            return
        self._submit_app_command(AppCommand.set_thread_name(name), expect_turn_completed=False)

    def _handle_plan_command(self, argument: str) -> None:
        mask = _runtime_plan_mask(self.app_runtime)
        if mask is None:
            self._append_system_notice("Plan mode unavailable right now.")
            self._set_status("Ready")
            return
        _apply_textual_collaboration_mask(self.app_runtime, mask)
        self._mark_session_header_configured()
        if not argument:
            self._append_system_notice("Switched to Plan mode.")
            self._set_status("Plan mode")
            return
        self._prompt_history.record_local_submission(HistoryEntry.new(argument))
        self._submit_plan_prompt(argument, mask)

    def _submit_plan_prompt(self, prompt: str, mask: Any) -> None:
        model = _runtime_display_model(self.app_runtime)
        effort = _mask_reasoning_effort(mask)
        collaboration_mode = CollaborationMode(
            mode=mask.mode,
            settings=Settings(
                model=model,
                reasoning_effort=effort,
                developer_instructions=_mask_developer_instructions(mask),
            ),
        )
        op = AppCommand.user_turn(
            [SubmissionUserInput("Text", {"text": prompt, "text_elements": ()})],
            cwd=_runtime_cwd(self.app_runtime),
            approval_policy=_runtime_permission_value(self.app_runtime, "approval_policy"),
            active_permission_profile=_active_permission_profile(self.app_runtime),
            model=model,
            effort=effort,
            summary=None,
            service_tier=_runtime_permission_value(self.app_runtime, "service_tier"),
            final_output_json_schema=None,
            collaboration_mode=collaboration_mode,
            personality=None,
        )
        self._busy = True
        self._turn_started_at = time.monotonic()
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._reset_active_exec_state()
        self._append_block("you", prompt)
        self._set_status("Working")
        self._submit_app_command(op)

    def _handle_clear_command(self) -> None:
        self.app_runtime.handle_app_event(AppEvent.clear_ui())
        self._blocks.clear()
        self._history_projection_next_index = 0
        self._reset_insert_history_reflow_state()
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._session_header_configured = _runtime_session_header_configured_at_startup(self.app_runtime)
        self._session_header_block_index = None
        self._ensure_session_header_block()
        self._refresh_transcript()
        self._set_status("Ready")

    def _handle_rollout_command(self) -> None:
        path = getattr(self.app_runtime, "rollout_path", None)
        if path is not None:
            self._append_system_notice(f"Current rollout path: {Path(path)}")
        else:
            self._append_system_notice("Rollout path is not available yet.")
        self._set_status("Ready")

    def _handle_vim_command(self) -> None:
        enabled = not _runtime_vim_enabled(self.app_runtime)
        _set_textual_vim_enabled(self.app_runtime, enabled)
        self._append_system_notice("Vim mode enabled." if enabled else "Vim mode disabled.")
        self._set_status("Ready")

    def _handle_ps_command(self) -> None:
        processes = _runtime_unified_exec_processes(self.app_runtime)
        cell = new_unified_exec_processes_output(processes)
        text = "\n".join(_line_text(line) for line in cell.display_lines(100)).strip()
        self._append_block("status", text)
        self._set_status("Ready")

    def _handle_stop_command(self) -> None:
        self._submit_app_command(AppCommand.clean_background_terminals(), expect_turn_completed=False)
        lifecycle = getattr(self.app_runtime.chat_widget, "command_lifecycle", None)
        if lifecycle is not None:
            try:
                lifecycle.unified_exec_processes.clear()
                lifecycle.sync_unified_exec_footer()
            except AttributeError:
                pass
        self._append_system_notice("Stopping all background terminals.")

    def _handle_diff_command(self) -> None:
        self.app_runtime.chat_widget.add_diff_in_progress()
        block = self._append_block("diff", "Computing diff...")
        self._set_status("Ready")
        runner = _workspace_command_runner(self.app_runtime)
        if runner is None:
            self._finish_diff_block(block, "Failed to compute diff: workspace command runner unavailable")
            return
        cwd = _runtime_cwd(self.app_runtime)

        def worker() -> None:
            try:
                is_git_repo, diff_text = asyncio.run(get_git_diff(runner, cwd))
                text = diff_text if is_git_repo else "`/diff` — _not inside a git repository_"
            except BaseException as exc:
                text = f"Failed to compute diff: {exc}"
            self.call_from_thread(self._finish_diff_block, block, text)

        threading.Thread(target=worker, name="pycodex-textual-diff", daemon=True).start()

    def _finish_diff_block(self, block: "_TranscriptBlock", text: str) -> None:
        self.app_runtime.handle_app_event(AppEvent.diff_result(text))
        block.text = str(text)
        self._refresh_transcript()
        self._set_status("Ready")

    def _run_turn_worker(self, prompt: str) -> None:
        try:
            event_stream = self.app_runtime.submit_user_turn(prompt)
            self._consume_turn_event_stream(event_stream)
        except BaseException as exc:
            self.call_from_thread(self._finish_turn, 1, str(exc), True)

    def _submit_app_command(self, op: AppCommand, *, expect_turn_completed: bool = True) -> None:
        self._busy = True
        self._turn_started_at = time.monotonic()
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._reset_active_exec_state()
        self._set_status("Working")
        worker = threading.Thread(
            target=self._run_app_command_worker,
            args=(op, expect_turn_completed),
            name="pycodex-textual-op",
            daemon=True,
        )
        self._turn_worker = worker
        worker.start()

    def _run_app_command_worker(self, op: AppCommand, expect_turn_completed: bool) -> None:
        try:
            event_stream = self.app_runtime.submit_op(op)
            self._consume_turn_event_stream(event_stream, expect_turn_completed=expect_turn_completed)
        except BaseException as exc:
            self.call_from_thread(self._finish_turn, 1, str(exc), True)

    def _consume_turn_event_stream(self, event_stream: Any, *, expect_turn_completed: bool = True) -> None:
        while True:
            event = event_stream.next_event(timeout=0.1)
            if event is None:
                if _event_stream_closed(event_stream):
                    if expect_turn_completed:
                        self.call_from_thread(
                            self._finish_turn,
                            1,
                            "active thread event stream closed before turn completed",
                            True,
                        )
                    else:
                        self.call_from_thread(self._finish_turn, 0, "")
                    return
                continue
            self.call_from_thread(self._handle_server_notification, event)
            if event.kind == "TurnCompleted":
                return

    def _handle_server_notification(self, event: ServerNotification) -> None:
        kind = str(event.kind)
        if kind == "ExecApprovalRequested":
            self._open_exec_approval_picker(event)
            return
        self.app_runtime.handle_notification(event)
        self._drain_runtime_notices()
        if kind == "TurnStarted":
            self._active_turn_id = _notification_turn_id(event)
            self._active_retry_status = None
            self._set_status("Working")
        elif kind == "ResponseStarted":
            self._set_status("Thinking")
        elif kind == "AgentMessageDelta":
            delta = _event_delta(event)
            if delta:
                self._active_retry_status = None
                self._append_agent_delta(delta)
                if self._busy:
                    self._set_status("Working")
        elif kind == "ReasoningSummaryTextDelta":
            delta = _event_delta(event)
            if delta:
                self._active_retry_status = None
            _trace_reasoning_projection(kind, source="summary_delta", displayed=True)
            self._append_reasoning_delta(delta)
        elif kind == "ReasoningSummaryPartAdded":
            _trace_reasoning_projection(kind, source="summary_part", displayed=True)
            self._push_reasoning_section_break()
        elif kind == "ReasoningTextDelta":
            displayed = _show_raw_agent_reasoning(self.app_runtime)
            _trace_reasoning_projection(kind, source="raw_delta", displayed=displayed)
            if displayed:
                self._active_retry_status = None
                self._append_reasoning_delta(_event_delta(event))
        elif kind == "ThreadNameUpdated":
            self._mark_session_header_configured()
        elif kind in {"SessionConfigured", "ThreadSessionConfigured", "ThreadSession"}:
            self._mark_session_header_configured()
        elif kind == "ItemStarted":
            self._append_item_started(event)
        elif kind == "ItemCompleted":
            self._append_item_completed(event)
        elif kind == "McpServerStatusUpdated":
            self._append_mcp_status()
        elif kind == "ThreadTokenUsageUpdated":
            self.app_runtime.chat_widget.set_token_info(
                token_usage_info_from_app_server(_payload_field(event.payload, "token_usage", None))
            )
            if not self._busy:
                self._set_status("Ready")
        elif kind == "Error":
            self._handle_error_notification(event)
        elif kind == "TurnCompleted":
            turn_id = _notification_turn_id(event)
            if turn_id is not None and self._active_turn_id is not None and turn_id != self._active_turn_id:
                return
            self._active_turn_id = None
            self._active_retry_status = None
            self._handle_turn_completed(event)

    def _handle_turn_completed(self, event: ServerNotification) -> None:
        code = 0
        message = ""
        turn = _payload_field(event.payload, "turn", {})
        status = _payload_field(turn, "status", "")
        if str(status) == "Failed":
            error = _payload_field(turn, "error", {})
            code = int(_payload_field(error, "exit_code", 1) or 1)
            message = str(_payload_field(error, "message", "") or "")
        elif str(status) == "Interrupted":
            message = "Interrupted"
        self._finish_reasoning_block()
        self._finish_turn(code, message, code != 0)

    def _handle_error_notification(self, event: ServerNotification) -> None:
        if not bool(_payload_field(event.payload, "will_retry", False)):
            error = _payload_field(event.payload, "error", {})
            message = str(_payload_field(error, "message", "") or "")
            if message:
                self._append_system_notice(message)
            return
        turn_id = _notification_turn_id(event)
        if not self._busy or (
            turn_id is not None and self._active_turn_id is not None and turn_id != self._active_turn_id
        ):
            return

        # Rust codex-tui::chatwidget::protocol routes retryable
        # ServerNotification::Error to on_stream_error: a live status update,
        # not a history cell.  Textual mirrors that visible contract here.
        error = _payload_field(event.payload, "error", {})
        message = str(_payload_field(error, "message", "") or "")
        details = _payload_field(error, "additional_details", None)
        if message:
            self._active_retry_status = _RetryStatus(message=message, details=None if details is None else str(details))
            self._set_retry_status(self._active_retry_status)

    def _reset_active_exec_state(self) -> None:
        self._active_exec_block = None
        self._active_exec_rows.clear()

    def _finish_turn(self, code: int = 0, message: str = "", is_error: bool = False) -> None:
        if message:
            if is_error:
                self._append_error_notice(message)
            elif not self._active_codex_block:
                self._append_block("codex", message)
        self.exit_code = code if code else self.exit_code
        self._busy = False
        self._active_turn_id = None
        self._active_retry_status = None
        self._active_codex_block = None
        self._active_reasoning_block = None
        self._active_exec_rows.clear()
        runtime_thread_id = getattr(self.app_runtime.active_thread_runtime, "thread_id", None)
        if runtime_thread_id is None or str(runtime_thread_id) == self.app_runtime.routing_state.active_thread_id:
            configure_app_runtime_thread_identity(self.app_runtime, self.app_runtime.active_thread_runtime)
        composer = self._composer()
        composer.focus()
        self._dispatch_completed_history_to_insert_history_cell()
        self._set_status("Ready")
        self._submit_next_queued_prompt()

    def _submit_next_queued_prompt(self) -> None:
        if self._busy or not self._queued_prompts:
            return
        next_prompt = self._queued_prompts.pop(0)
        if self._handle_local_slash_command(next_prompt):
            return
        self._prompt_history.record_local_submission(HistoryEntry.new(next_prompt))
        self._submit_prompt(next_prompt)

    def _interrupt_turn(self) -> None:
        try:
            from .app_command import AppCommand

            self.app_runtime.submit_op(AppCommand.interrupt())
            self._set_status("Interrupting")
        except Exception as exc:
            self._append_system_notice(f"Interrupt failed: {exc}")

    def _request_shutdown(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        try:
            self._set_status("Shutting down...")
            if self._busy:
                self._interrupt_turn()
            self.app_runtime.shutdown_current_thread(timeout_seconds=SHUTDOWN_FIRST_EXIT_TIMEOUT)
        finally:
            # Rust codex-tui disables input and exposes the shutdown-in-progress
            # composer surface before the terminal exits. Let Textual flush the
            # status update once so ConPTY/manual sessions can observe it.
            self.set_timer(0.05, lambda: self.exit(0))

    def _tick_status(self) -> None:
        self._pump_app_server_events()
        if self._consume_composer_control_shortcuts():
            return
        if not self._busy:
            return
        elapsed = int(time.monotonic() - self._turn_started_at)
        if self._active_retry_status is not None:
            self._set_retry_status(self._active_retry_status, elapsed_seconds=elapsed)
            return
        status = self.app_runtime.chat_widget.run_state_status_text()
        if self._reasoning_buffer:
            header = extract_first_bold(self._reasoning_buffer)
            if header:
                status = header
        self._set_active_status(status, elapsed_seconds=elapsed)

    def _set_ready_after_startup_if_idle(self) -> None:
        if self._last_mcp_status_header:
            return
        if self._shutdown_requested or self._busy or self._active_retry_status is not None:
            return
        try:
            current_status = str(self.query_one("#status-line", Static).renderable)
        except NoMatches:
            return
        if "Shutting down" in current_status or "Raw output mode" in current_status:
            return
        self._set_status("Ready")

    def _consume_composer_control_shortcuts(self) -> bool:
        try:
            composer = self._composer()
        except NoMatches:
            return False
        text = str(getattr(composer, "text", "") or "")
        if "\x14" not in text:
            return False
        if not _app_keymap_accepts_control_character(self.app_runtime, "open_transcript", "\x14"):
            return False
        composer.text = text.replace("\x14", "")
        _textual_timing_trace("textual_composer_control_shortcut", shortcut="ctrl+t", source="composer_text")
        self.action_open_transcript()
        return True

    def _append_agent_delta(self, delta: str) -> None:
        if not delta:
            return
        self._hide_active_exec_block()
        if self._active_codex_block is None:
            self._active_codex_block = self._append_block("codex", "")
        self._active_codex_block.text += delta
        self.app_runtime.chat_widget.turn.record_agent_markdown(self._active_codex_block.text)
        self._refresh_transcript()

    def _append_reasoning_delta(self, delta: str) -> None:
        if not delta:
            return
        self._reasoning_buffer += delta
        header = extract_first_bold(self._reasoning_buffer)
        if not self._has_running_exec_rows():
            self._set_status(f"Thinking: {header}" if header else "Thinking")

    def _push_reasoning_section_break(self) -> None:
        if self._reasoning_buffer:
            self._reasoning_full_buffer += self._reasoning_buffer
            self._reasoning_full_buffer += "\n\n"
            self._reasoning_buffer = ""

    def _finish_reasoning_block(self) -> None:
        text = (self._reasoning_full_buffer + self._reasoning_buffer).strip()
        if not text:
            return
        cell = new_reasoning_summary_block(text, _runtime_cwd(self.app_runtime))
        display_text = "\n".join(_line_text(line) for line in cell.display_lines(self._exec_cell_render_width())).strip()
        if not display_text:
            self._reasoning_buffer = ""
            self._reasoning_full_buffer = ""
            return
        if self._active_reasoning_block is None:
            self._active_reasoning_block = self._append_block("reasoning", display_text)
        else:
            self._active_reasoning_block.text = display_text
            self._refresh_transcript()
        self._reasoning_buffer = ""
        self._reasoning_full_buffer = ""

    def _append_item_started(self, event: ServerNotification) -> None:
        item = _event_item(event)
        if _item_kind(item) == "CommandExecution":
            command = str(_payload_field(item, "command", "") or "").strip()
            if command:
                # Rust renders command execution as live exec-cell/status
                # state for the current turn. Do not append a transcript
                # status block for every tool start; that causes the Textual
                # projection to scroll downward while tools run.
                call_id = str(_payload_field(item, "id", command) or command)
                self._active_exec_rows[call_id] = _render_command_execution_item_text(
                    item,
                    active=True,
                    width=self._exec_cell_render_width(),
                )
                self._refresh_active_exec_block()
        elif _item_kind(item) == "Reasoning":
            if not self._has_running_exec_rows():
                self._set_status("Thinking")

    def _append_item_completed(self, event: ServerNotification) -> None:
        item = _event_item(event)
        kind = _item_kind(item)
        if kind == "AgentMessage":
            text = _agent_message_item_text(item)
            if not text:
                return
            self._hide_active_exec_block()
            if self._active_codex_block is None:
                self._active_codex_block = self._append_block("codex", text)
            elif self._active_codex_block.text != text:
                self._active_codex_block.text = text
                self._refresh_transcript()
            self.app_runtime.chat_widget.turn.record_agent_markdown(text)
            return
        if kind == "Reasoning":
            has_summary = _reasoning_item_has_summary(item)
            has_content = _reasoning_item_has_content(item)
            text = _reasoning_item_text(item, show_summary=True)
            _trace_reasoning_projection(
                "ItemCompleted",
                source="completed_reasoning",
                displayed=bool(text),
                summary_present=has_summary,
                content_present=has_content,
            )
            if text:
                self._reasoning_buffer = text
                self._finish_reasoning_block()
            return
        if kind != "CommandExecution":
            return
        command = str(_payload_field(item, "command", "") or "").strip()
        call_id = str(_payload_field(item, "id", command) or command)
        if command:
            self._active_exec_rows[call_id] = _render_command_execution_item_text(
                item,
                active=False,
                width=self._exec_cell_render_width(),
            )
        self._refresh_active_exec_block()

    def _refresh_active_exec_block(self) -> None:
        if not self._active_exec_rows:
            return
        rows = list(self._active_exec_rows.values())
        lines = _compact_live_exec_lines(rows)
        text = "\n".join(lines)
        running = [row for row in rows if row.startswith("\u2022 Running ")]
        if running:
            self._set_status(running[-1].removeprefix("\u2022 "))
        elif self._busy:
            self._set_status("Working")
        if self._active_exec_block is None:
            self._active_exec_block = self._append_block("exec", text)
        else:
            self._active_exec_block.text = text
            self._refresh_transcript()

    def _has_running_exec_rows(self) -> bool:
        return any(row.startswith("\u2022 Running ") for row in self._active_exec_rows.values())

    def _exec_cell_render_width(self) -> int:
        width = getattr(getattr(self, "size", None), "width", None)
        try:
            return max(int(width or 100) - 4, 20)
        except (TypeError, ValueError):
            return 100

    def _hide_active_exec_block(self) -> None:
        block = self._active_exec_block
        if block is not None:
            with contextlib.suppress(ValueError):
                self._blocks.remove(block)
            self._active_exec_block = None
            self._refresh_transcript()
        self._active_exec_rows.clear()

    def _append_mcp_status(self) -> None:
        model = getattr(self.app_runtime.chat_widget, "mcp_startup", None)
        if model is None:
            return
        header = str(getattr(model, "status_header", "") or "")
        if header:
            if header != self._last_mcp_status_header:
                self._last_mcp_status_header = header
                self._append_system_notice(header)
            self._set_status(header)
        elif self._last_mcp_status_header and not self._busy:
            self._last_mcp_status_header = ""
            self._set_status("Ready")
        for warning in list(getattr(model, "warnings", []) or []):
            warning_text = str(warning)
            if warning_text in self._seen_mcp_warnings:
                continue
            self._append_system_notice(warning_text)

    def _pump_app_server_events(self) -> None:
        """Poll Rust ``app::app_server_events`` from the Textual product loop.

        Rust ``App::run`` selects over terminal input, active-thread events, and
        app-server events.  Startup MCP status belongs to that app-server lane,
        so Textual must drain it even before the first user turn is submitted.
        """

        next_event = getattr(self.app_runtime.active_thread_runtime, "next_app_server_event", None)
        if not callable(next_event):
            return
        processed = 0
        while processed < 64:
            event = next_event(timeout=0)
            if event is None:
                break
            processed += 1
            self.app_runtime.handle_app_server_event(event)
            self._drain_runtime_notices()
            self._append_mcp_status()
        if processed and not self._busy:
            self._set_status("Ready")

    def _append_status_card(self) -> None:
        rate_limits = _runtime_rate_limit_snapshots(self.app_runtime)
        should_refresh = _runtime_should_refresh_rate_limits(self.app_runtime)
        request_id = self.app_runtime.next_status_rate_limit_request_id() if should_refresh else None
        output, handle = new_status_output_with_rate_limits_handle(
            model_name=_runtime_display_model(self.app_runtime),
            model_details=_runtime_model_details(self.app_runtime),
            directory=self.app_runtime.cwd,
            permissions=_runtime_permissions_label(self.app_runtime),
            agents_summary=_runtime_agents_summary(self.app_runtime),
            collaboration_mode=_runtime_collaboration_mode_label(self.app_runtime),
            show_chatgpt_usage_link=_runtime_show_chatgpt_usage_link(self.app_runtime),
            account=_runtime_status_account_display(self.app_runtime),
            thread_name=_runtime_thread_name(self.app_runtime),
            session_id=self.app_runtime.current_displayed_thread_id() or self.app_runtime.thread_id,
            token_usage=_runtime_status_token_usage(self.app_runtime),
            rate_limits=rate_limits,
            refreshing_rate_limits=False,
        )
        lines = output.display_lines(100)
        text = "\n".join(_line_text(line) for line in lines).strip()
        self._append_block("status", text, rich_lines=lines)
        block_index = len(self._blocks) - 1
        if request_id is not None:
            self.app_runtime.register_status_rate_limit_handle(request_id, handle)
            self.app_runtime.handle_app_event(AppEvent.refresh_rate_limits(RateLimitRefreshOrigin.status_command(request_id)))
            refreshed_lines = output.display_lines(100)
            refreshed_text = "\n".join(_line_text(line) for line in refreshed_lines).strip()
            if 0 <= block_index < len(self._blocks):
                self._blocks[block_index] = _TranscriptBlock("status", refreshed_text, rich_lines=refreshed_lines)
                self._refresh_transcript()

    def _drain_runtime_notices(self) -> None:
        chat_widget = self.app_runtime.chat_widget
        info_messages = list(getattr(chat_widget, "info_messages", []) or [])
        error_messages = list(getattr(chat_widget, "error_messages", []) or [])
        if hasattr(chat_widget, "info_messages"):
            chat_widget.info_messages.clear()
        if hasattr(chat_widget, "error_messages"):
            chat_widget.error_messages.clear()
        for message, hint in info_messages:
            text = str(message)
            if hint:
                text = f"{text} {hint}"
            self._append_system_notice(text)
        for message in error_messages:
            self._append_system_notice(str(message))
        self._drain_chatwidget_history_notices()

    def _append_startup_replay_history(self) -> None:
        take = getattr(self.app_runtime, "take_startup_session_replay_history", None)
        if not callable(take):
            return
        for item in take():
            label, text = _startup_replay_block(item)
            if text:
                self._append_block(label, text)

    def _drain_chatwidget_history_notices(self) -> None:
        chat_widget = self.app_runtime.chat_widget
        history = getattr(chat_widget, "history", None)
        if not history:
            return
        remaining: list[Any] = []
        for item in list(history):
            if isinstance(item, dict) and item.get("kind") in {"info", "warning", "error"}:
                text = str(item.get("message", ""))
                hint = item.get("hint")
                if hint:
                    text = f"{text} {hint}"
                if text:
                    self._append_system_notice(text)
            else:
                remaining.append(item)
        try:
            history[:] = remaining
        except TypeError:
            setattr(chat_widget, "history", remaining)

    def _append_system_notice(self, text: str) -> None:
        notice = str(text)
        if notice.startswith("MCP ") or notice.startswith("MCP client "):
            if notice in self._seen_mcp_warnings:
                return
            self._seen_mcp_warnings.add(notice)
        self._append_block("status", notice)

    def _append_error_notice(self, text: str) -> None:
        self._append_block("error", str(text))

    def _append_block(self, label: str, text: str, *, rich_lines: Iterable[Any] | None = None) -> "_TranscriptBlock":
        block = _TranscriptBlock(label=label, text=str(text), rich_lines=tuple(rich_lines) if rich_lines is not None else None)
        self._blocks.append(block)
        self._refresh_transcript()
        return block

    def _refresh_transcript(self) -> None:
        log = self._transcript_log()
        log.clear()
        for index, block in enumerate(self._blocks):
            if index < self._terminal_scrollback_projected_until and _block_is_terminal_scrollback_history_cell(block):
                continue
            log.write(block.render(), expand=True, shrink=True)
        log.refresh(layout=True)
        self.refresh(layout=True)

    def _dispatch_completed_history_to_insert_history_cell(self) -> None:
        if self._history_projection_next_index >= len(self._blocks):
            return
        blocks = self._blocks[self._history_projection_next_index :]
        self._history_projection_next_index = len(self._blocks)
        lines: list[str] = []
        for block in blocks:
            if not _block_is_terminal_scrollback_history_cell(block):
                continue
            lines.extend(block.terminal_history_lines())
            lines.append("")
        while lines and not lines[-1]:
            lines.pop()
        if not lines:
            return
        plan = self.app_runtime.handle_app_event(
            AppEvent.insert_history_cell(
                {
                    "kind": "completed_turn",
                    "lines": tuple(lines),
                }
            )
        )
        self._handle_insert_history_cell_dispatch_plan(plan)
        # Rust writes finalized cells into terminal scrollback because ratatui
        # owns only the live viewport. Textual's RichLog is still the product
        # transcript surface here, so hiding successfully projected blocks makes
        # Windows Terminal appear blank after the scroll-region ANSI sequence is
        # emitted. Keep the source-backed blocks visible while still exercising
        # the Rust insert_history projection boundary for parity tests.
        self._refresh_transcript()

    def _handle_insert_history_cell_dispatch_plan(self, plan: Any) -> bool:
        if getattr(plan, "action", None) != "insert_history_cell":
            return False
        payload = None
        updates = getattr(plan, "updates", ()) or ()
        for name, value in updates:
            if name == "insert_history_cell":
                payload = value
                break
        return self._insert_history_cell_payload_to_terminal_scrollback(payload)

    def _insert_history_cell_payload_to_terminal_scrollback(self, payload: Any) -> bool:
        lines = _insert_history_cell_payload_lines(payload)
        if not lines:
            return False
        width = self._exec_cell_render_width()
        state = self._resize_reflow_state
        state.raw_output_mode = _raw_output_mode(self.app_runtime)
        cell = ResizeReflowHistoryCell(lines=list(lines))
        state.transcript_cells.append(cell)
        reflow_plan = insert_history_cell_lines_plan(state, cell, width)
        self._last_insert_history_reflow_plan = reflow_plan
        if reflow_plan.action != "insert_history_lines":
            return False
        height = max(int(getattr(getattr(self, "size", object()), "height", 24) or 24), 1)
        viewport_height = max(1, min(8, height))
        terminal = InsertHistoryTerminalModel(
            width=width,
            height=height,
            viewport_y=max(height - viewport_height, 1),
            viewport_height=viewport_height,
        )
        if _insert_history_wrap_policy_from_resize_reflow(reflow_plan.wrap_policy) is InsertHistoryLineWrapPolicy.TERMINAL:
            insert_history_lines_with_wrap_policy(terminal, [line.text for line in reflow_plan.lines], InsertHistoryLineWrapPolicy.TERMINAL)
        else:
            insert_history_lines(terminal, [line.text for line in reflow_plan.lines])
        ansi = terminal.output.getvalue()
        self._last_history_projection_ansi = ansi
        # Rust distinguishes "alt screen is allowed" from "alt screen is
        # currently active". Normal chat runs inline even when overlays may
        # later enter alt-screen, so completed history should be written to the
        # terminal scrollback whenever an overlay is not active.
        if not self._pycodex_alt_screen_active:
            writer = getattr(getattr(self, "_driver", None), "write", None)
            if callable(writer):
                try:
                    writer(ansi)
                    return True
                except Exception:
                    pass
        return False

    def _reset_insert_history_reflow_state(self) -> None:
        self._resize_reflow_state = ResizeReflowState(raw_output_mode=_raw_output_mode(self.app_runtime))
        self._last_insert_history_reflow_plan = None

    def _refresh_session_header(self) -> None:
        self._ensure_session_header_block()
        self._refresh_transcript()

    def _ensure_session_header_block(self) -> None:
        text = self._session_header_text()
        index = self._session_header_block_index
        if index is not None and 0 <= index < len(self._blocks) and self._blocks[index].label == "session_header":
            self._blocks[index].text = text
            self._blocks[index].rich_lines = None
            return

        # Rust keeps the placeholder SessionHeaderHistoryCell active until the
        # configured SessionInfoCell arrives, then merges rather than rendering
        # a duplicate box. Python mirrors that by reserving the first transcript
        # block for the session header and replacing it in place.
        self._blocks = [block for block in self._blocks if block.label != "session_header"]
        self._blocks.insert(0, _TranscriptBlock("session_header", text))
        self._session_header_block_index = 0
        if self._history_projection_next_index > 0:
            self._history_projection_next_index += 1

    def _mark_session_header_configured(self) -> None:
        self._session_header_configured = True
        self._refresh_session_header()
        if not self._busy:
            self._set_status("Ready")

    def _set_status(self, text: str) -> None:
        if text == "Ready":
            self._refresh_terminal_title(active_progress=False)
            try:
                status_line = self.query_one("#status-line", Static)
            except NoMatches:
                return
            status_line.update(_plain_status_text(self._idle_status_line_text()))
            self.refresh(layout=True)
            return
        if self._active_retry_status is not None:
            elapsed = int(time.monotonic() - self._turn_started_at) if self._turn_started_at else 0
            self._set_retry_status(self._active_retry_status, elapsed_seconds=elapsed)
            return
        if text == "Working":
            self._refresh_terminal_title(active_progress=True)
            try:
                status_line = self.query_one("#status-line", Static)
            except NoMatches:
                return
            status_line.update(_plain_status_text(_active_status_line_text(self.app_runtime)))
            self.refresh(layout=True)
            return
        if text == "Thinking":
            self._refresh_terminal_title(active_progress=True)
        try:
            status_line = self.query_one("#status-line", Static)
        except NoMatches:
            return
        status_line.update(_plain_status_text(f"status: {text}"))
        self.refresh(layout=True)

    def _set_active_status(self, header: str, *, elapsed_seconds: int | None = None) -> None:
        self._refresh_terminal_title(active_progress=True)
        self.query_one("#status-line", Static).update(
            _plain_status_text(
                _active_status_line_text(
                    self.app_runtime,
                    header=header,
                    elapsed_seconds=elapsed_seconds,
                )
            )
        )
        self.refresh(layout=True)

    def _set_retry_status(self, status: "_RetryStatus", *, elapsed_seconds: int | None = None) -> None:
        self._refresh_terminal_title(active_progress=True)
        self.query_one("#status-line", Static).update(
            _plain_status_text(
                _retry_status_line_text(
                    self.app_runtime,
                    message=status.message,
                    details=status.details,
                    elapsed_seconds=elapsed_seconds,
                )
            )
        )
        self.refresh(layout=True)

    def _refresh_terminal_title(self, *, active_progress: bool) -> None:
        # Rust chatwidget::status_surfaces defaults terminal titles to
        # activity + project-name.  Textual owns terminal backend integration,
        # so the product shell updates App.title rather than writing OSC
        # directly from this renderer.
        _, invalid_items = parse_terminal_title_items_with_invalids(
            _runtime_terminal_title_item_ids(self.app_runtime)
        )
        self._warn_invalid_terminal_title_items_once(invalid_items)
        title = _terminal_title_text(self.app_runtime, active_progress=active_progress)
        if not title:
            self._clear_managed_terminal_title()
            return
        if self._managed_terminal_title == title:
            return
        self.title = title
        self._managed_terminal_title = title

    def _clear_managed_terminal_title(self) -> None:
        if self._managed_terminal_title is None:
            return
        self.title = ""
        self._managed_terminal_title = None

    def _idle_status_line_text(self) -> str:
        raw_items = _runtime_status_line_item_ids(self.app_runtime)
        items, invalid_items = parse_status_line_items_with_invalids(raw_items)
        self._warn_invalid_status_line_items_once(invalid_items)
        parts = [
            value
            for item in items
            if (value := _runtime_status_line_value(self.app_runtime, item, "Ready")) is not None
        ]
        usage = _runtime_status_token_usage(self.app_runtime)
        context_left = _runtime_context_remaining_text(self.app_runtime)
        if usage.total > 0 and context_left and context_left not in parts:
            parts.append(context_left)
        status_line = " · ".join(part for part in parts if part)
        chat_widget = getattr(self.app_runtime, "chat_widget", None)
        agent_label = getattr(chat_widget, "active_agent_label", None)
        goal_indicator = getattr(chat_widget, "current_goal_status_indicator", None)
        return status_line_right_indicator_line(status_line or None, agent_label, goal_indicator) or ""

    def _startup_status_line_text(self) -> str:
        # Rust chatwidget.rs starts with DEFAULT_MODEL_DISPLAY_NAME = "loading"
        # until the session/model snapshot reaches the passive footer.
        parts = ["loading"]
        directory = _runtime_status_line_value(self.app_runtime, StatusLineItem.CURRENT_DIR, "Ready")
        context_left = _runtime_status_line_value(self.app_runtime, StatusLineItem.CONTEXT_REMAINING, "Ready")
        if directory:
            parts.append(directory)
        if context_left:
            parts.append(context_left)
        return " · ".join(parts)

    def _append_startup_notices(self) -> None:
        tooltip = _runtime_startup_tooltip(self.app_runtime) if self._session_header_configured else None
        if tooltip:
            self._append_system_notice(f"Tip: {_plain_markdown_text(tooltip)}")
        for warning in _runtime_startup_warnings(self.app_runtime):
            self._append_system_notice(str(warning))
        _, invalid_items = parse_status_line_items_with_invalids(_runtime_status_line_item_ids(self.app_runtime))
        self._warn_invalid_status_line_items_once(invalid_items)
        _, invalid_title_items = parse_terminal_title_items_with_invalids(
            _runtime_terminal_title_item_ids(self.app_runtime)
        )
        self._warn_invalid_terminal_title_items_once(invalid_title_items)

    def _warn_invalid_status_line_items_once(self, invalid_items: Iterable[str]) -> None:
        deduped = _dedupe_texts(invalid_items)
        if self._invalid_status_line_warned or not deduped or not self._notices_ready:
            return
        self._invalid_status_line_warned = True
        label = "item" if len(deduped) == 1 else "items"
        self._append_system_notice(f"Ignored invalid status line {label}: {proper_join(deduped)}.")

    def _warn_invalid_terminal_title_items_once(self, invalid_items: Iterable[str]) -> None:
        deduped = _dedupe_texts(invalid_items)
        if self._invalid_terminal_title_warned or not deduped or not self._notices_ready:
            return
        self._invalid_terminal_title_warned = True
        label = "item" if len(deduped) == 1 else "items"
        self._append_system_notice(f"Ignored invalid terminal title {label}: {proper_join(deduped)}.")

    def _composer(self) -> "CodexComposerTextArea":
        return self.query_one("#composer", CodexComposerTextArea)

    def _transcript_log(self) -> RichLog:
        return self.query_one("#transcript", CodexTranscriptLog)

    def _session_header_text(self) -> str:
        yolo_mode = _runtime_header_yolo_mode(self.app_runtime)
        model_text = _runtime_display_model(self.app_runtime) if self._session_header_configured else "loading"
        reasoning = _runtime_header_reasoning_effort(self.app_runtime) if self._session_header_configured else None
        cell = SessionHeaderHistoryCell.new(
            model_text,
            reasoning,
            _runtime_show_fast_status(self.app_runtime) if self._session_header_configured else False,
            self.app_runtime.cwd,
            _display_version(),
        ).with_yolo_mode(yolo_mode)
        return "\n".join(_line_text(line) for line in cell.display_lines(100))

    def _composer_prompt_text(self) -> str:
        placeholder = getattr(self.app_runtime.chat_widget, "normal_placeholder_text", None)
        placeholder_text = str(placeholder).strip() if placeholder is not None else ""
        if not placeholder_text:
            from .chatwidget.constructor import PLACEHOLDERS

            placeholder_text = PLACEHOLDERS[6]
        return f"\u203a {placeholder_text}"


@dataclass
class _TextualSelection:
    kind: str
    view: Any
    context: Any = None
    presets: tuple[Any, ...] = ()
    parent_views: list[Any] = field(default_factory=list)
    active_tab_idx: int | None = None
    search_query: str = ""


def _selection_display_name(kind: str) -> str:
    if kind == "agent":
        return "Agent"
    if kind == "multi-agent-enable":
        return "Subagents"
    if kind == "permissions":
        return "Permissions"
    if kind == "approval":
        return "Approval"
    if kind == "settings":
        return "Settings"
    if kind in {"keymap", "keymap-action-menu", "keymap-replace-binding", "keymap-capture", "keymap-debug"}:
        return "Keymap"
    if kind == "review":
        return "Review"
    if kind == "resume":
        return "Resume"
    if kind == "fork":
        return "Fork"
    return "Model"


def _selection_status_text(kind: str) -> str:
    if kind == "agent":
        return "Select Agent: up/down move; Enter select; Esc/q cancel"
    if kind == "multi-agent-enable":
        return "Enable Subagents: up/down move; Enter select; Esc/q cancel"
    if kind == "permissions":
        return "Update Permissions: up/down move; Enter select; Esc/q cancel"
    if kind == "approval":
        return "Command approval: up/down move; Enter select; Esc/q cancel"
    if kind == "settings":
        return "Settings: up/down move; Enter select; Esc/q cancel"
    if kind == "keymap":
        return "Keymap: up/down move; Enter select; Esc/q cancel"
    if kind in {"keymap-action-menu", "keymap-replace-binding"}:
        return "Edit Shortcut: up/down move; Enter select; Esc back"
    if kind == "keymap-capture":
        return "Remap Shortcut: press a key; Esc cancel"
    if kind == "keymap-debug":
        return "Keypress Inspector: press a key; Esc/q cancel"
    if kind == "review":
        return "Select Review: up/down move; Enter select; Esc/q cancel"
    if kind == "resume":
        return "Resume Session: up/down move; Enter select; Esc/q cancel"
    if kind == "fork":
        return "Fork Session: up/down move; Enter select; Esc/q cancel"
    return "Select Model: up/down move; Enter select; Esc/q cancel"


def _feature_keys(feature: str) -> tuple[str, ...]:
    text = str(feature)
    keys = [text, text.lower(), text.replace("-", "_").lower()]
    enum_value = _feature_enum_for_text(text)
    if enum_value is not None:
        keys.append(enum_value.key())
        keys.append(enum_value.value)
    if text == "Collab":
        keys.extend(("multi_agent", "collab"))
    return tuple(dict.fromkeys(keys))


def _feature_enum_for_text(feature: str) -> CodexFeature | None:
    for candidate in (feature, feature.lower(), feature.replace("-", "_").lower()):
        resolved = codex_feature_for_key(candidate)
        if resolved is not None:
            return resolved
    try:
        return CodexFeature(feature)
    except ValueError:
        return None


def _feature_candidates(feature: str) -> tuple[Any, ...]:
    enum_value = _feature_enum_for_text(str(feature))
    values: list[Any] = []
    if enum_value is not None:
        values.append(enum_value)
    values.extend(_feature_keys(feature))
    return tuple(dict.fromkeys(values))


@dataclass
class _PermissionPopupBottomPane:
    params: Any = None

    def show_selection_view(self, params: Any) -> None:
        self.params = params


class _PermissionFeatureSet:
    def __init__(self, source: Any = None) -> None:
        self.source = source

    def enabled(self, feature: str) -> bool:
        method = getattr(self.source, "enabled", None)
        if callable(method):
            for candidate in _feature_candidates(feature):
                try:
                    if bool(method(candidate)):
                        return True
                except TypeError:
                    continue
            return False
        if isinstance(self.source, Mapping):
            for key in _feature_keys(feature):
                if key in self.source:
                    return bool(self.source[key])
        enabled_set = getattr(self.source, "enabled_set", None)
        if enabled_set is not None:
            return feature in enabled_set
        for key in _feature_keys(feature):
            value = getattr(self.source, key, None)
            if value is not None:
                return bool(value)
        return False

    def set_enabled(self, feature: str, enabled: bool) -> None:
        method = getattr(self.source, "set_enabled", None)
        if callable(method):
            for candidate in _feature_candidates(feature):
                try:
                    method(candidate, enabled)
                    return
                except TypeError:
                    continue
        if isinstance(self.source, dict):
            for key in _feature_keys(feature):
                self.source[key] = bool(enabled)
            return
        enabled_set = getattr(self.source, "enabled_set", None)
        if enabled_set is not None:
            if enabled:
                enabled_set.add(feature)
            else:
                enabled_set.discard(feature)
            return
        if self.source is not None:
            setattr(self.source, feature, bool(enabled))
            setattr(self.source, feature.lower(), bool(enabled))


class _PermissionPopupWidget:
    """Adapter for Rust-derived ``chatwidget::permission_popups`` builders."""

    def __init__(self, app_runtime: TuiAppRuntime) -> None:
        self.app_runtime = app_runtime
        self.bottom_pane = _PermissionPopupBottomPane()
        self.config = _permission_config_for_runtime(app_runtime)
        self.review = SimpleNamespace(recent_auto_review_denials=())

    def open_permission_profiles_popup(self) -> Any:
        active_profile = _active_permission_profile(self.app_runtime)
        active_profile_id = _ui_permission_profile_id(getattr(active_profile, "id", None))
        result = open_permission_profiles_menu(
            PermissionMenuConfig(
                active_profile_id=active_profile_id,
                approval_policy=_approval_policy_value(getattr(self.config.permissions, "approval_policy", None)),
                approvals_reviewer=_approvals_reviewer_value(getattr(self.config, "approvals_reviewer", None)),
                guardian_approval_enabled=bool(self.config.features.enabled("GuardianApproval")),
                custom_permission_profiles=tuple(_custom_permission_profiles(self.app_runtime)),
                disabled_reasons=dict(getattr(self.config.permissions, "disabled_reasons", {}) or {}),
            )
        )
        for error in result.errors:
            self.add_error_message(error)
        if result.view is not None:
            self.bottom_pane.show_selection_view(result.view)
        return result.view

    def add_info_message(self, message: str, hint: str | None = None) -> None:
        self.app_runtime.chat_widget.add_info_message(message, hint)

    def add_error_message(self, message: str) -> None:
        self.app_runtime.chat_widget.add_error_message(message)

    def request_redraw(self) -> None:
        self.app_runtime.chat_widget.request_redraw()

    def thread_id(self) -> str:
        return self.app_runtime.current_displayed_thread_id()


class _SettingsPopupWidget:
    """Adapter for Rust-derived ``chatwidget::settings_popups`` builders."""

    def __init__(self, app_runtime: TuiAppRuntime, app: PyCodexTextualApp) -> None:
        self.app_runtime = app_runtime
        self.app = app
        self.bottom_pane = _PermissionPopupBottomPane()
        self.config = _settings_config_for_runtime(app_runtime)

    def is_session_configured(self) -> bool:
        return True

    def current_model_supports_personality(self) -> bool:
        return bool(getattr(self.app_runtime.active_thread_runtime, "supports_personality", False))

    def current_model(self) -> str:
        return _runtime_display_model(self.app_runtime)

    def add_info_message(self, message: str, hint: str | None = None) -> None:
        self.app_runtime.chat_widget.add_info_message(message, hint)

    def add_error_message(self, message: str) -> None:
        self.app_runtime.chat_widget.add_error_message(message)

    def current_realtime_audio_selection_label(self, kind: object) -> str:
        return self.current_realtime_audio_device_name(kind) or "System default"

    def current_realtime_audio_device_name(self, kind: object) -> str | None:
        noun = _realtime_audio_kind_key(kind)
        config_value = getattr(self.config.realtime_audio, noun, None)
        if config_value is not None and str(config_value).strip():
            return str(config_value)
        for source in (self.app_runtime.active_thread_runtime, getattr(self.app_runtime.active_thread_runtime, "session_config", None)):
            value = getattr(source, f"{noun}_device", None)
            value = value() if callable(value) else value
            if value is not None and str(value).strip():
                return str(value)
        return None

    def set_realtime_audio_device_name(self, kind: object, name: object | None) -> None:
        noun = _realtime_audio_kind_key(kind)
        value = None if name is None else str(name)
        setattr(self.config.realtime_audio, noun, value)
        _set_runtime_attr(self.app_runtime.active_thread_runtime, f"{noun}_device", value)
        _set_runtime_attr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), f"{noun}_device", value)

    def list_realtime_audio_device_names(self, kind: object) -> list[str]:
        provider = getattr(self.app_runtime.active_thread_runtime, "list_realtime_audio_device_names", None)
        if provider is None:
            provider = getattr(getattr(self.app_runtime.active_thread_runtime, "session_config", None), "list_realtime_audio_device_names", None)
        if not callable(provider):
            raise NotImplementedError("list_realtime_audio_device_names")
        return list(provider(kind))


def _scroll_transcript_half_page(transcript: RichLog, direction: int) -> None:
    rows = max((_transcript_overlay_page_rows(transcript) + 1) // 2, 1)
    _scroll_transcript_rows(transcript, direction, rows)


def _scroll_transcript_page(transcript: RichLog, direction: int) -> None:
    _scroll_transcript_rows(transcript, direction, _transcript_overlay_page_rows(transcript))


def _scroll_transcript_rows(transcript: RichLog, direction: int, rows: int) -> None:
    scroll_relative = getattr(transcript, "scroll_relative", None)
    if callable(scroll_relative):
        scroll_relative(y=rows * (1 if direction > 0 else -1), animate=False, force=True)
        return
    action = transcript.action_scroll_down if direction > 0 else transcript.action_scroll_up
    for _ in range(rows):
        action()


def _transcript_overlay_page_rows(transcript: RichLog) -> int:
    app = getattr(transcript, "app", None)
    app_height = int(getattr(getattr(app, "size", object()), "height", 0) or 0)
    if app_height > 0:
        # Rust codex-tui::pager_overlay::TranscriptOverlay reserves three hint
        # rows, then PagerView::content_area reserves one header and one footer
        # row inside the remaining top area.
        return max(app_height - 5, 1)
    height = max(int(getattr(getattr(transcript, "size", object()), "height", 1) or 1), 1)
    return height


def _transcript_scroll_percent(transcript: RichLog) -> int:
    scroll_y = max(int(getattr(transcript, "scroll_y", 0) or 0), 0)
    max_scroll_y = getattr(transcript, "max_scroll_y", None)
    try:
        max_scroll = max(int(max_scroll_y() if callable(max_scroll_y) else max_scroll_y or 0), 0)
    except (TypeError, ValueError):
        max_scroll = 0
    if max_scroll <= 0:
        return 100
    return min(max(round((scroll_y / max_scroll) * 100), 0), 100)


def _render_transcript_overlay_banner_text(transcript: RichLog | None = None) -> str:
    percent = 100 if transcript is None else _transcript_scroll_percent(transcript)
    return "\n".join(
        [
            "T R A N S C R I P T",
            "↑/↓ to scroll    pgup/pgdn to page    home/end to jump",
            f"q to quit    esc to edit prev    {percent}%",
        ]
    )


LIVE_EXEC_MAX_LINES = 5


def _compact_live_exec_lines(lines: list[str], *, max_lines: int = LIVE_EXEC_MAX_LINES) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    visible = max(max_lines - 1, 1)
    hidden = len(lines) - visible
    return [*lines[-visible:], f"+{hidden} more running"]


def _startup_replay_block(item: Any) -> tuple[str, str]:
    if isinstance(item, tuple) and len(item) >= 2:
        kind = str(item[0])
        text = "" if item[1] is None else str(item[1]).strip()
    elif isinstance(item, dict):
        kind = str(item.get("kind", "status"))
        text = str(item.get("message", item.get("text", "")) or "").strip()
    else:
        kind = "status"
        text = str(item).strip()
    label = {
        "user_message": "you",
        "agent_markdown": "codex",
        "reasoning_summary": "reasoning",
        "proposed_plan": "codex",
        "final_message_separator": "status",
    }.get(kind, "status")
    if kind == "final_message_separator":
        text = ""
    return label, text


def _render_command_execution_item_text(item: Any, *, active: bool, width: int) -> str:
    command = str(_payload_field(item, "command", "") or "").strip()
    call_id = str(_payload_field(item, "id", command) or command)
    source = _exec_cell_source(_payload_field(item, "source", "agent"))
    output = None
    duration = None
    if not active:
        status = str(_payload_field(item, "status", "Completed") or "Completed")
        exit_code_value = _payload_field(item, "exit_code", None)
        if exit_code_value is None:
            exit_code = 0 if status.lower() in {"completed", "success", "succeeded"} else 1
        else:
            try:
                exit_code = int(exit_code_value)
            except (TypeError, ValueError):
                exit_code = 1
        aggregated_output = str(_payload_field(item, "aggregated_output", "") or "")
        output = ExecCellCommandOutput(
            exit_code=exit_code,
            aggregated_output=aggregated_output,
            formatted_output=aggregated_output,
        )
        duration_ms = _payload_field(item, "duration_ms", None)
        if duration_ms is not None:
            try:
                duration = max(float(duration_ms), 0.0) / 1000.0
            except (TypeError, ValueError):
                duration = None
    call = ExecCellCall(
        call_id=call_id,
        command=[command],
        parsed=list(_payload_field(item, "command_actions", ()) or ()),
        output=output,
        source=source,
        start_time=0.0 if active else None,
        duration=duration,
    )
    cell = ExecCell.new(call, animations_enabled=False)
    lines = exec_cell_command_display_lines(cell, width)
    return "\n".join(render_exec_cell_line_text(line) for line in lines)


def _exec_cell_source(value: Any) -> str:
    raw = getattr(value, "value", value)
    normalized = str(raw)
    return {
        "user_shell": EXEC_CELL_USER_SHELL,
        "userShell": EXEC_CELL_USER_SHELL,
        "UserShell": EXEC_CELL_USER_SHELL,
        "unified_exec_interaction": EXEC_CELL_UNIFIED_EXEC_INTERACTION,
        "unifiedExecInteraction": EXEC_CELL_UNIFIED_EXEC_INTERACTION,
        "UnifiedExecInteraction": EXEC_CELL_UNIFIED_EXEC_INTERACTION,
    }.get(normalized, normalized)


def _coerce_history_entry_text(result: Any) -> str | None:
    if result is None:
        return None
    if isinstance(result, str):
        return result
    text = _payload_field(result, "text", None)
    if text is not None:
        return str(text)
    entry = _payload_field(result, "entry", None)
    if entry is not None and entry is not result:
        return _coerce_history_entry_text(entry)
    return str(result)


@dataclass
class _TranscriptBlock:
    label: str
    text: str
    rich_lines: tuple[Any, ...] | None = None
    style: str = field(init=False)

    def __post_init__(self) -> None:
        styles = {
            "you": "bold cyan",
            "codex": "bold green",
            "reasoning": "dim",
            "exec": "yellow",
            "status": "yellow",
            "error": "bold red",
        }
        object.__setattr__(self, "style", styles.get(self.label, "white"))

    def render(self) -> Text:
        if self.rich_lines is not None:
            return _rich_lines_to_text(self.rich_lines)
        if self.label == "session_header":
            return Text(str(self.text))
        rendered = Text()
        lines = str(self.text).splitlines() or [""]
        prefix, continuation, prefix_style, body_style = _transcript_block_prefix(self.label)
        for index, line in enumerate(lines):
            rendered.append(prefix if index == 0 else continuation, style=prefix_style)
            rendered.append(line, style=body_style)
            if index < len(lines) - 1:
                rendered.append("\n")
        return rendered

    def terminal_history_lines(self) -> list[str]:
        if self.rich_lines is not None:
            text = "\n".join(_line_text(line) for line in self.rich_lines).strip()
            return text.splitlines() or [""]
        if self.label == "session_header":
            return str(self.text).splitlines() or [""]
        body = str(self.text).splitlines() or [""]
        prefix, continuation, _prefix_style, _body_style = _transcript_block_prefix(self.label)
        return [f"{prefix if index == 0 else continuation}{line}" for index, line in enumerate(body)]


def _block_is_terminal_scrollback_history_cell(block: _TranscriptBlock) -> bool:
    return block.label in {"session_header", "you", "codex", "reasoning", "exec", "status", "error"}


def _transcript_block_prefix(label: str) -> tuple[str, str, str, str]:
    if label == "you":
        return "› ", "  ", "dim", "white"
    if label == "error":
        return "■ ", "  ", "bold red", "bold red"
    return "• ", "  ", "dim", "dim" if label == "reasoning" else "white"


@dataclass(frozen=True)
class _GoalEditPromptState:
    thread_id: Any
    status: ThreadGoalStatus
    token_budget: int | None


@dataclass(frozen=True)
class _RetryStatus:
    message: str
    details: str | None = None


class CodexComposerTextArea(TextArea):
    """Textual editor shell with Rust ``ChatComposer`` submit semantics."""

    show_line_numbers = False
    BINDINGS = [
        *getattr(TextArea, "BINDINGS", []),
        ("enter", "submit_codex", "Submit"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.history_search: HistorySearchSession | None = None
        self.command_popup: CommandPopup | None = None
        self.command_popup_signature: tuple[Any, ...] | None = None
        self.text_elements: list[Any] = []
        self.pending_pastes: list[tuple[str, str]] = []

    def action_submit_codex(self) -> None:
        app = getattr(self, "app", None)
        submit = getattr(app, "submit_composer_text", None)
        if callable(submit):
            submit(self.text)

    def action_open_transcript(self) -> None:
        self._open_transcript_from_composer()

    async def on_key(self, event: Any) -> None:
        key = str(getattr(event, "key", "") or "")
        _textual_timing_trace(
            "textual_composer_on_key",
            key=key,
            character=repr(getattr(event, "character", None)),
            is_ctrl_t=_is_ctrl_t_event(event),
        )
        app = getattr(self, "app", None)
        active_selection = getattr(app, "_active_selection", None)
        if getattr(active_selection, "kind", None) in {"keymap-debug", "keymap-capture"}:
            return
        if self._handle_clipboard_text_paste_key(event):
            return
        if self._handle_shortcut_overlay_key(event):
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "open_transcript", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._open_transcript_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "open_external_editor", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._open_external_editor_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "clear_terminal", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._clear_terminal_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "copy", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._copy_last_response_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "toggle_vim_mode", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._toggle_vim_mode_from_composer()
            return
        if key == "enter":
            event.stop()
            event.prevent_default()
            self.action_submit_codex()

    def action_cursor_up(self, select: bool = False) -> None:
        if not select and self._handle_app_selection_key("up"):
            return
        if not select and self._move_command_popup("up"):
            return
        if not select and self._navigate_history("older"):
            return
        super().action_cursor_up(select=select)

    def action_cursor_down(self, select: bool = False) -> None:
        if not select and self._handle_app_selection_key("down"):
            return
        if not select and self._move_command_popup("down"):
            return
        if not select and self._navigate_history("newer"):
            return
        super().action_cursor_down(select=select)

    async def _on_key(self, event: Any) -> None:
        key = str(getattr(event, "key", "") or "")
        _textual_timing_trace(
            "textual_composer__on_key",
            key=key,
            character=repr(getattr(event, "character", None)),
            is_ctrl_t=_is_ctrl_t_event(event),
        )
        app = getattr(self, "app", None)
        active_selection = getattr(app, "_active_selection", None)
        if getattr(active_selection, "kind", None) in {"keymap-debug", "keymap-capture"}:
            return
        if self._handle_clipboard_text_paste_key(event):
            return
        if self._handle_shortcut_overlay_key(event):
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "open_transcript", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._open_transcript_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "open_external_editor", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._open_external_editor_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "clear_terminal", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._clear_terminal_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "copy", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._copy_last_response_from_composer()
            return
        if _app_keymap_key_matches(getattr(getattr(self, "app", None), "app_runtime", None), key, "toggle_vim_mode", getattr(event, "character", None)):
            event.stop()
            event.prevent_default()
            self._toggle_vim_mode_from_composer()
            return
        if self._handle_app_selection_key(key):
            event.stop()
            event.prevent_default()
            return
        if self.history_search is not None:
            if _composer_history_search_key_matches(
                getattr(self, "app", None),
                key,
                "history_search_previous",
            ) or key == "up":
                event.stop()
                event.prevent_default()
                self._step_history_search(HistorySearchDirection.OLDER)
                return
            if _composer_history_search_key_matches(
                getattr(self, "app", None),
                key,
                "history_search_next",
            ) or key == "down":
                event.stop()
                event.prevent_default()
                self._step_history_search(HistorySearchDirection.NEWER)
                return
            if key == "enter":
                event.stop()
                event.prevent_default()
                self._accept_history_search()
                return
            if key in {"escape", "ctrl+c"}:
                event.stop()
                event.prevent_default()
                self._cancel_history_search()
                return
            if key == "backspace":
                event.stop()
                event.prevent_default()
                self._edit_history_search_query(self.history_search.query[:-1])
                return
            character = getattr(event, "character", None)
            if character and str(character).isprintable():
                event.stop()
                event.prevent_default()
                self._edit_history_search_query(self.history_search.query + str(character))
                return
        if _composer_history_search_key_matches(
            getattr(self, "app", None),
            key,
            "history_search_previous",
        ):
            event.stop()
            event.prevent_default()
            self._begin_or_repeat_history_search()
            return
        if key == "tab" and self.command_popup is not None:
            event.stop()
            event.prevent_default()
            self._complete_selected_command()
            return
        if key == "enter":
            event.stop()
            event.prevent_default()
            app = getattr(self, "app", None)
            submit = getattr(app, "submit_composer_text", None)
            if callable(submit):
                submit(self.text)
            return
        if key in {"shift+enter", "ctrl+j"}:
            event.stop()
            event.prevent_default()
            self.insert("\n")
            self._sync_command_popup_with_app()
            return
        await super()._on_key(event)
        self._sync_command_popup_with_app()

    def _handle_shortcut_overlay_key(self, event: Any) -> bool:
        character = getattr(event, "character", None)
        key = str(getattr(event, "key", "") or "")
        if not _composer_toggle_shortcuts_key_matches(getattr(self, "app", None), key, character):
            return False
        app = getattr(self, "app", None)
        toggle = getattr(app, "toggle_shortcut_overlay_from_composer", None)
        if not callable(toggle) or not toggle(self):
            return False
        event.stop()
        event.prevent_default()
        return True

    def _open_transcript_from_composer(self) -> None:
        app = getattr(self, "app", None)
        open_transcript = getattr(app, "action_open_transcript", None)
        if callable(open_transcript):
            open_transcript()

    def _open_external_editor_from_composer(self) -> None:
        app = getattr(self, "app", None)
        open_external_editor = getattr(app, "action_open_external_editor", None)
        if callable(open_external_editor):
            open_external_editor()

    def _clear_terminal_from_composer(self) -> None:
        app = getattr(self, "app", None)
        clear_terminal = getattr(app, "action_clear_terminal", None)
        if callable(clear_terminal):
            clear_terminal()

    def _copy_last_response_from_composer(self) -> None:
        app = getattr(self, "app", None)
        copy_last_response = getattr(app, "action_copy_last_response", None)
        if callable(copy_last_response):
            copy_last_response()

    def _toggle_vim_mode_from_composer(self) -> None:
        app = getattr(self, "app", None)
        toggle_vim_mode = getattr(app, "action_toggle_vim_mode", None)
        if callable(toggle_vim_mode):
            toggle_vim_mode()

    async def _on_paste(self, event: Any) -> None:
        event.stop()
        event.prevent_default()
        self.handle_paste_text(str(getattr(event, "text", "") or ""))

    def _handle_clipboard_text_paste_key(self, event: Any) -> bool:
        key = str(getattr(event, "key", "") or "")
        character = getattr(event, "character", None)
        if not _textual_key_is_ctrl_v(key, character):
            return False
        app = getattr(self, "app", None)
        reader = getattr(app, "read_clipboard_text", None)
        if not callable(reader):
            return False
        try:
            pasted = reader()
        except Exception:
            return False
        if not pasted:
            return True
        if not self.handle_paste_text(str(pasted)):
            return False
        event.stop()
        event.prevent_default()
        return True

    def handle_paste_text(self, pasted: str) -> bool:
        composer = self._composer_model()
        handled = composer.handle_paste(pasted)
        if not handled:
            return False
        self.text = composer.current_text()
        self.text_elements = list(composer.text_elements)
        self.pending_pastes = composer.pending_pastes_value()
        self._move_cursor_to_end()
        self._sync_command_popup_with_app()
        return True

    def prepare_submission_text(self) -> tuple[tuple[str, list[Any]] | None, list[str]]:
        composer = self._composer_model()
        prepared = composer.prepare_submission_text(record_history=True)
        self.text_elements = list(composer.text_elements)
        self.pending_pastes = composer.pending_pastes_value()
        return prepared, [str(error) for error in composer.errors]

    def clear_submission_state(self) -> None:
        self.text = ""
        self.text_elements = []
        self.pending_pastes = []
        self.hide_command_popup()
        self._move_cursor_to_end()

    def _navigate_history(self, direction: str) -> bool:
        if self.history_search is not None:
            return False
        app = getattr(self, "app", None)
        navigate = getattr(app, "navigate_composer_history", None)
        return bool(callable(navigate) and navigate(self, direction))

    def _begin_or_repeat_history_search(self) -> None:
        app = getattr(self, "app", None)
        begin = getattr(app, "begin_composer_history_search", None)
        step = getattr(app, "step_composer_history_search", None)
        if self.history_search is None:
            if callable(begin):
                begin(self)
        elif callable(step):
            step(self, HistorySearchDirection.OLDER)

    def _step_history_search(self, direction: HistorySearchDirection) -> None:
        app = getattr(self, "app", None)
        step = getattr(app, "step_composer_history_search", None)
        if callable(step):
            step(self, direction)

    def _edit_history_search_query(self, query: str) -> None:
        if self.history_search is None:
            return
        self.history_search.query = query
        app = getattr(self, "app", None)
        update = getattr(app, "update_composer_history_search", None)
        if callable(update):
            update(self)

    def _accept_history_search(self) -> None:
        app = getattr(self, "app", None)
        accept = getattr(app, "accept_composer_history_search", None)
        if callable(accept):
            accept(self)

    def _cancel_history_search(self) -> None:
        app = getattr(self, "app", None)
        cancel = getattr(app, "cancel_composer_history_search", None)
        if callable(cancel):
            cancel(self)

    def byte_cursor_offset(self) -> int:
        row, column = self.cursor_location
        lines = self.text.split("\n")
        prefix = "\n".join(lines[:row])
        if row > 0:
            prefix += "\n"
        return len((prefix + lines[row][:column]).encode("utf-8"))

    def apply_history_entry(self, entry: HistoryEntry) -> None:
        self.text = entry.text
        self.text_elements = []
        self.pending_pastes = []
        self.hide_command_popup()
        self._move_cursor_to_end()

    def begin_history_search(self) -> None:
        if self.history_search is not None:
            return
        self.history_search = HistorySearchSession(
            original_draft=(self.text, self.cursor_location),
            query="",
            status=HistorySearchStatus.IDLE,
        )

    def set_history_search_status(self, status: HistorySearchStatus) -> None:
        if self.history_search is not None:
            self.history_search.status = status

    def restore_history_search_original(
        self,
        *,
        keep_search: bool,
        status: HistorySearchStatus = HistorySearchStatus.IDLE,
    ) -> None:
        if self.history_search is None:
            return
        text, cursor = self.history_search.original_draft
        self.text = str(text)
        try:
            self.move_cursor(cursor)
        except Exception:
            self.move_cursor((0, len(self.text)))
        if keep_search:
            self.history_search.status = status
        else:
            self.history_search = None

    def accept_history_search(self) -> bool:
        if self.history_search is None:
            return False
        if self.history_search.status is HistorySearchStatus.MATCH:
            self.history_search = None
            return True
        return False

    def cancel_history_search(self) -> bool:
        if self.history_search is None:
            return False
        self.restore_history_search_original(keep_search=False)
        return True

    def sync_command_popup(self) -> CommandPopup | None:
        first_line = self.text.splitlines()[0] if self.text.splitlines() else self.text
        if not first_line.startswith("/") or self.history_search is not None:
            self.command_popup = None
            self.command_popup_signature = None
            return None
        flags = self._command_popup_flags()
        service_tiers = self._command_popup_service_tiers()
        signature = (flags, tuple(service_tiers))
        popup = self.command_popup if self.command_popup_signature == signature else None
        if popup is None:
            popup = CommandPopup.new(flags, service_tiers)
            self.command_popup_signature = signature
        popup.on_composer_text_change(self.text)
        if not popup.filtered_items():
            self.command_popup = None
            self.command_popup_signature = None
            return None
        self.command_popup = popup
        return popup

    def hide_command_popup(self) -> None:
        self.command_popup = None
        self.command_popup_signature = None
        app = getattr(self, "app", None)
        if getattr(app, "_active_selection", None) is not None:
            return
        clear = getattr(app, "clear_command_popup", None)
        if callable(clear):
            clear()

    def _command_popup_flags(self) -> CommandPopupFlags:
        app = getattr(self, "app", None)
        app_runtime = getattr(app, "app_runtime", None)
        if app_runtime is None:
            return CommandPopupFlags()
        return _command_popup_flags_for_runtime(app_runtime)

    def _command_popup_service_tiers(self) -> tuple[ServiceTierCommand, ...]:
        app = getattr(self, "app", None)
        app_runtime = getattr(app, "app_runtime", None)
        if app_runtime is None:
            return ()
        return _service_tier_commands_for_runtime(app_runtime)

    def _composer_model(self) -> ChatComposer:
        return ChatComposer(
            text=self.text,
            text_elements=self.text_elements,
            pending_pastes=self.pending_pastes,
            input_enabled=not bool(getattr(self, "disabled", False)),
        )

    def _move_cursor_to_end(self) -> None:
        lines = self.text.split("\n")
        row = max(len(lines) - 1, 0)
        column = len(lines[-1]) if lines else 0
        self.move_cursor((row, column))

    def _sync_command_popup_with_app(self) -> None:
        app = getattr(self, "app", None)
        sync = getattr(app, "sync_command_popup", None)
        if callable(sync):
            sync(self)

    def _move_command_popup(self, direction: str) -> bool:
        popup = self.sync_command_popup()
        if popup is None:
            return False
        if direction == "up":
            popup.move_up()
        else:
            popup.move_down()
        self._sync_command_popup_with_app()
        return True

    def _handle_app_selection_key(self, key: str) -> bool:
        app = getattr(self, "app", None)
        handler = getattr(app, "handle_selection_key", None)
        return bool(callable(handler) and handler(key))

    def _complete_selected_command(self) -> bool:
        popup = self.sync_command_popup()
        if popup is None:
            return False
        selected = popup.selected_item()
        if selected is None:
            return False
        first_line = self.text.split("\n", 1)[0]
        completion = selected_command_completion(first_line, selected.value)
        if completion is None:
            completion = f"/{selected.command()} "
        remainder = ""
        if "\n" in self.text:
            remainder = "\n" + self.text.split("\n", 1)[1]
        self.text = completion + remainder
        self.hide_command_popup()
        self._move_cursor_to_end()
        return True


def configure_app_runtime_thread_identity(app_runtime: TuiAppRuntime, active_thread_runtime: ActiveThreadRuntime) -> None:
    """Mirror the app/thread identity bridge from the terminal projection path."""

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


def _permission_config_for_runtime(app_runtime: TuiAppRuntime) -> Any:
    chat_widget = getattr(app_runtime, "chat_widget", None)
    config = getattr(chat_widget, "config", None)
    if config is None:
        config = SimpleNamespace()
        setattr(chat_widget, "config", config)
    cwd = str(getattr(app_runtime, "cwd", ".") or ".")
    if not hasattr(config, "cwd"):
        config.cwd = cwd
    permissions = getattr(config, "permissions", None)
    if permissions is None:
        permissions = SimpleNamespace()
        config.permissions = permissions
    if not hasattr(permissions, "approval_policy") or getattr(permissions, "approval_policy", None) is None:
        permissions.approval_policy = _runtime_permission_value(
            app_runtime,
            "approval_policy",
            AskForApproval.ON_REQUEST,
        )
    if not hasattr(permissions, "permission_profile") or getattr(permissions, "permission_profile", None) is None:
        permissions.permission_profile = _coerce_permission_profile(
            _runtime_permission_value(app_runtime, "permission_profile", None),
            cwd,
        )
    if not hasattr(permissions, "active_permission_profile"):
        permissions.active_permission_profile = lambda: getattr(permissions, "active_permission_profile_value", None)
    if not hasattr(config, "features") or getattr(config, "features", None) is None:
        config.features = _PermissionFeatureSet(_runtime_permission_value(app_runtime, "features", None))
    elif not hasattr(config.features, "enabled"):
        config.features = _PermissionFeatureSet(config.features)
    if not hasattr(config, "approvals_reviewer") or getattr(config, "approvals_reviewer", None) is None:
        config.approvals_reviewer = _runtime_permission_value(app_runtime, "approvals_reviewer", ApprovalsReviewer.USER)
    if not hasattr(config, "notices") or getattr(config, "notices", None) is None:
        config.notices = SimpleNamespace(hide_full_access_warning=False)
    elif not hasattr(config.notices, "hide_full_access_warning"):
        config.notices.hide_full_access_warning = False
    if not hasattr(config, "explicit_permission_profile_mode"):
        config.explicit_permission_profile_mode = _runtime_permission_value(
            app_runtime,
            "explicit_permission_profile_mode",
            True,
        )
    if not hasattr(config, "windows_sandbox_level"):
        config.windows_sandbox_level = None
    return config


def _settings_config_for_runtime(app_runtime: TuiAppRuntime) -> Any:
    chat_widget = getattr(app_runtime, "chat_widget", None)
    config = getattr(chat_widget, "config", None)
    if config is None:
        config = SimpleNamespace()
        setattr(chat_widget, "config", config)
    if not hasattr(config, "realtime_audio") or getattr(config, "realtime_audio", None) is None:
        config.realtime_audio = SimpleNamespace(microphone=None, speaker=None)
    if not hasattr(config, "features") or getattr(config, "features", None) is None:
        config.features = _PermissionFeatureSet(_runtime_permission_value(app_runtime, "features", None))
    elif not hasattr(config.features, "enabled"):
        config.features = _PermissionFeatureSet(config.features)
    if not hasattr(config, "tui_theme"):
        config.tui_theme = None
    if not hasattr(config, "personality"):
        config.personality = None
    return config


def _realtime_audio_kind_key(kind: object) -> str:
    noun = getattr(kind, "noun", None)
    if callable(noun):
        value = noun()
        if value:
            return str(value)
    text = str(getattr(kind, "value", kind)).strip().lower()
    if "speaker" in text:
        return "speaker"
    return "microphone"


def _runtime_permission_value(app_runtime: TuiAppRuntime, name: str, default: Any = None) -> Any:
    for source in (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
    ):
        value = getattr(source, name, None)
        value = value() if callable(value) and name != "features" else value
        if value is not None:
            return value
    return default


def _active_permission_profile(app_runtime: TuiAppRuntime) -> Any:
    for source in (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
    ):
        value = getattr(source, "active_permission_profile", None)
        if callable(value):
            return value()
        if value is not None:
            return value
    permissions = getattr(getattr(app_runtime.chat_widget, "config", None), "permissions", None)
    if permissions is not None:
        value = getattr(permissions, "active_permission_profile", None)
        if callable(value):
            return value()
        if value is not None:
            return value
    return None


def _approval_policy_value(value: Any) -> str:
    value = _coerce_approval_policy(value) or ProtocolAskForApproval.ON_REQUEST
    return str(getattr(value, "value", value))


def _approvals_reviewer_value(value: Any) -> str:
    value = _coerce_approvals_reviewer(value) or ProtocolApprovalsReviewer.USER
    if value is ProtocolApprovalsReviewer.AUTO_REVIEW:
        return "auto-review"
    return "user"


def _coerce_approval_policy(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, ProtocolAskForApproval):
        return value
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    key = text.lower().replace("_", "-")
    aliases = {
        "never": ProtocolAskForApproval.NEVER,
        "on-request": ProtocolAskForApproval.ON_REQUEST,
        "onrequest": ProtocolAskForApproval.ON_REQUEST,
        "on-failure": ProtocolAskForApproval.ON_FAILURE,
        "onfailure": ProtocolAskForApproval.ON_FAILURE,
        "unless-trusted": ProtocolAskForApproval.UNLESS_TRUSTED,
        "unlesstrusted": ProtocolAskForApproval.UNLESS_TRUSTED,
    }
    return aliases.get(key, value)


def _coerce_approvals_reviewer(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, ProtocolApprovalsReviewer):
        return value
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    key = text.lower().replace("_", "-")
    aliases = {
        "user": ProtocolApprovalsReviewer.USER,
        "auto": ProtocolApprovalsReviewer.AUTO_REVIEW,
        "auto-review": ProtocolApprovalsReviewer.AUTO_REVIEW,
        "autoreview": ProtocolApprovalsReviewer.AUTO_REVIEW,
        "guardian-subagent": ProtocolApprovalsReviewer.AUTO_REVIEW,
    }
    return aliases.get(key, value)


def _permission_profile_for_active_profile_id(app_runtime: TuiAppRuntime, profile_id: Any) -> PermissionProfile | None:
    cwd = str(getattr(app_runtime, "cwd", ".") or ".")
    text = str(profile_id or "").strip()
    if text == ":read-only":
        return PermissionProfile.read_only(network_access=False)
    if text == ":workspace":
        return PermissionProfile.auto(cwd, network_access=False)
    if text == ":danger-no-sandbox":
        return PermissionProfile.disabled()
    return None


def _ui_permission_profile_id(profile_id: Any) -> str | None:
    text = str(profile_id or "").strip()
    if not text:
        return None
    if text == BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS:
        return ":danger-no-sandbox"
    return text


def _core_permission_profile_id(profile_id: Any) -> str | None:
    text = str(profile_id or "").strip()
    if not text:
        return None
    if text == ":danger-no-sandbox":
        return BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS
    return text


def _core_active_permission_profile_for_profile_id(profile_id: Any) -> ProtocolActivePermissionProfile | None:
    core_id = _core_permission_profile_id(profile_id)
    if core_id in {
        BUILT_IN_PERMISSION_PROFILE_READ_ONLY,
        BUILT_IN_PERMISSION_PROFILE_WORKSPACE,
        BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS,
    }:
        return ProtocolActivePermissionProfile.new(core_id)
    return None


def _core_permission_profile_for_active_profile_id(profile_id: Any) -> ProtocolPermissionProfile | None:
    core_id = _core_permission_profile_id(profile_id)
    if core_id == BUILT_IN_PERMISSION_PROFILE_READ_ONLY:
        return ProtocolPermissionProfile.read_only()
    if core_id == BUILT_IN_PERMISSION_PROFILE_WORKSPACE:
        return ProtocolPermissionProfile.workspace_write()
    if core_id == BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS:
        return ProtocolPermissionProfile.disabled()
    return None


def _popup_approval_preset_for_profile_id(app_runtime: TuiAppRuntime, profile_id: Any) -> Any:
    cwd = str(getattr(app_runtime, "cwd", ".") or ".")
    target = str(profile_id or "").strip()
    preset_id = {
        ":read-only": "read-only",
        ":workspace": "auto",
        ":danger-no-sandbox": "full-access",
    }.get(target)
    if preset_id is None:
        return None
    for preset in popup_builtin_approval_presets(cwd):
        if preset.id == preset_id:
            return preset
    return None


def _custom_permission_profiles(app_runtime: TuiAppRuntime) -> list[CustomPermissionProfileSummary]:
    raw = _runtime_permission_value(app_runtime, "custom_permission_profiles", ())
    profiles: list[CustomPermissionProfileSummary] = []
    for item in list(raw or ()):
        profile_id = getattr(item, "id", None)
        if profile_id is None and isinstance(item, Mapping):
            profile_id = item.get("id")
        if profile_id is None:
            continue
        description = getattr(item, "description", None)
        if description is None and isinstance(item, Mapping):
            description = item.get("description")
        profiles.append(
            CustomPermissionProfileSummary(
                id=str(profile_id),
                description=None if description is None else str(description),
            )
        )
    return profiles


def _runtime_plan_mask(app_runtime: TuiAppRuntime) -> Any:
    return plan_mask(_runtime_first_value(app_runtime.chat_widget, names=("model_catalog",)))


def _mask_reasoning_effort(mask: Any) -> Any:
    return getattr(mask, "reasoning_effort", None)


def _mask_developer_instructions(mask: Any) -> str | None:
    value = getattr(mask, "developer_instructions", None)
    return None if value is None else str(value)


def _apply_textual_collaboration_mask(app_runtime: TuiAppRuntime, mask: Any) -> None:
    for target in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        if target is None:
            continue
        _set_runtime_attr(target, "active_collaboration_mask", mask)
        _set_runtime_attr(target, "collaboration_mode", mask)
        _set_runtime_attr(target, "current_collaboration_mode", mask)


def _runtime_unified_exec_processes(app_runtime: TuiAppRuntime) -> list[UnifiedExecProcessDetails]:
    lifecycle = getattr(getattr(app_runtime, "chat_widget", None), "command_lifecycle", None)
    processes = list(getattr(lifecycle, "unified_exec_processes", []) or [])
    out: list[UnifiedExecProcessDetails] = []
    for process in processes:
        command = getattr(process, "command_display", None)
        if command is None:
            continue
        chunks = list(getattr(process, "recent_chunks", []) or [])
        out.append(UnifiedExecProcessDetails(command_display=str(command), recent_chunks=[str(chunk) for chunk in chunks]))
    return out


def _runtime_vim_enabled(app_runtime: TuiAppRuntime) -> bool:
    for source in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        value = getattr(source, "vim_enabled", None)
        if value is not None:
            return bool(value)
        value = getattr(source, "tui_vim_mode_default", None)
        if value is not None:
            return bool(value)
    return False


def _set_textual_vim_enabled(app_runtime: TuiAppRuntime, enabled: bool) -> None:
    for target in (
        app_runtime.chat_widget,
        getattr(app_runtime.chat_widget, "config", None),
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
    ):
        if target is None:
            continue
        _set_runtime_attr(target, "vim_enabled", bool(enabled))


def _coerce_permission_profile(value: Any, cwd: str) -> PermissionProfile:
    if isinstance(value, PermissionProfile):
        return value
    text = str(getattr(value, "value", value) or "").strip().lower().replace("_", "-")
    if text in {"disabled", "danger-full-access", "full-access", "full access"}:
        return PermissionProfile.disabled()
    if text in {"read-only", "readonly", "read only"}:
        return PermissionProfile.read_only(network_access=False)
    return PermissionProfile.auto(cwd, network_access=False)


def _set_runtime_attr(target: Any, name: str, value: Any) -> None:
    if target is None:
        return
    try:
        setattr(target, name, value)
    except (AttributeError, TypeError):
        if isinstance(target, dict):
            target[name] = value


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


def _line_text(line: object) -> str:
    spans = getattr(line, "spans", None)
    if spans is None:
        return str(line)
    return "".join(str(getattr(span, "content", span)) for span in spans)


def _rich_lines_to_text(lines: Iterable[Any]) -> Text:
    rendered = Text()
    materialized = tuple(lines)
    for line_index, line in enumerate(materialized):
        spans = getattr(line, "spans", None)
        if spans is None:
            rendered.append(str(line))
        else:
            for span in spans:
                rendered.append(str(getattr(span, "content", span)), style=_rich_style_from_semantic(getattr(span, "style", None)))
        if line_index < len(materialized) - 1:
            rendered.append("\n")
    return rendered


def _rich_style_from_semantic(style: object) -> str | None:
    if style is None:
        return None
    if isinstance(style, str):
        return style
    if isinstance(style, Mapping):
        parts: list[str] = []
        fg = style.get("fg") or style.get("color")
        if fg:
            parts.append(str(fg))
        if style.get("bold"):
            parts.append("bold")
        if style.get("dim"):
            parts.append("dim")
        if style.get("underlined") or style.get("underline"):
            parts.append("underline")
        return " ".join(parts) or None
    return str(style)


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


def _runtime_thread_name(app_runtime: TuiAppRuntime) -> str | None:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("thread_name", "conversation_name", "name"),
    )
    return str(value) if value is not None and str(value).strip() else None


def _runtime_collaboration_mode_label(app_runtime: TuiAppRuntime) -> str:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("collaboration_mode_label", "collaboration_mode", "current_collaboration_mode"),
    )
    if value is None:
        return "Default"
    raw = str(getattr(value, "value", value)).strip()
    if not raw:
        return "Default"
    return raw.replace("_", " ").replace("-", " ").title()


def _runtime_status_account_display(app_runtime: TuiAppRuntime) -> StatusAccountDisplay | None:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("status_account_display", "account_display", "account", "auth_account", "auth_status"),
    )
    if value is not None:
        if isinstance(value, StatusAccountDisplay):
            return value
        kind = str(_runtime_value(value, "kind", "") or _runtime_value(value, "type", "") or "").lower()
        if kind in {"api_key", "apikey", "api-key"} or bool(_runtime_value(value, "api_key", False)):
            return StatusAccountDisplay.api_key()
        email = _runtime_value(value, "email", None) or _runtime_value(value, "account_email", None) or _runtime_value(value, "user_email", None)
        plan = _runtime_value(value, "plan", None) or _runtime_value(value, "plan_type", None) or _runtime_value(value, "subscription_plan", None)
        if email or plan:
            return StatusAccountDisplay.chat_gpt(email=str(email) if email else None, plan=str(plan) if plan else None)
        if isinstance(value, str) and value.strip():
            return StatusAccountDisplay.chat_gpt(email=value.strip())
    auth = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        names=("original_auth", "auth_json", "stored_auth", "auth", "resolved_auth", "auth_manager"),
    )
    if auth is not None:
        is_api_key = _runtime_value(auth, "is_api_key_auth", None)
        if is_api_key is True:
            return StatusAccountDisplay.api_key()
        api_key = _runtime_value(auth, "api_key", None) or _runtime_value(auth, "openai_api_key", None)
        if isinstance(api_key, str) and api_key:
            return StatusAccountDisplay.api_key()
        is_chatgpt = _runtime_value(auth, "is_chatgpt_auth", None)
        mode = _runtime_value(auth, "auth_mode", None)
        mode_text = "" if mode is None else str(getattr(mode, "value", mode)).lower()
        if is_chatgpt is True or "chatgpt" in mode_text:
            parsed = _status_account_from_auth_snapshot(auth)
            if parsed is not None:
                return parsed
            email = _runtime_value(auth, "get_account_email", None) or _runtime_value(auth, "email", None)
            plan = _runtime_value(auth, "account_plan_type", None) or _runtime_value(auth, "plan_type", None)
            return StatusAccountDisplay.chat_gpt(
                email=str(email) if email else None,
                plan=str(plan) if plan else None,
            )
    return None


def _status_account_from_auth_snapshot(auth: Any) -> StatusAccountDisplay | None:
    mode = _runtime_value(auth, "auth_mode", None)
    mode_text = "" if mode is None else str(getattr(mode, "value", mode)).lower()
    if mode_text in {"api_key", "apikey", "api-key"}:
        return StatusAccountDisplay.api_key()
    if "chatgpt" not in mode_text and mode_text not in {"codex_backend", "codex-backend"}:
        return None
    token_data = _runtime_value(auth, "tokens", None) or _runtime_value(auth, "get_current_token_data", None)
    email = None
    plan = None
    if isinstance(token_data, TokenData):
        email = token_data.id_token.email
        plan = token_data.id_token.get_chatgpt_plan_type()
    elif isinstance(token_data, Mapping):
        id_token = token_data.get("id_token")
        if isinstance(id_token, str) and id_token:
            try:
                parsed = parse_chatgpt_jwt_claims(id_token)
            except (IdTokenInfoError, ValueError, TypeError, UnicodeDecodeError):
                parsed = None
            if parsed is not None:
                email = parsed.email
                plan = parsed.get_chatgpt_plan_type()
        elif isinstance(id_token, Mapping):
            email = _optional_display_str(id_token.get("email"))
            raw_plan = id_token.get("chatgpt_plan_type") or id_token.get("plan_type")
            plan = plan_type_display_name(raw_plan) if raw_plan is not None else None
    return StatusAccountDisplay.chat_gpt(email=email, plan=plan)


def _optional_display_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _runtime_provider_requires_openai_auth(app_runtime: TuiAppRuntime) -> bool:
    provider = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        names=("model_provider", "provider"),
    )
    provider = provider or getattr(app_runtime.active_thread_runtime, "provider", None)
    for source in (provider, _runtime_value(provider, "info", None)):
        if source is None:
            continue
        value = _runtime_value(source, "requires_openai_auth", None)
        if value is not None:
            return bool(value)
    base_url = _runtime_value(provider, "base_url", None)
    return isinstance(base_url, str) and "chatgpt.com" in base_url


def _runtime_show_chatgpt_usage_link(app_runtime: TuiAppRuntime) -> bool:
    explicit = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("show_chatgpt_usage_link", "show_usage_link"),
    )
    if explicit is not None:
        return bool(explicit)
    if _runtime_provider_requires_openai_auth(app_runtime):
        return True
    account = _runtime_status_account_display(app_runtime)
    return account is not None and account != StatusAccountDisplay.api_key()


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
    sandbox_summary = _runtime_first_value(*sources, names=("sandbox_summary", "sandbox", "sandbox_mode"))
    sandbox_text = str(sandbox_summary or "read-only")
    suffix = workspace_root_suffix(_runtime_workspace_roots(app_runtime), app_runtime.cwd)
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
        return tuple(_TEXTUAL_DEFAULT_STATUS_LINE_ITEMS)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _runtime_terminal_title_item_ids(app_runtime: TuiAppRuntime) -> tuple[Any, ...]:
    value = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
        names=("tui_terminal_title", "terminal_title_items", "terminal_title"),
    )
    if value is None:
        return tuple(DEFAULT_TERMINAL_TITLE_ITEMS)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _runtime_session_header_configured_at_startup(app_runtime: TuiAppRuntime) -> bool:
    return bool(
        _runtime_first_value(
            app_runtime.active_thread_runtime,
            getattr(app_runtime.active_thread_runtime, "session_config", None),
            names=("session_header_configured_at_startup", "session_configured_at_startup"),
        )
    )


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


def _runtime_terminal_title_value(
    app_runtime: TuiAppRuntime,
    item: TerminalTitleItem,
    status: str,
    *,
    active_progress: bool,
) -> str | None:
    if item == TerminalTitleItem.APP_NAME:
        return "Codex"
    if item == TerminalTitleItem.PROJECT:
        project = _project_title_for_path(app_runtime.cwd)
        return truncate_terminal_title_part(project, 24) if project else None
    if item == TerminalTitleItem.CURRENT_DIR:
        return truncate_terminal_title_part(_display_directory_for_path(app_runtime.cwd), 48)
    if item == TerminalTitleItem.SPINNER:
        return terminal_title_spinner_frame_at(timedelta(milliseconds=0)) if active_progress else None
    if item == TerminalTitleItem.STATUS:
        return status
    if item == TerminalTitleItem.THREAD:
        title = getattr(app_runtime, "thread_name", None) or getattr(app_runtime, "thread_id", None)
        return None if title is None else truncate_terminal_title_part(str(title), 48)
    if item == TerminalTitleItem.CONTEXT_REMAINING:
        return _runtime_context_remaining_text(app_runtime)
    if item == TerminalTitleItem.CONTEXT_USED:
        usage = _runtime_status_token_usage(app_runtime)
        context = usage.context_window
        percent_used = 0 if context is None else max(0, 100 - int(context.percent_remaining))
        return f"Context {percent_used}% used"
    if item == TerminalTitleItem.CODEX_VERSION:
        return _display_version()
    if item == TerminalTitleItem.USED_TOKENS:
        total = _runtime_status_token_usage(app_runtime).total
        return None if total <= 0 else f"{format_tokens_compact(total)} used"
    if item == TerminalTitleItem.TOTAL_INPUT_TOKENS:
        return f"{format_tokens_compact(_runtime_status_token_usage(app_runtime).input)} in"
    if item == TerminalTitleItem.TOTAL_OUTPUT_TOKENS:
        return f"{format_tokens_compact(_runtime_status_token_usage(app_runtime).output)} out"
    if item == TerminalTitleItem.SESSION_ID:
        thread_id = getattr(app_runtime, "thread_id", None) or getattr(app_runtime.active_thread_runtime, "thread_id", None)
        return None if thread_id is None else str(thread_id)
    if item == TerminalTitleItem.FAST_MODE:
        return "fast" if " fast" in _runtime_model_with_reasoning(app_runtime) else None
    if item == TerminalTitleItem.MODEL:
        return truncate_terminal_title_part(_runtime_display_model(app_runtime), 32)
    if item == TerminalTitleItem.MODEL_WITH_REASONING:
        return truncate_terminal_title_part(_runtime_model_with_reasoning(app_runtime), 32)
    if item == TerminalTitleItem.TASK_PROGRESS:
        return None
    return None


def _dedupe_texts(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _runtime_context_remaining_text(app_runtime: TuiAppRuntime) -> str | None:
    context_window = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime, "chat_widget", None),
        names=("model_context_window", "context_window"),
    )
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


def _active_status_line_text(
    app_runtime: TuiAppRuntime,
    *,
    header: str = "Working",
    elapsed_seconds: int | None = 0,
) -> str:
    now = 0.0 if elapsed_seconds is None else float(max(0, int(elapsed_seconds)))
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.update_header(str(header or "Working"))
    binding = _runtime_interrupt_binding(app_runtime)
    widget.set_interrupt_binding(None if binding is None else StatusKeyBinding(binding))
    width = max(20, int(getattr(getattr(app_runtime, "terminal_size", None), "columns", 100) or 100))
    line = widget.render_lines(width, height=1, now=now)[0]
    return _plain_line(line)


def _retry_status_line_text(
    app_runtime: TuiAppRuntime,
    *,
    message: str,
    details: str | None,
    elapsed_seconds: int | None = 0,
) -> str:
    now = 0.0 if elapsed_seconds is None else float(max(0, int(elapsed_seconds)))
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.update_header(str(message or "Reconnecting..."))
    widget.update_details(
        details,
        StatusDetailsCapitalization.CapitalizeFirst,
        1,
    )
    binding = _runtime_interrupt_binding(app_runtime)
    widget.set_interrupt_binding(None if binding is None else StatusKeyBinding(binding))
    width = max(20, int(getattr(getattr(app_runtime, "terminal_size", None), "columns", 100) or 100))
    # Rust renders reconnect as a bottom-pane status indicator, not a history
    # cell. Keep the Textual projection at a stable two-line height so a retry
    # update does not shrink the transcript and visually clip the user's prompt.
    lines = widget.render_lines(width, height=2, now=now)
    return "\n".join(_plain_line(line) for line in lines)


def _terminal_title_text(app_runtime: TuiAppRuntime, *, active_progress: bool) -> str:
    items, _invalid_items = parse_terminal_title_items_with_invalids(_runtime_terminal_title_item_ids(app_runtime))
    previous: TerminalTitleItem | None = None
    parts: list[str] = []
    status = "Working" if active_progress else "Ready"
    for item in items:
        value = _runtime_terminal_title_value(app_runtime, item, status, active_progress=active_progress)
        if value is None:
            continue
        parts.append(item.separator_from_previous(previous) + value)
        previous = item
    return "".join(parts)


def _project_title_for_path(path: Path | str) -> str:
    cwd = Path(path)
    name = cwd.name.strip()
    return name or str(cwd)


def _runtime_interrupt_binding(app_runtime: TuiAppRuntime) -> str | None:
    raw_keymap = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        names=("tui_keymap", "keymap"),
    )
    try:
        keymap = RuntimeKeymap.from_config(raw_keymap or {})
        binding = primary_binding(keymap.chat.interrupt_turn)
    except Exception:
        binding = primary_binding(RuntimeKeymap.built_in_defaults().chat.interrupt_turn)
    if binding is None:
        return None
    return _key_binding_label(binding)


def _runtime_keymap_for_app_runtime(app_runtime: TuiAppRuntime | None) -> RuntimeKeymap:
    raw_keymap = None
    if app_runtime is not None:
        raw_keymap = _runtime_first_value(
            app_runtime.active_thread_runtime,
            getattr(app_runtime.active_thread_runtime, "session_config", None),
            names=("tui_keymap", "keymap"),
        )
    try:
        return RuntimeKeymap.from_config(raw_keymap or {})
    except Exception:
        return RuntimeKeymap.built_in_defaults()


def _footer_key_binding(binding: Any | None) -> FooterKeyBinding | None:
    if binding is None:
        return None
    code = str(getattr(binding, "code", binding) or "")
    modifiers = tuple(
        str(modifier).lower().replace("control", "ctrl")
        for modifier in sorted(getattr(binding, "modifiers", ()) or ())
    )
    return FooterKeyBinding(code, modifiers)


def _footer_key_hints_for_runtime(app_runtime: TuiAppRuntime | None) -> FooterKeyHints:
    keymap = _runtime_keymap_for_app_runtime(app_runtime)
    return FooterKeyHints(
        toggle_shortcuts=_footer_key_binding(primary_binding(keymap.composer.toggle_shortcuts)),
        queue=_footer_key_binding(primary_binding(keymap.composer.queue)),
        insert_newline=_footer_key_binding(primary_binding(keymap.editor.insert_newline)),
        external_editor=_footer_key_binding(primary_binding(keymap.app.open_external_editor)),
        edit_previous=FooterKeyBinding("Esc"),
        show_transcript=_footer_key_binding(primary_binding(keymap.app.open_transcript)),
        history_search=_footer_key_binding(primary_binding(keymap.composer.history_search_previous)),
        reasoning_down=_footer_key_binding(primary_binding(keymap.chat.decrease_reasoning_effort)),
        reasoning_up=_footer_key_binding(primary_binding(keymap.chat.increase_reasoning_effort)),
    )


def _composer_history_search_key_matches(
    app: object | None,
    key: str,
    action: str = "history_search_previous",
) -> bool:
    try:
        code, modifiers = _textual_key_to_key_parts(key)
        event_binding = KeyBinding(str(code), frozenset(str(item).upper() for item in modifiers))
        runtime_keymap = _runtime_keymap_for_app_runtime(getattr(app, "app_runtime", None))
    except Exception:
        return key == "ctrl+r" if action == "history_search_previous" else key == "ctrl+s"
    return event_binding in set(getattr(runtime_keymap.composer, action))


def _composer_toggle_shortcuts_key_matches(app: object | None, key: str, character: Any = None) -> bool:
    key_candidates = [str(key or "")]
    if character is not None:
        key_candidates.append(str(character))
    if str(key or "") == "question_mark":
        key_candidates.append("?")
    app_runtime = getattr(app, "app_runtime", None)
    runtime_keymap = _runtime_keymap_for_app_runtime(app_runtime)
    toggles = set(runtime_keymap.composer.toggle_shortcuts)
    for candidate in key_candidates:
        if not candidate:
            continue
        try:
            code, modifiers = _textual_key_to_key_parts(candidate)
        except Exception:
            continue
        if KeyBinding(str(code), frozenset(str(item).upper() for item in modifiers)) in toggles:
            return True
    return False


def _app_keymap_key_matches(
    app_runtime: TuiAppRuntime | None,
    key: str,
    action: str,
    character: Any = None,
) -> bool:
    runtime_keymap = _runtime_keymap_for_app_runtime(app_runtime)
    app_keymap = getattr(runtime_keymap, "app", None)
    bindings = set(getattr(app_keymap, action, ()) or ())
    for candidate in _key_event_candidates(key, character):
        try:
            code, modifiers = _textual_key_to_key_parts(candidate)
        except Exception:
            continue
        if KeyBinding(str(code), frozenset(str(item).upper() for item in modifiers)) in bindings:
            return True
    return False


def _key_event_candidates(key: str, character: Any = None) -> tuple[str, ...]:
    candidates: list[str] = []
    raw_key = str(key or "")
    if raw_key:
        candidates.append(raw_key)
    if character is not None:
        raw_character = str(character)
        if raw_character:
            candidates.append(raw_character)
            control = _control_character_key_spec(raw_character)
            if control is not None:
                candidates.append(control)
    return tuple(dict.fromkeys(candidates))


def _textual_key_is_ctrl_v(key: str, character: Any = None) -> bool:
    for candidate in _key_event_candidates(key, character):
        try:
            code, modifiers = _textual_key_to_key_parts(candidate)
        except Exception:
            continue
        if str(code).lower() == "v" and any(str(item).lower() == "control" for item in modifiers):
            return True
    return False


def _control_character_key_spec(character: str) -> str | None:
    if len(character) != 1:
        return None
    codepoint = ord(character)
    if 1 <= codepoint <= 26:
        return f"ctrl+{chr(ord('a') + codepoint - 1)}"
    return None


def _app_keymap_accepts_control_character(app_runtime: TuiAppRuntime | None, action: str, character: str) -> bool:
    spec = _control_character_key_spec(character)
    return False if spec is None else _app_keymap_key_matches(app_runtime, spec, action)


def _key_binding_label(binding: Any) -> str:
    code = str(getattr(binding, "code", binding) or "").strip()
    modifiers = tuple(str(item).lower() for item in (getattr(binding, "modifiers", ()) or ()))
    normalized_code = code.lower()
    if not modifiers:
        return normalized_code
    prefix: list[str] = []
    if "control" in modifiers:
        prefix.append("ctrl")
    if "alt" in modifiers:
        prefix.append("alt")
    if "shift" in modifiers:
        prefix.append("shift")
    prefix.append(normalized_code)
    return "+".join(prefix)


def _plain_line(line: Any) -> str:
    if isinstance(line, (list, tuple)):
        return "".join(_plain_line(part) for part in line)
    spans = getattr(line, "spans", None)
    if spans is None:
        if hasattr(line, "text"):
            return str(getattr(line, "text"))
        text = str(line)
        if text in {"standard-popup-hint", "standard_popup_hint_line"}:
            return standard_popup_hint_line()
        return text
    return "".join(str(getattr(span, "content", getattr(span, "text", span))) for span in spans)


def _insert_history_cell_payload_lines(payload: Any) -> list[str]:
    cell = payload
    if isinstance(payload, Mapping) and "cell" in payload:
        cell = payload.get("cell")

    display_lines = getattr(cell, "display_lines", None)
    if callable(display_lines):
        try:
            return [_plain_line(line) for line in display_lines(100)]
        except TypeError:
            return [_plain_line(line) for line in display_lines()]
        except Exception:
            return []

    if isinstance(cell, Mapping):
        raw_lines = cell.get("lines")
        if raw_lines is not None:
            return [str(line) for line in raw_lines]
        parts: list[str] = []
        for key in ("title", "message", "hint"):
            value = cell.get(key)
            if value:
                parts.extend(str(value).splitlines())
        return parts

    if isinstance(payload, Mapping):
        parts = []
        for key in ("title", "message", "hint"):
            value = payload.get(key)
            if value:
                parts.extend(str(value).splitlines())
        return parts

    if isinstance(cell, str):
        return cell.splitlines()
    return []


def _insert_history_wrap_policy_from_resize_reflow(value: Any) -> InsertHistoryLineWrapPolicy:
    if value is ResizeReflowHistoryLineWrapPolicy.Terminal:
        return InsertHistoryLineWrapPolicy.TERMINAL
    raw = str(getattr(value, "value", value) or "").lower().replace("-", "_")
    if raw in {"terminal", "historylinewrappolicy.terminal"}:
        return InsertHistoryLineWrapPolicy.TERMINAL
    return InsertHistoryLineWrapPolicy.PRE_WRAP


def _plain_markdown_text(value: str) -> str:
    return str(value).replace("**", "").replace("__", "")


def _runtime_rate_limit_snapshots(app_runtime: TuiAppRuntime) -> tuple[RateLimitSnapshotDisplay, ...]:
    runtime = app_runtime.active_thread_runtime
    model_client = getattr(runtime, "model_client", None)
    model_client_state = getattr(model_client, "state", None)
    now = datetime.now().astimezone()
    sources = (
        runtime,
        getattr(runtime, "session_config", None),
        model_client,
        model_client_state,
        getattr(app_runtime, "chat_widget", None),
    )
    names = (
        "rate_limit_snapshots_by_limit_id",
        "rate_limits_by_limit_id",
        "latest_rate_limits_by_limit_id",
        "latest_rate_limits",
        "rate_limits",
        "latest_rate_limit_snapshot",
    )
    snapshots: list[RateLimitSnapshotDisplay] = []
    seen: set[str] = set()
    for source in sources:
        if source is None:
            continue
        for name in names:
            raw = _runtime_value(source, name, None)
            for snapshot in _coerce_runtime_rate_limit_snapshots(raw, now=now):
                if snapshot.limit_name in seen:
                    continue
                snapshots.append(snapshot)
                seen.add(snapshot.limit_name)
    return tuple(snapshots)


def _coerce_runtime_rate_limit_snapshots(
    raw: object,
    *,
    now: datetime,
    limit_name: str = "codex",
) -> tuple[RateLimitSnapshotDisplay, ...]:
    if raw is None:
        return ()
    if isinstance(raw, RateLimitSnapshotDisplay):
        return (raw,)
    if isinstance(raw, RateLimitWindowDisplay):
        return (RateLimitSnapshotDisplay(limit_name, now, primary=raw),)
    if isinstance(raw, Mapping):
        if _runtime_value(raw, "rate_limits") is not None or _runtime_value(raw, "rateLimits") is not None:
            return tuple(
                snapshot
                for value in app_server_rate_limit_snapshots(raw)
                for snapshot in _coerce_runtime_rate_limit_snapshots(value, now=now, limit_name=limit_name)
            )
        if _looks_like_rate_limit_snapshot(raw):
            return (_runtime_snapshot_display(raw, now=now, limit_name=limit_name),)
        snapshots: list[RateLimitSnapshotDisplay] = []
        for key, value in raw.items():
            snapshots.extend(_coerce_runtime_rate_limit_snapshots(value, now=now, limit_name=str(key)))
        return tuple(snapshots)
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        snapshots: list[RateLimitSnapshotDisplay] = []
        for value in raw:
            snapshots.extend(_coerce_runtime_rate_limit_snapshots(value, now=now, limit_name=limit_name))
        return tuple(snapshots)
    return (_runtime_snapshot_display(raw, now=now, limit_name=limit_name),)


def _looks_like_rate_limit_snapshot(raw: Mapping[object, object]) -> bool:
    keys = {str(key) for key in raw.keys()}
    return bool(keys & {"primary", "secondary", "credits", "limit_id", "limit_name"})


def _runtime_snapshot_display(raw: object, *, now: datetime, limit_name: str) -> RateLimitSnapshotDisplay:
    if isinstance(raw, RateLimitSnapshotDisplay):
        return raw
    if isinstance(raw, RateLimitWindowDisplay):
        return RateLimitSnapshotDisplay(limit_name, now, primary=raw)
    explicit_name = _runtime_value(raw, "limit_name") or _runtime_value(raw, "limit_id") or limit_name
    return rate_limit_snapshot_display_for_limit(raw, str(explicit_name), now)


def _runtime_should_refresh_rate_limits(app_runtime: TuiAppRuntime) -> bool:
    runtime = app_runtime.active_thread_runtime
    raw = _runtime_first_value(
        runtime,
        getattr(runtime, "session_config", None),
        getattr(runtime, "model_client", None),
        names=("should_refresh_rate_limits", "refresh_rate_limits_on_status"),
    )
    if raw is not None:
        return bool(raw)
    if not callable(getattr(runtime, "fetch_account_rate_limits", None)):
        return False
    if _runtime_provider_requires_openai_auth(app_runtime):
        return True
    account = _runtime_status_account_display(app_runtime)
    return account is not None and account != StatusAccountDisplay.api_key()


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


def _event_delta(event: ServerNotification) -> str:
    value = _payload_field(event.payload, "delta", "")
    return "" if value is None else str(value)


def _notification_turn_id(event: ServerNotification) -> str | None:
    turn = _payload_field(event.payload, "turn", None)
    value = _payload_field(turn, "id", None) if turn is not None else _payload_field(event.payload, "turn_id", None)
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _event_item(event: ServerNotification) -> Any:
    return _payload_field(event.payload, "item", None)


def _item_kind(item: Any) -> str:
    return str(_payload_field(item, "kind", ""))


def _is_ctrl_t_event(event: Any) -> bool:
    key = str(getattr(event, "key", "") or "")
    character = getattr(event, "character", None)
    return _is_ctrl_t_key(key) or character == "\x14"


def _is_ctrl_t_key(key: str) -> bool:
    return key.replace("-", "_").replace("+", "_").lower() in {"ctrl_t", "control_t"}


def _agent_message_item_text(item: Any) -> str:
    parts: list[str] = []
    for content in _payload_field(item, "content", ()) or ():
        content_type = str(_payload_field(content, "type", "") or "").lower()
        if content_type in {"text", "output_text"}:
            text = _payload_field(content, "text", "")
            if text:
                parts.append(str(text))
    return "".join(parts)


def _reasoning_item_text(item: Any, *, show_summary: bool = True) -> str:
    summary = _payload_field(item, "summary", ()) or ()
    if not show_summary:
        summary = ()
    if isinstance(summary, str):
        return summary
    parts: list[str] = []
    for entry in summary:
        text = _payload_field(entry, "text", entry)
        if text:
            parts.append(str(text))
    if parts:
        return "\n".join(parts)
    if _show_raw_reasoning_item(item):
        content = _payload_field(item, "content", ()) or ()
        for entry in content:
            text = _payload_field(entry, "text", entry)
            if text:
                parts.append(str(text))
    return "\n".join(parts)


def _reasoning_item_has_summary(item: Any) -> bool:
    summary = _payload_field(item, "summary", ()) or ()
    if isinstance(summary, str):
        return bool(summary.strip())
    return any(bool(_payload_field(entry, "text", entry)) for entry in summary)


def _reasoning_item_has_content(item: Any) -> bool:
    content = _payload_field(item, "content", ()) or ()
    if isinstance(content, str):
        return bool(content.strip())
    return any(bool(_payload_field(entry, "text", entry)) for entry in content)


def _show_raw_reasoning_item(item: Any) -> bool:
    # ItemCompleted(Reasoning) normally carries summary text only. This helper
    # exists so raw-content shapes do not accidentally stringify a mapping when
    # summary is absent; config gating for live raw deltas remains in the app.
    return False


def _payload_field(payload: Any, name: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _show_raw_agent_reasoning(app_runtime: TuiAppRuntime) -> bool:
    config = getattr(getattr(app_runtime, "chat_widget", object()), "config", object())
    return bool(getattr(config, "show_raw_agent_reasoning", False))


def _trace_reasoning_projection(
    kind: str,
    *,
    source: str,
    displayed: bool,
    summary_present: bool | None = None,
    content_present: bool | None = None,
) -> None:
    """Write a content-free reasoning projection trace when explicitly enabled.

    Rust ``codex-tui::chatwidget::protocol`` distinguishes visible
    ``ReasoningSummaryTextDelta`` from raw ``ReasoningTextDelta`` gated by
    ``show_raw_agent_reasoning``.  The live OAuth path can only prove that
    boundary safely if diagnostics record event classification without writing
    the reasoning text itself.
    """

    path = os.environ.get("PYCODEX_TUI_REASONING_TRACE")
    if not path:
        return
    record: dict[str, object] = {
        "t": time.monotonic(),
        "kind": str(kind),
        "source": str(source),
        "displayed": bool(displayed),
    }
    if summary_present is not None:
        record["summary_present"] = bool(summary_present)
    if content_present is not None:
        record["content_present"] = bool(content_present)
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass


def _history_search_status_for_result(result: Any) -> HistorySearchStatus:
    kind = str(getattr(result, "kind", result))
    if kind in {"Found", "AtBoundary"}:
        return HistorySearchStatus.MATCH
    if kind == "Pending":
        return HistorySearchStatus.SEARCHING
    return HistorySearchStatus.NO_MATCH


def _render_command_popup_text(popup: CommandPopup) -> Text:
    rendered = Text()
    matches = popup.filtered()
    if not matches:
        rendered.append("  no matches", style="dim")
        return rendered
    selected_idx = popup.state.selected_idx if popup.state.selected_idx is not None else 0
    for index, (item, _indices) in enumerate(matches[:8]):
        marker = ">" if index == selected_idx else " "
        style = "bold cyan" if index == selected_idx else "dim"
        rendered.append(f"{marker} /{item.command():<18}", style=style)
        rendered.append(item.description(), style=style)
        rendered.append("\n")
    return rendered


def _ensure_selection_tab(selection: _TextualSelection) -> None:
    tabs = list(getattr(selection.view, "tabs", ()) or ())
    if not tabs:
        selection.active_tab_idx = None
        return
    if selection.active_tab_idx is not None and 0 <= selection.active_tab_idx < len(tabs):
        return
    initial_tab_id = getattr(selection.view, "initial_tab_id", None)
    selection.active_tab_idx = next((idx for idx, tab in enumerate(tabs) if getattr(tab, "id", None) == initial_tab_id), 0)


def _selection_active_items(selection: _TextualSelection) -> list[Any]:
    _ensure_selection_tab(selection)
    tabs = list(getattr(selection.view, "tabs", ()) or ())
    if selection.active_tab_idx is not None and 0 <= selection.active_tab_idx < len(tabs):
        items = list(getattr(tabs[selection.active_tab_idx], "items", ()) or ())
    else:
        items = list(getattr(selection.view, "items", ()) or ())
    query = selection.search_query.strip().lower()
    if not query or not bool(getattr(selection.view, "is_searchable", False)):
        return items
    return [
        item
        for item in items
        if query in str(getattr(item, "search_value", None) or getattr(item, "name", "")).lower()
    ]


def _selection_accepts_search_key(selection: _TextualSelection, key: str) -> bool:
    if not bool(getattr(selection.view, "is_searchable", False)):
        return False
    if len(key) != 1:
        return False
    return key.isprintable() and not key.isspace()


def _selection_active_header(selection: _TextualSelection) -> Any:
    _ensure_selection_tab(selection)
    tabs = list(getattr(selection.view, "tabs", ()) or ())
    if selection.active_tab_idx is not None and 0 <= selection.active_tab_idx < len(tabs):
        return getattr(tabs[selection.active_tab_idx], "header", None)
    return getattr(selection.view, "header", None)


def _selection_active_footer_hint(selection: _TextualSelection) -> Any:
    _ensure_selection_tab(selection)
    tabs = list(getattr(selection.view, "tabs", ()) or ())
    active_tab_id = None
    if selection.active_tab_idx is not None and 0 <= selection.active_tab_idx < len(tabs):
        active_tab_id = getattr(tabs[selection.active_tab_idx], "id", None)
    if active_tab_id is not None:
        for tab_id, hint in getattr(selection.view, "tab_footer_hints", ()) or ():
            if tab_id == active_tab_id:
                return hint
    return getattr(selection.view, "footer_hint", None)


def _first_enabled_selection_index(selection: _TextualSelection) -> int:
    for index, item in enumerate(_selection_active_items(selection)):
        if not getattr(item, "is_disabled", False) and getattr(item, "disabled_reason", None) is None:
            return index
    return 0


def _initial_selection_index(selection: _TextualSelection) -> int:
    # Rust codex-tui::bottom_pane::list_selection_view::apply_filter restores
    # the current row before consulting initial_selected_idx.  Textual renders a
    # lightweight projection of SelectionViewParams, so mirror that selection
    # policy here rather than defaulting every popup to row zero.
    items = _selection_active_items(selection)
    if not bool(getattr(selection.view, "is_searchable", False)):
        for index, item in enumerate(items):
            if (
                getattr(item, "is_current", False)
                and not getattr(item, "is_disabled", False)
                and getattr(item, "disabled_reason", None) is None
            ):
                return index
    initial = getattr(selection.view, "initial_selected_idx", None)
    if initial is not None:
        try:
            index = int(initial)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < len(items):
            item = items[index]
            if not getattr(item, "is_disabled", False) and getattr(item, "disabled_reason", None) is None:
                return index
    return _first_enabled_selection_index(selection)


def _render_selection_view_text(selection: _TextualSelection, selected_idx: int) -> Text:
    view = selection.view
    rendered = Text()
    title, subtitle = _selection_header_lines(_selection_active_header(selection))
    title = title or getattr(view, "title", None) or "Select"
    subtitle = subtitle or getattr(view, "subtitle", None)
    rendered.append(str(title), style="bold")
    rendered.append("\n")
    if subtitle:
        rendered.append(str(subtitle), style="dim")
        rendered.append("\n")
    tabs = list(getattr(view, "tabs", ()) or ())
    if tabs:
        _ensure_selection_tab(selection)
        labels: list[str] = []
        for index, tab in enumerate(tabs):
            label = str(getattr(tab, "label", "") or getattr(tab, "id", ""))
            labels.append(f"[{label}]" if index == selection.active_tab_idx else label)
        rendered.append("  ".join(labels), style="dim")
        rendered.append("\n")
    if selection.search_query:
        rendered.append(f"search: {selection.search_query}\n", style="dim")
    items = _selection_active_items(selection)
    if not items:
        rendered.append("  no matches\n", style="dim")
    if selection.kind in {"model", "permissions"}:
        _append_rust_selection_rows(rendered, items[:12], selected_idx)
    else:
        for index, item in enumerate(items[:12]):
            marker = ">" if index == selected_idx else " "
            current = " (current)" if getattr(item, "is_current", False) else ""
            default = " (default)" if getattr(item, "is_default", False) else ""
            style = "bold cyan" if index == selected_idx else "dim"
            prefix = _plain_line(getattr(item, "name_prefix_spans", ()) or ())
            rendered.append(f"{marker} {prefix}{getattr(item, 'name', '')}{current}{default}\n", style=style)
            description = getattr(item, "description", None)
            if description and index == selected_idx:
                rendered.append(f"  {description}\n", style="dim")
            selected_description = getattr(item, "selected_description", None)
            if selected_description and index == selected_idx:
                rendered.append(f"  {selected_description}\n", style="yellow")
    footer_hint = _selection_active_footer_hint(selection)
    if footer_hint:
        rendered.append(_plain_line(footer_hint), style="dim")
        rendered.append("\n")
    return rendered


def _append_rust_selection_rows(rendered: Text, items: list[Any], selected_idx: int) -> None:
    enabled_items = [item for item in items if not getattr(item, "is_disabled", False) and getattr(item, "disabled_reason", None) is None]
    number_width = len(str(max(len(enabled_items), 1)))
    names: list[str] = []
    descriptions: list[str | None] = []
    enabled_number = 0
    for index, item in enumerate(items):
        if item in enabled_items:
            enabled_number += 1
            numbered = f"{enabled_number:>{number_width}}. "
        else:
            numbered = " " * (number_width + 2)
        marker = ">" if index == selected_idx else " "
        current = " (current)" if getattr(item, "is_current", False) else ""
        default = " (default)" if getattr(item, "is_default", False) else ""
        prefix = _plain_line(getattr(item, "name_prefix_spans", ()) or ())
        names.append(f"{marker} {numbered}{prefix}{getattr(item, 'name', '')}{current}{default}")
        descriptions.append(
            getattr(item, "selected_description", None)
            if index == selected_idx and getattr(item, "selected_description", None) is not None
            else getattr(item, "description", None)
        )
    desc_col = max((len(name) for name in names), default=0) + 2
    term_width = shutil.get_terminal_size((100, 24)).columns
    content_width = max(min(term_width, 100), desc_col + 20)
    desc_width = max(content_width - desc_col, 20)
    for index, (name, description) in enumerate(zip(names, descriptions)):
        style = "bold cyan" if index == selected_idx else "dim"
        if description:
            desc_lines = textwrap.wrap(
                str(description),
                width=desc_width,
                break_long_words=False,
                break_on_hyphens=False,
            ) or [""]
            rendered.append(name.ljust(desc_col), style=style)
            rendered.append(desc_lines[0], style=style if index == selected_idx else "dim")
            rendered.append("\n")
            for continuation in desc_lines[1:]:
                rendered.append(" " * desc_col, style=style)
                rendered.append(continuation, style=style if index == selected_idx else "dim")
                rendered.append("\n")
        else:
            rendered.append(f"{name}\n", style=style)


_KEYMAP_PICKER_ACTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("global", "open_transcript", "Open Transcript", "Open the transcript overlay."),
    ("global", "open_external_editor", "Open External Editor", "Open the current draft in an external editor."),
    ("global", "copy", "Copy", "Copy the last agent response to the clipboard."),
    ("global", "clear_terminal", "Clear Terminal", "Clear the terminal UI."),
    ("global", "toggle_vim_mode", "Toggle Vim Mode", "Turn Vim composer mode on or off."),
    ("global", "toggle_raw_output", "Toggle Raw Output", "Toggle raw scrollback mode."),
    ("chat", "interrupt_turn", "Interrupt Turn", "Interrupt the active turn."),
    ("chat", "decrease_reasoning_effort", "Decrease Reasoning Effort", "Decrease reasoning effort."),
    ("chat", "increase_reasoning_effort", "Increase Reasoning Effort", "Increase reasoning effort."),
    ("chat", "edit_queued_message", "Edit Queued Message", "Edit the most recently queued message."),
    ("composer", "submit", "Submit", "Submit the current composer draft."),
    ("composer", "queue", "Queue", "Queue the draft while a task is running."),
)


def _keymap_picker_widget_for_runtime(app_runtime: TuiAppRuntime) -> KeymapPickerWidgetState:
    raw_keymap = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        names=("tui_keymap", "keymap"),
    )
    try:
        runtime_keymap: Any = RuntimeKeymap.from_config(raw_keymap or {})
    except Exception as exc:
        runtime_keymap = exc
    return KeymapPickerWidgetState(
        tui_keymap=raw_keymap or {},
        runtime_keymap=runtime_keymap,
        fast_mode_enabled=bool(_runtime_value(app_runtime.active_thread_runtime, "fast_mode_enabled")),
    )


def _keymap_selection_view(view: KeymapView) -> SelectionViewParams:
    runtime_keymap = getattr(view, "runtime_keymap", None) or RuntimeKeymap.built_in_defaults()
    selected_action = getattr(view, "selected_action", None)
    action_filter = getattr(view, "filter", None)
    setup_filter = KeymapSetupActionFilter(
        fast_mode_enabled=bool(getattr(action_filter, "fast_mode_enabled", False))
    )
    keymap_config = getattr(view, "config", None) or {}
    if isinstance(selected_action, tuple) and len(selected_action) == 2:
        return build_keymap_picker_selection_for_action(
            runtime_keymap,
            keymap_config,
            setup_filter,
            str(selected_action[0]),
            str(selected_action[1]),
        )
    return build_keymap_picker_selection(runtime_keymap, keymap_config, setup_filter)


def _keymap_selection_kind_for_view(view: object) -> str:
    if isinstance(view, keymap_setup.KeymapCaptureView):
        return "keymap-capture"
    view_id = getattr(view, "view_id", None)
    if view_id == keymap_setup.KEYMAP_ACTION_MENU_VIEW_ID:
        return "keymap-action-menu"
    if view_id == keymap_setup.KEYMAP_REPLACE_BINDING_MENU_VIEW_ID:
        return "keymap-replace-binding"
    return "keymap"


def _keymap_selection_item_events(item: object) -> list[object]:
    events: list[object] = []
    for action in getattr(item, "actions", ()) or ():
        if callable(action):
            tx = _AppEventCollector()
            action(tx)
            events.extend(tx.events)
        else:
            events.append(action)
    for event in getattr(item, "action_events", ()) or ():
        events.append(event)
    return events


@dataclass
class _AppEventCollector:
    events: list[object] = field(default_factory=list)

    def send(self, event: object) -> None:
        self.events.append(event)


def _coerce_keymap_app_event(event: object) -> AppEvent | None:
    if isinstance(event, AppEvent):
        return event
    if isinstance(event, str) and event:
        return AppEvent.of(event)
    if isinstance(event, tuple) and len(event) == 2:
        return AppEvent.of("OpenKeymapActionMenu", context=str(event[0]), action=str(event[1]))
    if isinstance(event, Mapping):
        kind = event.get("type") or event.get("kind")
        if kind:
            payload = {str(key): value for key, value in event.items() if key not in {"type", "kind"}}
            return AppEvent.of(str(kind), **payload)
    kind = getattr(event, "kind", None)
    payload = getattr(event, "payload", None)
    if kind:
        return AppEvent.of(str(kind), **(dict(payload) if isinstance(payload, Mapping) else {}))
    return None


def _keymap_captured_event_from_textual_key(view: object, key: str) -> AppEvent | None:
    if not isinstance(view, keymap_setup.KeymapCaptureView):
        return None
    try:
        code, modifiers = _textual_key_to_key_parts(key)
        spec = keymap_setup.key_parts_to_config_key_spec(code, modifiers)
    except Exception as exc:
        view.error_message = str(exc)
        return None
    return AppEvent.keymap_captured(view.context, view.action, spec, view.intent)


def _textual_key_to_key_parts(key: str) -> tuple[str, set[str]]:
    text = str(key).strip()
    lower = text.lower()
    modifiers: set[str] = set()
    while True:
        if lower.startswith("ctrl+"):
            modifiers.add("CONTROL")
            text = text[5:]
            lower = lower[5:]
            continue
        if lower.startswith("control+"):
            modifiers.add("CONTROL")
            text = text[8:]
            lower = lower[8:]
            continue
        if lower.startswith("alt+"):
            modifiers.add("ALT")
            text = text[4:]
            lower = lower[4:]
            continue
        if lower.startswith("shift+"):
            modifiers.add("SHIFT")
            text = text[6:]
            lower = lower[6:]
            continue
        break
    named = {
        "enter": "Enter",
        "tab": "Tab",
        "backspace": "Backspace",
        "delete": "Delete",
        "escape": "Esc",
        "esc": "Esc",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "home": "Home",
        "end": "End",
        "pageup": "PageUp",
        "page_up": "PageUp",
        "pagedown": "PageDown",
        "page_down": "PageDown",
        "space": " ",
    }
    code = named.get(lower, text)
    if code == text and len(lower) > 1 and lower[0] == "f" and lower[1:].isdigit():
        code = "F" + lower[1:]
    if len(code) == 1 and code.isupper():
        modifiers.add("SHIFT")
    return code, modifiers


def _store_runtime_keymap_config(app_runtime: TuiAppRuntime, keymap_config: object) -> None:
    for target in (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.active_thread_runtime, "config", None),
    ):
        if target is None:
            continue
        _set_runtime_attr(target, "tui_keymap", keymap_config)
        _set_runtime_attr(target, "keymap", keymap_config)


def _config_from_app_runtime(app_runtime: TuiAppRuntime) -> object | None:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    if runtime is None:
        return None
    for name in ("session_config", "config"):
        value = getattr(runtime, name, None)
        if value is not None:
            return value
    return None


def _runtime_keymap_action_bindings(runtime_keymap: Any, context: str, action: str) -> list[Any]:
    section_name = "app" if context == "global" else context
    section = _runtime_value(runtime_keymap, section_name)
    value = _runtime_value(section, action, ())
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return []


def _key_binding_list_label(bindings: Iterable[Any]) -> str:
    labels = [_key_binding_label(binding).replace("+", "-") for binding in bindings]
    labels = [label for label in labels if label]
    return ", ".join(labels) if labels else "unbound"


def _render_keymap_debug_text(view: KeymapView, key: str | None) -> Text:
    runtime_keymap = getattr(view, "runtime_keymap", None) or RuntimeKeymap.built_in_defaults()
    rendered = Text()
    rendered.append("Keypress Inspector\n", style="bold")
    if not key:
        rendered.append("Waiting for a keypress\n", style="dim")
        return rendered
    label = _normalize_textual_key_for_keymap_debug(key)
    action = _keymap_debug_action_for_label(runtime_keymap, label)
    rendered.append(f"{label}\n", style="bold cyan")
    if action:
        rendered.append(action, style="dim")
        rendered.append("\n")
    else:
        rendered.append("No matching action\n", style="dim")
    return rendered


def _render_keymap_capture_text(view: object) -> Text:
    rendered = Text()
    if isinstance(view, keymap_setup.KeymapCaptureView):
        for index, line in enumerate(view.render(width=80)):
            style = "bold" if index == 0 else "dim"
            if line.startswith("Error:"):
                style = "red"
            rendered.append(str(line), style=style)
            rendered.append("\n")
        return rendered
    rendered.append("Remap Shortcut\n", style="bold")
    rendered.append("Press the new key now. Esc cancels.\n", style="dim")
    return rendered


def _normalize_textual_key_for_keymap_debug(key: str) -> str:
    normalized = str(key).strip().lower()
    if normalized.startswith("ctrl+"):
        return "ctrl-" + normalized.removeprefix("ctrl+")
    if normalized.startswith("control+"):
        return "ctrl-" + normalized.removeprefix("control+")
    if normalized.startswith("alt+"):
        return "alt-" + normalized.removeprefix("alt+")
    return normalized


def _keymap_debug_action_for_label(runtime_keymap: Any, label: str) -> str | None:
    matches: list[str] = []
    for context, action, title, _description in _KEYMAP_PICKER_ACTIONS:
        for binding in _runtime_keymap_action_bindings(runtime_keymap, context, action):
            if _key_binding_label(binding).replace("+", "-") == label:
                matches.append(f"{context}.{action} ({title})")
    return ", ".join(matches) if matches else None


def _agent_selection_view(app_runtime: TuiAppRuntime) -> SelectionViewParams:
    rows = app_runtime.agent_navigation.ordered_threads()
    current = app_runtime.current_displayed_thread_id()
    primary = app_runtime.routing_state.primary_thread_id
    items: list[SelectionItem] = []
    selected_idx: int | None = None
    for index, (thread_id, entry) in enumerate(rows):
        name = format_agent_picker_item_name(
            entry.agent_nickname,
            entry.agent_role,
            primary == thread_id,
        )
        closed = " closed" if entry.is_closed else ""
        item = SelectionItem(
            name=name,
            description=f"{thread_id}{closed}",
            is_current=thread_id == current,
            actions=[thread_id],
            dismiss_on_select=True,
        )
        if thread_id == current:
            selected_idx = index
        items.append(item)
    return SelectionViewParams(
        title="Select Agent",
        subtitle=app_runtime.agent_navigation.picker_subtitle(),
        footer_hint="Enter select; Esc/q cancel.",
        items=items,
        initial_selected_idx=selected_idx,
    )


def _multi_agent_enable_view() -> SelectionViewParams:
    return SelectionViewParams(
        title=MULTI_AGENT_ENABLE_TITLE,
        subtitle="Subagents can be enabled for future sessions.",
        footer_hint="Enter select; Esc/q cancel.",
        items=[
            SelectionItem(name=MULTI_AGENT_ENABLE_YES, actions=["enable"], dismiss_on_select=True),
            SelectionItem(name=MULTI_AGENT_ENABLE_NO, actions=["cancel"], dismiss_on_select=True),
        ],
        initial_selected_idx=0,
    )


def _agent_picker_plan_entries(app_runtime: TuiAppRuntime) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    primary = app_runtime.routing_state.primary_thread_id
    for thread_id, entry in app_runtime.agent_navigation.ordered_threads():
        entries.append(
            {
                "thread_id": thread_id,
                "agent_nickname": getattr(entry, "agent_nickname", None),
                "agent_role": getattr(entry, "agent_role", None),
                "is_closed": bool(getattr(entry, "is_closed", False)),
                "is_primary": thread_id == primary,
            }
        )
    return entries


def _runtime_feature_enabled(app_runtime: TuiAppRuntime, feature: str, default: bool = False) -> bool:
    value = _runtime_permission_value(app_runtime, "features", None)
    if value is None:
        value = getattr(getattr(app_runtime.chat_widget, "config", None), "features", None)
    if value is None:
        return bool(default)
    feature_set = value if hasattr(value, "enabled") else _PermissionFeatureSet(value)
    try:
        return bool(feature_set.enabled(feature))
    except Exception:
        return bool(default)


def _command_popup_flags_for_runtime(app_runtime: TuiAppRuntime) -> CommandPopupFlags:
    """Mirror Rust ``ChatComposer::builtin_command_flags`` for Textual.

    Rust keeps slash popup visibility on the composer, but the flags are driven
    by session/runtime feature state.  The Textual shell keeps only a lightweight
    composer widget, so derive the same semantic flags at popup-sync time.
    """

    service_tiers = _service_tier_commands_for_runtime(app_runtime)
    return CommandPopupFlags(
        collaboration_modes_enabled=(
            _runtime_feature_enabled(app_runtime, "Collab")
            or _runtime_feature_enabled(app_runtime, "CollaborationModes")
        ),
        connectors_enabled=_runtime_feature_enabled(app_runtime, "Apps"),
        plugins_command_enabled=_runtime_feature_enabled(app_runtime, "Plugins"),
        service_tier_commands_enabled=(
            bool(service_tiers) and _runtime_feature_enabled(app_runtime, "FastMode")
        ),
        goal_command_enabled=_runtime_feature_enabled(app_runtime, "Goals"),
        personality_command_enabled=(
            _runtime_feature_enabled(app_runtime, "Personality")
            or _runtime_bool_runtime_value(app_runtime, "supports_personality")
            or _runtime_bool_runtime_value(app_runtime, "current_model_supports_personality")
        ),
        realtime_conversation_enabled=_runtime_feature_enabled(app_runtime, "RealtimeConversation"),
        audio_device_selection_enabled=(
            _runtime_bool_runtime_value(app_runtime, "audio_device_selection_enabled")
            or _runtime_bool_runtime_value(app_runtime, "realtime_audio_device_selection_enabled")
        ),
        windows_degraded_sandbox_active=_runtime_bool_runtime_value(app_runtime, "windows_degraded_sandbox_active"),
        side_conversation_active=_runtime_bool_runtime_value(app_runtime, "side_conversation_active"),
    )


def _service_tier_commands_for_runtime(app_runtime: TuiAppRuntime) -> tuple[ServiceTierCommand, ...]:
    """Return Rust ``ServiceTierCommand`` values for the current model."""

    current_model = _runtime_display_model(app_runtime)
    raw_models = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
        names=("available_models", "model_presets", "models"),
    )
    for model in list(raw_models or ()):
        model_name = _runtime_value(model, "model") or _runtime_value(model, "id") or _runtime_value(model, "name")
        if str(model_name or "") != current_model:
            continue
        tiers = _runtime_value(model, "service_tiers") or _runtime_value(model, "serviceTiers") or ()
        commands = tuple(_service_tier_command_from_runtime(tier) for tier in list(tiers or ()))
        return tuple(command for command in commands if command.name)

    raw_commands = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
        names=("service_tier_commands", "serviceTierCommands"),
    )
    if raw_commands is None:
        return ()
    commands = tuple(_service_tier_command_from_runtime(command) for command in list(raw_commands or ()))
    return tuple(command for command in commands if command.name)


def _service_tier_command_from_runtime(value: object) -> ServiceTierCommand:
    return ServiceTierCommand(
        id=str(_runtime_value(value, "id") or _runtime_value(value, "request_value") or _runtime_value(value, "requestValue") or ""),
        name=str(_runtime_value(value, "name") or "").lower(),
        description=str(_runtime_value(value, "description") or ""),
    )


def _runtime_bool_runtime_value(app_runtime: TuiAppRuntime, name: str) -> bool:
    value = _runtime_permission_value(app_runtime, name, None)
    if value is None:
        return False
    return bool(value)


def _set_runtime_feature_enabled(app_runtime: TuiAppRuntime, feature: str, enabled: bool) -> None:
    targets = (
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        getattr(app_runtime.chat_widget, "config", None),
    )
    wrote = False
    for target in targets:
        if target is None:
            continue
        features = getattr(target, "features", None)
        if features is None:
            continue
        feature_set = features if hasattr(features, "set_enabled") else _PermissionFeatureSet(features)
        try:
            feature_set.set_enabled(feature, enabled)
            wrote = True
        except Exception:
            continue
    if not wrote:
        config = _permission_config_for_runtime(app_runtime)
        features = getattr(config, "features", None)
        feature_set = features if hasattr(features, "set_enabled") else _PermissionFeatureSet(features)
        feature_set.set_enabled(feature, enabled)


def _runtime_resume_picker_rows(app_runtime: TuiAppRuntime) -> list[ResumePickerRow]:
    active_runtime = app_runtime.active_thread_runtime
    sources = (
        active_runtime,
        getattr(active_runtime, "session_config", None),
        getattr(active_runtime, "app_server", None),
        getattr(active_runtime, "app_server_session", None),
        app_runtime,
    )
    raw_rows: Any = None
    for source in sources:
        if source is None:
            continue
        for name in (
            "resume_picker_rows",
            "list_resume_picker_rows",
            "list_resume_threads",
            "list_threads_for_resume_picker",
            "thread_list",
        ):
            candidate = getattr(source, name, None)
            if candidate is None:
                continue
            raw_rows = candidate() if callable(candidate) else candidate
            if hasattr(raw_rows, "__await__"):
                raw_rows = _runtime_run_coro_blocking(raw_rows)
            break
        if raw_rows is not None:
            break
    if raw_rows is None:
        return []
    if isinstance(raw_rows, Mapping):
        raw_rows = raw_rows.get("data") or raw_rows.get("rows") or raw_rows.get("threads") or ()
    rows: list[ResumePickerRow] = []
    for raw in list(raw_rows or ()):
        row = _coerce_resume_picker_row(raw)
        if row is not None and row.thread_id:
            rows.append(row)
    return rows


def _coerce_resume_picker_row(raw: Any) -> ResumePickerRow | None:
    if isinstance(raw, ResumePickerRow):
        return raw
    if isinstance(raw, Mapping):
        return row_from_app_server_thread(raw)
    if hasattr(raw, "thread_id") or hasattr(raw, "id"):
        return row_from_app_server_thread(raw)
    return None


def _resume_picker_state_from_rows(
    rows: list[ResumePickerRow],
    action: SessionPickerAction,
    app_runtime: TuiAppRuntime | None = None,
) -> PickerState:
    state = PickerState(show_all=True, action=action)
    if app_runtime is not None:
        state.picker_loader = lambda request: _handle_resume_picker_load_request(app_runtime, state, request)
    state.ingest_page(PickerPage(list(rows)))
    return state


def _resume_picker_selection_view_from_state(state: PickerState) -> SelectionViewParams:
    return _resume_picker_selection_view(list(state.filtered_rows), state.action, state=state)


def _resume_picker_selection_view(
    rows: list[ResumePickerRow],
    action: SessionPickerAction,
    *,
    state: PickerState | None = None,
) -> SelectionViewParams:
    items: list[SelectionItem] = []
    for row in rows:
        thread_id = str(row.thread_id or "")
        if not thread_id:
            continue
        name = row.display_preview() or thread_id
        metadata = []
        if row.cwd is not None:
            metadata.append(str(row.cwd))
        if row.branch:
            metadata.append(str(row.branch))
        if row.model_provider:
            metadata.append(str(row.model_provider))
        if state is not None and row.expanded and row.preview:
            metadata.append(str(row.preview))
        description = " · ".join(metadata) or thread_id
        selected_description = thread_id
        selection = action.selection(row.path, thread_id)
        items.append(
            SelectionItem(
                name=name,
                description=description,
                selected_description=selected_description,
                actions=[selection],
                dismiss_on_select=True,
                search_value=" ".join(
                    str(part)
                    for part in (name, row.preview, row.cwd, row.branch, row.model_provider, thread_id)
                    if part
                ),
            )
        )
    if not items:
        items.append(SelectionItem(name="No sessions found", is_disabled=True))
    subtitle = "Sort: Updated"
    footer_hint = "Enter resume; Esc/q cancel."
    initial_selected_idx = 0
    if state is not None:
        filter_label = getattr(getattr(state, "filter_mode", None), "value", "All")
        sort_label = sort_key_label(getattr(state, "sort_key", "UpdatedAt"))
        toolbar = getattr(getattr(state, "toolbar_control", None), "value", "Filter")
        progress = picker_footer_progress_label(state)
        subtitle = f"Filter: {filter_label}   Sort: {sort_label}   Focus: {toolbar}   {progress}"
        footer_hint = (
            "Enter resume; type search; Space search; Backspace erase; Tab focus; "
            "Right change; Ctrl+T transcript; Ctrl+E expand; Ctrl+O density; Esc clear/cancel."
        )
        initial_selected_idx = state.selected
    return SelectionViewParams(
        title=action.title(),
        subtitle=subtitle,
        footer_hint=footer_hint,
        items=items,
        initial_selected_idx=initial_selected_idx,
    )


def _resume_picker_textual_key(key: str) -> str:
    if key == "escape":
        return "esc"
    if key == "space":
        return " "
    if key in {"shift+tab", "backtab"}:
        return "backtab"
    if key in {"ctrl+t", "ctrl_t"}:
        return "ctrl-t"
    if key in {"ctrl+e", "ctrl_e"}:
        return "ctrl-e"
    if key in {"ctrl+o", "ctrl_o"}:
        return "ctrl-o"
    if key in {"ctrl+l", "ctrl_l"}:
        return "ctrl-l"
    if key in {"ctrl+c", "ctrl_c"}:
        return "ctrl-c"
    if key in {"ctrl+d", "ctrl_d"}:
        return "ctrl-d"
    return key


def _run_picker_coro_synchronously(coro: Any) -> Any:
    try:
        yielded = coro.send(None)
    except StopIteration as exc:
        return exc.value
    finally:
        with contextlib.suppress(Exception):
            coro.close()
    raise RuntimeError(f"resume picker coroutine yielded unexpectedly: {yielded!r}")


def _handle_resume_picker_load_request(app_runtime: TuiAppRuntime, state: PickerState, request: Any) -> None:
    kind = getattr(request, "kind", None)
    payload = getattr(request, "payload", None)
    if kind != "Transcript":
        return
    thread_id = str(payload or "").strip()
    if not thread_id:
        return
    try:
        transcript = _load_resume_picker_transcript(app_runtime, thread_id)
    except Exception as exc:
        transcript = [TranscriptCell("plain", f"Failed to load transcript: {exc}", (f"Failed to load transcript: {exc}",))]
    _run_picker_coro_synchronously(state.handle_background_event(BackgroundEvent.transcript(thread_id, transcript)))


def _load_resume_picker_transcript(app_runtime: TuiAppRuntime, thread_id: str) -> list[TranscriptCell]:
    visibility = _raw_reasoning_visibility_for_runtime(app_runtime)
    for source in _resume_picker_transcript_sources(app_runtime):
        if source is None:
            continue
        thread = _call_thread_reader(source, thread_id)
        if thread is not None:
            return thread_to_transcript_cells(thread, visibility)
    return _load_resume_picker_local_thread(app_runtime, thread_id, visibility)


def _resume_picker_transcript_sources(app_runtime: TuiAppRuntime) -> tuple[Any, ...]:
    active_runtime = app_runtime.active_thread_runtime
    return (
        active_runtime,
        getattr(active_runtime, "app_server_session", None),
        getattr(active_runtime, "app_server", None),
        getattr(active_runtime, "session_config", None),
        app_runtime,
    )


def _call_thread_reader(source: Any, thread_id: str) -> Any | None:
    for name in ("thread_read", "read_thread", "load_session_transcript", "load_resume_transcript"):
        reader = getattr(source, name, None)
        if not callable(reader):
            continue
        for args in ((thread_id, True), (thread_id,), ({"thread_id": thread_id, "include_history": True},)):
            try:
                result = reader(*args)
            except TypeError:
                continue
            if hasattr(result, "__await__"):
                result = _runtime_run_coro_blocking(result)
            return result
    return None


def _load_resume_picker_local_thread(
    app_runtime: TuiAppRuntime,
    thread_id: str,
    visibility: RawReasoningVisibility,
) -> list[TranscriptCell]:
    from pycodex.protocol import ThreadId
    from pycodex.thread_store import LocalThreadStore, LocalThreadStoreConfig, ReadThreadParams

    active_runtime = app_runtime.active_thread_runtime
    codex_home = (
        getattr(active_runtime, "codex_home", None)
        or getattr(getattr(active_runtime, "session_config", None), "codex_home", None)
        or getattr(app_runtime, "codex_home", None)
    )
    if codex_home is None:
        raise RuntimeError("resume transcript provider is not available")
    provider_id = (
        getattr(getattr(active_runtime, "provider", None), "id", None)
        or getattr(getattr(active_runtime, "provider", None), "name", None)
        or getattr(getattr(active_runtime, "session_config", None), "default_model_provider_id", None)
        or "openai"
    )
    store = LocalThreadStore(
        LocalThreadStoreConfig(
            codex_home=Path(codex_home),
            sqlite_home=Path(codex_home),
            default_model_provider_id=str(provider_id),
        )
    )
    thread = _runtime_run_coro_blocking(
        store.read_thread(
            ReadThreadParams(
                thread_id=ThreadId.from_string(thread_id),
                include_archived=False,
                include_history=True,
            )
        )
    )
    return thread_to_transcript_cells(thread, visibility)


def _raw_reasoning_visibility_for_runtime(app_runtime: TuiAppRuntime) -> RawReasoningVisibility:
    config = getattr(app_runtime, "config", None) or getattr(app_runtime.active_thread_runtime, "session_config", None)
    return RawReasoningVisibility.Visible if bool(getattr(config, "show_raw_agent_reasoning", False)) else RawReasoningVisibility.Hidden


def _render_resume_picker_transcript_overlay(cells: Any) -> str:
    lines = ["T R A N S C R I P T", "q/Esc close", ""]
    for cell in list(cells or ()):
        label = str(getattr(cell, "kind", "plain") or "plain")
        text_lines = tuple(getattr(cell, "lines", ()) or ())
        if not text_lines:
            text = str(getattr(cell, "text", "") or "")
            text_lines = tuple(text.splitlines()) if text else ()
        if label:
            lines.append(label)
        if text_lines:
            lines.extend(f"  {line}" for line in text_lines)
        lines.append("")
    return "\n".join(lines).rstrip()


def _active_agent_selection_notice(app_runtime: TuiAppRuntime) -> str:
    thread_id = app_runtime.current_displayed_thread_id()
    label = app_runtime.sync_active_agent_label()
    if label:
        return f"Watching {label}"
    if thread_id:
        return f"Watching thread {thread_id}"
    return "No agent thread selected."


def _selection_header_lines(header: object) -> tuple[str | None, str | None]:
    if header is None:
        return None, None
    lines = getattr(header, "lines", None)
    if lines is not None:
        values = [str(value).strip() for value in lines if value]
        if not values:
            return None, None
        return values[0], "\n".join(values[1:]) if len(values) > 1 else None
    if isinstance(header, tuple):
        values = [_plain_line(value).strip() for value in header if value]
        return (values[0] if values else None, values[1] if len(values) > 1 else None)
    if isinstance(header, str):
        return header, None
    return str(header), None


def _runtime_model_presets(app_runtime: TuiAppRuntime) -> tuple[ModelPreset, ...]:
    current = _runtime_display_model(app_runtime)
    raw = _runtime_first_value(
        app_runtime.active_thread_runtime,
        getattr(app_runtime.active_thread_runtime, "session_config", None),
        names=("available_models", "model_presets", "models"),
    )
    presets = tuple(_model_preset_from_runtime(item, current) for item in (raw or ()))
    visible = tuple(preset for preset in presets if preset.model)
    if visible:
        return visible
    managed = _runtime_model_manager_presets(app_runtime, current)
    if managed:
        return managed
    bundled = _bundled_model_popup_presets(current)
    if bundled:
        return bundled
    return (_fallback_current_model_preset(current),)


def _runtime_model_manager_presets(app_runtime: TuiAppRuntime, current: str) -> tuple[ModelPreset, ...]:
    runtime = app_runtime.active_thread_runtime
    session_config = getattr(runtime, "session_config", None)
    services = getattr(session_config, "services", None)
    sources = (
        runtime,
        getattr(services, "models_manager", None),
        getattr(session_config, "models_manager", None),
        getattr(app_runtime, "models_manager", None),
    )
    for source in sources:
        if source is None:
            continue
        for method_name in ("list_models", "try_list_models"):
            method = getattr(source, method_name, None)
            if not callable(method):
                continue
            try:
                if method_name == "list_models":
                    result = method("online_if_uncached")
                else:
                    result = method()
            except TypeError:
                try:
                    result = method()
                except Exception:
                    continue
            except Exception:
                continue
            try:
                if hasattr(result, "__await__"):
                    result = _runtime_run_coro_blocking(result)
            except Exception:
                continue
            presets = tuple(_model_preset_from_runtime(item, current) for item in (result or ()))
            visible = tuple(preset for preset in presets if preset.model)
            if visible:
                return visible
    return ()


def _bundled_model_popup_presets(current: str) -> tuple[ModelPreset, ...]:
    try:
        from pycodex.models_manager import bundled_models_response, model_presets_from_models
        from pycodex.protocol import ModelsResponse
    except Exception:
        return ()
    try:
        response = ModelsResponse.from_mapping(bundled_models_response())
        raw = model_presets_from_models(response.models)
    except Exception:
        return ()
    presets = tuple(_model_preset_from_runtime(item, current) for item in raw)
    return tuple(preset for preset in presets if preset.model)


def _fallback_current_model_preset(current: str) -> ModelPreset:
    if str(current).startswith("codex-auto-"):
        return ModelPreset(model=current, is_default=True)
    return ModelPreset(
        model=current,
        default_reasoning_effort=ReasoningEffortConfig.Medium,
        supported_reasoning_efforts=(
            ReasoningEffortPreset(ReasoningEffortConfig.Low, "Fast responses with lighter reasoning"),
            ReasoningEffortPreset(ReasoningEffortConfig.Medium, "Balances speed and reasoning depth for everyday tasks"),
            ReasoningEffortPreset(ReasoningEffortConfig.High, "Greater reasoning depth for complex problems"),
            ReasoningEffortPreset(ReasoningEffortConfig.XHigh, "Extra high reasoning depth for complex problems"),
        ),
        is_default=True,
    )


def _model_preset_from_runtime(value: object, current_model: str) -> ModelPreset:
    if isinstance(value, str):
        return ModelPreset(model=value, is_default=value == current_model)
    model = _runtime_value(value, "model") or _runtime_value(value, "id") or _runtime_value(value, "name")
    if model is None:
        return ModelPreset(model="")
    effort = _coerce_reasoning_effort(
        _runtime_value(value, "default_reasoning_effort")
        or _runtime_value(value, "reasoning_effort")
        or _runtime_value(value, "effort")
    )
    return ModelPreset(
        model=str(model),
        description=str(_runtime_value(value, "description") or ""),
        default_reasoning_effort=effort or ReasoningEffortConfig.Medium,
        supported_reasoning_efforts=_coerce_supported_reasoning_efforts(
            _runtime_value(value, "supported_reasoning_efforts")
            or _runtime_value(value, "supported_efforts")
            or _runtime_value(value, "reasoning_efforts")
        ),
        is_default=bool(_runtime_value(value, "is_default")) or str(model) == current_model,
        show_in_picker=bool(_runtime_value(value, "show_in_picker", True)),
    )


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


def _workspace_command_runner(app_runtime: TuiAppRuntime) -> object | None:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    runner = _runtime_value(runtime, "workspace_command_runner", None)
    if runner is not None:
        return runner
    request_handle = _request_handle_from_runtime(runtime)
    if request_handle is not None:
        return AppServerWorkspaceCommandRunner.new(request_handle)
    return None


def _request_handle_from_runtime(runtime: object | None) -> object | None:
    if runtime is None:
        return None
    for name in ("request_handle", "get_request_handle"):
        handle = getattr(runtime, name, None)
        if callable(handle):
            handle = handle()
        if handle is not None:
            return handle
    container = getattr(runtime, "app_server", None)
    if container is not None:
        handle = getattr(container, "request_handle", None)
        if callable(handle):
            handle = handle()
        if handle is not None:
            return handle
    return None


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


def _coerce_reasoning_effort(value: object | None) -> ReasoningEffortConfig | None:
    if value is None:
        return None
    if isinstance(value, ReasoningEffortConfig):
        return value
    normalized = str(getattr(value, "value", value)).replace("-", "").replace("_", "").lower()
    aliases = {
        "none": ReasoningEffortConfig.None_,
        "minimal": ReasoningEffortConfig.Minimal,
        "low": ReasoningEffortConfig.Low,
        "medium": ReasoningEffortConfig.Medium,
        "high": ReasoningEffortConfig.High,
        "xhigh": ReasoningEffortConfig.XHigh,
        "extrahigh": ReasoningEffortConfig.XHigh,
    }
    return aliases.get(normalized)


def _coerce_supported_reasoning_efforts(value: object | None) -> tuple[ReasoningEffortPreset, ...]:
    if not value:
        return ()
    presets: list[ReasoningEffortPreset] = []
    for item in value if isinstance(value, (list, tuple)) else (value,):
        if isinstance(item, ReasoningEffortPreset):
            presets.append(item)
            continue
        effort = _coerce_reasoning_effort(_runtime_value(item, "effort", item))
        if effort is not None:
            presets.append(ReasoningEffortPreset(effort=effort, description=str(_runtime_value(item, "description", "") or "")))
    return tuple(presets)


def _raw_output_mode(app_runtime: TuiAppRuntime) -> bool:
    chat_widget = getattr(app_runtime, "chat_widget", None)
    raw = getattr(chat_widget, "raw_output_mode", None)
    if callable(raw):
        return bool(raw())
    if raw is not None:
        return bool(raw)
    return bool(getattr(chat_widget, "raw_mode", False))


def _parse_raw_output_arg(value: str) -> bool | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def _parse_slash_command(prompt: str) -> SlashCommand | None:
    command, _, _argument = prompt.strip().partition(" ")
    try:
        return SlashCommand.parse(command)
    except ValueError:
        return None


def _runtime_thread_goal_get(app_runtime: TuiAppRuntime, thread_id: Any) -> tuple[ThreadGoal | None, Any | None]:
    method = _runtime_thread_goal_method(app_runtime, "thread_goal_get", "get_thread_goal")
    if method is None:
        return None, RuntimeError("thread goals are not available in this runtime")
    try:
        result = _call_thread_goal_method(method, thread_id=thread_id)
    except Exception as exc:
        return None, exc
    return _coerce_thread_goal_result(result), None


def _runtime_thread_goal_set(
    app_runtime: TuiAppRuntime,
    thread_id: Any,
    *,
    objective: str | None = None,
    status: Any = None,
    token_budget: int | None = None,
    replace: bool = False,
) -> tuple[ThreadGoal | None, Any | None]:
    if replace:
        _runtime_thread_goal_clear(app_runtime, thread_id)
    method = _runtime_thread_goal_method(app_runtime, "thread_goal_set", "set_thread_goal")
    if method is None:
        return None, RuntimeError("thread goals are not available in this runtime")
    payload = {"thread_id": thread_id}
    if objective is not None:
        payload["objective"] = objective
    if status is not None:
        payload["status"] = getattr(status, "value", status)
    if token_budget is not None:
        payload["token_budget"] = token_budget
    try:
        result = _call_thread_goal_method(method, **payload)
    except Exception as exc:
        return None, exc
    return _coerce_thread_goal_result(result) or ThreadGoal(
        status=status or ThreadGoalStatus.Active,
        thread_id=str(thread_id),
        objective=objective or "",
        token_budget=token_budget,
    ), None


def _runtime_thread_goal_clear(app_runtime: TuiAppRuntime, thread_id: Any) -> tuple[bool | None, Any | None]:
    method = _runtime_thread_goal_method(app_runtime, "thread_goal_clear", "clear_thread_goal")
    if method is None:
        return None, RuntimeError("thread goals are not available in this runtime")
    try:
        result = _call_thread_goal_method(method, thread_id=thread_id)
    except Exception as exc:
        return None, exc
    if isinstance(result, bool):
        return result, None
    if isinstance(result, Mapping):
        for key in ("cleared", "deleted", "ok", "success"):
            if key in result:
                return bool(result[key]), None
    return True, None


def _runtime_thread_goal_method(app_runtime: TuiAppRuntime, *names: str) -> Any | None:
    runtime = app_runtime.active_thread_runtime
    sources = (
        runtime,
        getattr(runtime, "session_config", None),
        getattr(runtime, "app_server_session", None),
        getattr(runtime, "app_server", None),
        app_runtime,
    )
    for source in sources:
        if source is None:
            continue
        for name in names:
            method = getattr(source, name, None)
            if callable(method):
                return method
    return None


def _call_thread_goal_method(method: Any, **payload: Any) -> Any:
    try:
        result = method(**payload)
    except TypeError:
        thread_id = payload.get("thread_id")
        if "objective" in payload:
            try:
                result = method(thread_id, payload.get("objective"), payload.get("status"), payload.get("token_budget"))
            except TypeError:
                result = method(thread_id, payload.get("objective"), payload.get("status"))
        elif "status" in payload:
            result = method(thread_id, payload.get("status"))
        else:
            result = method(thread_id)
    if hasattr(result, "__await__"):
        result = _runtime_run_coro_blocking(result)
    return result


def _coerce_thread_goal_result(result: Any) -> ThreadGoal | None:
    if result is None:
        return None
    if isinstance(result, ThreadGoal):
        return result
    raw = result
    if isinstance(raw, Mapping):
        raw = raw.get("goal", raw.get("thread_goal", raw.get("data", raw)))
        if raw is None:
            return None
    else:
        for name in ("goal", "thread_goal", "data"):
            value = getattr(raw, name, None)
            if value is not None:
                raw = value
                break
    status = _runtime_value(raw, "status", None)
    if status is None:
        return None
    status = getattr(status, "value", status)
    return ThreadGoal(
        status=status,
        thread_id=str(_runtime_value(raw, "thread_id", _runtime_value(raw, "id", "thread-1"))),
        objective=str(_runtime_value(raw, "objective", "")),
        token_budget=_runtime_value(raw, "token_budget", None),
        tokens_used=int(_runtime_value(raw, "tokens_used", 0) or 0),
        time_used_seconds=int(_runtime_value(raw, "time_used_seconds", 0) or 0),
        created_at=int(_runtime_value(raw, "created_at", 0) or 0),
        updated_at=int(_runtime_value(raw, "updated_at", 0) or 0),
    )


def _thread_goal_summary_text(goal: ThreadGoal) -> str:
    return "\n".join(
        part
        for part in (
            "Goal",
            f"Status: {getattr(goal.status, 'value', goal.status)}",
            f"Objective: {goal.objective}",
            f"Usage: {goal.tokens_used}/{goal.token_budget} tokens used" if goal.token_budget is not None else f"Usage: {goal.tokens_used} tokens used",
        )
        if part
    )


def _edited_goal_status(status: Any) -> ThreadGoalStatus:
    value = getattr(status, "value", status)
    normalized = ThreadGoalStatus(value)
    if normalized in {ThreadGoalStatus.BudgetLimited, ThreadGoalStatus.Complete}:
        return ThreadGoalStatus.Active
    return normalized


def _thread_goal_selection_view(plan: ThreadGoalActionPlan) -> SelectionViewParams:
    view = plan.selection_view
    if view is None:
        return SelectionViewParams(title="Goal", items=[])
    return SelectionViewParams(
        title=view.title,
        subtitle=view.subtitle,
        footer_hint=view.footer_hint,
        items=[
            SelectionItem(
                name=item.name,
                description=item.description,
                actions=[item.event] if item.event is not None else [],
                dismiss_on_select=item.dismiss_on_select,
            )
            for item in view.items
        ],
    )


def _slash_help_notice() -> str:
    commands = [f"/{name}" for name, _command in built_in_slash_commands()]
    if commands and commands[0] == "/model":
        commands[0] = "/model [name]"
    commands.extend(["/transcript", "/raw [on|off]", "/help"])
    return "Available: " + ", ".join(commands)


def _runtime_terminal_title_items(app_runtime: TuiAppRuntime) -> tuple[TerminalTitleItem, ...]:
    items, _invalid_items = parse_terminal_title_items_with_invalids(_runtime_terminal_title_item_ids(app_runtime))
    return tuple(items)


def _runtime_status_line_items(app_runtime: TuiAppRuntime) -> tuple[StatusLineItem, ...]:
    items, _invalid_items = parse_status_line_items_with_invalids(_runtime_status_line_item_ids(app_runtime))
    return tuple(items)


def _raw_output_mode_notice(enabled: bool) -> str:
    if enabled:
        return "Raw output mode on: transcript text is shown for clean terminal selection."
    return "Raw output mode off: rich transcript rendering restored."


def _event_stream_closed(event_stream: object) -> bool:
    closed = getattr(event_stream, "closed", False)
    return bool(closed() if callable(closed) else closed)


def _is_tty(stream: Any) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(callable(isatty) and isatty())


__all__ = [
    "PyCodexTextualApp",
    "configure_app_runtime_thread_identity",
    "run_textual_tui",
    "should_use_textual_tui",
]
