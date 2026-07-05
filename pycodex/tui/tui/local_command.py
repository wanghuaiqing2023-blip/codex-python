"""Local command planning for the lightweight terminal TUI product path.

Rust anchors:
- ``codex-tui::slash_command`` defines command names and aliases.
- ``codex-tui::app::history_ui`` owns transcript reset behavior for ``/clear``.

This module only plans the small command subset handled directly by
``terminal_runtime``. Commands with richer UI behavior, such as ``/model``,
remain outside this local runner path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..slash_command import SlashCommand


HELP_MESSAGE = "\u2022 Commands: /clear, /status, /quit"


@dataclass(frozen=True)
class TerminalLocalCommandPlan:
    action: str
    message: str | None = None


@dataclass
class TerminalLocalCommandDispatcher:
    """Stateful dispatcher for terminal-local slash command handling."""

    clear: Callable[[], Any]
    help_: Callable[[str], Any]
    status: Callable[[], Any]

    def run(self, prompt: str) -> bool | str:
        return run_terminal_local_command(
            prompt,
            clear=self.clear,
            help_=self.help_,
            status=self.status,
        )


_EXIT_ALIASES = {":q", "q", "quit", "exit"}


def plan_terminal_local_command(prompt: str) -> TerminalLocalCommandPlan:
    stripped = prompt.strip()
    lowered = stripped.lower()
    if lowered in _EXIT_ALIASES:
        return TerminalLocalCommandPlan("exit")
    if lowered == "/?":
        return TerminalLocalCommandPlan("help", HELP_MESSAGE)
    command = _parse_slash_command(lowered)
    if command in {SlashCommand.QUIT, SlashCommand.EXIT}:
        return TerminalLocalCommandPlan("exit")
    if command is SlashCommand.CLEAR:
        return TerminalLocalCommandPlan("clear")
    if command is SlashCommand.STATUS:
        return TerminalLocalCommandPlan("status")
    if lowered == "/help":
        return TerminalLocalCommandPlan("help", HELP_MESSAGE)
    return TerminalLocalCommandPlan("none")


def run_terminal_local_command_plan(
    plan: TerminalLocalCommandPlan,
    *,
    clear: Callable[[], Any],
    help_: Callable[[str], Any],
    status: Callable[[], Any],
) -> bool | str:
    """Dispatch a terminal local-command plan through runner callbacks."""

    if plan.action == "exit":
        return "exit"
    if plan.action == "clear":
        clear()
        return True
    if plan.action == "help":
        help_(plan.message or "")
        return True
    if plan.action == "status":
        status()
        return True
    return False


def run_terminal_local_command(
    prompt: str,
    *,
    clear: Callable[[], Any],
    help_: Callable[[str], Any],
    status: Callable[[], Any],
) -> bool | str:
    """Plan and dispatch the lightweight terminal local-command subset."""

    return run_terminal_local_command_plan(
        plan_terminal_local_command(prompt),
        clear=clear,
        help_=help_,
        status=status,
    )


def _parse_slash_command(text: str) -> SlashCommand | None:
    if not text.startswith("/"):
        return None
    try:
        return SlashCommand.parse(text)
    except ValueError:
        return None


__all__ = [
    "HELP_MESSAGE",
    "TerminalLocalCommandDispatcher",
    "TerminalLocalCommandPlan",
    "plan_terminal_local_command",
    "run_terminal_local_command",
    "run_terminal_local_command_plan",
]
