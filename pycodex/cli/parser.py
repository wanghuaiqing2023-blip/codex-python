"""Top-level CLI parser for the Python Codex port.

This module mirrors the top-level command dispatch shape from upstream
``codex/codex-rs/cli/src/main.rs`` while keeping command implementations as
future porting work. Parsing is deliberately explicit instead of relying on a
third-party CLI framework so the runtime dependency set stays in the standard
library.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from typing import Iterable, TextIO

from pycodex.config import CliConfigOverrides, ConfigOverride
from pycodex.exec import ExecCli, ExecCliParseError, parse_exec_args
from pycodex.protocol import AskForApproval, ProfileV2Name, ProfileV2NameParseError, SandboxMode
from pycodex.protocol.config_types import ConfigTypeParseError

from .spec import COMMANDS_BY_NAME, UPSTREAM_CLI_MAIN, CommandSpec, visible_commands


ROOT_USAGE = "codex [OPTIONS] [PROMPT]\n       codex [OPTIONS] <COMMAND> [ARGS]"


class CliParseError(ValueError):
    """Raised when arguments do not match the ported Codex CLI surface."""


@dataclass(frozen=True)
class ParsedCli:
    """Parsed top-level Codex CLI invocation."""

    command: str | None
    command_spec: CommandSpec | None
    command_args: tuple[str, ...] = ()
    prompt: str | None = None
    config_overrides: tuple[str, ...] = ()
    enable: tuple[str, ...] = ()
    disable: tuple[str, ...] = ()
    remote: str | None = None
    remote_auth_token_env: str | None = None
    strict_config: bool = False
    root_options: dict[str, object] = field(default_factory=dict)
    upstream_source: str = UPSTREAM_CLI_MAIN

    @property
    def is_interactive(self) -> bool:
        return self.command is None

    def cli_config_overrides(self) -> CliConfigOverrides:
        """Return raw overrides in the shared config override parser type."""

        return CliConfigOverrides(list(self.config_overrides))

    def parsed_config_overrides(self) -> list[ConfigOverride]:
        """Parse root ``-c/--config`` flags using the ported upstream logic."""

        return self.cli_config_overrides().parse_overrides()

    def exec_cli(self) -> ExecCli:
        """Parse this invocation as ``codex exec`` and inherit root options."""

        if self.command != "exec":
            raise CliParseError("Parsed CLI invocation is not an exec command")

        exec_cli = parse_exec_args(self.command_args, root_config_overrides=self.config_overrides)
        return _inherit_exec_root_options(exec_cli, self)


@dataclass
class _ParseState:
    config_overrides: list[str] = field(default_factory=list)
    enable: list[str] = field(default_factory=list)
    disable: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    add_dirs: list[str] = field(default_factory=list)
    remote: str | None = None
    remote_auth_token_env: str | None = None
    strict_config: bool = False
    root_options: dict[str, object] = field(default_factory=dict)

    def as_root_options(self) -> dict[str, object]:
        options = dict(self.root_options)
        if self.images:
            options["images"] = tuple(self.images)
        if self.add_dirs:
            options["add_dir"] = tuple(self.add_dirs)
        return options


_VALUE_OPTIONS = {
    "--config": "config",
    "-c": "config",
    "--enable": "enable",
    "--disable": "disable",
    "--remote": "remote",
    "--remote-auth-token-env": "remote_auth_token_env",
    "--image": "image",
    "-i": "image",
    "--model": "model",
    "-m": "model",
    "--local-provider": "local_provider",
    "--profile": "profile",
    "-p": "profile",
    "--sandbox": "sandbox",
    "-s": "sandbox",
    "--cd": "cwd",
    "-C": "cwd",
    "--add-dir": "add_dir",
    "--ask-for-approval": "approval_policy",
    "-a": "approval_policy",
}

_FLAG_OPTIONS = {
    "--strict-config": "strict_config",
    "--oss": "oss",
    "--dangerously-bypass-approvals-and-sandbox": "dangerously_bypass_approvals_and_sandbox",
    "--yolo": "dangerously_bypass_approvals_and_sandbox",
    "--dangerously-bypass-hook-trust": "dangerously_bypass_hook_trust",
    "--search": "search",
    "--no-alt-screen": "no_alt_screen",
}


def parse_args(argv: Iterable[str] | None = None) -> ParsedCli:
    """Parse a top-level Codex invocation.

    The first non-option token matching an upstream top-level command starts
    command mode. Remaining tokens are preserved for that command's future
    parser. If no command is present, at most one positional prompt is accepted,
    matching upstream's ``Option<String>`` prompt shape.
    """

    tokens = list(sys.argv[1:] if argv is None else argv)
    state = _ParseState()
    positional: list[str] = []
    i = 0

    while i < len(tokens):
        token = tokens[i]

        if token == "--":
            positional.extend(tokens[i + 1 :])
            break

        command = COMMANDS_BY_NAME.get(token)
        if command is not None and not positional:
            return ParsedCli(
                command=command.name,
                command_spec=command,
                command_args=tuple(tokens[i + 1 :]),
                config_overrides=tuple(state.config_overrides),
                enable=tuple(state.enable),
                disable=tuple(state.disable),
                remote=state.remote,
                remote_auth_token_env=state.remote_auth_token_env,
                strict_config=state.strict_config,
                root_options=state.as_root_options(),
            )

        if token in ("--help", "-h"):
            raise CliParseError(_format_help())

        consumed = _consume_option(tokens, i, state)
        if consumed:
            i += consumed
            continue

        if token.startswith("-"):
            raise CliParseError(f"Unknown option: {token}")

        positional.append(token)
        i += 1

    if len(positional) > 1:
        joined = " ".join(positional[1:])
        raise CliParseError(f"Unexpected extra argument(s): {joined}")

    return ParsedCli(
        command=None,
        command_spec=None,
        prompt=positional[0] if positional else None,
        config_overrides=tuple(state.config_overrides),
        enable=tuple(state.enable),
        disable=tuple(state.disable),
        remote=state.remote,
        remote_auth_token_env=state.remote_auth_token_env,
        strict_config=state.strict_config,
        root_options=state.as_root_options(),
    )


def _consume_option(tokens: list[str], index: int, state: _ParseState) -> int:
    token = tokens[index]

    if token in _FLAG_OPTIONS:
        dest = _FLAG_OPTIONS[token]
        if dest == "strict_config":
            state.strict_config = True
        else:
            state.root_options[dest] = True
        return 1

    option, sep, inline_value = token.partition("=")
    if sep and option in _VALUE_OPTIONS:
        _store_value(_VALUE_OPTIONS[option], inline_value, state, option)
        return 1

    if token in _VALUE_OPTIONS:
        if index + 1 >= len(tokens):
            raise CliParseError(f"Missing value for option: {token}")
        _store_value(_VALUE_OPTIONS[token], tokens[index + 1], state, token)
        return 2

    return 0


def _store_value(dest: str, value: str, state: _ParseState, option: str) -> None:
    if value == "" and dest != "config":
        raise CliParseError(f"Missing value for option: {option}")

    if dest == "config":
        state.config_overrides.append(value)
    elif dest == "enable":
        state.enable.append(value)
    elif dest == "disable":
        state.disable.append(value)
    elif dest == "remote":
        state.remote = value
    elif dest == "remote_auth_token_env":
        state.remote_auth_token_env = value
    elif dest == "image":
        state.images.extend(part for part in value.split(",") if part)
    elif dest == "add_dir":
        state.add_dirs.append(value)
    elif dest == "sandbox":
        try:
            state.root_options[dest] = SandboxMode.parse(value)
        except ConfigTypeParseError as exc:
            raise CliParseError(str(exc)) from exc
    elif dest == "approval_policy":
        try:
            state.root_options[dest] = AskForApproval.parse_cli(value)
        except ConfigTypeParseError as exc:
            raise CliParseError(str(exc)) from exc
    elif dest == "profile":
        try:
            state.root_options[dest] = ProfileV2Name.parse(value)
        except ProfileV2NameParseError as exc:
            raise CliParseError(str(exc)) from exc
    else:
        state.root_options[dest] = value


def _format_help() -> str:
    lines = [
        "Codex CLI",
        "",
        "Usage:",
        f"  {ROOT_USAGE}",
        "",
        "Options:",
        "  -c, --config key=value      Override a configuration value.",
        "      --enable FEATURE        Enable a feature flag.",
        "      --disable FEATURE       Disable a feature flag.",
        "      --remote ADDR           Connect the TUI to a remote app server endpoint.",
        "      --strict-config         Error on unknown config.toml fields.",
        "  -h, --help                  Show this help message.",
        "",
        "Commands:",
    ]
    for command in visible_commands():
        aliases = f" ({', '.join(command.aliases)})" if command.aliases else ""
        lines.append(f"  {command.name:<18}{command.help}{aliases}")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """CLI entry point.

    Recognized commands currently stop at dispatch because the Rust command
    bodies are still being ported.
    """

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    try:
        parsed = parse_args(argv)
    except CliParseError as exc:
        message = str(exc)
        stream = out if message.startswith("Codex CLI") else err
        print(message, file=stream)
        return 0 if stream is out else 2

    if parsed.is_interactive:
        print("pycodex: interactive TUI is recognized but not implemented yet.", file=err)
    elif parsed.command == "exec":
        try:
            parsed.exec_cli()
        except ExecCliParseError as exc:
            print(str(exc), file=err)
            return 2
        print("pycodex: command 'exec' is recognized but not implemented yet.", file=err)
    else:
        print(
            f"pycodex: command '{parsed.command}' is recognized but not implemented yet.",
            file=err,
        )
    return 64


def _inherit_exec_root_options(exec_cli: ExecCli, parsed: ParsedCli) -> ExecCli:
    """Mirror ``SharedCliOptions::inherit_exec_root_options`` for top-level exec."""

    root = parsed.root_options
    images = tuple(root.get("images", ())) + exec_cli.images
    add_dir = tuple(root.get("add_dir", ())) + exec_cli.add_dir
    root_selected_sandbox = "sandbox" in root or bool(root.get("dangerously_bypass_approvals_and_sandbox"))
    exec_selected_sandbox = exec_cli.sandbox is not None or exec_cli.dangerously_bypass_approvals_and_sandbox

    return replace(
        exec_cli,
        strict_config=exec_cli.strict_config or parsed.strict_config,
        images=images,
        model=exec_cli.model if exec_cli.model is not None else _typed_root_value(root, "model", str),
        oss=exec_cli.oss or bool(root.get("oss", False)),
        local_provider=exec_cli.local_provider
        if exec_cli.local_provider is not None
        else _typed_root_value(root, "local_provider", str),
        profile=exec_cli.profile if exec_cli.profile is not None else _typed_root_value(root, "profile", ProfileV2Name),
        sandbox=exec_cli.sandbox
        if exec_selected_sandbox or not root_selected_sandbox
        else _typed_root_value(root, "sandbox", SandboxMode),
        dangerously_bypass_approvals_and_sandbox=exec_cli.dangerously_bypass_approvals_and_sandbox
        if exec_selected_sandbox
        else bool(root.get("dangerously_bypass_approvals_and_sandbox", False)),
        dangerously_bypass_hook_trust=exec_cli.dangerously_bypass_hook_trust
        or bool(root.get("dangerously_bypass_hook_trust", False)),
        cwd=exec_cli.cwd if exec_cli.cwd is not None else _typed_root_value(root, "cwd", str),
        add_dir=add_dir,
    )


def _typed_root_value(root: dict[str, object], key: str, expected_type: type):
    value = root.get(key)
    if isinstance(value, expected_type):
        return value
    return None
