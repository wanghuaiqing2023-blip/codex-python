"""Upstream CLI command specification.

Ported from ``codex/codex-rs/cli/src/main.rs``:

- ``MultitoolCli`` defines the top-level parser.
- ``Subcommand`` defines these command names, aliases, and hidden commands.

Only the command surface is represented here. Command implementations are added
module-by-module as the Rust crates are ported.
"""

from __future__ import annotations

from dataclasses import dataclass


UPSTREAM_CLI_MAIN = "codex/codex-rs/cli/src/main.rs"


@dataclass(frozen=True)
class CommandSpec:
    """A top-level Codex command as declared by upstream clap metadata."""

    name: str
    upstream_variant: str
    help: str
    aliases: tuple[str, ...] = ()
    hidden: bool = False
    platform: str | None = None

    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


TOP_LEVEL_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "exec",
        "Exec",
        "Run Codex non-interactively.",
        aliases=("e",),
    ),
    CommandSpec("review", "Review", "Run a code review non-interactively."),
    CommandSpec("login", "Login", "Manage login."),
    CommandSpec("logout", "Logout", "Remove stored authentication credentials."),
    CommandSpec("mcp", "Mcp", "Manage external MCP servers for Codex."),
    CommandSpec("plugin", "Plugin", "Manage Codex plugins."),
    CommandSpec("mcp-server", "McpServer", "Start Codex as an MCP server (stdio)."),
    CommandSpec("app-server", "AppServer", "[experimental] Run the app server or related tooling."),
    CommandSpec(
        "remote-control",
        "RemoteControl",
        "[experimental] Manage the app-server daemon with remote control enabled.",
    ),
    CommandSpec(
        "app",
        "App",
        "Launch the Codex desktop app (opens the app installer if missing).",
        platform="macos/windows",
    ),
    CommandSpec("completion", "Completion", "Generate shell completion scripts."),
    CommandSpec("update", "Update", "Update Codex to the latest version."),
    CommandSpec(
        "doctor",
        "Doctor",
        "Diagnose local Codex installation, config, auth, and runtime health.",
    ),
    CommandSpec("sandbox", "Sandbox", "Run commands within a Codex-provided sandbox."),
    CommandSpec("debug", "Debug", "Debugging tools."),
    CommandSpec("execpolicy", "Execpolicy", "Execpolicy tooling.", hidden=True),
    CommandSpec(
        "apply",
        "Apply",
        "Apply the latest diff produced by Codex agent as a git apply to your local working tree.",
        aliases=("a",),
    ),
    CommandSpec(
        "resume",
        "Resume",
        "Resume a previous interactive session.",
    ),
    CommandSpec(
        "fork",
        "Fork",
        "Fork a previous interactive session.",
    ),
    CommandSpec(
        "cloud",
        "Cloud",
        "[EXPERIMENTAL] Browse tasks from Codex Cloud and apply changes locally.",
        aliases=("cloud-tasks",),
    ),
    CommandSpec(
        "responses-api-proxy",
        "ResponsesApiProxy",
        "Internal: run the responses API proxy.",
        hidden=True,
    ),
    CommandSpec(
        "stdio-to-uds",
        "StdioToUds",
        "Internal: relay stdio to a Unix domain socket.",
        hidden=True,
    ),
    CommandSpec(
        "exec-server",
        "ExecServer",
        "[EXPERIMENTAL] Run the standalone exec-server service.",
    ),
    CommandSpec("features", "Features", "Inspect feature flags."),
)


COMMANDS_BY_NAME: dict[str, CommandSpec] = {
    name: command for command in TOP_LEVEL_COMMANDS for name in command.all_names()
}


def visible_commands() -> tuple[CommandSpec, ...]:
    return tuple(command for command in TOP_LEVEL_COMMANDS if not command.hidden)
