"""CLI app-exit formatting helpers.

Ported from ``codex/codex-rs/cli/src/main.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Any, TextIO

from pycodex.protocol import TokenUsage
from pycodex.utils_cli import resume_hint
from .update_action import UpdateAction


@dataclass(frozen=True)
class ExitReason:
    kind: str
    message: str | None = None

    @classmethod
    def user_requested(cls) -> "ExitReason":
        return cls("UserRequested")

    @classmethod
    def fatal(cls, message: str) -> "ExitReason":
        return cls("Fatal", message)


@dataclass(frozen=True)
class AppExitInfo:
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    thread_id: Any | None = None
    thread_name: str | None = None
    update_action: Any | None = None
    exit_reason: ExitReason = field(default_factory=ExitReason.user_requested)

    @classmethod
    def fatal(cls, message: str) -> "AppExitInfo":
        return cls(exit_reason=ExitReason.fatal(message))


def format_exit_messages(exit_info: AppExitInfo, color_enabled: bool = False) -> list[str]:
    if not isinstance(exit_info, AppExitInfo):
        raise TypeError("exit_info must be an AppExitInfo")

    lines: list[str] = []
    token_usage = exit_info.token_usage
    if not isinstance(token_usage, TokenUsage):
        raise TypeError("exit_info.token_usage must be a TokenUsage")
    if not token_usage.is_zero():
        lines.append(str(token_usage))

    command = resume_hint(exit_info.thread_name, exit_info.thread_id)
    if command is not None:
        if color_enabled:
            command = f"\x1b[36m{command}\x1b[39m"
        lines.append(f"To continue this session, run {command}")

    return lines


def handle_app_exit(
    exit_info: AppExitInfo,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    color_enabled: bool = False,
    run_update_action: Any | None = None,
) -> None:
    if not isinstance(exit_info, AppExitInfo):
        raise TypeError("exit_info must be an AppExitInfo")
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    reason = exit_info.exit_reason
    if not isinstance(reason, ExitReason):
        raise TypeError("exit_info.exit_reason must be an ExitReason")
    if reason.kind == "Fatal":
        print(f"ERROR: {reason.message or ''}", file=err)
        raise SystemExit(1)
    if reason.kind != "UserRequested":
        raise ValueError(f"unknown exit reason: {reason.kind}")

    update_action = exit_info.update_action
    for line in format_exit_messages(exit_info, color_enabled):
        print(line, file=out)
    if update_action is not None:
        if run_update_action is None:
            raise RuntimeError("run_update_action callback is required when update_action is set")
        run_update_action(update_action)


def run_update_action(
    action: UpdateAction,
    *,
    stdout: TextIO | None = None,
    runner: Any | None = None,
) -> None:
    if not isinstance(action, UpdateAction):
        raise TypeError("action must be an UpdateAction")
    out = stdout if stdout is not None else sys.stdout
    if runner is None:
        raise RuntimeError("runner callback is required to execute update action")

    command, args = action.command_args()
    command_str = action.command_str()
    print(file=out)
    print(f"Updating Codex via `{command_str}`...", file=out)

    status = runner(command, args)
    success = status if isinstance(status, bool) else getattr(status, "success", None)
    if callable(success):
        success = success()
    if success is None:
        success = getattr(status, "returncode", None) == 0
    if not success:
        raise RuntimeError(f"`{command_str}` failed with status {status}")

    print("\n\U0001f389 Update ran successfully! Please restart Codex.", file=out)
