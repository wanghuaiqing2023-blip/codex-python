"""User shell command record helpers ported from ``core/src/user_shell_command.rs``."""

from __future__ import annotations

from pycodex.protocol import (
    ContentItem,
    ExecToolCallOutput,
    ResponseItem,
    TruncationPolicyConfig,
)

from .context import UserShellCommand
from .tool_context import formatted_truncate_text


def format_exec_output_str(
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> str:
    """Format combined exec output for model-visible user-shell records."""

    _ensure_exec_output(exec_output)
    _ensure_truncation_policy(truncation_policy)
    content = _build_content_with_timeout(exec_output)
    return formatted_truncate_text(content, truncation_policy)


def format_user_shell_command_record(
    command: str,
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> str:
    _ensure_command(command)
    _ensure_exec_output(exec_output)
    _ensure_truncation_policy(truncation_policy)
    return _user_shell_command_fragment(command, exec_output, truncation_policy).render()


def user_shell_command_record_item(
    command: str,
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> ResponseItem:
    _ensure_command(command)
    _ensure_exec_output(exec_output)
    _ensure_truncation_policy(truncation_policy)
    fragment = _user_shell_command_fragment(command, exec_output, truncation_policy)
    return ResponseItem.message("user", (ContentItem.input_text(fragment.render()),))


def _user_shell_command_fragment(
    command: str,
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> UserShellCommand:
    output = format_exec_output_str(exec_output, truncation_policy)
    return UserShellCommand.new(command, exec_output.exit_code, exec_output.duration, output)


def _build_content_with_timeout(exec_output: ExecToolCallOutput) -> str:
    _ensure_exec_output(exec_output)
    if exec_output.timed_out:
        duration_ms = int(exec_output.duration.total_seconds() * 1000)
        return f"command timed out after {duration_ms} milliseconds\n{exec_output.aggregated_output.text}"
    return exec_output.aggregated_output.text


def _ensure_command(command: str) -> None:
    if not isinstance(command, str):
        raise TypeError("command must be a str")


def _ensure_exec_output(exec_output: ExecToolCallOutput) -> None:
    if not isinstance(exec_output, ExecToolCallOutput):
        raise TypeError("exec_output must be an ExecToolCallOutput")


def _ensure_truncation_policy(truncation_policy: TruncationPolicyConfig) -> None:
    if not isinstance(truncation_policy, TruncationPolicyConfig):
        raise TypeError("truncation_policy must be a TruncationPolicyConfig")


__all__ = [
    "format_exec_output_str",
    "format_user_shell_command_record",
    "user_shell_command_record_item",
]
