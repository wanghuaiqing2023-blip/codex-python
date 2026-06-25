"""Python port entry point for Codex TUI.

Upstream Rust implementation for the terminal UI is in ``codex-rs/tui``.
This package mirrors the Rust ``codex-tui`` module boundaries so behavior can be
ported module-by-module.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
import textwrap
from dataclasses import dataclass
from enum import Enum
from os import terminal_size
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from ._porting import RustTuiModule
from .app.runtime import ActiveThreadRuntime, TuiAppRuntime
from .chatwidget import extract_first_bold
from .chatwidget.protocol import ServerNotification
from pycodex.exec.session import RemoteAppServerEndpoint, app_server_control_socket_path

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="lib",
    source="codex/codex-rs/tui/src/lib.rs",
    status="complete",
)


class TUIUnavailableError(RuntimeError):
    """Backward-compatible exception class for callers that still import it."""


class ExitReason(Enum):
    """Python boundary for Rust ``codex_tui::ExitReason``."""

    UNKNOWN = "unknown"
    USER_REQUESTED = "UserRequested"
    FATAL = "Fatal"

    @classmethod
    def user_requested(cls) -> "ExitReason":
        return cls.USER_REQUESTED

    @classmethod
    def fatal(cls, message: str) -> "ExitReasonPayload":
        return ExitReasonPayload(cls.FATAL, message)


@dataclass(frozen=True)
class ExitReasonPayload:
    reason: ExitReason
    message: str | None = None


@dataclass(frozen=True)
class AppExitInfo:
    """Python boundary for Rust ``codex_tui::AppExitInfo``."""

    exit_reason: ExitReason | ExitReasonPayload = ExitReason.USER_REQUESTED
    token_usage: Any = None
    thread_id: str | None = None
    thread_name: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def reason(self) -> ExitReason | ExitReasonPayload:
        return self.exit_reason


@dataclass(frozen=True)
class AppServerTarget:
    kind: str
    endpoint: RemoteAppServerEndpoint | None = None

    @classmethod
    def embedded(cls) -> "AppServerTarget":
        return cls("Embedded")

    @classmethod
    def local_daemon(cls, endpoint: RemoteAppServerEndpoint) -> "AppServerTarget":
        return cls("LocalDaemon", endpoint=endpoint)

    @classmethod
    def remote(cls, endpoint: RemoteAppServerEndpoint) -> "AppServerTarget":
        return cls("Remote", endpoint=endpoint)

    def uses_remote_workspace(self) -> bool:
        return self.kind == "Remote"

    def thread_params_mode(self) -> str:
        return "Remote" if self.uses_remote_workspace() else "Embedded"


@dataclass(frozen=True)
class Cli:
    """Python boundary for Rust ``codex_tui::Cli``.

    The concrete argparse mapping will be filled in from ``tui/src/cli.rs``.
    """

    raw_args: tuple[str, ...] = ()


TUI_LOG_FILE_NAME = "codex-tui.log"


def remote_addr_parse_error_message(addr: str) -> str:
    return (
        f"invalid remote address `{addr}`; expected `ws://host:port`, "
        "`wss://host:port`, `unix://`, or `unix://PATH`"
    )


def remote_addr_has_explicit_port(addr: str, parsed: Any | None = None) -> bool:
    parsed = urlparse(addr) if parsed is None else parsed
    if parsed.hostname is None:
        return False
    if parsed.port is not None:
        return True
    if "://" not in addr:
        return False
    rest = addr.split("://", 1)[1]
    authority = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host_and_port = authority.rsplit("@", 1)[-1]
    default = {"ws": 80, "wss": 443}.get(parsed.scheme)
    if default is None:
        return False
    expected_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return host_and_port == f"{expected_host}:{default}"


def websocket_url_supports_auth_token(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme == "wss" and parsed.hostname:
        return True
    if parsed.scheme != "ws" or not parsed.hostname:
        return False
    host = parsed.hostname
    if host.lower() == "localhost":
        return True
    try:
        import ipaddress

        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_remote_addr(
    addr: str,
    *,
    codex_home: Path | str | None = None,
    cwd: Path | str | None = None,
) -> RemoteAppServerEndpoint:
    if addr.startswith("unix://"):
        socket_path = addr.removeprefix("unix://")
        if socket_path == "":
            if codex_home is None:
                from pycodex.utils.home_dir import find_codex_home

                codex_home = find_codex_home()
            return RemoteAppServerEndpoint.unix_socket(app_server_control_socket_path(codex_home))
        path = Path(socket_path)
        if not path.is_absolute():
            path = (Path.cwd() if cwd is None else Path(cwd)) / path
        return RemoteAppServerEndpoint.unix_socket(path)

    parsed = urlparse(addr)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(remote_addr_parse_error_message(addr)) from exc
    if (
        parsed.scheme in {"ws", "wss"}
        and parsed.hostname is not None
        and remote_addr_has_explicit_port(addr, parsed)
        and (parsed.path or "/") == "/"
        and parsed.query == ""
        and parsed.fragment == ""
        and port is not None
    ):
        return RemoteAppServerEndpoint.websocket(parsed.geturl())
    raise ValueError(remote_addr_parse_error_message(addr))


def remote_addr_supports_auth_token(endpoint: RemoteAppServerEndpoint) -> bool:
    if endpoint.kind != "websocket":
        return False
    return websocket_url_supports_auth_token(str(endpoint.websocket_url))


def app_server_target_for_launch(
    explicit_remote_endpoint: RemoteAppServerEndpoint | None,
    default_daemon_socket: Path | str | None,
    can_reuse_implicit_local_daemon: bool,
) -> AppServerTarget:
    if explicit_remote_endpoint is not None:
        return AppServerTarget.remote(explicit_remote_endpoint)
    if can_reuse_implicit_local_daemon and default_daemon_socket is not None:
        return AppServerTarget.local_daemon(RemoteAppServerEndpoint.unix_socket(default_daemon_socket))
    return AppServerTarget.embedded()


def latest_session_cwd_filter(
    uses_remote_workspace: bool,
    remote_cwd_override: Path | str | None,
    config: Any,
    show_all: bool,
) -> Path | None:
    if show_all:
        return None
    if uses_remote_workspace:
        return None if remote_cwd_override is None else Path(remote_cwd_override)
    cwd = getattr(config, "cwd", None)
    if cwd is None and isinstance(config, dict):
        cwd = config.get("cwd")
    return None if cwd is None else Path(cwd)


def config_cwd_for_app_server_target(
    cwd: Path | str | None,
    app_server_target: AppServerTarget,
    environment_manager: Any | None = None,
) -> Path | None:
    if app_server_target.uses_remote_workspace() or _environment_manager_is_remote(environment_manager):
        return None
    target = Path.cwd() if cwd is None else Path(cwd)
    return target.resolve(strict=True)


def _environment_manager_is_remote(environment_manager: Any | None) -> bool:
    if environment_manager is None:
        return False
    default_environment = getattr(environment_manager, "default_environment", None)
    environment = default_environment() if callable(default_environment) else getattr(environment_manager, "environment", None)
    is_remote = getattr(environment, "is_remote", None)
    return bool(is_remote() if callable(is_remote) else is_remote)


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


ENTER_ALT_SCREEN = "\x1b[?1049h"
LEAVE_ALT_SCREEN = "\x1b[?1049l"
ENABLE_ALT_SCROLL = "\x1b[?1007h"
DISABLE_ALT_SCROLL = "\x1b[?1007l"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_SCREEN = "\x1b[2J"
CURSOR_HOME = "\x1b[H"
RESET_STYLE = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
SAVE_CURSOR = "\x1b[s"
RESTORE_CURSOR = "\x1b[u"


def run_terminal_tui(
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None,
    active_thread_runtime: ActiveThreadRuntime | None = None,
    use_alt_screen: bool = True,
) -> int:
    """Run PyCodex's dependency-light terminal TUI runtime.

    Rust ``codex-cli`` enters ``codex_tui::run_main`` when no subcommand is
    provided. Rust ``tui.rs`` owns terminal modes, alternate screen entry, and
    restoration; this Python boundary mirrors those terminal side effects and
    forwards submitted prompts to the already-ported exec runtime.
    """

    if _enabled(os.environ.get("PYCODEX_TUI_FALLBACK")):
        stderr.write("pycodex: interactive TUI is disabled in this Python port.\n")
        return 0

    input_stream = stdin
    if input_stream is None:
        import sys

        input_stream = sys.stdin

    readline = getattr(input_stream, "readline", None)
    if not callable(readline):
        stderr.write("pycodex: interactive input stream does not support readline().\n")
        return 2

    writer = stdout
    _configure_output_errors(writer)
    transcript_lines: list[str] = []
    interactive_input = _is_interactive_input(input_stream)
    if active_thread_runtime is None:
        stderr.write("pycodex: TUI requires an active thread runtime.\n")
        return 2
    app_runtime = TuiAppRuntime(active_thread_runtime=active_thread_runtime)
    try:
        _enter_terminal(writer, use_alt_screen=use_alt_screen)
        _draw_header(writer, status="Ready", prompt_hint="Type a message. /quit exits.")

        while True:
            writer.write(f"{CYAN}> {RESET_STYLE}")
            _flush(writer)
            line = readline()
            if line == "":
                writer.write("\n")
                return 0
            if isinstance(line, bytes):
                prompt = line.decode("utf-8", errors="replace").rstrip("\r\n")
            else:
                prompt = str(line).rstrip("\r\n")
            if not prompt.strip():
                continue
            if prompt.strip().lower() in {"/quit", "/exit", ":q", "q", "quit", "exit"}:
                return 0
            if prompt.strip().lower() in {"/transcript", "/history"}:
                _run_transcript_pager(writer, input_stream, transcript_lines)
                writer.write(f"{DIM}status:{RESET_STYLE} {GREEN}Ready{RESET_STYLE}\n")
                writer.write(f"{DIM}Type another message. /quit exits.{RESET_STYLE}\n")
                continue
            user_lines = _append_history_entry(writer, "you", prompt, color=CYAN)
            transcript_lines.extend(user_lines)
            writer.write(f"{DIM}status:{RESET_STYLE} {GREEN}Working{RESET_STYLE}\n")
            _flush(writer)
            code, output, live_rendered, turn_transcript_lines = _run_turn_event_loop(writer, app_runtime, prompt)
            transcript_lines.extend(turn_transcript_lines)
            if output.strip():
                if live_rendered:
                    reply_lines = _history_entry_lines("codex", output.rstrip())
                else:
                    reply_lines = _append_history_entry(writer, "codex", output.rstrip(), color=GREEN)
                transcript_lines.extend(reply_lines)
                if interactive_input and _should_auto_page(reply_lines):
                    _run_transcript_pager(writer, input_stream, transcript_lines)
            _flush(writer)
            if code != 0:
                return code
            writer.write(f"{DIM}status:{RESET_STYLE} {GREEN}Ready{RESET_STYLE}\n")
            writer.write(f"{DIM}Type another message. /quit exits.{RESET_STYLE}\n")
    finally:
        _leave_terminal(writer, use_alt_screen=use_alt_screen)


def _run_turn_event_loop(
    writer: TextIO,
    app_runtime: TuiAppRuntime,
    prompt: str,
) -> tuple[int, str, bool, list[str]]:
    event_stream = app_runtime.submit_user_turn(prompt)
    started = time.monotonic()
    progress_interval = _progress_interval_seconds()
    next_update = started + progress_interval
    poll_interval = min(0.1, progress_interval)
    code = 0
    failure_message = ""
    live_render = _LiveAgentRenderState()
    while True:
        event = event_stream.next_event(timeout=poll_interval)
        if event is None:
            if _event_stream_closed(event_stream):
                if app_runtime.chat_widget.turn.bottom_pane.task_running:
                    code = 1
                    failure_message = "active thread event stream closed before turn completed"
                break
            if not app_runtime.chat_widget.turn.bottom_pane.task_running:
                continue
        else:
            if event.kind == "TurnCompleted":
                turn = event.payload.get("turn", {}) if isinstance(event.payload, dict) else {}
                if str(turn.get("status")) == "Failed":
                    error = turn.get("error") or {}
                    code = int(error.get("exit_code") or 1)
                    failure_message = str(error.get("message") or "")
            app_runtime.handle_notification(event)
            if event.kind == "AgentMessageDelta":
                _write_live_agent_delta(writer, live_render, _event_delta(event))
            elif event.kind in {"ReasoningSummaryTextDelta", "ReasoningTextDelta", "ReasoningSummaryPartAdded"}:
                _write_live_reasoning_event(
                    writer,
                    live_render,
                    event,
                    show_raw_agent_reasoning=_show_raw_agent_reasoning(app_runtime),
                )
            elif event.kind == "ResponseStarted":
                _write_live_response_started(writer, live_render)
            elif event.kind in {"ItemStarted", "ItemCompleted"}:
                _write_live_command_event(writer, live_render, event)
                _write_live_reasoning_event(
                    writer,
                    live_render,
                    event,
                    show_raw_agent_reasoning=_show_raw_agent_reasoning(app_runtime),
                )
            if event.kind == "TurnCompleted":
                break
        now = time.monotonic()
        if now < next_update:
            continue
        if live_render.started:
            next_update = now + progress_interval
            continue
        elapsed = int(now - started)
        status = app_runtime.chat_widget.run_state_status_text()
        detail = _progress_detail_for_status(status, live_render)
        writer.write(
            f"{SAVE_CURSOR}\r{DIM}status:{RESET_STYLE} "
            f"{GREEN}{status}{RESET_STYLE} {DIM}{elapsed}s elapsed; {detail}{RESET_STYLE}"
            f"{RESTORE_CURSOR}"
        )
        _flush(writer)
        next_update = now + progress_interval
    output = app_runtime.chat_widget.assistant_text()
    if live_render.started:
        writer.write("\n")
        _flush(writer)
    return code, output or failure_message, live_render.started, live_render.final_reasoning_transcript_lines()


def _event_stream_closed(event_stream: object) -> bool:
    closed = getattr(event_stream, "closed", False)
    return bool(closed() if callable(closed) else closed)


def _show_raw_agent_reasoning(app_runtime: TuiAppRuntime) -> bool:
    config = getattr(getattr(app_runtime, "chat_widget", object()), "config", object())
    return bool(getattr(config, "show_raw_agent_reasoning", False))


@dataclass
class _LiveAgentRenderState:
    started: bool = False
    at_line_start: bool = True
    reasoning_started: bool = False
    reasoning_buffer: str = ""
    full_reasoning_buffer: str = ""
    reasoning_header: str | None = None
    displayed_reasoning_header: str | None = None
    raw_reasoning_buffer: str = ""

    def push_reasoning_summary_delta(self, delta: str) -> None:
        self.reasoning_started = True
        self.reasoning_buffer += delta
        header = extract_first_bold(self.reasoning_buffer)
        if header is not None:
            self.reasoning_header = header

    def push_reasoning_section_break(self) -> None:
        self.reasoning_started = True
        self.full_reasoning_buffer += self.reasoning_buffer
        self.full_reasoning_buffer += "\n\n"
        self.reasoning_buffer = ""

    def final_reasoning_text(self) -> str:
        return self.full_reasoning_buffer + self.reasoning_buffer

    def final_reasoning_transcript_lines(self) -> list[str]:
        text = self.final_reasoning_text().strip()
        if not text:
            return []
        return _history_entry_lines("reasoning", text)


def _event_delta(event: ServerNotification) -> str:
    payload = event.payload
    if isinstance(payload, dict):
        value = payload.get("delta")
    else:
        value = getattr(payload, "delta", "")
    return "" if value is None else str(value)


def _write_live_agent_delta(writer: TextIO, state: _LiveAgentRenderState, delta: str) -> None:
    if not delta:
        return
    if not state.started:
        writer.write(f"\n{GREEN}codex{RESET_STYLE}\n")
        state.started = True
        state.at_line_start = True
    for part in delta.splitlines(keepends=True):
        if state.at_line_start:
            writer.write("  ")
        writer.write(part)
        state.at_line_start = part.endswith("\n")
    if delta and not delta.splitlines(keepends=True):
        if state.at_line_start:
            writer.write("  ")
        writer.write(delta)
        state.at_line_start = False
    _flush(writer)


def _write_live_command_event(writer: TextIO, state: _LiveAgentRenderState, event: ServerNotification) -> None:
    item = _event_item(event)
    if not isinstance(item, dict) or item.get("kind") != "CommandExecution":
        return
    command = str(item.get("command") or "").strip()
    if not command:
        return
    if state.started and not state.at_line_start:
        writer.write("\n")
        state.at_line_start = True
    if event.kind == "ItemStarted":
        writer.write(f"{DIM}• Running{RESET_STYLE} {command}\n")
    else:
        status = str(item.get("status") or "Completed")
        exit_code = item.get("exit_code")
        suffix = f" exit {exit_code}" if exit_code is not None else ""
        writer.write(f"{DIM}• {status}{suffix}:{RESET_STYLE} {command}\n")
        output = _command_output_preview(item)
        if output:
            for line in output.splitlines():
                writer.write(f"{DIM}  {line}{RESET_STYLE}\n")
    _flush(writer)


def _write_live_reasoning_event(
    writer: TextIO,
    state: _LiveAgentRenderState,
    event: ServerNotification,
    *,
    show_raw_agent_reasoning: bool = False,
) -> None:
    if event.kind == "ReasoningSummaryTextDelta":
        state.push_reasoning_summary_delta(_event_delta(event))
        _write_live_reasoning_status(writer, state)
        return
    if event.kind == "ReasoningTextDelta":
        if show_raw_agent_reasoning:
            state.raw_reasoning_buffer += _event_delta(event)
            state.push_reasoning_summary_delta(_event_delta(event))
            _write_live_reasoning_status(writer, state)
        return
    if event.kind == "ReasoningSummaryPartAdded":
        state.push_reasoning_section_break()
        return
    if event.kind != "ItemStarted":
        return
    item = _event_item(event)
    if not isinstance(item, dict) or item.get("kind") != "Reasoning":
        return
    if state.reasoning_started:
        return
    if state.started and not state.at_line_start:
        writer.write("\n")
        state.at_line_start = True
    writer.write(f"{DIM}Thinking{RESET_STYLE}\n")
    state.reasoning_started = True
    _flush(writer)


def _write_live_reasoning_status(writer: TextIO, state: _LiveAgentRenderState) -> None:
    if state.started:
        return
    header = state.reasoning_header
    if not header or header == state.displayed_reasoning_header:
        return
    state.displayed_reasoning_header = header
    writer.write(f"{DIM}Thinking: {header}{RESET_STYLE}\n")
    _flush(writer)


def _write_live_response_started(writer: TextIO, state: _LiveAgentRenderState) -> None:
    if state.reasoning_started or state.started:
        return
    writer.write(f"{DIM}Thinking{RESET_STYLE}\n")
    state.reasoning_started = True
    _flush(writer)


def _event_item(event: ServerNotification) -> Any:
    payload = event.payload
    if isinstance(payload, dict):
        return payload.get("item")
    return getattr(payload, "item", None)


def _progress_detail_for_status(status: str, state: _LiveAgentRenderState) -> str:
    if state.reasoning_header:
        return state.reasoning_header
    if str(status) == "Thinking" or state.reasoning_started:
        return "reasoning..."
    return "waiting for model..."


def _command_output_preview(item: dict[str, Any], *, max_chars: int = 600) -> str:
    output = item.get("aggregated_output")
    if not isinstance(output, str):
        return ""
    text = output.strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n..."


def _progress_interval_seconds() -> float:
    raw = os.environ.get("PYCODEX_TUI_PROGRESS_INTERVAL_SECONDS")
    if raw is not None:
        try:
            return max(float(raw), 0.01)
        except ValueError:
            return 5.0
    return 5.0


def run_line_mode_tui(
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None,
    active_thread_runtime: ActiveThreadRuntime,
) -> int:
    """Backward-compatible alias for the terminal TUI runtime."""

    return run_terminal_tui(stdout=stdout, stderr=stderr, stdin=stdin, active_thread_runtime=active_thread_runtime)


def _enter_terminal(writer: TextIO, *, use_alt_screen: bool) -> None:
    if use_alt_screen:
        writer.write(ENTER_ALT_SCREEN)
        writer.write(ENABLE_ALT_SCROLL)
    writer.write(HIDE_CURSOR)
    writer.write(CURSOR_HOME)
    _flush(writer)


def _configure_output_errors(writer: TextIO) -> None:
    """Prefer replacement over crashing on terminal encoding edge cases."""

    reconfigure = getattr(writer, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(errors="replace")
        except (OSError, TypeError, ValueError):
            pass


def _leave_terminal(writer: TextIO, *, use_alt_screen: bool) -> None:
    writer.write(RESET_STYLE)
    writer.write(SHOW_CURSOR)
    if use_alt_screen:
        writer.write(DISABLE_ALT_SCROLL)
        writer.write(LEAVE_ALT_SCREEN)
    else:
        writer.write("\n")
    _flush(writer)


def _draw_header(
    writer: TextIO,
    *,
    status: str,
    prompt_hint: str,
) -> None:
    writer.write(CURSOR_HOME)
    writer.write(CLEAR_SCREEN)
    writer.write(f"{BOLD}Codex{RESET_STYLE} {DIM}Python TUI{RESET_STYLE}\n")
    writer.write(f"{DIM}status:{RESET_STYLE} {GREEN}{status}{RESET_STYLE}\n")
    writer.write(f"{DIM}{prompt_hint}{RESET_STYLE}\n\n")
    _flush(writer)


def _append_history_entry(writer: TextIO, label: str, text: str, *, color: str) -> list[str]:
    """Append finalized chat history instead of repainting a clipped transcript.

    Rust ``codex-tui::insert_history`` writes finalized history rows into the
    terminal scrollback above the active viewport.  This dependency-light entry
    point mirrors the important user-facing contract: completed replies remain
    in terminal history and are not discarded by a full-screen redraw.
    """

    rendered = _history_entry_lines(label, text)
    writer.write(f"\n{color}{label}{RESET_STYLE}\n")
    for line in rendered[1:-1]:
        writer.write(f"{line}\n")
    writer.write("\n")
    _flush(writer)
    return rendered


def _history_entry_lines(label: str, text: str) -> list[str]:
    rendered = [label]
    rendered.extend(f"  {line}" for line in _wrapped_history_lines(str(text)))
    rendered.append("")
    return rendered


def _wrapped_history_lines(text: str) -> list[str]:
    width = max(_terminal_size().columns - 2, 20)
    lines: list[str] = []
    wrapper = textwrap.TextWrapper(
        width=width,
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        break_on_hyphens=False,
    )
    for raw_line in text.splitlines() or [""]:
        wrapped = wrapper.wrap(raw_line)
        lines.extend(wrapped or [""])
    return lines


def _is_interactive_input(input_stream: object) -> bool:
    isatty = getattr(input_stream, "isatty", None)
    return bool(callable(isatty) and isatty())


def _terminal_size() -> terminal_size:
    return shutil.get_terminal_size((100, 30))


def _should_auto_page(rendered_reply_lines: list[str]) -> bool:
    size = _terminal_size()
    visible_rows = max(size.lines - 5, 5)
    return len(rendered_reply_lines) > visible_rows


def _run_transcript_pager(writer: TextIO, input_stream: object, transcript_lines: list[str]) -> None:
    """Render a lightweight transcript pager aligned with Rust ``pager_overlay``.

    Rust exposes ``TranscriptOverlay`` through the global ``open_transcript``
    action and lets pager keybindings move through transcript content.  The
    Python entrypoint is still readline-based, so pager commands are line based:
    Enter/space/page-down/j advances, b/page-up/k moves back, and q exits.
    """

    readline = getattr(input_stream, "readline", None)
    if not callable(readline):
        return
    lines = transcript_lines or ["No transcript yet."]
    offset = 0
    while True:
        size = _terminal_size()
        page_height = max(size.lines - 4, 1)
        max_offset = max(len(lines) - page_height, 0)
        offset = min(max(offset, 0), max_offset)
        _draw_transcript_page(writer, lines, offset, page_height, max_offset)
        command = readline()
        if isinstance(command, bytes):
            command_text = command.decode("utf-8", errors="replace").strip().lower()
        else:
            command_text = str(command).strip().lower()
        if command == "":
            return
        if command_text in {"q", "quit", "esc", "/quit", "/exit"}:
            return
        if command_text in {"b", "k", "p", "page-up", "pgup", "u"}:
            offset = max(offset - page_height, 0)
        elif command_text in {"home", "top", "g"}:
            offset = 0
        elif command_text in {"end", "bottom", "g end"}:
            offset = max_offset
        else:
            offset = min(offset + page_height, max_offset)


def _draw_transcript_page(
    writer: TextIO,
    lines: list[str],
    offset: int,
    page_height: int,
    max_offset: int,
) -> None:
    writer.write(CURSOR_HOME)
    writer.write(CLEAR_SCREEN)
    writer.write(f"{BOLD}T R A N S C R I P T{RESET_STYLE}\n")
    writer.write(f"{DIM}Enter/space next   b previous   q close{RESET_STYLE}\n")
    for line in lines[offset : offset + page_height]:
        writer.write(f"{line}\n")
    shown_end = min(offset + page_height, len(lines))
    writer.write(
        f"{YELLOW}-- {offset + 1}-{shown_end}/{len(lines)}"
        f" {'bottom' if offset >= max_offset else 'more'} --{RESET_STYLE} "
    )
    _flush(writer)


def _flush(writer: TextIO) -> None:
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def run_tui(*_args: object, stderr: object | None = None, **_kwargs: object) -> int:
    """Start the interactive TUI.

    The non-interactive Python port currently does not implement this path. Return
    the unimplemented command exit code used by the parser (64) after printing a
    clear diagnostic.
    """

    if stderr is None:
        import sys

        stderr = sys.stderr
    write = getattr(stderr, "write", None)
    if callable(write):
        if _enabled(os.environ.get("PYCODEX_TUI_FALLBACK")):
            write("pycodex: interactive TUI is disabled in this Python port.\n")
            return 0
        write("pycodex: interactive TUI is recognized but not implemented yet.\n")
    return 64


async def run_main(*_args: object, **kwargs: object) -> AppExitInfo:
    """Python boundary for Rust ``codex_tui::run_main``.

    The Rust root wires config/app-server setup and then enters the terminal
    app.  Python's product path already constructs the exec-backed prompt
    runner in ``pycodex.cli.parser``; this boundary accepts that runner as an
    injection point and executes the same terminal runtime.
    """

    import sys

    active_thread_runtime = kwargs.get("active_thread_runtime")
    if active_thread_runtime is None:
        stderr = kwargs.get("stderr", sys.stderr)
        write = getattr(stderr, "write", None)
        if callable(write):
            write("pycodex: codex_tui::run_main requires an active thread runtime in this Python port.\n")
        return AppExitInfo(exit_reason=ExitReasonPayload(ExitReason.FATAL, "missing active thread runtime"))

    code = run_terminal_tui(
        stdout=kwargs.get("stdout", sys.stdout),
        stderr=kwargs.get("stderr", sys.stderr),
        stdin=kwargs.get("stdin", sys.stdin),
        active_thread_runtime=active_thread_runtime,
        use_alt_screen=not bool(kwargs.get("no_alt_screen", False)),
    )
    if code == 0:
        return AppExitInfo(exit_reason=ExitReason.USER_REQUESTED)
    return AppExitInfo(exit_reason=ExitReasonPayload(ExitReason.FATAL, f"TUI exited with status {code}"))


__all__ = [
    "AppServerTarget",
    "AppExitInfo",
    "Cli",
    "ExitReason",
    "ExitReasonPayload",
    "RemoteAppServerEndpoint",
    "RUST_MODULE",
    "TUI_LOG_FILE_NAME",
    "app_server_target_for_launch",
    "config_cwd_for_app_server_target",
    "latest_session_cwd_filter",
    "remote_addr_has_explicit_port",
    "remote_addr_parse_error_message",
    "remote_addr_supports_auth_token",
    "resolve_remote_addr",
    "TUIUnavailableError",
    "websocket_url_supports_auth_token",
    "run_terminal_tui",
    "run_line_mode_tui",
    "run_main",
    "run_tui",
]

