"""Human-readable event processor for ``codex exec``.

Port of ``codex-exec/src/event_processor_with_human_output.rs``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import sys
from typing import TextIO

from pycodex.protocol import (
    PermissionProfile,
    SessionConfiguredEvent,
    TurnItem,
    approval_policy_display_value,
)
from pycodex.utils.sandbox_summary import summarize_permission_profile

from .event_processor import (
    CodexStatus,
    DEFAULT_CODEX_VERSION,
    JsonValue,
    _command_actions,
    _command_completion_line,
    _collab_tool_debug,
    _duration_suffix,
    _field,
    _file_change_entries,
    _is_terminal,
    _message_with_details,
    _mcp_status_text,
    _model_rerouted_message,
    _notification_details,
    _normalized_item_type,
    _normalized_status,
    _optional_int,
    _optional_reasoning,
    _patch_kind_text,
    _patch_status_text,
    _permission_profile_from_config,
    _session_configured_session_id,
    _turn_error_message,
    _turn_item_from_value,
    _turn_item_to_app_server_like_mapping,
    _turn_items,
    _uses_responses_wire_api,
    _warning_summary,
    agent_message_text_from_notification_item,
    final_message_from_notification_items,
    handle_last_message,
    notification_method,
    notification_params,
    usage_from_notification,
)
from .events import Usage, final_message_from_turn_items

class EventProcessorWithHumanOutput:
    """Human-output state that mirrors the upstream final-output decisions."""

    def __init__(self, last_message_path: str | Path | None = None) -> None:
        self.last_message_path = Path(last_message_path) if last_message_path is not None else None
        self.final_message: str | None = None
        self.final_message_rendered = False
        self.emit_final_message_on_shutdown = False
        self.last_usage: Usage | None = None
        self.show_agent_reasoning = True
        self.show_raw_agent_reasoning = False

    def configure_from_config(self, config: JsonValue) -> "EventProcessorWithHumanOutput":
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


def format_with_separators(value: int) -> str:
    return f"{value:,}"


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

__all__ = [
    "EventProcessorWithHumanOutput",
    "agent_message_text_from_notification_item",
    "blended_total",
    "config_summary_entries",
    "config_summary_lines",
    "format_with_separators",
    "human_item_completed_lines",
    "human_item_started_lines",
    "human_notification_lines",
    "reasoning_text_from_notification_item",
    "should_print_final_message_to_stdout",
    "should_print_final_message_to_tty",
    "summarize_permission_profile",
    "summarize_sandbox_policy",
]
