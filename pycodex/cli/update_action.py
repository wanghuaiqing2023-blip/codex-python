"""Update action command formatting.

Ported from ``codex/codex-rs/tui/src/update_action.rs``.
"""

from __future__ import annotations

from enum import Enum

from pycodex.shell_command import shlex_join


class UpdateAction(Enum):
    NPM_GLOBAL_LATEST = "NpmGlobalLatest"
    BUN_GLOBAL_LATEST = "BunGlobalLatest"
    BREW_UPGRADE = "BrewUpgrade"
    STANDALONE_UNIX = "StandaloneUnix"
    STANDALONE_WINDOWS = "StandaloneWindows"

    def command_args(self) -> tuple[str, tuple[str, ...]]:
        if self is UpdateAction.NPM_GLOBAL_LATEST:
            return ("npm", ("install", "-g", "@openai/codex"))
        if self is UpdateAction.BUN_GLOBAL_LATEST:
            return ("bun", ("install", "-g", "@openai/codex"))
        if self is UpdateAction.BREW_UPGRADE:
            return ("brew", ("upgrade", "--cask", "codex"))
        if self is UpdateAction.STANDALONE_UNIX:
            return (
                "sh",
                ("-c", "curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh"),
            )
        if self is UpdateAction.STANDALONE_WINDOWS:
            return (
                "powershell",
                (
                    "-ExecutionPolicy",
                    "Bypass",
                    "-c",
                    "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
                ),
            )
        raise ValueError(f"unknown update action: {self!r}")

    def command_str(self) -> str:
        command, args = self.command_args()
        return shlex_join((command, *args))


def update_action_label(action: UpdateAction | None) -> str:
    if action is None:
        return "manual or unknown"
    if not isinstance(action, UpdateAction):
        raise TypeError("action must be an UpdateAction or None")
    if action is UpdateAction.NPM_GLOBAL_LATEST:
        return "npm install -g @openai/codex"
    if action is UpdateAction.BUN_GLOBAL_LATEST:
        return "bun install -g @openai/codex"
    if action is UpdateAction.BREW_UPGRADE:
        return "brew upgrade --cask codex"
    if action in {UpdateAction.STANDALONE_UNIX, UpdateAction.STANDALONE_WINDOWS}:
        return "standalone installer"
    raise ValueError(f"unknown update action: {action!r}")
