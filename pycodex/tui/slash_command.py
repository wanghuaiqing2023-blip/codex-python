"""Slash command definitions for Rust ``codex-tui::slash_command``."""

from __future__ import annotations

import sys
from enum import Enum
from typing import List, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="slash_command", source="codex/codex-rs/tui/src/slash_command.rs", status="complete")


class SlashCommand(Enum):
    # Keep declaration order aligned with Rust; it is popup presentation order.
    MODEL = "model"
    IDE = "ide"
    PERMISSIONS = "permissions"
    KEYMAP = "keymap"
    VIM = "vim"
    ELEVATE_SANDBOX = "setup-default-sandbox"
    SANDBOX_READ_ROOT = "sandbox-add-read-dir"
    EXPERIMENTAL = "experimental"
    AUTO_REVIEW = "approve"
    MEMORIES = "memories"
    SKILLS = "skills"
    HOOKS = "hooks"
    REVIEW = "review"
    RENAME = "rename"
    NEW = "new"
    RESUME = "resume"
    FORK = "fork"
    INIT = "init"
    COMPACT = "compact"
    PLAN = "plan"
    GOAL = "goal"
    AGENT = "agent"
    SIDE = "side"
    BTW = "btw"
    COPY = "copy"
    RAW = "raw"
    DIFF = "diff"
    MENTION = "mention"
    STATUS = "status"
    DEBUG_CONFIG = "debug-config"
    TITLE = "title"
    STATUSLINE = "statusline"
    THEME = "theme"
    PETS = "pets"
    MCP = "mcp"
    APPS = "apps"
    PLUGINS = "plugins"
    LOGOUT = "logout"
    QUIT = "quit"
    EXIT = "exit"
    FEEDBACK = "feedback"
    ROLLOUT = "rollout"
    PS = "ps"
    STOP = "stop"
    CLEAR = "clear"
    PERSONALITY = "personality"
    REALTIME = "realtime"
    SETTINGS = "settings"
    TEST_APPROVAL = "test-approval"
    MULTI_AGENTS = "subagents"
    MEMORY_DROP = "debug-m-drop"
    MEMORY_UPDATE = "debug-m-update"

    def description(self) -> str:
        return _DESCRIPTIONS[self]

    def command(self) -> str:
        return self.value

    def supports_inline_args(self) -> bool:
        return self in _INLINE_ARG_COMMANDS

    def available_in_side_conversation(self) -> bool:
        return self in _SIDE_CONVERSATION_COMMANDS

    def available_during_task(self) -> bool:
        return self in _AVAILABLE_DURING_TASK

    def is_visible(self) -> bool:
        if self is SlashCommand.SANDBOX_READ_ROOT:
            return sys.platform == "win32"
        if self is SlashCommand.COPY:
            return sys.platform != "android"
        if self in {SlashCommand.ROLLOUT, SlashCommand.TEST_APPROVAL}:
            return __debug__
        return True

    @classmethod
    def parse(cls, text: str) -> "SlashCommand":
        normalized = text.strip()
        if normalized.startswith("/"):
            normalized = normalized[1:]
        try:
            return _ALIASES[normalized]
        except KeyError:
            raise ValueError(f"unknown slash command: {text}") from None


_DESCRIPTIONS = {
    SlashCommand.FEEDBACK: "send logs to maintainers",
    SlashCommand.NEW: "start a new chat during a conversation",
    SlashCommand.INIT: "create an AGENTS.md file with instructions for Codex",
    SlashCommand.COMPACT: "summarize conversation to prevent hitting the context limit",
    SlashCommand.REVIEW: "review my current changes and find issues",
    SlashCommand.RENAME: "rename the current thread",
    SlashCommand.RESUME: "resume a saved chat",
    SlashCommand.CLEAR: "clear the terminal and start a new chat",
    SlashCommand.FORK: "fork the current chat",
    SlashCommand.QUIT: "exit Codex",
    SlashCommand.EXIT: "exit Codex",
    SlashCommand.COPY: "copy last response as markdown",
    SlashCommand.RAW: "toggle raw scrollback mode for copy-friendly terminal selection",
    SlashCommand.DIFF: "show git diff (including untracked files)",
    SlashCommand.MENTION: "mention a file",
    SlashCommand.SKILLS: "use skills to improve how Codex performs specific tasks",
    SlashCommand.HOOKS: "view and manage lifecycle hooks",
    SlashCommand.STATUS: "show current session configuration and token usage",
    SlashCommand.DEBUG_CONFIG: "show config layers and requirement sources for debugging",
    SlashCommand.TITLE: "configure which items appear in the terminal title",
    SlashCommand.STATUSLINE: "configure which items appear in the status line",
    SlashCommand.THEME: "choose a syntax highlighting theme",
    SlashCommand.PETS: "choose or hide the terminal pet",
    SlashCommand.PS: "list background terminals",
    SlashCommand.STOP: "stop all background terminals",
    SlashCommand.MEMORY_DROP: "DO NOT USE",
    SlashCommand.MEMORY_UPDATE: "DO NOT USE",
    SlashCommand.MODEL: "choose what model and reasoning effort to use",
    SlashCommand.IDE: "include current selection, open files, and other context from your IDE",
    SlashCommand.PERSONALITY: "choose a communication style for Codex",
    SlashCommand.REALTIME: "toggle realtime voice mode (experimental)",
    SlashCommand.SETTINGS: "configure realtime microphone/speaker",
    SlashCommand.PLAN: "switch to Plan mode",
    SlashCommand.GOAL: "set or view the goal for a long-running task",
    SlashCommand.AGENT: "switch the active agent thread",
    SlashCommand.MULTI_AGENTS: "switch the active agent thread",
    SlashCommand.SIDE: "start a side conversation in an ephemeral fork",
    SlashCommand.BTW: "start a side conversation in an ephemeral fork",
    SlashCommand.PERMISSIONS: "choose what Codex is allowed to do",
    SlashCommand.KEYMAP: "remap TUI shortcuts",
    SlashCommand.VIM: "toggle Vim mode for the composer",
    SlashCommand.ELEVATE_SANDBOX: "set up elevated agent sandbox",
    SlashCommand.SANDBOX_READ_ROOT: "let sandbox read a directory: /sandbox-add-read-dir <absolute_path>",
    SlashCommand.EXPERIMENTAL: "toggle experimental features",
    SlashCommand.AUTO_REVIEW: "approve one retry of a recent auto-review denial",
    SlashCommand.MEMORIES: "configure memory use and generation",
    SlashCommand.MCP: "list configured MCP tools; use /mcp verbose for details",
    SlashCommand.APPS: "manage apps",
    SlashCommand.PLUGINS: "browse plugins",
    SlashCommand.LOGOUT: "log out of Codex",
    SlashCommand.ROLLOUT: "print the rollout file path",
    SlashCommand.TEST_APPROVAL: "test approval request",
}

_INLINE_ARG_COMMANDS = {
    SlashCommand.REVIEW,
    SlashCommand.RENAME,
    SlashCommand.PLAN,
    SlashCommand.GOAL,
    SlashCommand.IDE,
    SlashCommand.KEYMAP,
    SlashCommand.MCP,
    SlashCommand.RAW,
    SlashCommand.PETS,
    SlashCommand.SIDE,
    SlashCommand.BTW,
    SlashCommand.RESUME,
    SlashCommand.SANDBOX_READ_ROOT,
}

_SIDE_CONVERSATION_COMMANDS = {
    SlashCommand.COPY,
    SlashCommand.RAW,
    SlashCommand.DIFF,
    SlashCommand.MENTION,
    SlashCommand.STATUS,
    SlashCommand.IDE,
}

_AVAILABLE_DURING_TASK = {
    SlashCommand.DIFF,
    SlashCommand.COPY,
    SlashCommand.RAW,
    SlashCommand.RENAME,
    SlashCommand.MENTION,
    SlashCommand.SKILLS,
    SlashCommand.HOOKS,
    SlashCommand.STATUS,
    SlashCommand.DEBUG_CONFIG,
    SlashCommand.PS,
    SlashCommand.STOP,
    SlashCommand.GOAL,
    SlashCommand.MCP,
    SlashCommand.APPS,
    SlashCommand.PLUGINS,
    SlashCommand.TITLE,
    SlashCommand.STATUSLINE,
    SlashCommand.AUTO_REVIEW,
    SlashCommand.FEEDBACK,
    SlashCommand.IDE,
    SlashCommand.QUIT,
    SlashCommand.EXIT,
    SlashCommand.SIDE,
    SlashCommand.BTW,
    SlashCommand.ROLLOUT,
    SlashCommand.TEST_APPROVAL,
    SlashCommand.REALTIME,
    SlashCommand.SETTINGS,
    SlashCommand.AGENT,
    SlashCommand.MULTI_AGENTS,
}

_ALIASES = {command.command(): command for command in SlashCommand}
_ALIASES.update(
    {
        "clean": SlashCommand.STOP,
        "pet": SlashCommand.PETS,
        "approve": SlashCommand.AUTO_REVIEW,
        "multi-agents": SlashCommand.MULTI_AGENTS,
        "subagents": SlashCommand.MULTI_AGENTS,
    }
)


def built_in_slash_commands() -> List[Tuple[str, SlashCommand]]:
    return [(command.command(), command) for command in SlashCommand if command.is_visible()]


__all__ = [
    "RUST_MODULE",
    "SlashCommand",
    "built_in_slash_commands",
]

