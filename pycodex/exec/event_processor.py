"""Event processors for non-interactive ``codex exec`` output.

This is a standard-library port of the dependency-free behavior in
``codex/codex-rs/exec/src/event_processor.rs`` plus the testable state-machine
pieces of the human and JSONL processors.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from pycodex.protocol import (
    NetworkSandboxPolicy,
    PermissionProfile,
    SandboxPolicy,
    SessionConfiguredEvent,
    TurnItem,
    approval_policy_display_value,
    turn_completed_notification as protocol_turn_completed_notification,
    turn_started_notification as protocol_turn_started_notification,
)

from .events import (
    ExecThreadItem,
    ThreadErrorEvent,
    ThreadEvent,
    Usage,
    agent_message_item,
    collab_tool_call_item,
    command_execution_item,
    error_item,
    exec_item_from_turn_item,
    final_message_from_turn_items,
    reasoning_item,
    todo_list_item,
    web_search_item,
)

JsonValue = Any
DEFAULT_CODEX_VERSION = "0.0.0"
_EXEC_JSON_TURN_ITEM_TYPES = {
    "AgentMessage",
    "Reasoning",
    "CommandExecution",
    "FileChange",
    "McpToolCall",
    "CollabAgentToolCall",
    "WebSearch",
}


class CodexStatus(str, Enum):
    RUNNING = "running"
    INITIATE_SHUTDOWN = "initiate_shutdown"

    @property
    def status(self) -> "CodexStatus":
        return self


@dataclass(frozen=True)
class CollectedThreadEvents:
    events: tuple[ThreadEvent, ...]
    status: CodexStatus


def exec_turn_started_notification(
    thread_id: str,
    turn_id: str,
    items: tuple[TurnItem, ...] | list[TurnItem] = (),
    *,
    started_at: int | float | None = None,
) -> dict[str, JsonValue]:
    return protocol_turn_started_notification(thread_id, turn_id, items, started_at=started_at)


def exec_turn_completed_notification(
    thread_id: str,
    turn_id: str,
    items: tuple[TurnItem, ...] | list[TurnItem],
    *,
    status: str = "completed",
    started_at: int | float | None = None,
    completed_at: int | float | None = None,
    duration_ms: int | float | None = None,
    error: JsonValue = None,
) -> dict[str, JsonValue]:
    return protocol_turn_completed_notification(
        thread_id,
        turn_id,
        items,
        status=status,
        error=error,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )


@dataclass
class RunningTodoList:
    item_id: str
    items: tuple[tuple[str, bool], ...]


def handle_last_message(
    last_agent_message: str | None,
    output_file: str | Path,
    *,
    stderr: TextIO | None = None,
) -> None:
    path = Path(output_file)
    err = sys.stderr if stderr is None else stderr
    try:
        path.write_text(last_agent_message or "", encoding="utf-8")
    except OSError as exc:
        print(f"Failed to write last message file {json.dumps(str(path))}: {exc}", file=err)
    if last_agent_message is None:
        print(f"Warning: no last agent message; wrote empty content to {path}", file=err)


class JsonEventProcessor:
    """Collect and emit upstream-shaped ``codex exec --json`` events."""

    def __init__(self, last_message_path: str | Path | None = None) -> None:
        self.last_message_path = Path(last_message_path) if last_message_path is not None else None
        self._next_item_number = 0
        self._raw_to_exec_item_id: dict[str, str] = {}
        self.last_critical_error: ThreadErrorEvent | None = None
        self.final_message: str | None = None
        self.emit_final_message_on_shutdown = False
        self.last_usage: Usage | None = None
        self.running_todo_list: RunningTodoList | None = None

    def next_item_id(self) -> str:
        item_id = f"item_{self._next_item_number}"
        self._next_item_number += 1
        return item_id

    def thread_started_event(self, thread_id: str) -> ThreadEvent:
        return ThreadEvent.thread_started(thread_id)

    def collect_config_summary(self, session_configured: SessionConfiguredEvent | JsonValue) -> CollectedThreadEvents:
        return CollectedThreadEvents(
            events=(self.thread_started_event(_session_configured_thread_id(session_configured)),),
            status=CodexStatus.RUNNING,
        )

    def print_config_summary(
        self,
        config: JsonValue,
        prompt: str,
        session_configured: SessionConfiguredEvent | JsonValue,
        *,
        output: TextIO | None = None,
    ) -> None:
        self.emit_json_lines(self.collect_config_summary(session_configured).events, output)

    def collect_warning(self, message: str) -> CollectedThreadEvents:
        return CollectedThreadEvents(
            events=(ThreadEvent.item_completed(error_item(self.next_item_id(), message)),),
            status=CodexStatus.RUNNING,
        )

    def collect_error(self, message: str) -> CollectedThreadEvents:
        error = ThreadErrorEvent(message)
        self.last_critical_error = error
        return CollectedThreadEvents(events=(ThreadEvent.error(error),), status=CodexStatus.RUNNING)

    def process_warning(self, message: str, *, output: TextIO | None = None) -> CodexStatus:
        collected = self.collect_warning(message)
        self.emit_json_lines(collected.events, output)
        return collected.status

    def collect_turn_started(self) -> CollectedThreadEvents:
        return CollectedThreadEvents(events=(ThreadEvent.turn_started(),), status=CodexStatus.RUNNING)

    def collect_item_started(self, item: TurnItem) -> CollectedThreadEvents:
        mapped = self._map_started_item(item)
        events = (ThreadEvent.item_started(mapped),) if mapped is not None else ()
        return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

    def collect_item_completed(self, item: TurnItem) -> CollectedThreadEvents:
        mapped = self._map_completed_item(item)
        if mapped is not None and mapped.type == "agent_message":
            self.final_message = str(mapped.payload.get("text", ""))
        events = (ThreadEvent.item_completed(mapped),) if mapped is not None else ()
        return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

    def collect_turn_completed(
        self,
        *,
        status: str,
        items: tuple[TurnItem, ...] | list[TurnItem] = (),
        error: str | None = None,
        usage: Usage | None = None,
    ) -> CollectedThreadEvents:
        events: list[ThreadEvent] = []
        if self.running_todo_list is not None:
            events.append(ThreadEvent.item_completed(todo_list_item(self.running_todo_list.item_id, self.running_todo_list.items)))
            self.running_todo_list = None
        events.extend(self._reconcile_unfinished_started_items(tuple(items)))
        normalized_status = _normalized_status(status)

        if normalized_status == "completed":
            final_message = final_message_from_turn_items(tuple(items))
            if final_message is not None:
                self.final_message = final_message
            self.emit_final_message_on_shutdown = True
            events.append(ThreadEvent.turn_completed(usage or self.last_usage or Usage()))
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        if normalized_status == "failed":
            self.final_message = None
            self.emit_final_message_on_shutdown = False
            failure = ThreadErrorEvent(error or (self.last_critical_error.message if self.last_critical_error else "turn failed"))
            events.append(ThreadEvent.turn_failed(failure))
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        if normalized_status == "interrupted":
            self.final_message = None
            self.emit_final_message_on_shutdown = False
            return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

        return CollectedThreadEvents(tuple(events), CodexStatus.RUNNING)

    def collect_thread_events(self, notification: JsonValue) -> CollectedThreadEvents:
        method = notification_method(notification)
        params = notification_params(notification)

        if method in {"configWarning", "warning"}:
            return self.collect_warning(_message_with_details(_warning_summary(params), _notification_details(params)))

        if method == "error":
            return self.collect_error(_turn_error_message(_field(params, "error") or params) or "")

        if method == "deprecationNotice":
            return self.collect_warning(_message_with_details(_warning_summary(params), _notification_details(params)))

        if method in {"hook/started", "hook/completed", "model/verification", "turn/diff/updated"}:
            return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

        if method == "item/started":
            item = _field(params, "item")
            mapped = self._map_started_notification_item(item)
            events = (ThreadEvent.item_started(mapped),) if mapped is not None else ()
            return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

        if method == "item/completed":
            item = _field(params, "item")
            mapped = self._map_completed_notification_item(item)
            if mapped is not None and mapped.type == "agent_message":
                self.final_message = str(mapped.payload.get("text", ""))
            events = (ThreadEvent.item_completed(mapped),) if mapped is not None else ()
            return CollectedThreadEvents(events=events, status=CodexStatus.RUNNING)

        if method == "model/rerouted":
            message = _model_rerouted_message(params, include_reason=True)
            return CollectedThreadEvents(
                events=(ThreadEvent.item_completed(error_item(self.next_item_id(), message)),),
                status=CodexStatus.RUNNING,
            )

        if method == "thread/tokenUsage/updated":
            self.last_usage = usage_from_notification(params)
            return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

        if method == "turn/plan/updated":
            items = map_todo_items(_field(params, "plan") or ())
            if self.running_todo_list is not None:
                self.running_todo_list.items = items
                return CollectedThreadEvents(
                    events=(ThreadEvent.item_updated(todo_list_item(self.running_todo_list.item_id, items)),),
                    status=CodexStatus.RUNNING,
                )
            item_id = self.next_item_id()
            self.running_todo_list = RunningTodoList(item_id=item_id, items=items)
            return CollectedThreadEvents(
                events=(ThreadEvent.item_started(todo_list_item(item_id, items)),),
                status=CodexStatus.RUNNING,
            )

        if method == "turn/started":
            return self.collect_turn_started()

        if method == "turn/completed":
            turn = _field(params, "turn")
            items = _turn_items(turn)
            events: list[ThreadEvent] = []
            if self.running_todo_list is not None:
                events.append(ThreadEvent.item_completed(todo_list_item(self.running_todo_list.item_id, self.running_todo_list.items)))
                self.running_todo_list = None
            events.extend(self._reconcile_unfinished_notification_items(items))

            status = _normalized_status(_field(turn, "status"))
            if status == "completed":
                final_message = final_message_from_notification_items(items)
                if final_message is not None:
                    self.final_message = final_message
                self.emit_final_message_on_shutdown = True
                events.append(ThreadEvent.turn_completed(self.last_usage or Usage()))
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            if status == "failed":
                self.final_message = None
                self.emit_final_message_on_shutdown = False
                failure_message = (
                    _turn_error_message(_field(turn, "error"))
                    or (self.last_critical_error.message if self.last_critical_error else None)
                    or "turn failed"
                )
                events.append(ThreadEvent.turn_failed(ThreadErrorEvent(failure_message)))
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            if status == "interrupted":
                self.final_message = None
                self.emit_final_message_on_shutdown = False
                return CollectedThreadEvents(tuple(events), CodexStatus.INITIATE_SHUTDOWN)

            return CollectedThreadEvents(tuple(events), CodexStatus.RUNNING)

        return CollectedThreadEvents(events=(), status=CodexStatus.RUNNING)

    collect_server_notification = collect_thread_events

    def process_server_notification(self, notification: JsonValue, *, output: TextIO | None = None) -> CodexStatus:
        collected = self.collect_thread_events(notification)
        self.emit_json_lines(collected.events, output)
        return collected.status

    def print_final_output(self, *, stderr: TextIO | None = None) -> None:
        if self.emit_final_message_on_shutdown and self.last_message_path is not None:
            handle_last_message(self.final_message, self.last_message_path, stderr=stderr)

    def emit_json_lines(self, events: tuple[ThreadEvent, ...] | list[ThreadEvent], output: TextIO | None = None) -> None:
        out = sys.stdout if output is None else output
        for event in events:
            print(event.to_json_line(), file=out)

    def _started_item_id(self, raw_id: str) -> str:
        existing = self._raw_to_exec_item_id.get(raw_id)
        if existing is not None:
            return existing
        item_id = self.next_item_id()
        self._raw_to_exec_item_id[raw_id] = item_id
        return item_id

    def _completed_item_id(self, raw_id: str) -> str:
        return self._raw_to_exec_item_id.pop(raw_id, None) or self.next_item_id()

    def _map_started_item(self, item: TurnItem) -> ExecThreadItem | None:
        if item.type in {"AgentMessage", "Reasoning"}:
            return None
        if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
            return None
        return exec_item_from_turn_item(item, self._started_item_id(item.id()))

    def _map_completed_item(self, item: TurnItem) -> ExecThreadItem | None:
        if item.type == "Reasoning":
            text = "\n".join(getattr(item.item, "summary_text", ()))
            if text.strip() == "":
                return None
        if item.type in {"AgentMessage", "Reasoning"}:
            return exec_item_from_turn_item(item, self.next_item_id())
        if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
            return None
        return exec_item_from_turn_item(item, self._completed_item_id(item.id()))

    def _reconcile_unfinished_started_items(self, turn_items: tuple[TurnItem, ...]) -> tuple[ThreadEvent, ...]:
        events: list[ThreadEvent] = []
        for item in turn_items:
            raw_id = item.id()
            if raw_id not in self._raw_to_exec_item_id:
                continue
            mapped = self._map_completed_item(item)
            if mapped is not None:
                events.append(ThreadEvent.item_completed(mapped))
        return tuple(events)

    def _map_started_notification_item(self, item: JsonValue) -> ExecThreadItem | None:
        if _uses_raw_exec_notification_boundary(item):
            raw_id = _item_id(item)
            make_id = (lambda: self._started_item_id(raw_id)) if raw_id is not None else self.next_item_id
            return exec_item_from_app_server_item(item, make_id)
        turn_item = _turn_item_from_value(item)
        if turn_item is not None:
            return self._map_started_item(turn_item)
        raw_id = _item_id(item)
        make_id = (lambda: self._started_item_id(raw_id)) if raw_id is not None else self.next_item_id
        return exec_item_from_app_server_item(item, make_id)

    def _map_completed_notification_item(self, item: JsonValue) -> ExecThreadItem | None:
        if _uses_raw_exec_notification_boundary(item):
            raw_id = _item_id(item)
            make_id = (lambda: self._completed_item_id(raw_id)) if raw_id is not None else self.next_item_id
            return exec_item_from_app_server_item(item, make_id)
        turn_item = _turn_item_from_value(item)
        if turn_item is not None:
            return self._map_completed_item(turn_item)
        raw_id = _item_id(item)
        make_id = (lambda: self._completed_item_id(raw_id)) if raw_id is not None else self.next_item_id
        return exec_item_from_app_server_item(item, make_id)

    def _reconcile_unfinished_notification_items(self, items: tuple[JsonValue, ...]) -> tuple[ThreadEvent, ...]:
        events: list[ThreadEvent] = []
        for item in items:
            raw_id = _item_id(item)
            if raw_id is None or raw_id not in self._raw_to_exec_item_id:
                continue
            mapped = self._map_completed_notification_item(item)
            if mapped is not None:
                events.append(ThreadEvent.item_completed(mapped))
        return tuple(events)


class HumanEventProcessor:
    """Human-output state that mirrors the upstream final-output decisions."""

    def __init__(self, last_message_path: str | Path | None = None) -> None:
        self.last_message_path = Path(last_message_path) if last_message_path is not None else None
        self.final_message: str | None = None
        self.final_message_rendered = False
        self.emit_final_message_on_shutdown = False
        self.last_usage: Usage | None = None
        self.show_agent_reasoning = True
        self.show_raw_agent_reasoning = False

    def configure_from_config(self, config: JsonValue) -> "HumanEventProcessor":
        """Apply upstream human-output reasoning visibility flags from config."""

        hide_agent_reasoning = _field(config, "hide_agent_reasoning", "hideAgentReasoning")
        if hide_agent_reasoning is not None:
            self.show_agent_reasoning = not bool(hide_agent_reasoning)
        show_raw_agent_reasoning = _field(config, "show_raw_agent_reasoning", "showRawAgentReasoning")
        if show_raw_agent_reasoning is not None:
            self.show_raw_agent_reasoning = bool(show_raw_agent_reasoning)
        return self

    def print_config_summary(
        self,
        config: JsonValue,
        prompt: str,
        session_configured: SessionConfiguredEvent | JsonValue,
        *,
        stderr: TextIO | None = None,
        version: str = DEFAULT_CODEX_VERSION,
    ) -> None:
        err = sys.stderr if stderr is None else stderr
        for line in config_summary_lines(config, prompt, session_configured, version=version):
            print(line, file=err)

    def collect_warning(self, message: str, *, stderr: TextIO | None = None) -> CodexStatus:
        err = sys.stderr if stderr is None else stderr
        print(f"warning: {message}", file=err)
        return CodexStatus.RUNNING

    def process_warning(self, message: str, *, stderr: TextIO | None = None) -> CodexStatus:
        return self.collect_warning(message, stderr=stderr)

    def collect_item_started(self, item: TurnItem, *, stderr: TextIO | None = None) -> CodexStatus:
        err = sys.stderr if stderr is None else stderr
        for line in human_item_started_lines(item):
            print(line, file=err)
        return CodexStatus.RUNNING

    def collect_item_completed(self, item: TurnItem, *, stderr: TextIO | None = None) -> CodexStatus:
        err = sys.stderr if stderr is None else stderr
        if item.type == "AgentMessage":
            final_message = final_message_from_turn_items((item,))
            self.final_message = final_message
            self.final_message_rendered = final_message is not None
            if final_message is not None:
                print("codex", file=err)
                print(final_message, file=err)
        else:
            for line in human_item_completed_lines(
                item,
                show_agent_reasoning=self.show_agent_reasoning,
                show_raw_agent_reasoning=self.show_raw_agent_reasoning,
            ):
                print(line, file=err)
        return CodexStatus.RUNNING

    def collect_turn_completed(
        self,
        *,
        status: str,
        items: tuple[TurnItem, ...] | list[TurnItem] = (),
        error: str | None = None,
        stderr: TextIO | None = None,
    ) -> CodexStatus:
        err = sys.stderr if stderr is None else stderr
        normalized_status = _normalized_status(status)
        if normalized_status == "completed":
            rendered_message = self.final_message if self.final_message_rendered else None
            final_message = final_message_from_turn_items(tuple(items))
            if final_message is not None:
                self.final_message_rendered = rendered_message == final_message
                self.final_message = final_message
            self.emit_final_message_on_shutdown = True
            return CodexStatus.INITIATE_SHUTDOWN

        if normalized_status in {"failed", "interrupted"}:
            self.final_message = None
            self.final_message_rendered = False
            self.emit_final_message_on_shutdown = False
            if normalized_status == "failed" and error is not None:
                print(f"ERROR: {error}", file=err)
            if normalized_status == "interrupted":
                print("turn interrupted", file=err)
            return CodexStatus.INITIATE_SHUTDOWN

        return CodexStatus.RUNNING

    def process_server_notification(self, notification: JsonValue, *, stderr: TextIO | None = None) -> CodexStatus:
        method = notification_method(notification)
        params = notification_params(notification)
        err = sys.stderr if stderr is None else stderr

        if method == "item/started":
            for line in human_item_started_lines(_field(params, "item")):
                print(line, file=err)
            return CodexStatus.RUNNING

        if method == "item/completed":
            item = _field(params, "item")
            text = agent_message_text_from_notification_item(item)
            if text is not None:
                self.final_message = text
                self.final_message_rendered = True
                print("codex", file=err)
                print(text, file=err)
            else:
                for line in human_item_completed_lines(
                    item,
                    show_agent_reasoning=self.show_agent_reasoning,
                    show_raw_agent_reasoning=self.show_raw_agent_reasoning,
                ):
                    print(line, file=err)
            return CodexStatus.RUNNING

        if method == "thread/tokenUsage/updated":
            self.last_usage = usage_from_notification(params)
            return CodexStatus.RUNNING

        if method == "turn/completed":
            turn = _field(params, "turn")
            status = _normalized_status(_field(turn, "status"))
            if status == "completed":
                rendered_message = self.final_message if self.final_message_rendered else None
                final_message = final_message_from_notification_items(_turn_items(turn))
                if final_message is not None:
                    self.final_message_rendered = rendered_message == final_message
                    self.final_message = final_message
                self.emit_final_message_on_shutdown = True
                return CodexStatus.INITIATE_SHUTDOWN
            if status == "failed":
                self.final_message = None
                self.final_message_rendered = False
                self.emit_final_message_on_shutdown = False
                error_message = _turn_error_message(_field(turn, "error"))
                if error_message is not None:
                    print(f"ERROR: {error_message}", file=err)
                return CodexStatus.INITIATE_SHUTDOWN
            if status == "interrupted":
                self.final_message = None
                self.final_message_rendered = False
                self.emit_final_message_on_shutdown = False
                print("turn interrupted", file=err)
                return CodexStatus.INITIATE_SHUTDOWN
            return CodexStatus.RUNNING

        for line in human_notification_lines(notification):
            print(line, file=err)
        return CodexStatus.RUNNING

    def print_final_output(
        self,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        stdout_is_terminal: bool | None = None,
        stderr_is_terminal: bool | None = None,
    ) -> None:
        if self.emit_final_message_on_shutdown and self.last_message_path is not None:
            handle_last_message(self.final_message, self.last_message_path, stderr=stderr)

        message = self.final_message if self.emit_final_message_on_shutdown else None
        out = sys.stdout if stdout is None else stdout
        err = sys.stderr if stderr is None else stderr
        stdout_tty = _is_terminal(out, stdout_is_terminal)
        stderr_tty = _is_terminal(err, stderr_is_terminal)

        if self.last_usage is not None:
            print("tokens used", file=err)
            print(format_with_separators(blended_total(self.last_usage)), file=err)

        if should_print_final_message_to_stdout(message, stdout_tty, stderr_tty):
            print(message, file=out)
        elif should_print_final_message_to_tty(message, self.final_message_rendered, stdout_tty, stderr_tty):
            print("codex", file=err)
            print(message, file=err)


def blended_total(usage: Usage) -> int:
    cached_input = max(usage.cached_input_tokens, 0)
    non_cached_input = max(usage.input_tokens - cached_input, 0)
    return max(non_cached_input + max(usage.output_tokens, 0), 0)


def config_summary_entries(
    config: JsonValue,
    session_configured: SessionConfiguredEvent | JsonValue,
) -> tuple[tuple[str, str], ...]:
    cwd = Path(str(_field(config, "cwd") or _field(session_configured, "cwd") or ""))
    permission_profile = _permission_profile_from_config(config, session_configured)
    workspace_roots = tuple(Path(str(path)) for path in (_field(config, "workspace_roots", "workspaceRoots") or ()))
    approval_policy = approval_policy_display_value(
        _field(config, "approval_policy", "approvalPolicy") or _field(session_configured, "approval_policy")
    )
    entries: list[tuple[str, str]] = [
        ("workdir", str(cwd)),
        ("model", str(_field(session_configured, "model") or _field(config, "model") or "")),
        ("provider", str(_field(session_configured, "model_provider_id", "modelProviderId") or _field(config, "model_provider_id", "modelProviderId") or "")),
        ("approval", approval_policy),
        ("sandbox", summarize_permission_profile(permission_profile, cwd, workspace_roots)),
    ]
    if _uses_responses_wire_api(config):
        entries.append(("reasoning effort", _optional_reasoning(_field(config, "reasoning_effort", "model_reasoning_effort", "modelReasoningEffort"))))
        entries.append(("reasoning summaries", _optional_reasoning(_field(config, "reasoning_summary", "model_reasoning_summary", "modelReasoningSummary"))))
    entries.append(("session id", _session_configured_session_id(session_configured)))
    return tuple(entries)


def config_summary_lines(
    config: JsonValue,
    prompt: str,
    session_configured: SessionConfiguredEvent | JsonValue,
    *,
    version: str = DEFAULT_CODEX_VERSION,
) -> tuple[str, ...]:
    lines = [f"OpenAI Codex v{version}", "--------"]
    lines.extend(f"{key}: {value}" for key, value in config_summary_entries(config, session_configured))
    lines.extend(("--------", "user", prompt))
    return tuple(lines)


def summarize_sandbox_policy(sandbox_policy: SandboxPolicy | JsonValue) -> str:
    if not isinstance(sandbox_policy, SandboxPolicy):
        sandbox_policy = SandboxPolicy.from_mapping(sandbox_policy)
    if sandbox_policy.type == "danger-full-access":
        return "danger-full-access"
    if sandbox_policy.type == "read-only":
        summary = "read-only"
        return _with_network_suffix(summary, sandbox_policy.network_sandbox_policy())
    if sandbox_policy.type == "external-sandbox":
        summary = "external-sandbox"
        return _with_network_suffix(summary, sandbox_policy.network_sandbox_policy())
    if sandbox_policy.type == "workspace-write":
        entries = ["workdir"]
        if not sandbox_policy.exclude_slash_tmp:
            entries.append("/tmp")
        if not sandbox_policy.exclude_tmpdir_env_var:
            entries.append("$TMPDIR")
        entries.extend(str(path) for path in sandbox_policy.writable_roots)
        summary = f"workspace-write [{', '.join(entries)}]"
        return _with_network_suffix(summary, sandbox_policy.network_sandbox_policy())
    return str(sandbox_policy.type)


def summarize_permission_profile(
    permission_profile: PermissionProfile,
    cwd: Path | str,
    workspace_roots: tuple[Path, ...] | list[Path] = (),
) -> str:
    try:
        legacy = permission_profile.to_legacy_sandbox_policy(cwd)
    except Exception:
        return _with_network_suffix("custom permissions", permission_profile.network_sandbox_policy())
    if legacy.type != "workspace-write":
        return summarize_sandbox_policy(legacy)

    entries = ["workdir"]
    if not legacy.exclude_slash_tmp:
        entries.append("/tmp")
    if not legacy.exclude_tmpdir_env_var:
        entries.append("$TMPDIR")
    cwd_path = Path(cwd)
    entries.extend(str(Path(root)) for root in workspace_roots if Path(root) != cwd_path)
    summary = f"workspace-write [{', '.join(entries)}]"
    return _with_network_suffix(summary, legacy.network_sandbox_policy())


def format_with_separators(value: int) -> str:
    return f"{value:,}"


def notification_method(notification: JsonValue) -> str | None:
    raw = _field(notification, "method", "type", "kind")
    if raw is None:
        return None
    raw = str(raw)
    aliases = {
        "AccountLoginCompleted": "account/login/completed",
        "account_login_completed": "account/login/completed",
        "AccountRateLimitsUpdated": "account/rateLimits/updated",
        "account_rate_limits_updated": "account/rateLimits/updated",
        "AccountUpdated": "account/updated",
        "account_updated": "account/updated",
        "AgentMessageDelta": "item/agentMessage/delta",
        "agent_message_delta": "item/agentMessage/delta",
        "AppListUpdated": "app/list/updated",
        "app_list_updated": "app/list/updated",
        "CommandExecOutputDelta": "command/exec/outputDelta",
        "command_exec_output_delta": "command/exec/outputDelta",
        "CommandExecutionOutputDelta": "item/commandExecution/outputDelta",
        "command_execution_output_delta": "item/commandExecution/outputDelta",
        "ConfigWarning": "configWarning",
        "config_warning": "configWarning",
        "ContextCompacted": "thread/compacted",
        "context_compacted": "thread/compacted",
        "DeprecationNotice": "deprecationNotice",
        "deprecation_notice": "deprecationNotice",
        "Error": "error",
        "ExternalAgentConfigImportCompleted": "externalAgentConfig/import/completed",
        "external_agent_config_import_completed": "externalAgentConfig/import/completed",
        "FileChangeOutputDelta": "item/fileChange/outputDelta",
        "file_change_output_delta": "item/fileChange/outputDelta",
        "FileChangePatchUpdated": "item/fileChange/patchUpdated",
        "file_change_patch_updated": "item/fileChange/patchUpdated",
        "FsChanged": "fs/changed",
        "fs_changed": "fs/changed",
        "FuzzyFileSearchSessionCompleted": "fuzzyFileSearch/sessionCompleted",
        "fuzzy_file_search_session_completed": "fuzzyFileSearch/sessionCompleted",
        "FuzzyFileSearchSessionUpdated": "fuzzyFileSearch/sessionUpdated",
        "fuzzy_file_search_session_updated": "fuzzyFileSearch/sessionUpdated",
        "GuardianWarning": "guardianWarning",
        "guardian_warning": "guardianWarning",
        "HookStarted": "hook/started",
        "hook_started": "hook/started",
        "HookCompleted": "hook/completed",
        "hook_completed": "hook/completed",
        "ItemStarted": "item/started",
        "item_started": "item/started",
        "ItemGuardianApprovalReviewStarted": "item/autoApprovalReview/started",
        "item_guardian_approval_review_started": "item/autoApprovalReview/started",
        "ItemGuardianApprovalReviewCompleted": "item/autoApprovalReview/completed",
        "item_guardian_approval_review_completed": "item/autoApprovalReview/completed",
        "ItemCompleted": "item/completed",
        "item_completed": "item/completed",
        "ModelRerouted": "model/rerouted",
        "model_rerouted": "model/rerouted",
        "ModelVerification": "model/verification",
        "model_verification": "model/verification",
        "McpServerOauthLoginCompleted": "mcpServer/oauthLogin/completed",
        "mcp_server_oauth_login_completed": "mcpServer/oauthLogin/completed",
        "McpServerStatusUpdated": "mcpServer/startupStatus/updated",
        "mcp_server_status_updated": "mcpServer/startupStatus/updated",
        "McpToolCallProgress": "item/mcpToolCall/progress",
        "mcp_tool_call_progress": "item/mcpToolCall/progress",
        "PlanDelta": "item/plan/delta",
        "plan_delta": "item/plan/delta",
        "ProcessExited": "process/exited",
        "process_exited": "process/exited",
        "ProcessOutputDelta": "process/outputDelta",
        "process_output_delta": "process/outputDelta",
        "RawResponseItemCompleted": "rawResponseItem/completed",
        "raw_response_item_completed": "rawResponseItem/completed",
        "ReasoningSummaryPartAdded": "item/reasoning/summaryPartAdded",
        "reasoning_summary_part_added": "item/reasoning/summaryPartAdded",
        "ReasoningSummaryTextDelta": "item/reasoning/summaryTextDelta",
        "reasoning_summary_text_delta": "item/reasoning/summaryTextDelta",
        "ReasoningTextDelta": "item/reasoning/textDelta",
        "reasoning_text_delta": "item/reasoning/textDelta",
        "RemoteControlStatusChanged": "remoteControl/status/changed",
        "remote_control_status_changed": "remoteControl/status/changed",
        "ServerRequestResolved": "serverRequest/resolved",
        "server_request_resolved": "serverRequest/resolved",
        "SkillsChanged": "skills/changed",
        "skills_changed": "skills/changed",
        "TerminalInteraction": "item/commandExecution/terminalInteraction",
        "terminal_interaction": "item/commandExecution/terminalInteraction",
        "ThreadArchived": "thread/archived",
        "thread_archived": "thread/archived",
        "ThreadUnarchived": "thread/unarchived",
        "thread_unarchived": "thread/unarchived",
        "ThreadClosed": "thread/closed",
        "thread_closed": "thread/closed",
        "ThreadGoalCleared": "thread/goal/cleared",
        "thread_goal_cleared": "thread/goal/cleared",
        "ThreadGoalUpdated": "thread/goal/updated",
        "thread_goal_updated": "thread/goal/updated",
        "ThreadNameUpdated": "thread/name/updated",
        "thread_name_updated": "thread/name/updated",
        "ThreadSettingsUpdated": "thread/settings/updated",
        "thread_settings_updated": "thread/settings/updated",
        "ThreadStarted": "thread/started",
        "thread_started": "thread/started",
        "ThreadStatusChanged": "thread/status/changed",
        "thread_status_changed": "thread/status/changed",
        "ThreadTokenUsageUpdated": "thread/tokenUsage/updated",
        "thread_token_usage_updated": "thread/tokenUsage/updated",
        "ThreadRealtimeClosed": "thread/realtime/closed",
        "thread_realtime_closed": "thread/realtime/closed",
        "ThreadRealtimeError": "thread/realtime/error",
        "thread_realtime_error": "thread/realtime/error",
        "ThreadRealtimeItemAdded": "thread/realtime/itemAdded",
        "thread_realtime_item_added": "thread/realtime/itemAdded",
        "ThreadRealtimeOutputAudioDelta": "thread/realtime/outputAudio/delta",
        "thread_realtime_output_audio_delta": "thread/realtime/outputAudio/delta",
        "ThreadRealtimeSdp": "thread/realtime/sdp",
        "thread_realtime_sdp": "thread/realtime/sdp",
        "ThreadRealtimeStarted": "thread/realtime/started",
        "thread_realtime_started": "thread/realtime/started",
        "ThreadRealtimeTranscriptDelta": "thread/realtime/transcript/delta",
        "thread_realtime_transcript_delta": "thread/realtime/transcript/delta",
        "ThreadRealtimeTranscriptDone": "thread/realtime/transcript/done",
        "thread_realtime_transcript_done": "thread/realtime/transcript/done",
        "TurnCompleted": "turn/completed",
        "turn_completed": "turn/completed",
        "TurnDiffUpdated": "turn/diff/updated",
        "turn_diff_updated": "turn/diff/updated",
        "TurnPlanUpdated": "turn/plan/updated",
        "turn_plan_updated": "turn/plan/updated",
        "TurnStarted": "turn/started",
        "turn_started": "turn/started",
        "Warning": "warning",
        "WindowsSandboxSetupCompleted": "windowsSandbox/setupCompleted",
        "windows_sandbox_setup_completed": "windowsSandbox/setupCompleted",
        "WindowsWorldWritableWarning": "windows/worldWritableWarning",
        "windows_world_writable_warning": "windows/worldWritableWarning",
    }
    return aliases.get(raw, raw)


def notification_params(notification: JsonValue) -> JsonValue:
    params = _field(notification, "params", "payload")
    return notification if params is None else params


def usage_from_notification(value: JsonValue) -> Usage:
    token_usage = _field(value, "tokenUsage", "token_usage")
    if token_usage is None:
        token_usage = value
    total = _field(token_usage, "total")
    if total is None:
        total = token_usage
    return Usage(
        input_tokens=_int_field(total, "inputTokens", "input_tokens"),
        cached_input_tokens=_int_field(total, "cachedInputTokens", "cached_input_tokens"),
        output_tokens=_int_field(total, "outputTokens", "output_tokens"),
        reasoning_output_tokens=_int_field(total, "reasoningOutputTokens", "reasoning_output_tokens"),
    )


def map_todo_items(plan: JsonValue) -> tuple[tuple[str, bool], ...]:
    if not isinstance(plan, list | tuple):
        return ()
    return tuple(
        (
            str(_field(step, "step") or ""),
            _normalized_status(_field(step, "status")) == "completed",
        )
        for step in plan
    )


def exec_item_from_app_server_item(item: JsonValue, make_id: Any) -> ExecThreadItem | None:
    if isinstance(item, Mapping):
        item_type = _normalized_item_type(_field(item, "type"))
        if item_type == "web_search":
            return web_search_item(
                make_id(),
                type(
                    "WebSearchNotificationItem",
                    (),
                    {
                        "id": str(_field(item, "id") or ""),
                        "query": str(_field(item, "query") or ""),
                        "action": _field(item, "action"),
                    },
                )(),
            )
        if item_type == "collab_agent_tool_call":
            return collab_tool_call_item(
                make_id(),
                tool=_field(item, "tool"),
                sender_thread_id=str(_field(item, "senderThreadId", "sender_thread_id") or ""),
                receiver_thread_ids=tuple(str(thread_id) for thread_id in (_field(item, "receiverThreadIds", "receiver_thread_ids") or ())),
                prompt=_optional_str(_field(item, "prompt")),
                agents_states=_field(item, "agentsStates", "agents_states") or {},
                status=_field(item, "status"),
            )
        if item_type == "mcp_tool_call":
            payload = {
                "server": _field(item, "server") or "",
                "tool": _field(item, "tool") or "",
                "arguments": _field(item, "arguments"),
                "result": _mcp_result_mapping(_field(item, "result")),
                "status": _mcp_status_text(_field(item, "status")),
            }
            if "error" in item:
                payload["error"] = _mcp_error_mapping(_field(item, "error"))
            return ExecThreadItem(make_id(), "mcp_tool_call", payload)
        if item_type == "file_change":
            return ExecThreadItem(
                make_id(),
                "file_change",
                {
                    "changes": _file_change_entries(_field(item, "changes") or ()),
                    "status": _patch_status_for_exec_json(_field(item, "status")),
                },
            )

    turn_item = _turn_item_from_value(item)
    if turn_item is not None:
        if not _turn_item_emits_exec_json(turn_item):
            return None
        return exec_item_from_turn_item(turn_item, make_id())

    item_type = _normalized_item_type(_field(item, "type"))
    if item_type == "agent_message":
        return agent_message_item(make_id(), agent_message_text_from_notification_item(item) or "")

    if item_type == "reasoning":
        text = "\n".join(str(entry) for entry in (_field(item, "summary", "summary_text") or ()))
        if text.strip() == "":
            return None
        return reasoning_item(make_id(), text)

    if item_type == "command_execution":
        return command_execution_item(
            make_id(),
            command=str(_field(item, "command") or ""),
            cwd=_field(item, "cwd"),
            process_id=_optional_str(_field(item, "processId", "process_id")),
            source=_optional_str(_field(item, "source")),
            command_actions=_command_actions(_field(item, "commandActions", "command_actions")),
            aggregated_output=str(_field(item, "aggregatedOutput", "aggregated_output") or ""),
            exit_code=_optional_int(_field(item, "exitCode", "exit_code")),
            duration_ms=_optional_int(_field(item, "durationMs", "duration_ms")),
            status=_field(item, "status"),
        )

    if item_type == "file_change":
        return ExecThreadItem(
            make_id(),
            "file_change",
            {
                "changes": _file_change_entries(_field(item, "changes") or ()),
                "status": _patch_status_for_exec_json(_field(item, "status")),
            },
        )

    if item_type == "mcp_tool_call":
        error = _mcp_error_mapping(_field(item, "error"))
        payload = {
            "server": _field(item, "server") or "",
            "tool": _field(item, "tool") or "",
            "arguments": _field(item, "arguments"),
            "result": _mcp_result_mapping(_field(item, "result")),
            "status": _mcp_status_text(_field(item, "status")),
        }
        if not isinstance(item, Mapping) or "error" in item:
            payload["error"] = error
        return ExecThreadItem(
            make_id(),
            "mcp_tool_call",
            payload,
        )

    if item_type == "collab_agent_tool_call":
        return collab_tool_call_item(
            make_id(),
            tool=_field(item, "tool"),
            sender_thread_id=str(_field(item, "senderThreadId", "sender_thread_id") or ""),
            receiver_thread_ids=tuple(str(thread_id) for thread_id in (_field(item, "receiverThreadIds", "receiver_thread_ids") or ())),
            prompt=_optional_str(_field(item, "prompt")),
            agents_states=_field(item, "agentsStates", "agents_states") or {},
            status=_field(item, "status"),
        )

    if item_type == "web_search":
        return web_search_item(
            make_id(),
            type(
                "WebSearchNotificationItem",
                (),
                {
                    "id": str(_field(item, "id") or ""),
                    "query": str(_field(item, "query") or ""),
                    "action": _field(item, "action"),
                },
            )(),
        )

    return None


def final_message_from_notification_items(items: tuple[JsonValue, ...] | list[JsonValue]) -> str | None:
    turn_items: list[TurnItem] = []
    all_turn_items = True
    for item in items:
        turn_item = _turn_item_from_value(item)
        if turn_item is None:
            all_turn_items = False
            break
        turn_items.append(turn_item)
    if all_turn_items:
        return final_message_from_turn_items(tuple(turn_items))

    for item in reversed(tuple(items)):
        text = agent_message_text_from_notification_item(item)
        if text is not None:
            return text
    for item in reversed(tuple(items)):
        if _normalized_item_type(_field(item, "type")) == "plan":
            text = _field(item, "text")
            if text is not None:
                return str(text)
    return None


def _turn_item_emits_exec_json(item: TurnItem) -> bool:
    if item.type not in _EXEC_JSON_TURN_ITEM_TYPES:
        return False
    if item.type == "Reasoning":
        text = "\n".join(str(entry) for entry in getattr(item.item, "summary_text", ()))
        return bool(text.strip())
    return True


def agent_message_text_from_notification_item(item: JsonValue) -> str | None:
    turn_item = _turn_item_from_value(item)
    if turn_item is not None:
        return final_message_from_turn_items((turn_item,))
    if _normalized_item_type(_field(item, "type")) != "agent_message":
        return None
    text = _field(item, "text")
    if text is not None:
        return str(text)
    content = _field(item, "content")
    if isinstance(content, list | tuple):
        return "".join(str(_field(entry, "text") or "") for entry in content)
    return ""


def human_item_started_lines(item: JsonValue) -> tuple[str, ...]:
    turn_item = _turn_item_from_value(item)
    if turn_item is not None:
        item = _turn_item_to_app_server_like_mapping(turn_item)

    item_type = _normalized_item_type(_field(item, "type"))
    if item_type == "command_execution":
        return (
            "exec",
            f"{_field(item, 'command') or ''} in {_field(item, 'cwd') or ''}",
        )
    if item_type == "mcp_tool_call":
        return (f"mcp: {_field(item, 'server') or ''}/{_field(item, 'tool') or ''} started",)
    if item_type == "web_search":
        return (f"web search: {_field(item, 'query') or ''}",)
    if item_type == "file_change":
        return ("apply patch",)
    if item_type == "collab_agent_tool_call":
        return (f"collab: {_collab_tool_debug(_field(item, 'tool'))}",)
    return ()


def human_item_completed_lines(
    item: JsonValue,
    *,
    show_agent_reasoning: bool = True,
    show_raw_agent_reasoning: bool = False,
) -> tuple[str, ...]:
    turn_item = _turn_item_from_value(item)
    if turn_item is not None and turn_item.type == "CommandExecution":
        command_item = turn_item.item
        status = _normalized_status(getattr(command_item, "status", None))
        if status == "failed":
            output = str(getattr(command_item, "aggregated_output", "") or "")
            exit_code = _optional_int(getattr(command_item, "exit_code", None)) or 1
            lines = [f"exec: failed (exit {exit_code})"]
            if output.strip():
                lines.append(output)
            return tuple(lines)
    if turn_item is not None:
        item = _turn_item_to_app_server_like_mapping(turn_item)

    item_type = _normalized_item_type(_field(item, "type"))
    if item_type == "reasoning":
        if not show_agent_reasoning:
            return ()
        text = reasoning_text_from_notification_item(item, show_raw_agent_reasoning=show_raw_agent_reasoning)
        return (text,) if text.strip() else ()

    if item_type == "command_execution":
        lines = [_command_completion_line(item)]
        output = str(_field(item, "aggregatedOutput", "aggregated_output") or "")
        if output.strip():
            lines.append(output)
        return tuple(lines)

    if item_type == "file_change":
        lines = [f"patch: {_patch_status_text(_field(item, 'status'))}"]
        lines.extend(str(change.get("path", "")) for change in _file_change_entries(_field(item, "changes") or ()))
        return tuple(lines)

    if item_type == "mcp_tool_call":
        lines = [f"mcp: {_field(item, 'server') or ''}/{_field(item, 'tool') or ''} ({_mcp_status_text(_field(item, 'status'))})"]
        error = _field(item, "error")
        message = _field(error, "message")
        if message is not None:
            lines.append(str(message))
        return tuple(lines)

    if item_type == "web_search":
        return (f"web search: {_field(item, 'query') or ''}",)

    if item_type == "context_compaction":
        return ("context compacted",)

    return ()


def reasoning_text_from_notification_item(item: JsonValue, *, show_raw_agent_reasoning: bool = False) -> str:
    turn_item = _turn_item_from_value(item)
    if turn_item is not None and turn_item.type == "Reasoning":
        summary = tuple(str(entry) for entry in getattr(turn_item.item, "summary_text", ()))
        raw_content = tuple(str(entry) for entry in getattr(turn_item.item, "raw_content", ()))
    else:
        summary = tuple(str(entry) for entry in (_field(item, "summary", "summary_text") or ()))
        raw_content = tuple(str(entry) for entry in (_field(item, "content", "raw_content") or ()))
    entries = raw_content if show_raw_agent_reasoning and raw_content else summary
    return "\n".join(entries)


def human_notification_lines(notification: JsonValue) -> tuple[str, ...]:
    method = notification_method(notification)
    params = notification_params(notification)

    if method in {"configWarning", "warning"}:
        return (f"warning: {_message_with_details(_warning_summary(params), _notification_details(params))}",)

    if method == "error":
        return (f"ERROR: {_turn_error_message(_field(params, 'error') or params) or ''}",)

    if method == "deprecationNotice":
        lines = [f"deprecated: {_warning_summary(params)}"]
        details = _notification_details(params)
        if details:
            lines.append(str(details))
        return tuple(lines)

    if method == "hook/started":
        name = _field(_field(params, "run"), "eventName", "event_name")
        return (f"hook: {name}",)

    if method == "hook/completed":
        run = _field(params, "run")
        name = _field(run, "eventName", "event_name")
        status = _field(run, "status")
        return (f"hook: {name} {status}",)

    if method == "model/rerouted":
        return (_model_rerouted_message(params, include_reason=False),)

    if method == "turn/diff/updated":
        diff = str(_field(params, "diff") or "")
        return (diff,) if diff.strip() else ()

    if method == "turn/plan/updated":
        lines: list[str] = []
        explanation = _field(params, "explanation")
        if explanation:
            lines.append(str(explanation))
        plan = _field(params, "plan") or ()
        if isinstance(plan, list | tuple):
            for step in plan:
                status = _normalized_status(_field(step, "status"))
                marker = "[x]" if status == "completed" else "[>]" if status == "in_progress" else "[ ]"
                lines.append(f"  {marker} {_field(step, 'step') or ''}")
        return tuple(lines)

    return ()


def should_print_final_message_to_stdout(
    final_message: str | None,
    stdout_is_terminal: bool,
    stderr_is_terminal: bool,
) -> bool:
    return final_message is not None and not (stdout_is_terminal and stderr_is_terminal)


def should_print_final_message_to_tty(
    final_message: str | None,
    final_message_rendered: bool,
    stdout_is_terminal: bool,
    stderr_is_terminal: bool,
) -> bool:
    return final_message is not None and not final_message_rendered and stdout_is_terminal and stderr_is_terminal


def _permission_profile_from_config(config: JsonValue, session_configured: JsonValue) -> PermissionProfile:
    profile = _field(config, "permission_profile", "permissionProfile")
    if profile is None:
        profile = _field(session_configured, "permission_profile", "permissionProfile")
    if isinstance(profile, PermissionProfile):
        return profile
    if profile is not None:
        return PermissionProfile.from_mapping(profile)
    return PermissionProfile.read_only()


def _uses_responses_wire_api(config: JsonValue) -> bool:
    raw = _field(config, "wire_api", "wireApi")
    provider = _field(config, "model_provider", "modelProvider")
    if raw is None and provider is not None:
        raw = _field(provider, "wire_api", "wireApi")
    return raw is None or str(_enum_value(raw)).lower() == "responses"


def _optional_reasoning(value: JsonValue) -> str:
    if value is None:
        return "none"
    return str(_enum_value(value))


def _with_network_suffix(summary: str, network_policy: NetworkSandboxPolicy | JsonValue) -> str:
    policy = network_policy if isinstance(network_policy, NetworkSandboxPolicy) else NetworkSandboxPolicy(str(network_policy))
    return f"{summary} (network access enabled)" if policy.is_enabled() else summary


def _session_configured_thread_id(session_configured: JsonValue) -> str:
    value = _field(session_configured, "thread_id", "threadId")
    if value is None:
        value = _field(session_configured, "session_id", "sessionId")
    return _id_to_string(value)


def _session_configured_session_id(session_configured: JsonValue) -> str:
    return _id_to_string(_field(session_configured, "session_id", "sessionId"))


def _id_to_string(value: JsonValue) -> str:
    if hasattr(value, "to_json") and callable(value.to_json):
        return str(value.to_json())
    return "" if value is None else str(value)


def _enum_value(value: JsonValue) -> JsonValue:
    return value.value if isinstance(value, Enum) else value


def _field(value: JsonValue, *names: str) -> JsonValue:
    if value is None:
        return None
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _int_field(value: JsonValue, *names: str) -> int:
    return _optional_int(_field(value, *names)) or 0


def _optional_int(value: JsonValue) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: JsonValue) -> str | None:
    if value is None:
        return None
    return str(value)


def _command_actions(value: JsonValue) -> tuple[JsonValue, ...] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return None


def _message_with_details(summary: JsonValue, details: JsonValue) -> str:
    summary_text = str(summary)
    if details:
        return f"{summary_text} ({details})"
    return summary_text


def _warning_summary(params: JsonValue) -> str:
    return str(_field(params, "summary", "message") or "")


def _notification_details(params: JsonValue) -> JsonValue:
    return _field(params, "details", "additionalDetails", "additional_details")


def _turn_error_message(error: JsonValue) -> str | None:
    if error is None:
        return None
    if isinstance(error, str):
        return error
    message = _field(error, "message")
    if message is None:
        return str(error)
    return _message_with_details(message, _field(error, "additionalDetails", "additional_details"))


def _model_rerouted_message(params: JsonValue, *, include_reason: bool) -> str:
    message = f"model rerouted: {_field(params, 'fromModel', 'from_model')} -> {_field(params, 'toModel', 'to_model')}"
    reason = _field(params, "reason")
    if include_reason:
        message = f"{message} ({_model_reroute_reason_debug(reason)})"
    return message


def _model_reroute_reason_debug(reason: JsonValue) -> str:
    value = _enum_value(reason)
    if value is None:
        return "None"
    text = str(value)
    if "_" in text:
        return "".join(part[:1].upper() + part[1:] for part in text.split("_") if part)
    return text[:1].upper() + text[1:] if text else text


def _turn_items(turn: JsonValue) -> tuple[JsonValue, ...]:
    items = _field(turn, "items")
    return tuple(items) if isinstance(items, list | tuple) else ()


def _turn_item_from_value(value: JsonValue) -> TurnItem | None:
    if isinstance(value, TurnItem):
        return value
    if not isinstance(value, Mapping):
        return None
    try:
        return TurnItem.from_mapping(value)
    except (KeyError, TypeError, ValueError):
        return None


def _item_id(item: JsonValue) -> str | None:
    turn_item = item if isinstance(item, TurnItem) else None
    if turn_item is not None:
        try:
            return turn_item.id()
        except AttributeError:
            return None
    raw = _field(item, "id")
    return None if raw is None else str(raw)


def _normalized_status(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "Completed": "completed",
        "completed": "completed",
        "Failed": "failed",
        "failed": "failed",
        "Interrupted": "interrupted",
        "interrupted": "interrupted",
        "InProgress": "in_progress",
        "inProgress": "in_progress",
        "in_progress": "in_progress",
        "Pending": "pending",
        "pending": "pending",
        "Declined": "declined",
        "declined": "declined",
    }
    return aliases.get(raw, raw)


def _normalized_item_type(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "AgentMessage": "agent_message",
        "agentMessage": "agent_message",
        "Reasoning": "reasoning",
        "reasoning": "reasoning",
        "CommandExecution": "command_execution",
        "commandExecution": "command_execution",
        "FileChange": "file_change",
        "fileChange": "file_change",
        "McpToolCall": "mcp_tool_call",
        "mcpToolCall": "mcp_tool_call",
        "CollabAgentToolCall": "collab_agent_tool_call",
        "collabAgentToolCall": "collab_agent_tool_call",
        "WebSearch": "web_search",
        "webSearch": "web_search",
        "ContextCompaction": "context_compaction",
        "contextCompaction": "context_compaction",
        "Plan": "plan",
        "plan": "plan",
    }
    return aliases.get(raw, raw)


def _uses_raw_exec_notification_boundary(item: JsonValue) -> bool:
    if not isinstance(item, Mapping):
        return False
    return _normalized_item_type(_field(item, "type")) in {
        "collab_agent_tool_call",
        "file_change",
        "web_search",
    }


def _turn_item_to_app_server_like_mapping(item: TurnItem) -> dict[str, JsonValue]:
    try:
        return item.to_app_server_mapping()
    except ValueError:
        pass
    return {"type": item.type, "id": item.id()}


def _file_change_entries(changes: JsonValue) -> list[dict[str, str]]:
    if isinstance(changes, Mapping):
        return [
            {
                "path": Path(str(path)).as_posix(),
                "kind": _patch_kind_text(_patch_kind_value(change)),
            }
            for path, change in changes.items()
        ]
    if isinstance(changes, list | tuple):
        return [
            {
                "path": Path(str(_field(change, "path") or "")).as_posix(),
                "kind": _patch_kind_text(_patch_kind_value(_field(change, "kind"))),
            }
            for change in changes
        ]
    return []


def _patch_kind_value(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        kind = _field(value, "kind")
        if kind is not None:
            return _patch_kind_value(kind)
        return _field(value, "type")
    return value


def _patch_kind_text(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    if raw in {"add", "Add"}:
        return "add"
    if raw in {"delete", "Delete"}:
        return "delete"
    if raw in {"update", "Update", ""}:
        return "update"
    return raw


def _patch_status_text(value: JsonValue) -> str:
    status = _normalized_status(value)
    if status == "completed":
        return "completed"
    if status in {"failed", "declined"}:
        return status
    if status in {"in_progress", ""}:
        return "in_progress"
    return status


def _patch_status_for_exec_json(value: JsonValue) -> str:
    status = _patch_status_text(value)
    if status == "declined":
        return "failed"
    return status


def _mcp_status_text(value: JsonValue) -> str:
    status = _normalized_status(value)
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status in {"in_progress", ""}:
        return "in_progress"
    return status


def _mcp_result_mapping(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    if hasattr(value, "to_mapping") and callable(value.to_mapping):
        return value.to_mapping()
    if not isinstance(value, Mapping):
        return value
    data: dict[str, JsonValue] = {
        "content": list(value.get("content", ())),
        "structured_content": value.get("structuredContent", value.get("structured_content")),
    }
    meta = value.get("_meta")
    if meta is not None:
        data["_meta"] = meta
    return data


def _mcp_error_mapping(value: JsonValue) -> JsonValue:
    if value is None:
        return None
    message = _field(value, "message")
    return {"message": str(message)} if message is not None else value


def _command_completion_line(item: JsonValue) -> str:
    status = _normalized_status(_field(item, "status"))
    suffix = _duration_suffix(_field(item, "durationMs", "duration_ms"))
    if status == "completed":
        return f" succeeded{suffix}:"
    if status == "failed":
        return f" exited {_optional_int(_field(item, 'exitCode', 'exit_code')) or 1}{suffix}:"
    if status == "declined":
        return f" declined{suffix}:"
    return f" in progress{suffix}:"


def _duration_suffix(value: JsonValue) -> str:
    duration = _optional_int(value)
    return f" in {duration}ms" if duration is not None else ""


def _collab_tool_debug(value: JsonValue) -> str:
    raw = str(_enum_value(value) or "")
    aliases = {
        "spawnAgent": "SpawnAgent",
        "spawn_agent": "SpawnAgent",
        "SpawnAgent": "SpawnAgent",
        "sendInput": "SendInput",
        "send_input": "SendInput",
        "SendInput": "SendInput",
        "resumeAgent": "ResumeAgent",
        "resume_agent": "ResumeAgent",
        "ResumeAgent": "ResumeAgent",
        "wait": "Wait",
        "Wait": "Wait",
        "closeAgent": "CloseAgent",
        "close_agent": "CloseAgent",
        "CloseAgent": "CloseAgent",
    }
    return aliases.get(raw, raw)


def _is_terminal(stream: TextIO, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    isatty = getattr(stream, "isatty", None)
    return bool(isatty()) if callable(isatty) else False


__all__ = [
    "CodexStatus",
    "CollectedThreadEvents",
    "HumanEventProcessor",
    "JsonEventProcessor",
    "agent_message_text_from_notification_item",
    "blended_total",
    "config_summary_entries",
    "config_summary_lines",
    "exec_turn_completed_notification",
    "exec_turn_started_notification",
    "exec_item_from_app_server_item",
    "format_with_separators",
    "handle_last_message",
    "human_item_completed_lines",
    "human_item_started_lines",
    "human_notification_lines",
    "map_todo_items",
    "notification_method",
    "notification_params",
    "should_print_final_message_to_stdout",
    "should_print_final_message_to_tty",
    "summarize_permission_profile",
    "summarize_sandbox_policy",
    "usage_from_notification",
]
