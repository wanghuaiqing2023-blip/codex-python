"""User shell command record helpers ported from ``core/src/user_shell_command.rs``."""

from __future__ import annotations

import sys
from collections.abc import Mapping

from pycodex.protocol import (
    ContentItem,
    ExecToolCallOutput,
    ResponseItem,
    TruncationPolicyConfig,
)

from .context import UserShellCommand
from .tools.context import formatted_truncate_text


def format_exec_output_str(
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> str:
    """Format combined exec output for model-visible user-shell records."""

    _ensure_exec_output(exec_output)
    _ensure_truncation_policy(truncation_policy)
    content = _build_content_with_timeout(exec_output)
    return formatted_truncate_text(content, truncation_policy)


def format_exec_output_for_model(
    exec_output: ExecToolCallOutput,
    truncation_policy: TruncationPolicyConfig,
) -> str:
    """Format exec output for direct tool responses returned to the model."""

    _ensure_exec_output(exec_output)
    _ensure_truncation_policy(truncation_policy)
    duration_seconds = _round_duration_seconds_for_model(exec_output.duration.total_seconds())
    content = _build_content_with_timeout(exec_output)
    total_lines = len(content.splitlines())
    formatted_output = _truncate_text(content, truncation_policy)
    sections = [
        f"Exit code: {exec_output.exit_code}",
        f"Wall time: {duration_seconds:g} seconds",
    ]
    if total_lines != len(formatted_output.splitlines()):
        sections.append(f"Total output lines: {total_lines}")
    sections.append("Output:")
    sections.append(formatted_output)
    return "\n".join(sections)


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


def env_for_user_shell_command(
    env: Mapping[str, str],
    *,
    target_os: str | None = None,
) -> dict[str, str]:
    """Return the environment used by the explicit user-shell escape hatch."""

    from .tools.runtimes import (
        CODEX_PROXY_GIT_SSH_COMMAND_MARKER,
        PROXY_ACTIVE_ENV_KEY,
        PROXY_ENV_KEYS,
        PROXY_GIT_SSH_COMMAND_ENV_KEY,
    )

    result = _env_dict(env)
    if PROXY_ACTIVE_ENV_KEY not in result:
        return result

    for key in PROXY_ENV_KEYS:
        result.pop(key, None)

    if _is_macos_target(target_os):
        git_ssh_command = result.get(PROXY_GIT_SSH_COMMAND_ENV_KEY)
        if git_ssh_command is not None and git_ssh_command.startswith(CODEX_PROXY_GIT_SSH_COMMAND_MARKER):
            result.pop(PROXY_GIT_SSH_COMMAND_ENV_KEY, None)

    return result


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


def _round_duration_seconds_for_model(seconds: float) -> float:
    if seconds >= 0:
        return int(seconds * 10 + 0.5) / 10
    return int(seconds * 10 - 0.5) / 10


def _env_dict(env: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(env, Mapping):
        raise TypeError("env must be a mapping")
    result: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("env keys and values must be strings")
        result[key] = value
    return result


def _is_macos_target(target_os: str | None = None) -> bool:
    if target_os is None:
        target_os = sys.platform
    if not isinstance(target_os, str):
        raise TypeError("target_os must be a string or None")
    return target_os.lower() in {"darwin", "macos", "mac", "osx"}


def _truncate_text(content: str, policy: TruncationPolicyConfig) -> str:
    if len(content.encode("utf-8")) <= _policy_byte_budget(policy):
        return content
    from .tools.context import truncate_text

    return truncate_text(content, policy)


def _policy_byte_budget(policy: TruncationPolicyConfig) -> int:
    if policy.mode.value == "bytes":
        return max(policy.limit, 0)
    from pycodex.utils.string import approx_bytes_for_tokens

    return approx_bytes_for_tokens(policy.limit)


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
    "env_for_user_shell_command",
    "format_exec_output_for_model",
    "format_exec_output_str",
    "format_user_shell_command_record",
    "user_shell_command_record_item",
]
