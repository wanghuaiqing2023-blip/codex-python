"""Top-level CLI parser for the Python Codex port.

This module mirrors the top-level command dispatch shape from upstream
``codex/codex-rs/cli/src/main.rs`` while keeping command implementations as
future porting work. Parsing is deliberately explicit instead of relying on a
third-party CLI framework so the runtime dependency set stays in the standard
library.
"""

from __future__ import annotations

import asyncio
import ast
import base64
import errno
from functools import cmp_to_key
import ipaddress
import json
import shutil
from datetime import datetime, timezone
import io
import socket
import re
import os
import subprocess
import sys
import tokenize
import threading
import time
import platform
import tempfile
import webbrowser
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, TextIO
import shlex
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from pycodex import __version__
from pycodex.cli.app_cmd import (
    candidate_applications_dirs,
    candidate_codex_app_paths,
    default_mac_dmg_url,
    display_windows_workspace_path,
    find_codex_app_in_mount,
    mac_app_install_plan,
    mac_copy_app_bundle_command,
    mac_detach_dmg_command,
    mac_download_dmg_command,
    mac_mount_dmg_command,
    mac_open_app_command,
    parse_hdiutil_attach_mount_point,
    workspace_for_app_command,
)
from pycodex.config import CliConfigOverrides, ConfigOverride
from pycodex.core import maybe_migrate_personality, PersonalityMigrationStatus
from pycodex.exec import (
    ExecCli,
    ExecCliParseError,
    ExecConfigPlanError,
    ExecRunError,
    ExecSessionConfig,
    HumanEventProcessor,
    JsonEventProcessor,
    build_exec_config_bootstrap_plan,
    direct_resume_thread_id,
    ensure_exec_trusted_directory,
    exec_session_config_from_bootstrap_plan,
    exec_trusted_directory_check,
    parse_exec_args,
    prepare_exec_run_plan,
    resolve_remote_endpoint,
    app_server_control_socket_path,
    remote_exec_session_connect_and_run,
    RemoteAppServerConnectArgs,
    RemoteAppServerEndpoint,
)
from pycodex.exec.local_runtime import (
    align_local_http_exec_resume_model_client,
    build_default_local_http_exec_runtime,
    emit_local_http_exec_error,
    emit_local_http_exec_result,
    local_http_exec_enabled,
    local_http_exec_max_tool_rounds,
    local_http_exec_shell_tools_enabled,
    local_http_exec_tool_output_max_chars,
    local_http_exec_config_summary,
    local_http_exec_initial_messages_from_rollout,
    local_http_review_rollout_input_items,
    persist_local_http_exec_rollout,
    run_exec_review_http_sampling,
    run_exec_resume_user_turn_http_sampling,
    run_exec_user_turn_http_sampling,
    run_exec_user_turn_with_shell_tools_http_sampling,
)
from pycodex.exec.core_runtime import (
    build_default_core_exec_runtime,
    core_exec_enabled,
    emit_core_exec_config_summary,
    emit_core_exec_result,
    run_core_exec_command,
    resolve_core_exec_resume_target,
)
from pycodex.protocol import AltScreenMode, AskForApproval, ProfileV2Name, ProfileV2NameParseError, SandboxMode
from pycodex.protocol.config_types import ConfigTypeParseError
from pycodex.responses_api_proxy import (
    ResponsesApiProxyError,
    read_auth_header_for_main,
    run_main as run_responses_api_proxy_main,
)
from pycodex.cli.login import (
    AuthDotJson,
    AUTH_MODE_AGENT_IDENTITY,
    AUTH_MODE_API_KEY,
    AUTH_MODE_CHATGPT,
    AUTH_MODE_CHATGPT_AUTH_TOKENS,
    _extract_auth_claims_from_jwt,
    delete_auth_file,
    read_auth_json,
    run_chatgpt_login,
    resolve_auth_mode,
    safe_format_key,
    write_auth_json,
)
from pycodex.login.device_code_auth import (
    DEVICE_CODE_NOT_ENABLED_MESSAGE,
    poll_for_token,
    request_user_code,
)

from pycodex.cli.features import FeatureCliError, FeatureToggles, FeaturesCli, parse_features_args, run_features_command
from pycodex.cli.features import FeaturesSubcommand
from pycodex.cli.debug_sandbox import build_debug_sandbox_execution_plan, debug_sandbox_subprocess_argv
from .doctor_updates import (
    default_reachability_plan,
    doctor_background_server_check,
    doctor_auth_check,
    doctor_config_check,
    doctor_fallback_state_check,
    doctor_git_check,
    doctor_installation_check,
    doctor_mcp_check,
    doctor_network_check,
    doctor_provider_reachability_check,
    doctor_runtime_check,
    doctor_sandbox_check,
    doctor_search_check,
    doctor_state_check,
    doctor_system_check,
    doctor_terminal_check,
    doctor_terminal_title_check,
    doctor_thread_inventory_check,
    doctor_updates_check_from_config,
    doctor_websocket_check,
    provider_reachability_plan_from_config,
    redacted_doctor_checks_mapping,
    redacted_doctor_report_mapping,
)
from pycodex.tui import run_tui
from pycodex.tui.app.runtime import CoreExecActiveThreadRuntime, TuiAppRuntime
from pycodex.execpolicy import ExecPolicyPrefixRule
from pycodex.git_utils import current_branch_name, default_branch_name
from pycodex.utils.home_dir import find_codex_home
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping, write_toml_mapping
from .spec import COMMANDS_BY_NAME, UPSTREAM_CLI_MAIN, CommandSpec, visible_commands


ROOT_USAGE = "codex [OPTIONS] [PROMPT]\n       codex [OPTIONS] <COMMAND> [ARGS]"


def _fallback_enabled(feature: str) -> bool:
    """Return true when a command-level fallback is intentionally enabled."""

    value = os.environ.get(feature, "").strip().lower()
    return value in {"1", "true", "yes", "on", "enable", "enabled"}


class CliParseError(ValueError):
    """Raised when arguments do not match the ported Codex CLI surface."""


@dataclass
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
    version_requested: bool = False

    @property
    def is_interactive(self) -> bool:
        return self.command is None

    def cli_config_overrides(self) -> CliConfigOverrides:
        """Return root config overrides after folding feature toggles."""

        return CliConfigOverrides(list(self.config_overrides_with_feature_toggles()))

    def parsed_config_overrides(self) -> list[ConfigOverride]:
        """Parse effective root config overrides using the ported upstream logic."""

        return self.cli_config_overrides().parse_overrides()

    def feature_toggles(self) -> FeatureToggles:
        return FeatureToggles(enable=self.enable, disable=self.disable)

    def feature_toggle_overrides(self) -> tuple[str, ...]:
        return tuple(self.feature_toggles().to_overrides())

    def config_overrides_with_feature_toggles(self) -> tuple[str, ...]:
        return (*self.config_overrides, *self.feature_toggle_overrides())

    def features_cli(self) -> FeaturesCli:
        if self.command != "features":
            raise CliParseError("Parsed CLI invocation is not a features command")
        try:
            return parse_features_args(self.command_args)
        except FeatureCliError as exc:
            raise CliParseError(str(exc)) from exc

    def exec_cli(self) -> ExecCli:
        """Parse this invocation as ``codex exec`` and inherit root options."""

        if self.command != "exec":
            raise CliParseError("Parsed CLI invocation is not an exec command")
        reject_remote_mode_for_subcommand(
            self.remote if "remote" in self.root_options else None,
            self.remote_auth_token_env if "remote_auth_token_env" in self.root_options else None,
            "exec",
        )

        exec_cli = parse_exec_args(
            self.command_args,
            root_config_overrides=self.config_overrides_with_feature_toggles(),
        )
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
            raw_command_args = tuple(tokens[i + 1 :])
            if command.name not in _REMOTE_ROOT_OPTION_SUBCOMMANDS:
                reject_remote_mode_for_subcommand(
                    state.remote,
                    state.remote_auth_token_env,
                    _remote_command_name_for_subcommand(command.name, raw_command_args),
                )
            command_args = _parse_command_args(command.name, raw_command_args)
            return ParsedCli(
                command=command.name,
                command_spec=command,
                command_args=command_args,
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
        if token in {"--version", "-V"}:
            return ParsedCli(
                command=None,
                command_spec=None,
                prompt=None,
                config_overrides=tuple(state.config_overrides),
                enable=tuple(state.enable),
                disable=tuple(state.disable),
                remote=state.remote,
                remote_auth_token_env=state.remote_auth_token_env,
                strict_config=state.strict_config,
                root_options=state.as_root_options(),
                version_requested=True,
            )

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


def _parse_command_args(command_name: str, args: tuple[str, ...]) -> tuple[str, ...]:
    parser = {
        "exec": _parse_exec_args,
        "login": _parse_login_args,
        "logout": _parse_logout_args,
        "doctor": _parse_doctor_args,
        "mcp": _parse_mcp_args,
        "plugin": _parse_plugin_args,
        "resume": _parse_resume_args,
        "fork": _parse_fork_args,
        "remote-control": _parse_remote_control_args,
        "mcp-server": _parse_mcp_server_args,
        "app-server": _parse_app_server_args,
        "execpolicy": _parse_execpolicy_args,
        "responses-api-proxy": _parse_responses_api_proxy_args,
        "exec-server": _parse_exec_server_args,
        "update": _parse_update_args,
        "app": _parse_app_args,
        "cloud": _parse_cloud_args,
        "apply": _parse_apply_args,
        "sandbox": _parse_sandbox_args,
        "review": _parse_review_args,
        "debug": _parse_debug_args,
        "stdio-to-uds": _parse_stdio_to_uds_args,
        "completion": _parse_completion_args,
    }.get(command_name, lambda values: values)

    return parser(args)


def _first_non_option_arg(command_args: tuple[str, ...]) -> str | None:
    for arg in command_args:
        if arg.startswith("-"):
            continue
        return arg
    return None


def _parse_exec_args(args: tuple[str, ...]) -> tuple[str, ...]:
    return args


def _parse_completion_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if not args:
        return args

    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-h", "--help"}:
            index += 1
            continue
        if arg == "-s":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for option --shell")
            index += 2
            continue
        if arg.startswith("--shell="):
            if len(arg) == len("--shell="):
                raise CliParseError("Missing value for option --shell")
            index += 1
            continue
        if arg == "--shell":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for option --shell")
            index += 2
            continue
        if arg.startswith("--"):
            raise CliParseError(f"Unknown argument for completion: {arg}")
        raise CliParseError(f"Unexpected argument for completion: {arg}")

    return args


def _parse_review_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "--help" in args or "-h" in args:
        return args
    return args


def _parse_doctor_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    for arg in args:
        if arg in _DOCTOR_OPTIONS:
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for doctor: {arg}")
    return args


def _parse_mcp_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        raise CliParseError("mcp requires a subcommand: list, get, add, remove, login, or logout")

    subcommand = args[0]
    if subcommand not in _MCP_SUBCOMMANDS:
        raise CliParseError(f"Unknown mcp subcommand: {subcommand}")

    if subcommand == "list":
        for arg in args[1:]:
            if arg == "--json":
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for mcp list: {arg}")
            raise CliParseError("Too many arguments for `mcp list`.")
        return args

    if subcommand == "get":
        name = None
        has_json = False
        for arg in args[1:]:
            if arg == "--json":
                if has_json:
                    raise CliParseError("Too many arguments for mcp get.")
                has_json = True
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for mcp {subcommand}: {arg}")
            if name is not None:
                raise CliParseError(f"Too many arguments for mcp {subcommand}.")
            name = arg
        if name is None:
            raise CliParseError("mcp get requires MCP server name.")
        return args

    if subcommand in {"login", "logout"}:
        if len(args) < 2:
            raise CliParseError(f"{subcommand} requires MCP server name.")
        if subcommand == "logout":
            if len(args) != 2:
                raise CliParseError(f"Too many arguments for mcp {subcommand}.")
            if args[1].startswith("-"):
                raise CliParseError(f"{subcommand} requires MCP server name.")
            return args

        if args[1].startswith("-"):
            raise CliParseError(f"{subcommand} requires MCP server name.")
        if len(args) == 2:
            return args

        index = 2
        while index < len(args):
            arg = args[index]
            if arg == "--scopes":
                if index + 1 >= len(args):
                    raise CliParseError("Missing value for --scopes.")
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for mcp {subcommand}: {arg}")
            raise CliParseError(f"Unknown argument for mcp {subcommand}: {arg}")
        return args

    if subcommand == "remove":
        if len(args) != 2:
            raise CliParseError("mcp remove requires MCP server name.")
        if args[1].startswith("-"):
            raise CliParseError("mcp remove requires MCP server name.")
        return args

    # mcp add
    if len(args) < 2:
        raise CliParseError("mcp add requires MCP server name.")
    if args[1].startswith("-"):
        raise CliParseError("mcp add requires MCP server name.")
    has_url = False
    has_command = False
    has_env = False
    index = 2
    while index < len(args):
        arg = args[index]
        if arg == "--":
            if index + 1 >= len(args):
                raise CliParseError("mcp add requires command after `--`.")
            has_command = True
            break
        if arg == "--url":
            if has_command:
                raise CliParseError("`mcp add` cannot combine `--url` with command mode.")
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --url.")
            if args[index + 1].startswith("-"):
                raise CliParseError("Missing value for --url.")
            has_url = True
            if has_env:
                raise CliParseError("--env is only valid when using command mode.")
            index += 2
            continue
        if arg == "--env":
            if has_url:
                raise CliParseError("--env is only valid when using command mode.")
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --env.")
            has_env = True
            index += 2
            continue
        if arg == "--bearer-token-env-var" or arg == "--oauth-client-id" or arg == "--oauth-resource":
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            index += 2
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for mcp add: {arg}")
        raise CliParseError(f"Unexpected argument for mcp add: {arg}")
    if not has_url and not has_command:
        raise CliParseError("mcp add requires --url or command.")
    return args


def _parse_plugin_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        raise CliParseError("plugin requires a subcommand.")

    subcommand = args[0]
    if subcommand not in _PLUGIN_SUBCOMMANDS:
        raise CliParseError(f"Unknown plugin subcommand: {subcommand}")

    remainder = list(args[1:])
    if subcommand == "marketplace":
        if not remainder:
            raise CliParseError("plugin marketplace requires a subcommand.")
        market_subcommand = remainder[0]
        if market_subcommand not in _PLUGIN_MARKETPLACE_SUBCOMMANDS:
            raise CliParseError(f"Unknown plugin marketplace subcommand: {market_subcommand}")
        market_args = remainder[1:]
        if market_subcommand == "list":
            if market_args:
                raise CliParseError("Too many arguments for `plugin marketplace list`.")
            return args
        if market_subcommand == "add":
            if not market_args:
                raise CliParseError("plugin marketplace add requires source.")
            index = 2
            while index < len(remainder):
                arg = remainder[index]
                if arg == "--ref":
                    if index + 1 >= len(remainder):
                        raise CliParseError("Missing value for --ref.")
                    index += 2
                    continue
                if arg == "--sparse":
                    if index + 1 >= len(remainder) or remainder[index + 1].startswith("-"):
                        raise CliParseError("Missing value for --sparse.")
                    index += 2
                    while index < len(remainder) and not remainder[index].startswith("-"):
                        index += 1
                    continue
                if arg.startswith("-"):
                    raise CliParseError(f"Unknown argument for plugin marketplace add: {arg}")
                raise CliParseError(f"Unknown argument for plugin marketplace add: {arg}")
            return args
        if market_subcommand == "upgrade":
            if len(market_args) > 1:
                raise CliParseError("plugin marketplace upgrade accepts at most one marketplace name.")
            return args
        if market_subcommand == "remove":
            if len(market_args) != 1:
                raise CliParseError("plugin marketplace remove requires marketplace name.")
            return args
        return args

    if subcommand in {"add", "remove"}:
        if not remainder:
            raise CliParseError(f"plugin {subcommand} requires <plugin>[@<marketplace>].")
        plugin_selector = remainder[0]
        if plugin_selector.startswith("-"):
            raise CliParseError(f"plugin {subcommand} requires <plugin>[@<marketplace>].")
        if len(remainder) > 3:
            raise CliParseError(f"Too many arguments for `plugin {subcommand}`.")
        if len(remainder) >= 2 and remainder[1] in {"--marketplace", "-m"}:
            if len(remainder) != 3 or remainder[2].startswith("-"):
                raise CliParseError(f"plugin {subcommand} --marketplace requires MARKETPLACE.")
            return args
        if len(remainder) > 1:
            raise CliParseError(f"Unknown argument for plugin {subcommand}: {remainder[1]}")
        return args

    # plugin list
    if subcommand == "list":
        if not remainder:
            return args
        if len(remainder) > 2:
            raise CliParseError("Too many arguments for `plugin list`.")
        if remainder[0] in {"--marketplace", "-m"}:
            if len(remainder) != 2 or remainder[1].startswith("-"):
                raise CliParseError("plugin list --marketplace requires MARKETPLACE.")
            return args
        raise CliParseError(f"Unknown argument for plugin list: {remainder[0]}")

    raise CliParseError(f"Unknown plugin subcommand: {subcommand}")


def _parse_remote_control_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        return args
    has_subcommand = False
    has_json = False
    for arg in args:
        if arg == "--json":
            if has_json:
                raise CliParseError("Too many arguments for `remote-control`.")
            has_json = True
            continue
        if arg in {"start", "stop"}:
            if has_subcommand:
                raise CliParseError("Too many arguments for `remote-control`.")
            has_subcommand = True
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for remote-control: {arg}")
        raise CliParseError(f"Unknown argument for remote-control: {arg}")
    return args


def _parse_mcp_server_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    for arg in args:
        if arg == "--strict-config":
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for mcp-server: {arg}")
        raise CliParseError(f"Unexpected argument for mcp-server: {arg}")
    return args


def _parse_exec_server_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    index = 0
    has_remote = False
    has_environment_id = False
    has_listen = False
    needs_remote_for_agent_auth = False
    while index < len(args):
        arg = args[index]
        if arg == "--strict-config":
            index += 1
            continue
        if arg == "--listen":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --listen.")
            has_listen = True
            index += 2
            continue
        if arg == "--remote":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --remote.")
            has_remote = True
            index += 2
            continue
        if arg == "--environment-id":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --environment-id.")
            has_environment_id = True
            index += 2
            continue
        if arg == "--name":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --name.")
            index += 2
            continue
        if arg == "--use-agent-identity-auth":
            needs_remote_for_agent_auth = True
            index += 1
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for exec-server: {arg}")
        raise CliParseError(f"Unexpected argument for exec-server: {arg}")
    if has_remote and has_listen:
        raise CliParseError("--listen cannot be used with --remote.")
    if has_remote and not has_environment_id:
        raise CliParseError("--environment-id is required when --remote is set.")
    if needs_remote_for_agent_auth and not has_remote:
        raise CliParseError("--use-agent-identity-auth requires --remote.")
    return args


def _parse_app_server_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        return args
    original_args = args

    root_bool_options = {"--strict-config", "--remote-control", "--analytics-default-enabled"}
    root_value_options = {
        "--listen",
        "--ws-auth",
        "--ws-token-file",
        "--ws-token-sha256",
        "--ws-shared-secret-file",
        "--ws-issuer",
        "--ws-audience",
        "--ws-max-clock-skew-seconds",
    }
    root_ws_auth: str | None = None
    root_ws_token_file = False
    root_ws_token_sha256 = False
    root_ws_shared_secret_file = False
    root_ws_issuer = False
    root_ws_audience = False
    root_ws_max_clock_skew = False
    index = 0

    if args[0].startswith("-"):
        while index < len(args) and args[index].startswith("-"):
            arg = args[index]
            if arg in root_bool_options:
                index += 1
                continue
            if arg in root_value_options:
                if index + 1 >= len(args):
                    raise CliParseError(f"Missing value for {arg}.")
                value = args[index + 1]
                if arg == "--listen":
                    _validate_app_server_listen_url(value)
                if arg == "--ws-auth":
                    if value not in {"capability-token", "signed-bearer-token"}:
                        raise CliParseError("Invalid value for --ws-auth.")
                    if root_ws_auth is not None:
                        raise CliParseError("Only one --ws-auth value is allowed.")
                    root_ws_auth = value
                elif arg == "--ws-token-file":
                    root_ws_token_file = True
                elif arg == "--ws-token-sha256":
                    root_ws_token_sha256 = True
                elif arg == "--ws-shared-secret-file":
                    root_ws_shared_secret_file = True
                elif arg == "--ws-issuer":
                    root_ws_issuer = True
                elif arg == "--ws-audience":
                    root_ws_audience = True
                elif arg == "--ws-max-clock-skew-seconds":
                    root_ws_max_clock_skew = True
                index += 2
                continue
            break
        if root_ws_token_file and root_ws_token_sha256:
            raise CliParseError(
                "`--ws-token-file` and `--ws-token-sha256` are mutually exclusive."
            )
        if root_ws_auth is None:
            if (
                root_ws_token_file
                or root_ws_token_sha256
                or root_ws_shared_secret_file
                or root_ws_issuer
                or root_ws_audience
                or root_ws_max_clock_skew
            ):
                raise CliParseError(
                    "websocket auth flags require `--ws-auth` "
                    "(`--ws-auth capability-token` or `--ws-auth signed-bearer-token`)"
                )
        elif root_ws_auth == "capability-token":
            if root_ws_shared_secret_file or root_ws_issuer or root_ws_audience or root_ws_max_clock_skew:
                raise CliParseError(
                    "`--ws-shared-secret-file`, `--ws-issuer`, `--ws-audience`, and "
                    "`--ws-max-clock-skew-seconds` require `--ws-auth signed-bearer-token`"
                )
            if not (root_ws_token_file or root_ws_token_sha256):
                raise CliParseError(
                    "`--ws-token-file` or `--ws-token-sha256` is required when "
                    "`--ws-auth capability-token` is set"
                )
        else:
            if root_ws_token_file or root_ws_token_sha256:
                raise CliParseError(
                    "`--ws-token-file` and `--ws-token-sha256` require "
                    "`--ws-auth capability-token`, not `signed-bearer-token`"
                )
            if not root_ws_shared_secret_file:
                raise CliParseError(
                    "`--ws-shared-secret-file` is required when "
                    "`--ws-auth signed-bearer-token` is set"
                )
        if index >= len(args):
            return args
        if index == len(args) - 1 and args[index].startswith("-"):
            raise CliParseError(f"Unknown argument for app-server: {args[index]}")
        args = args[index:]

    if args[0].startswith("-"):
        raise CliParseError(f"Unknown argument for app-server: {args[0]}")

    rest = tuple(args[1:])
    subcommand = args[0]
    if subcommand == "daemon":
        if not rest:
            raise CliParseError("app-server daemon requires a subcommand.")
        daemon_command = rest[0]
        if daemon_command not in _APP_SERVER_DAEMON_SUBCOMMANDS:
            raise CliParseError(f"Unknown app-server daemon subcommand: {daemon_command}")
        if daemon_command == "bootstrap":
            if len(rest) > 2:
                if rest[1] == "--remote-control":
                    raise CliParseError("Too many arguments for `app-server daemon bootstrap`.")
                raise CliParseError(f"Unknown argument for app-server daemon bootstrap: {rest[1]}")
            if len(rest) == 2 and rest[1] != "--remote-control":
                raise CliParseError(f"Unknown argument for app-server daemon bootstrap: {rest[1]}")
            if len(rest) == 1 or rest[1] == "--remote-control":
                return original_args
        elif len(rest) != 1:
            raise CliParseError(f"Too many arguments for `app-server daemon {daemon_command}`.")
        return original_args

    if subcommand == "proxy":
        if not rest:
            return original_args
        index = 0
        while index < len(rest):
            arg = rest[index]
            if arg == "--sock":
                if index + 1 >= len(rest):
                    raise CliParseError("Missing value for --sock.")
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for app-server proxy: {arg}")
            raise CliParseError(f"Unknown argument for app-server proxy: {arg}")
        return original_args

    if subcommand == "generate-ts":
        if not rest:
            raise CliParseError("app-server generate-ts requires --out.")
        index = 0
        seen_out = False
        while index < len(rest):
            arg = rest[index]
            if arg in {"--out", "-o"}:
                if seen_out:
                    raise CliParseError("app-server generate-ts accepts only one --out value.")
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                seen_out = True
                index += 2
                continue
            if arg in {"--prettier", "-p"}:
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                index += 2
                continue
            if arg == "--experimental":
                index += 1
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for app-server generate-ts: {arg}")
            raise CliParseError(f"Unknown argument for app-server generate-ts: {arg}")
        if not seen_out:
            raise CliParseError("app-server generate-ts requires --out.")
        return original_args

    if subcommand == "generate-json-schema":
        if not rest:
            raise CliParseError("app-server generate-json-schema requires --out.")
        index = 0
        seen_out = False
        while index < len(rest):
            arg = rest[index]
            if arg in {"--out", "-o"}:
                if seen_out:
                    raise CliParseError("app-server generate-json-schema accepts only one --out value.")
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                seen_out = True
                index += 2
                continue
            if arg == "--experimental":
                index += 1
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for app-server generate-json-schema: {arg}")
            raise CliParseError(f"Unknown argument for app-server generate-json-schema: {arg}")
        if not seen_out:
            raise CliParseError("app-server generate-json-schema requires --out.")
        return original_args

    if subcommand == "generate-internal-json-schema":
        if not rest:
            raise CliParseError("app-server generate-internal-json-schema requires --out.")
        index = 0
        seen_out = False
        while index < len(rest):
            arg = rest[index]
            if arg in {"--out", "-o"}:
                if seen_out:
                    raise CliParseError("app-server generate-internal-json-schema accepts only one --out value.")
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                seen_out = True
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for app-server generate-internal-json-schema: {arg}")
            raise CliParseError(f"Unknown argument for app-server generate-internal-json-schema: {arg}")
        if not seen_out:
            raise CliParseError("app-server generate-internal-json-schema requires --out.")
        return original_args

    raise CliParseError(f"Unknown app-server subcommand: {subcommand}")


def _validate_app_server_listen_url(listen: str) -> None:
    if listen == "off":
        return
    if listen == "stdio://" or listen == "unix://":
        return
    if listen.startswith("unix://"):
        return
    if not listen.startswith("ws://"):
        raise CliParseError(
            "unsupported --listen URL "
            f"`{listen}`; expected `stdio://`, `unix://`, `unix://PATH`, `ws://IP:PORT`, or `off`"
        )

    target = listen[len("ws://") :]
    host, colon, port_text = target.rpartition(":")
    if not colon or not host:
        raise CliParseError(f"invalid websocket --listen URL `{listen}`; expected `ws://IP:PORT`")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        raise CliParseError(f"invalid websocket --listen URL `{listen}`; expected `ws://IP:PORT`")
    if not port_text.isdigit():
        raise CliParseError(f"invalid websocket --listen URL `{listen}`; expected `ws://IP:PORT`")
    port = int(port_text)
    if not 0 <= port <= 65535:
        raise CliParseError(f"invalid websocket --listen URL `{listen}`; expected `ws://IP:PORT`")


def _parse_execpolicy_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        raise CliParseError("execpolicy requires a subcommand: check")

    subcommand = args[0]
    if subcommand != "check":
        raise CliParseError(f"Unknown execpolicy subcommand: {subcommand}")

    rest = list(args[1:])
    if not rest:
        raise CliParseError("execpolicy check requires --rules.")

    has_rules = False
    index = 0
    command_started = False
    while index < len(rest):
        arg = rest[index]
        if command_started:
            break
        if arg in {"--pretty", "--resolve-host-executables"}:
            index += 1
            continue
        if arg in {"--rules", "-r"}:
            if index + 1 >= len(rest):
                raise CliParseError(f"Missing value for {arg}.")
            has_rules = True
            index += 2
            continue
        if arg == "--":
            command_started = True
            index += 1
            if index >= len(rest):
                raise CliParseError("execpolicy check requires COMMAND.")
            break
        if arg.startswith("-") and not arg.startswith("--rules") and not arg.startswith("-r"):
            command_started = True
            break
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for execpolicy check: {arg}")
        command_started = True

    if not command_started:
        raise CliParseError("execpolicy check requires COMMAND.")
    if not has_rules:
        raise CliParseError("execpolicy check requires --rules.")
    return args


def _parse_responses_api_proxy_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--port":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --port.")
            value = args[index + 1]
            try:
                parsed = int(value)
            except ValueError as exc:
                raise CliParseError(f"Invalid value for --port: {value}") from exc
            if not 0 <= parsed <= 65535:
                raise CliParseError(f"Invalid value for --port: {value}")
            index += 2
            continue
        if arg == "--server-info":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --server-info.")
            index += 2
            continue
        if arg == "--http-shutdown":
            index += 1
            continue
        if arg == "--upstream-url":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --upstream-url.")
            index += 2
            continue
        if arg == "--dump-dir":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --dump-dir.")
            index += 2
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for responses-api-proxy: {arg}")
        raise CliParseError(f"Unexpected argument for responses-api-proxy: {arg}")
    return args


def _parse_sandbox_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    parsed_permissions_profile = False
    requires_permissions_profile = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--permissions-profile":
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            parsed_permissions_profile = True
            index += 2
            continue
        if arg in {"--profile", "-p"}:
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            index += 2
            continue
        if arg in {"--cd", "-C"}:
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            requires_permissions_profile = True
            index += 2
            continue
        if arg == "--include-managed-config":
            requires_permissions_profile = True
            index += 1
            continue
        if arg == "--allow-unix-socket":
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            index += 2
            continue
        if arg == "--log-denials":
            index += 1
            continue
        if arg == "--":
            return args[index:]
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for sandbox: {arg}")
        index += 1
    if requires_permissions_profile and not parsed_permissions_profile:
        raise CliParseError(
            "the following required argument was not provided: --permissions-profile"
        )
    return args


def _parse_resume_args(args: tuple[str, ...]) -> tuple[str, ...]:
    return _parse_resumption_args(args, "resume", allow_include_non_interactive=True)


def _parse_fork_args(args: tuple[str, ...]) -> tuple[str, ...]:
    return _parse_resumption_args(args, "fork", allow_include_non_interactive=False)


def _parse_resumption_args(
    args: tuple[str, ...],
    command_name: str,
    *,
    allow_include_non_interactive: bool,
) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args

    index = 0
    session_id: str | None = None
    saw_last = False

    while index < len(args):
        arg = args[index]
        if arg == "--last":
            if command_name == "fork" and session_id is not None:
                raise CliParseError("fork does not support --last with session-id.")
            saw_last = True
            index += 1
            continue

        if arg == "--all":
            if command_name not in {"resume", "fork"}:
                raise CliParseError(f"Unknown argument for {command_name}: {arg}")
            index += 1
            continue

        if arg == "--include-non-interactive":
            if not allow_include_non_interactive:
                raise CliParseError(f"Unknown argument for {command_name}: {arg}")
            index += 1
            continue

        if arg in {"--remote", "--remote-auth-token-env"}:
            if index + 1 >= len(args):
                raise CliParseError(f"Missing value for {arg}.")
            index += 2
            continue

        if arg == "--":
            raise CliParseError(f"Unknown argument for {command_name}: {arg}")

        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for {command_name}: {arg}")

        if session_id is not None:
            raise CliParseError(f"Too many arguments for `{command_name}`.")

        session_id = arg
        if command_name == "fork" and saw_last:
            raise CliParseError("fork does not support --last with session-id.")
        index += 1

    return args


def _parse_apply_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args

    if not args:
        raise CliParseError("apply requires TASK_ID.")
    if args[0] == "--":
        if len(args) < 2:
            raise CliParseError("apply requires TASK_ID.")
        if len(args) > 2:
            raise CliParseError("Too many arguments for `apply`.")
        return args
    if len(args) > 1:
        raise CliParseError("Too many arguments for `apply`.")
    if args[0].startswith("-"):
        raise CliParseError(f"Unknown argument for apply: {args[0]}")
    return args


def _parse_logout_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if args:
        raise CliParseError(f"unexpected argument '{args[0]}' for `codex logout`")
    return args


def _parse_cloud_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args

    if not args:
        return args

    command = args[0]
    if command not in {"exec", "status", "list", "apply", "diff"}:
        raise CliParseError(f"Unknown cloud subcommand: {command}")

    remainder = args[1:]
    if command == "exec":
        index = 0
        seen_query = False
        while index < len(remainder):
            arg = remainder[index]
            if arg == "--env":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --env.")
                index += 2
                continue
            if arg == "--attempts":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --attempts.")
                parse_cloud_attempts_value(remainder[index + 1], "--attempts")
                index += 2
                continue
            if arg == "--branch":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --branch.")
                index += 2
                continue
            if arg == "--":
                if seen_query:
                    raise CliParseError("Too many arguments for `cloud exec`.")
                if index + 1 >= len(remainder):
                    return args
                seen_query = True
                index += 2
                if index < len(remainder):
                    raise CliParseError("Too many arguments for `cloud exec`.")
                return args
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for cloud exec: {arg}")
            if not seen_query:
                seen_query = True
                index += 1
                continue
            raise CliParseError("Too many arguments for `cloud exec`.")
        return args

    if command == "status":
        if len(remainder) != 1:
            if not remainder:
                raise CliParseError("cloud status requires TASK_ID.")
            raise CliParseError("Too many arguments for `cloud status`.")
        if remainder[0].startswith("-"):
            raise CliParseError(f"Unknown argument for cloud status: {remainder[0]}")
        return args

    if command == "list":
        index = 0
        while index < len(remainder):
            arg = remainder[index]
            if arg == "--env":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --env.")
                index += 2
                continue
            if arg == "--limit":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --limit.")
                parse_cloud_limit_value(remainder[index + 1], "--limit")
                index += 2
                continue
            if arg == "--cursor":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --cursor.")
                index += 2
                continue
            if arg == "--json":
                index += 1
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for cloud list: {arg}")
            raise CliParseError("Too many arguments for `cloud list`.")
        return args

    if command in {"apply", "diff"}:
        task_id = None
        seen_attempt = False
        index = 0
        while index < len(remainder):
            arg = remainder[index]
            if arg == "--":
                if task_id is not None:
                    raise CliParseError(f"Too many arguments for `cloud {command}`.")
                if index + 1 >= len(remainder):
                    raise CliParseError(f"cloud {command} requires TASK_ID.")
                task_id = remainder[index + 1]
                index += 2
                if index < len(remainder):
                    raise CliParseError(f"Too many arguments for `cloud {command}`.")
                return args
            if arg == "--attempt":
                if index + 1 >= len(remainder):
                    raise CliParseError("Missing value for --attempt.")
                parse_cloud_attempts_value(remainder[index + 1], "--attempt")
                if seen_attempt:
                    raise CliParseError(f"Too many arguments for `cloud {command}`.")
                seen_attempt = True
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for cloud {command}: {arg}")
            if task_id is None:
                task_id = arg
                index += 1
                continue
            raise CliParseError(f"Too many arguments for `cloud {command}`.")
        if task_id is None:
            raise CliParseError(f"cloud {command} requires TASK_ID.")
        return args

    raise CliParseError(f"Unknown cloud subcommand: {command}")


def parse_cloud_attempts_value(value: str, flag: str) -> None:
    try:
        int_value = int(value)
    except ValueError as exc:
        raise CliParseError(f"Invalid value for {flag}: {value}") from exc
    if not 1 <= int_value <= 4:
        raise CliParseError(f"Invalid value for {flag}: {value}")


def parse_cloud_limit_value(value: str, flag: str) -> None:
    try:
        int_value = int(value)
    except ValueError as exc:
        raise CliParseError(f"Invalid value for {flag}: {value}") from exc
    if not 1 <= int_value <= 20:
        raise CliParseError(f"Invalid value for {flag}: {value}")


def _parse_update_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if args:
        raise CliParseError(f"Unknown argument for update: {args[0]}")
    return args


def _parse_app_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args

    index = 0
    seen_path = False
    while index < len(args):
        arg = args[index]
        if arg == "--download-url":
            if index + 1 >= len(args):
                raise CliParseError("Missing value for --download-url.")
            index += 2
            continue
        if arg.startswith("-"):
            raise CliParseError(f"Unknown argument for app: {arg}")
        if seen_path:
            raise CliParseError("Too many arguments for `app`.")
        seen_path = True
        index += 1

    return args


def _parse_stdio_to_uds_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if len(args) != 1:
        raise CliParseError("Expected exactly one argument: <socket-path>")
    return args


def _parse_debug_args(args: tuple[str, ...]) -> tuple[str, ...]:
    if "-h" in args or "--help" in args:
        return args
    if not args:
        raise CliParseError("debug requires a subcommand.")

    subcommand = args[0]
    if subcommand not in _DEBUG_SUBCOMMANDS:
        raise CliParseError(f"Unknown debug subcommand: {subcommand}")

    rest = list(args[1:])
    if subcommand == "models":
        if len(rest) > 1:
            raise CliParseError("Too many arguments for `debug models`.")
        if len(rest) == 1 and rest[0] != "--bundled":
            raise CliParseError(f"Unknown argument for debug models: {rest[0]}")
        return args

    if subcommand == "app-server":
        if not rest:
            raise CliParseError("debug app-server send-message-v2 requires USER_MESSAGE.")
        if rest[0] != "send-message-v2":
            raise CliParseError(f"Unknown debug app-server subcommand: {rest[0]}")
        if len(rest) != 2:
            raise CliParseError("debug app-server send-message-v2 requires USER_MESSAGE.")
        return args

    if subcommand == "prompt-input":
        if not rest:
            return args
        prompt: str | None = None
        index = 0
        while index < len(rest):
            arg = rest[index]
            if arg in {"--image", "-i"}:
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for debug prompt-input: {arg}")
            if prompt is None:
                prompt = arg
                index += 1
                continue
            raise CliParseError("Too many arguments for `debug prompt-input`.")
        return args

    if subcommand == "trace-reduce":
        if not rest:
            raise CliParseError("debug trace-reduce requires a trace bundle path.")
        index = 0
        while index < len(rest):
            arg = rest[index]
            if arg in {"--output", "-o"}:
                if index + 1 >= len(rest):
                    raise CliParseError(f"Missing value for {arg}.")
                index += 2
                continue
            if arg.startswith("-"):
                raise CliParseError(f"Unknown argument for debug trace-reduce: {arg}")
            if index == len(rest) - 1:
                index += 1
                continue
            raise CliParseError("Too many arguments for `debug trace-reduce`.")
        return args

    if subcommand == "clear-memories":
        if rest:
            raise CliParseError("debug clear-memories does not accept arguments.")
        return args

    return args


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
        state.root_options[dest] = value
    elif dest == "remote_auth_token_env":
        state.remote_auth_token_env = value
        state.root_options[dest] = value
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
        "  -V, --version               Print version.",
        "  -h, --help                  Show this help message.",
        "",
        "Commands:",
    ]
    for command in visible_commands():
        aliases = f" ({', '.join(command.aliases)})" if command.aliases else ""
        lines.append(f"  {command.name:<18}{command.help}{aliases}")
    return "\n".join(lines)



_UNSUPPORTED_STRICT_CONFIG_COMMANDS = {
    "apply",
    "cloud",
    "completion",
    "debug",
    "execpolicy",
    "features",
    "login",
    "logout",
    "mcp",
    "plugin",
    "responses-api-proxy",
    "sandbox",
    "stdio-to-uds",
    "update",
}

_PROFILE_V2_UNSUPPORTED_MESSAGE = (
    "--profile only applies to runtime commands and `codex mcp`: "
    "`codex`, `codex exec`, `codex review`, `codex resume`, `codex fork`, "
    "`codex mcp`, `codex sandbox`, and `codex debug prompt-input`."
)

_DOCTOR_OPTIONS = {"--json", "--summary", "--all", "--no-color", "--ascii"}
_MCP_SUBCOMMANDS = {"list", "get", "add", "remove", "login", "logout"}
_PLUGIN_SUBCOMMANDS = {"add", "list", "marketplace", "remove"}
_PLUGIN_MARKETPLACE_SUBCOMMANDS = {"add", "list", "upgrade", "remove"}
_DEFAULT_PLUGIN_VERSION = "local"
_DEBUG_SUBCOMMANDS = {"models", "app-server", "prompt-input", "trace-reduce", "clear-memories"}
_APP_SERVER_DAEMON_SUBCOMMANDS = {
    "bootstrap",
    "start",
    "restart",
    "enable-remote-control",
    "disable-remote-control",
    "stop",
    "version",
    "pid-update-loop",
}
_MCP_STATE_FILE = "mcp-state.json"
_PLUGIN_STATE_FILE = "plugin-state.json"
_APP_SERVER_STATE_FILE = "app-server-state.json"
_APP_SERVER_CONTROL_SOCKET_DIR = "app-server-control"
_APP_SERVER_CONTROL_SOCKET_FILE = "app-server-control.sock"

_COMPLETION_SHELLS = ("bash", "zsh", "fish", "powershell", "pwsh")

_CLOUD_BASE_URL = "https://chatgpt.com/backend-api"
_CLOUD_DEFAULT_LIST_LIMIT = 20
_CLOUD_TASKS_URL_SUFFIX = "/backend-api"
_DEVICE_AUTH_DEFAULT_ISSUER = "https://auth.openai.com"
_DEVICE_AUTH_DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_DEVICE_AUTH_MAX_WAIT_SECONDS = 15 * 60
_APP_DMG_URL_ARM64 = "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg"
_APP_DMG_URL_X64 = "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg"
_APP_WINDOWS_INSTALLER_URL = "https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi"
_APP_MICROSOFT_STORE_URL = "https://apps.microsoft.com/detail/9PLM9XGG6VKS"


def _cloud_auth_token() -> str:
    try:
        auth = read_auth_json()
        if auth is None:
            raise RuntimeError("Not logged in. Run `codex login --with-access-token` first.")
        mode = resolve_auth_mode(auth)
    except (ValueError, OSError, RuntimeError) as exc:
        raise RuntimeError(f"Failed to read authentication: {exc}") from exc

    if mode == AUTH_MODE_API_KEY:
        token = auth.openai_api_key
        if token:
            return token
        raise RuntimeError("API key entry is empty. Re-run `codex login --with-api-key`.")

    if mode in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS}:
        tokens = auth.tokens if isinstance(auth.tokens, dict) else {}
        for key in ("access_token", "ACCESS_TOKEN", "token", "agent_access_token"):
            token = tokens.get(key) if isinstance(tokens.get(key), str) else None
            if token:
                return token
        raise RuntimeError("Access token is missing from chatgpt auth cache. Re-run `codex login`.")

    if auth.agent_identity:
        return auth.agent_identity

    raise RuntimeError("No usable auth token was found. Re-run `codex login`.")


def _cloud_request_json(
    *,
    url: str,
    method: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> dict | list | str:
    data = None
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "pycodex",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url=url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = body.strip() or exc.reason
        raise RuntimeError(f"HTTP error {exc.code} for {url}: {message}")
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc}")

    if not body:
        return {}

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response from {url}: {exc}")


def _cloud_task_url(task_id: str) -> str:
    normalized = _CLOUD_BASE_URL.rstrip("/")
    if normalized.endswith(_CLOUD_TASKS_URL_SUFFIX):
        root = normalized[: -len(_CLOUD_TASKS_URL_SUFFIX)]
        return f"{root}/codex/tasks/{task_id}"
    if normalized.endswith("/api/codex"):
        root = normalized.removesuffix("/api/codex")
        return f"{root}/codex/tasks/{task_id}"
    if normalized.endswith("/codex"):
        return f"{normalized}/tasks/{task_id}"
    return f"{normalized}/codex/tasks/{task_id}"


def _resolve_cloud_git_ref(branch: str | None) -> str:
    selected = branch.strip() if branch else ""
    if selected:
        return selected

    try:
        cwd = "."
        current = current_branch_name(cwd)
        if current:
            return current
        default = default_branch_name(cwd)
        if default:
            return default
    except Exception:
        pass
    return "main"


def _parse_cloud_task_id(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        raise RuntimeError("cloud task id must not be empty.")
    without_fragment = trimmed.split("#", 1)[0]
    without_query = without_fragment.split("?", 1)[0]
    without_query = without_query.rstrip("/")
    if "/" in without_query:
        candidate = without_query.rsplit("/", 1)[-1]
    else:
        candidate = without_query
    candidate = candidate.strip()
    if not candidate:
        raise RuntimeError("cloud task id must not be empty.")
    return candidate


def _created_task_id_from_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected response format from cloud task endpoint.")

    task_data = payload.get("task")
    if isinstance(task_data, dict):
        raw_id = task_data.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            return raw_id.strip()

    raw_id = payload.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()

    task_id = payload.get("task_id")
    if isinstance(task_id, str) and task_id.strip():
        return task_id.strip()

    raise RuntimeError("Cloud create task response did not include a task id.")


def _resolve_query_input(
    query: str | None,
    *,
    stdin: object | None,
    stdin_is_terminal: bool | None,
    stderr: TextIO,
) -> str | None:
    if query is not None and query != "-":
        return query
    return _read_stdin_text(
        stdin,
        required=True,
        command="cloud exec query",
        stderr=stderr,
        stdin_is_terminal=stdin_is_terminal,
    )


def _extract_unified_diff(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload,
        payload.get("task") if isinstance(payload.get("task"), dict) else None,
    ]

    for container in candidates:
        if not isinstance(container, dict):
            continue
        for turn_key in ("current_diff_task_turn", "current_assistant_turn"):
            turn = container.get(turn_key)
            if not isinstance(turn, dict):
                continue
            output_items = turn.get("output_items")
            if isinstance(output_items, list):
                for item in output_items:
                    if not isinstance(item, dict):
                        continue
                    kind = item.get("type") or item.get("kind")
                    if kind == "output_diff":
                        value = item.get("diff")
                        if isinstance(value, str) and value.strip():
                            return value
                    if kind == "pr":
                        nested = item.get("output_diff")
                        if isinstance(nested, dict):
                            value = nested.get("diff")
                            if isinstance(value, str) and value.strip():
                                return value
    return None


def _parse_optional_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _collect_cloud_attempt_diffs(
    payload: object,
    *,
    token: str,
    task_id: str,
) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected response format from cloud task endpoint.")

    attempts: list[dict[str, object]] = []
    seen_turn_ids: set[str] = set()

    def _add_attempt(turn: object) -> None:
        if not isinstance(turn, dict):
            return
        turn_id = turn.get("id")
        if isinstance(turn_id, str) and turn_id in seen_turn_ids:
            return
        diff = _extract_unified_diff({"current_assistant_turn": turn})
        if not diff:
            return

        placement = turn.get("attempt_placement")
        if isinstance(placement, str):
            try:
                placement = int(placement)
            except ValueError:
                placement = None

        created_raw = turn.get("created_at")
        created_at = _parse_optional_datetime(created_raw)

        if isinstance(turn_id, str):
            seen_turn_ids.add(turn_id)

        attempts.append(
            {
                "diff": diff,
                "attempt_placement": placement,
                "created_at": created_at,
                "turn_id": turn_id if isinstance(turn_id, str) else "",
            }
        )

    task_payload = payload.get("task") if isinstance(payload.get("task"), dict) else payload
    if not isinstance(task_payload, dict):
        raise RuntimeError("Unexpected response format from cloud task endpoint.")

    current_turn = task_payload.get("current_assistant_turn")
    if current_turn is None and "current_diff_task_turn" in task_payload:
        current_turn = task_payload.get("current_diff_task_turn")
    _add_attempt(current_turn)

    sibling_turns: object | None = None
    if not isinstance(current_turn, dict):
        current_turn = None

    turn_id = current_turn.get("id") if isinstance(current_turn, dict) else None
    if isinstance(turn_id, str) and turn_id.strip():
        sibling_url = f"{_CLOUD_BASE_URL}/wham/tasks/{task_id}/turns/{turn_id.strip()}/sibling_turns"
        sibling_payload = _cloud_request_json(url=sibling_url, method="GET", token=token)
        sibling_turns = None
        if isinstance(sibling_payload, dict):
            sibling_turns = sibling_payload.get("sibling_turns")
        if sibling_turns is None and isinstance(sibling_payload, list):
            sibling_turns = sibling_payload

    if isinstance(sibling_turns, list):
        for item in sibling_turns:
            _add_attempt(item)

    def _attempt_sort_key(item: dict[str, object]) -> tuple[object, object, object, str]:
        placement = item.get("attempt_placement")
        turn_id = str(item.get("turn_id", ""))
        if isinstance(placement, int):
            return (0, placement, 0, turn_id)

        created_at = item.get("created_at")
        if isinstance(created_at, datetime):
            return (1, 0, created_at, turn_id)

        return (1, 1, "", turn_id)

    attempts.sort(key=_attempt_sort_key)
    return attempts


def _select_cloud_attempt_diff(
    attempts: list[dict[str, object]],
    attempt: int | None,
) -> str | None:
    if not attempts:
        return None
    index = (attempt or 1) - 1
    if index < 0:
        return None
    if index >= len(attempts):
        return None
    selected = attempts[index]
    diff = selected.get("diff")
    return diff if isinstance(diff, str) and diff.strip() else None


def _task_status_from_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    containers = [payload]
    if isinstance(payload.get("task"), dict):
        containers.append(payload.get("task"))

    for container in containers:
        status_display = container.get("task_status_display")
        if isinstance(status_display, dict):
            status = status_display.get("status")
            if isinstance(status, str) and status:
                return status
        elif isinstance(status_display, str) and status_display:
            return status_display

        status = container.get("status")
        if isinstance(status, str) and status:
            return status

    return None


def _is_ready_status(status: str | None) -> bool:
    if status is None:
        return False
    return status.lower().strip() in {"ready", "completed", "applied"}


def _list_cloud_tasks(token: str, *, env: str | None, limit: int, cursor: str | None) -> tuple[list[dict], object | None]:
    params = [
        ("task_filter", "current"),
        ("limit", str(limit)),
    ]
    if env is not None:
        params.append(("environment_id", env))
    if cursor is not None:
        params.append(("cursor", cursor))
    url = f"{_CLOUD_BASE_URL}/wham/tasks/list?{urlencode(params)}"

    response = _cloud_request_json(url=url, method="GET", token=token)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected list response from cloud tasks endpoint.")

    items = response.get("items")
    if not isinstance(items, list):
        items = response.get("tasks", []) if isinstance(response.get("tasks"), list) else []

    normalized_tasks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item
        if not isinstance(source.get("id"), str):
            nested = source.get("task")
            if isinstance(nested, dict):
                source = nested

        task_id = source.get("id")
        if not isinstance(task_id, str):
            continue

        status_raw = _task_status_from_payload(source)
        summary = source.get("summary") if isinstance(source.get("summary"), dict) else {}
        status_obj = source.get("task_status_display")

        if isinstance(status_obj, dict):
            status = status_obj.get("status")
            if isinstance(status, str) and status:
                status_raw = status

        normalized_tasks.append(
            {
                "id": task_id,
                "url": source.get("url") or f"{_CLOUD_BASE_URL}/tasks/{task_id}",
                "title": source.get("title")
                if isinstance(source.get("title"), str)
                else source.get("name")
                if isinstance(source.get("name"), str)
                else "",
                "status": status_raw or "",
                "updated_at": source.get("updated_at")
                if isinstance(source.get("updated_at"), str)
                else source.get("created_at")
                if isinstance(source.get("created_at"), str)
                else None,
                "environment_id": source.get("environment_id") if isinstance(source.get("environment_id"), str) else None,
                "environment_label": source.get("environment_label")
                if isinstance(source.get("environment_label"), str)
                else None,
                "summary": {
                    "files_changed": summary.get("files_changed", 0)
                    if isinstance(summary, dict)
                    else 0,
                    "lines_added": summary.get("lines_added", 0)
                    if isinstance(summary, dict)
                    else 0,
                    "lines_removed": summary.get("lines_removed", 0)
                    if isinstance(summary, dict)
                    else 0,
                },
                "is_review": source.get("is_review", False),
                "attempt_total": source.get("attempt_total", 0)
                if isinstance(source.get("attempt_total"), int)
                else 0,
            }
        )

    return normalized_tasks, response.get("cursor")


def _print_cloud_list_output(
    tasks: list[dict],
    cursor: object | None,
    *,
    stdout: TextIO,
    json_output: bool,
) -> None:
    if json_output:
        print(
            json.dumps({"tasks": tasks, "cursor": cursor}, ensure_ascii=False, indent=2),
            file=stdout,
        )
        return

    if not tasks:
        print("No tasks found.", file=stdout)
        return

    for item in tasks:
        task_id = item.get("id", "<unknown>")
        status = item.get("status") or "unknown"
        title = item.get("title") or ""
        url = item.get("url") or ""
        print(f"{task_id}  {status}  {title}", file=stdout)
        if url:
            print(f"  {url}", file=stdout)


def _cloud_task_id_and_attempt(command: str, args: tuple[str, ...]) -> tuple[str, int | None]:
    if command not in {"apply", "diff"}:
        raise ValueError("unsupported cloud subcommand")

    task_id: str | None = None
    attempt: int | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--attempt":
            parse_cloud_attempts_value(args[index + 1], "--attempt")
            attempt = int(args[index + 1])
            index += 2
            continue
        if arg == "--":
            task_id = args[index + 1] if index + 1 < len(args) else None
            break
        if task_id is None:
            task_id = arg
            index += 1
            continue
        index += 1

    if task_id is None:
        raise RuntimeError(f"cloud {command} requires TASK_ID.")
    task_id = _parse_cloud_task_id(task_id)
    return task_id, attempt


def _apply_task_diff_with_git(diff: str, *, stdout: TextIO, stderr: TextIO) -> int:
    command = ["git", "apply", "--3way"]
    try:
        process = subprocess.run(
            command,
            input=diff.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        print(f"git command not found: {exc}", file=stderr)
        return 2
    except OSError as exc:
        print(f"Failed to run git apply: {exc}", file=stderr)
        return 2

    if process.returncode == 0:
        print("Successfully applied diff", file=stdout)
        return 0

    out = (process.stdout or b"").decode("utf-8", errors="replace")
    err = (process.stderr or b"").decode("utf-8", errors="replace")
    text = (out + "\n" + err).strip()
    if text:
        print(text, file=stderr)

    applied_match = re.search(r"(\d+)\s+files?\s+applied", text)
    skipped_match = re.search(r"(\d+)\s+files?\s+skipped", text)
    conflict_match = re.search(r"(\d+)\s+conflict", text)
    if applied_match or skipped_match or conflict_match:
        applied = applied_match.group(1) if applied_match else "0"
        skipped = skipped_match.group(1) if skipped_match else "0"
        conflicts = conflict_match.group(1) if conflict_match else "0"
        print(
            f"Git apply failed (applied={applied} skipped={skipped} conflicts={conflicts})",
            file=stderr,
        )
    else:
        print("Git apply failed.", file=stderr)
    return 1


def main(
    argv: Iterable[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    """CLI entry point.

    Recognized commands currently stop at dispatch for interactive and most
    management commands while non-interactive execution plans are now prepared
    through the ported `exec`/`review` pipeline.
    """

    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr

    try:
        parsed = parse_args(argv)
        parsed.config_overrides_with_feature_toggles()
        if parsed.strict_config:
            _reject_unsupported_strict_config_command(parsed.command, parsed.command_args)
        if parsed.command == "exec" and (
            parsed.remote is not None or parsed.remote_auth_token_env is not None
        ) and local_http_exec_enabled(os.environ):
            reject_remote_mode_for_subcommand(
                parsed.remote,
                parsed.remote_auth_token_env,
                "exec",
            )
        if parsed.command is not None and parsed.command not in _REMOTE_ROOT_OPTION_SUBCOMMANDS:
            reject_remote_mode_for_subcommand(
                parsed.remote,
                parsed.remote_auth_token_env,
                _remote_command_name_for_subcommand(parsed.command, parsed.command_args),
            )
        if (
            "profile" in parsed.root_options
            and parsed.command is not None
            and not any(arg in {"-h", "--help"} for arg in parsed.command_args)
        ):
            _reject_profile_v2_for_subcommand(parsed.command, parsed.command_args)
        if parsed.command == "features" and not any(
            arg in {"-h", "--help"} for arg in parsed.command_args
        ):
            parsed.features_cli()
    except (CliParseError, FeatureCliError) as exc:
        message = str(exc)
        stream = out if message.startswith("Codex CLI") else err
        print(message, file=stream)
        return 0 if stream is out else 2

    if parsed.version_requested:
        print(f"codex {__version__}", file=out)
        return 0

    if parsed.is_interactive:
        if parsed.prompt is not None and (local_http_exec_enabled() or core_exec_enabled()):
            normalized_prompt = _normalize_tui_prompt(parsed.prompt)
            fallback = replace(
                parsed,
                command="exec",
                command_spec=COMMANDS_BY_NAME.get("exec"),
                command_args=(normalized_prompt,),
                prompt=None,
            )
            return _run_noninteractive_exec(
                fallback,
                stdout=out,
                stderr=err,
                stdin=stdin,
                stdin_is_terminal=stdin_is_terminal,
            )
        if os.environ.get("PYCODEX_INTERACTIVE_TO_EXEC_FALLBACK", "").strip().lower() in {"1", "true", "yes", "on"}:
            fallback_prompt = (
                _normalize_tui_prompt(parsed.prompt)
                if parsed.prompt is not None
                else None
            )
            fallback = replace(
                parsed,
                command="exec",
                command_spec=COMMANDS_BY_NAME.get("exec"),
                command_args=() if fallback_prompt is None else (fallback_prompt,),
                prompt=None,
            )
            return _run_noninteractive_exec(
                fallback,
                stdout=out,
                stderr=err,
                stdin=stdin,
                stdin_is_terminal=stdin_is_terminal,
            )
        return _run_tui(
            parsed,
            stdout=out,
            stderr=err,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
        )
    elif parsed.command in {"exec", "review"}:
        if any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_exec_help_text_for_args(parsed.command_args) if parsed.command == "exec" else _review_help_text(), file=out)
            return 0
        return _run_noninteractive_exec(
            parsed,
            stdout=out,
            stderr=err,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
        )
    elif parsed.command == "completion":
        return _run_completion(
            parsed,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "features":
        if any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_features_help_text(), file=out)
            return 0
        features_cli = parsed.features_cli()
        raw_overrides = parsed.config_overrides_with_feature_toggles()
        if parsed.root_options.get("search") and features_cli.subcommand == FeaturesSubcommand.LIST:
            raw_overrides = (*raw_overrides, "web_search=live")
        return run_features_command(
            features_cli,
            raw_config_overrides=raw_overrides,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "cloud":
        return _run_cloud_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
        )
    elif parsed.command == "apply":
        if not parsed.command_args or any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_apply_help_text(), file=out)
            return 0
        return _run_apply_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "doctor":
        return _run_doctor(
            parsed=parsed,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "sandbox":
        return _run_sandbox(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "exec-server":
        return _run_exec_server(
            parsed=parsed,
            stdout=out,
            stderr=err,
        )
    elif parsed.command in {"login", "logout", "update"}:
        if parsed.command == "login":
            return _run_login(
                parsed=parsed,
                stdout=out,
                stderr=err,
                stdin=stdin,
                stdin_is_terminal=stdin_is_terminal,
            )
        if parsed.command == "logout":
            return _run_logout(parsed=parsed, stdout=out, stderr=err)
        return _run_update(parsed=parsed, stdout=out, stderr=err)
    elif parsed.command == "remote-control":
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_remote_control_help_text(parsed.command_args), file=out)
            return 0
        return _run_remote_control_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "mcp":
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_mcp_help_text(parsed.command_args), file=out)
            return 0
        return _run_mcp_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "plugin":
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_plugin_help_text(parsed.command_args), file=out)
            return 0
        return _run_plugin_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command in {"mcp-server", "debug", "resume", "fork"}:
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            if parsed.command == "resume":
                print(_resume_help_text(), file=out)
            elif parsed.command == "fork":
                print(_fork_help_text(), file=out)
            else:
                print(_unimplemented_command_help_text(parsed.command), file=out)
            return 0
        if parsed.command == "mcp-server":
            return _run_mcp_server_command(
                parsed.command_args,
                stdout=out,
                stderr=err,
                stdin=stdin,
            )
        if parsed.command == "debug":
            return _run_debug_command(
                parsed.command_args,
                stdout=out,
                stderr=err,
            )
        return _run_resume_or_fork_command(
            parsed,
            stdout=out,
            stderr=err,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
        )
    elif parsed.command == "app":
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_app_help_text(), file=out)
            return 0
        return _run_app_command(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "app-server":
        if parsed.command_args and any(arg in {"-h", "--help"} for arg in parsed.command_args):
            print(_app_server_help_text(parsed.command_args), file=out)
            return 0
        return _run_app_server_command(parsed.command_args, stdout=out, stderr=err)
    elif parsed.command == "execpolicy":
        return _run_execpolicy_check(
            parsed.command_args,
            stdout=out,
            stderr=err,
        )
    elif parsed.command == "responses-api-proxy":
        return _run_responses_api_proxy(
            parsed.command_args,
            stdout=out,
            stderr=err,
            stdin=stdin,
        )
    elif parsed.command == "stdio-to-uds":
        return _run_stdio_to_uds(
            parsed.command_args,
            stdout=out,
            stderr=err,
            stdin=stdin,
        )
    else:
        print(
            f"pycodex: command '{parsed.command}' is recognized but not implemented yet.",
            file=err,
        )
    return 64


def _run_tui(
    parsed: ParsedCli | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    if parsed is None:
        return run_tui(stderr=stderr)

    out = sys.stdout if stdout is None else stdout
    terminal_guard_message = _interactive_tui_terminal_guard_message(stdin_is_terminal, stderr)
    if terminal_guard_message is not None:
        print(f"ERROR: {terminal_guard_message}", file=stderr)
        return 1
    try:
        active_thread_runtime = _build_tui_core_active_thread_runtime(parsed, stderr=stderr)
    except (CliParseError, ExecCliParseError, ExecConfigPlanError, ExecRunError, ValueError) as exc:
        print(str(exc), file=stderr)
        return 2
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=stderr)
        return 1

    startup_session_kwargs = _startup_session_kwargs(parsed)
    if startup_session_kwargs:
        app_runtime = TuiAppRuntime(active_thread_runtime, **startup_session_kwargs)
        active_thread_runtime = app_runtime.active_thread_runtime
    tui_stdin = sys.stdin if stdin_is_terminal and stdin is getattr(sys.stdin, "buffer", None) else stdin
    from pycodex.tui.textual_runtime import determine_alt_screen_mode, run_textual_tui, should_use_textual_tui

    use_alt_screen = determine_alt_screen_mode(
        bool(parsed.root_options.get("no_alt_screen", False)),
        getattr(getattr(active_thread_runtime, "session_config", None), "tui_alternate_screen", AltScreenMode.AUTO),
    )

    if should_use_textual_tui(
        stdout=out,
        stdin=tui_stdin,
        active_thread_runtime=active_thread_runtime,
        use_alt_screen=use_alt_screen,
    ):

        if startup_session_kwargs:
            return run_textual_tui(
                active_thread_runtime=app_runtime,
                stdout=out,
                stdin=tui_stdin,
                use_alt_screen=use_alt_screen,
            )
        return run_textual_tui(
            active_thread_runtime=active_thread_runtime,
            stdout=out,
            stdin=tui_stdin,
            use_alt_screen=use_alt_screen,
        )
    print("Error: stdin is not a terminal", file=stderr)
    return 1


def _interactive_tui_terminal_guard_message(stdin_is_terminal: bool | None, stderr: TextIO) -> str | None:
    """Mirror Rust ``codex-cli::run_interactive_tui`` TERM=dumb startup guard.

    Rust refuses to start the interactive TUI when TERM is ``dumb`` and no real
    terminal is available for the confirmation prompt.  Other non-terminal
    startup failures are owned by ``codex-tui/src/tui.rs::init``; Python mirrors
    that boundary in ``_run_tui`` after constructing the active-thread runtime.
    """

    if os.environ.get("TERM") != "dumb":
        return None
    if stdin_is_terminal is None:
        return None
    stderr_is_terminal = _stream_is_terminal(stderr)
    if bool(stdin_is_terminal) and stderr_is_terminal:
        return None
    return (
        'TERM is set to "dumb". Refusing to start the interactive TUI because '
        "no terminal is available for a confirmation prompt (stdin/stderr is "
        "not a TTY). Run in a supported terminal or unset TERM."
    )


def _stream_is_terminal(stream: object) -> bool:
    isatty = getattr(stream, "isatty", None)
    try:
        return bool(isatty()) if callable(isatty) else False
    except OSError:
        return False


def _normalize_tui_prompt(prompt: str) -> str:
    return prompt.replace("\r\n", "\n").replace("\r", "\n")


def _build_tui_core_active_thread_runtime(parsed: ParsedCli, *, stderr: TextIO) -> CoreExecActiveThreadRuntime:
    reject_remote_mode_for_subcommand(
        parsed.remote if "remote" in parsed.root_options else None,
        parsed.remote_auth_token_env if "remote_auth_token_env" in parsed.root_options else None,
        "tui",
    )
    exec_cli = parse_exec_args(
        (),
        root_config_overrides=parsed.config_overrides_with_feature_toggles(),
    )
    exec_cli = _inherit_exec_root_options(exec_cli, parsed)
    if warning := exec_cli.removed_full_auto_warning():
        print(warning, file=stderr)
    codex_home = Path(find_codex_home())
    config_toml = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    migration_status = maybe_migrate_personality(
        codex_home,
        config_toml,
        override_profile=str(exec_cli.profile) if exec_cli.profile is not None else None,
    )
    if migration_status == PersonalityMigrationStatus.APPLIED:
        config_toml = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    bootstrap_plan = build_exec_config_bootstrap_plan(exec_cli, config_toml=config_toml)
    ensure_exec_trusted_directory(
        exec_trusted_directory_check(exec_cli, bootstrap_plan.config_cwd)
    )
    exec_policy_rules = _execpolicy_rules_for_local_http_exec(
        codex_home,
        bootstrap_plan.config_cwd,
        ignore_rules=exec_cli.ignore_rules,
    )
    session_config = _build_exec_session_config(
        bootstrap_plan,
        exec_policy_rules=exec_policy_rules,
    )
    auth_json = read_auth_json()
    model_client, provider, model_info, resolved_auth = build_default_core_exec_runtime(
        session_config,
        auth=auth_json,
        config_toml=config_toml,
    )
    return CoreExecActiveThreadRuntime(
        session_config,
        model_client,
        provider,
        model_info,
        auth=resolved_auth,
        original_auth=auth_json,
        codex_home=codex_home,
        max_tool_followups=local_http_exec_max_tool_rounds(),
        startup_prewarm_enabled=True,
    )


def _startup_session_kwargs(parsed: ParsedCli) -> dict[str, object]:
    root = parsed.root_options
    action = root.get("tui_startup_session_action")
    if action not in {"resume", "fork"}:
        return {}
    return {
        "startup_session_action": action,
        "startup_session_id": root.get("tui_startup_session_id") if isinstance(root.get("tui_startup_session_id"), str) else None,
        "startup_session_last": bool(root.get("tui_startup_session_last", False)),
        "startup_session_show_all": bool(root.get("tui_startup_session_show_all", False)),
        "startup_session_include_non_interactive": bool(root.get("tui_startup_session_include_non_interactive", False)),
    }


def _read_json_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read {path}: {exc}") from exc

    if isinstance(raw, dict):
        return raw
    raise RuntimeError(f"invalid state format in {path}: expected object")


def _write_json_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _safe_codex_home() -> Path:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise RuntimeError(f"failed to resolve CODEX_HOME: {exc}") from exc


def _load_mcp_servers(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config_path = codex_home / CONFIG_TOML_FILE
    config = read_toml_mapping(config_path)
    servers_value = config.get("mcp_servers")
    if not isinstance(servers_value, MutableMapping):
        return {}, config

    servers: dict[str, Any] = {}
    for name, server in servers_value.items():
        if isinstance(name, str) and isinstance(server, MutableMapping):
            servers[name] = dict(server)
    return servers, config


def _write_mcp_servers(codex_home: Path, servers: Mapping[str, Any], *, base_config: MutableMapping[str, Any]) -> None:
    if servers:
        base_config["mcp_servers"] = {
            str(name): dict(value)
            for name, value in sorted(servers.items(), key=lambda item: str(item[0]))
        }
    else:
        base_config.pop("mcp_servers", None)
    write_toml_mapping(codex_home / CONFIG_TOML_FILE, base_config)


def _parse_mcp_add_definition(command_args: tuple[str, ...]) -> dict[str, Any]:
    name = command_args[1]
    _validate_mcp_server_name(name)

    index = 2
    definition: dict[str, Any] = {}
    env: dict[str, str] = {}
    saw_command = False
    while index < len(command_args):
        arg = command_args[index]
        if arg == "--":
            saw_command = True
            command = list(command_args[index + 1 :])
            if command:
                definition["command"] = command[0]
                if len(command) > 1:
                    definition["args"] = command[1:]
            break
        if arg == "--url":
            definition["url"] = command_args[index + 1]
            index += 2
            continue
        if arg == "--env":
            env_pair = command_args[index + 1]
            key, value = _parse_mcp_env_pair(env_pair)
            env[key] = value
            index += 2
            continue
        if arg == "--bearer-token-env-var":
            definition["bearer_token_env_var"] = command_args[index + 1]
            index += 2
            continue
        if arg == "--oauth-client-id":
            definition.setdefault("oauth", {})["client_id"] = command_args[index + 1]
            index += 2
            continue
        if arg == "--oauth-resource":
            definition["oauth_resource"] = command_args[index + 1]
            index += 2
            continue
        index += 1

    if env:
        definition["env"] = env
    return definition


def _parse_mcp_env_pair(raw: str) -> tuple[str, str]:
    key, separator, value = raw.partition("=")
    key = key.strip()
    if not separator or not key:
        raise RuntimeError("environment entries must be in KEY=VALUE form")
    return key, value


def _validate_mcp_server_name(name: str) -> None:
    if name and all(ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) for ch in name):
        return
    raise RuntimeError(f"invalid server name '{name}' (use letters, numbers, '-', '_')")


def _plugin_key(name: str, marketplace: str) -> str:
    return f"{name}@{marketplace}"


def _validate_plugin_segment(segment: str, kind: str) -> None:
    if not segment:
        raise ValueError(f"invalid {kind}: must not be empty")
    if not all(ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) for ch in segment):
        raise ValueError(f"invalid {kind}: only ASCII letters, digits, `_`, and `-` are allowed")


def _validate_plugin_version_segment(version: str) -> None:
    if not version:
        raise ValueError("invalid plugin version: must not be empty")
    if version in {".", ".."}:
        raise ValueError("invalid plugin version: path traversal is not allowed")
    if not all(ch.isascii() and (ch.isalnum() or ch in {".", "+", "_", "-"}) for ch in version):
        raise ValueError("invalid plugin version: only ASCII letters, digits, `.`, `+`, `_`, and `-` are allowed")


def _version_segment_invalid(version: str) -> bool:
    try:
        _validate_plugin_version_segment(version)
    except ValueError:
        return True
    return False


def _semver_core(version: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _compare_plugin_versions(left: str, right: str) -> int:
    left_semver = _semver_core(left)
    right_semver = _semver_core(right)
    if left_semver is not None and right_semver is not None:
        return (left_semver > right_semver) - (left_semver < right_semver)
    return (left > right) - (left < right)


def _old_plugin_version_would_stay_active(old_version: str, new_version: str) -> bool:
    return old_version == _DEFAULT_PLUGIN_VERSION or _compare_plugin_versions(old_version, new_version) > 0


def _parse_plugin_selector(value: str, explicit_marketplace: str | None) -> tuple[str, str]:
    plugin_name = value
    marketplace = explicit_marketplace
    tail = ""
    if "@" in value:
        head, tail = value.rsplit("@", 1)
        plugin_name = head
        if explicit_marketplace is None and head and tail:
            marketplace = tail
        elif explicit_marketplace is not None and head and tail and tail != explicit_marketplace:
            raise ValueError(
                f"plugin id `{value}` belongs to marketplace `{tail}`, "
                f"but --marketplace specified `{explicit_marketplace}`"
            )
    if explicit_marketplace is None and "@" in value and not tail:
        raise ValueError(f"Invalid plugin selector: {value}")
    if not plugin_name:
        raise ValueError(f"Invalid plugin selector: {value}")
    if marketplace is None:
        raise ValueError("plugin requires --marketplace unless passed as <plugin>@<marketplace>")
    try:
        _validate_plugin_segment(plugin_name, "plugin name")
        _validate_plugin_segment(marketplace, "marketplace name")
    except ValueError as exc:
        if "@" in value and explicit_marketplace is None:
            raise ValueError(f"{exc} in `{value}`") from exc
        raise
    return plugin_name, marketplace


def _plugin_marketplace_name_from_source(source: str) -> str:
    source_path = Path(source).expanduser()
    if source_path.exists():
        if source_path.is_file():
            raise RuntimeError("local marketplace source must be a directory, not a file")
        manifest_path = source_path / ".agents" / "plugins" / "marketplace.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"failed to read marketplace manifest {manifest_path}: {exc}") from exc
            if isinstance(manifest, MutableMapping):
                manifest_name = manifest.get("name")
                if isinstance(manifest_name, str) and manifest_name:
                    try:
                        _validate_plugin_segment(manifest_name, "marketplace name")
                    except ValueError as exc:
                        raise RuntimeError(str(exc)) from exc
                    return manifest_name
        if source_path.name:
            candidate = source_path.name
            try:
                _validate_plugin_segment(candidate, "marketplace name")
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            return candidate

    parsed = urlparse(source)
    if parsed.scheme and parsed.path:
        candidate = Path(parsed.path).name
    elif "/" in source or "\\" in source:
        candidate = Path(source).name
    else:
        candidate = source

    candidate = candidate.rsplit("@", 1)[0]
    if candidate.endswith(".git"):
        candidate = candidate[:-4]
    try:
        _validate_plugin_segment(candidate or source, "marketplace name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return candidate or source


def _load_marketplace_config(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    marketplaces_value = config.get("marketplaces")
    marketplaces: dict[str, Any] = {}
    if isinstance(marketplaces_value, MutableMapping):
        for name, entry in marketplaces_value.items():
            if isinstance(name, str) and isinstance(entry, MutableMapping):
                marketplaces[name] = dict(entry)
    return marketplaces, config


def _write_marketplace_config(codex_home: Path, marketplaces: Mapping[str, Any], config: MutableMapping[str, Any]) -> None:
    if marketplaces:
        config["marketplaces"] = {
            str(name): dict(entry)
            for name, entry in sorted(marketplaces.items(), key=lambda item: str(item[0]))
            if isinstance(entry, MutableMapping)
        }
    else:
        config.pop("marketplaces", None)
    write_toml_mapping(codex_home / CONFIG_TOML_FILE, config)


def _marketplace_config_update(source: str, ref: str | None, sparse: list[str]) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    if source_path.exists():
        if sparse:
            raise RuntimeError("--sparse is only supported for git marketplace sources")
        source_type = "local"
        source_value = str(source_path.resolve())
    else:
        source_type = "git"
        source_value = source

    entry: dict[str, Any] = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source_type": source_type,
        "source": source_value,
    }
    if ref is not None:
        entry["ref"] = ref
    if sparse:
        entry["sparse_paths"] = sparse
    return entry


def _load_plugin_config(codex_home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
    plugins_value = config.get("plugins")
    plugins: dict[str, Any] = {}
    if isinstance(plugins_value, MutableMapping):
        for name, entry in plugins_value.items():
            if isinstance(name, str) and isinstance(entry, MutableMapping):
                plugins[name] = dict(entry)
    return plugins, config


def _write_plugin_config(codex_home: Path, plugins: Mapping[str, Any], config: MutableMapping[str, Any]) -> None:
    if plugins:
        config["plugins"] = {
            str(name): dict(entry)
            for name, entry in sorted(plugins.items(), key=lambda item: str(item[0]))
            if isinstance(entry, MutableMapping)
        }
    else:
        config.pop("plugins", None)
    write_toml_mapping(codex_home / CONFIG_TOML_FILE, config)


def _read_marketplace_manifest(marketplace_root: Path) -> Mapping[str, Any]:
    manifest_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RuntimeError("marketplace root does not contain a supported manifest") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read marketplace manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, MutableMapping):
        raise RuntimeError("marketplace manifest must be an object")
    return manifest


def _find_marketplace_plugin(manifest: Mapping[str, Any], plugin_name: str) -> Mapping[str, Any]:
    try:
        _validate_plugin_segment(plugin_name, "plugin name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise RuntimeError("marketplace manifest must contain a plugins array")
    matches = [
        plugin
        for plugin in plugins
        if isinstance(plugin, MutableMapping) and plugin.get("name") == plugin_name
    ]
    if not matches:
        raise RuntimeError("plugin not found in marketplace")
    if len(matches) > 1:
        raise RuntimeError("plugin matched multiple marketplace entries")
    return matches[0]


def _copy_local_marketplace_plugin(
    codex_home: Path,
    marketplace: str,
    plugin_name: str,
    marketplace_entry: Mapping[str, Any],
) -> tuple[str, Path]:
    if marketplace_entry.get("source_type") != "local":
        raise RuntimeError("only local marketplace plugin installation is implemented")
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError("configured local marketplace source is missing or empty")
    marketplace_root = Path(source_value)
    manifest = _read_marketplace_manifest(marketplace_root)
    plugin = _find_marketplace_plugin(manifest, plugin_name)
    source = plugin.get("source")
    if not isinstance(source, MutableMapping) or source.get("source") != "local":
        raise RuntimeError("only local marketplace plugin sources are implemented")
    plugin_path_value = source.get("path")
    if not isinstance(plugin_path_value, str) or not plugin_path_value:
        raise RuntimeError("local marketplace plugin source path is missing")
    plugin_source = (marketplace_root / plugin_path_value).resolve()
    plugin_manifest_path = plugin_source / ".codex-plugin" / "plugin.json"
    try:
        plugin_manifest = json.loads(plugin_manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise RuntimeError("plugin root does not contain .codex-plugin/plugin.json") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read plugin manifest {plugin_manifest_path}: {exc}") from exc
    if not isinstance(plugin_manifest, MutableMapping):
        raise RuntimeError("plugin manifest must be an object")
    manifest_name = plugin_manifest.get("name")
    if not isinstance(manifest_name, str) or not manifest_name:
        raise RuntimeError("invalid plugin name: must not be empty")
    try:
        _validate_plugin_segment(manifest_name, "plugin name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if manifest_name != plugin_name:
        raise RuntimeError(f"plugin.json name `{manifest_name}` does not match marketplace plugin name `{plugin_name}`")
    raw_version = plugin_manifest.get("version")
    if raw_version is None:
        version = _DEFAULT_PLUGIN_VERSION
    elif not isinstance(raw_version, str):
        raise RuntimeError("invalid plugin version in plugin.json: expected string")
    else:
        version = raw_version.strip()
        if not version:
            raise RuntimeError("invalid plugin version in plugin.json: must not be blank")
    try:
        _validate_plugin_version_segment(version)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    installed_root = codex_home / "plugins" / "cache" / marketplace / plugin_name / version
    if installed_root.exists():
        shutil.rmtree(installed_root)
    installed_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, installed_root)
    _remove_old_plugin_versions(installed_root.parent, version)
    return version, installed_root


def _remove_old_plugin_versions(target_root: Path, plugin_version: str) -> None:
    if not target_root.is_dir():
        return
    for entry in target_root.iterdir():
        if not entry.is_dir():
            continue
        old_version = entry.name
        if old_version == plugin_version:
            continue
        try:
            _validate_plugin_version_segment(old_version)
        except ValueError:
            continue
        try:
            shutil.rmtree(entry)
        except OSError as exc:
            if _old_plugin_version_would_stay_active(old_version, plugin_version):
                raise RuntimeError(
                    f"failed to activate updated plugin cache version `{plugin_version}` while `{old_version}` remains active"
                ) from exc


def _remove_installed_plugin_cache(codex_home: Path, marketplace: str, plugin_name: str) -> None:
    plugin_cache_root = codex_home / "plugins" / "cache" / marketplace / plugin_name
    if plugin_cache_root.exists():
        shutil.rmtree(plugin_cache_root)


def _marketplace_root_display(marketplace: str, marketplace_entry: Mapping[str, Any]) -> str:
    try:
        _validate_plugin_segment(marketplace, "marketplace name")
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError(f"`{marketplace}` <invalid source>: configured local marketplace source is missing or empty")
    if marketplace_entry.get("source_type") == "local":
        marketplace_root = Path(source_value)
        _read_marketplace_manifest(marketplace_root)
        return str(marketplace_root)
    return source_value


def _plugin_manifest_version(plugin_root: Path) -> str:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(manifest, MutableMapping):
        return ""
    version = manifest.get("version")
    return version if isinstance(version, str) else ""


def _installed_plugin_version(codex_home: Path, marketplace: str, plugin_name: str) -> str:
    plugin_cache_root = codex_home / "plugins" / "cache" / marketplace / plugin_name
    if not plugin_cache_root.is_dir():
        return ""
    versions = [
        path.name
        for path in plugin_cache_root.iterdir()
        if path.is_dir()
    ]
    versions = [
        version
        for version in versions
        if not _version_segment_invalid(version)
    ]
    if not versions:
        return ""
    if _DEFAULT_PLUGIN_VERSION in versions:
        active_version = _DEFAULT_PLUGIN_VERSION
    else:
        active_version = sorted(versions, key=cmp_to_key(_compare_plugin_versions))[-1]
    active_root = plugin_cache_root / active_version
    return _plugin_manifest_version(active_root) or active_version


def _local_marketplace_plugin_path(marketplace_root: Path, plugin: Mapping[str, Any]) -> Path | None:
    source = plugin.get("source")
    if not isinstance(source, MutableMapping) or source.get("source") != "local":
        return None
    plugin_path_value = source.get("path")
    if not isinstance(plugin_path_value, str) or not plugin_path_value:
        return None
    return (marketplace_root / plugin_path_value).resolve()


def _render_plugin_table_for_marketplace(
    codex_home: Path,
    marketplace: str,
    marketplace_entry: Mapping[str, Any],
    plugin_config: Mapping[str, Any],
    *,
    stdout: TextIO,
) -> bool:
    if marketplace_entry.get("source_type") != "local":
        return False
    source_value = marketplace_entry.get("source")
    if not isinstance(source_value, str) or not source_value:
        raise RuntimeError("configured local marketplace source is missing or empty")
    marketplace_root = Path(source_value)
    manifest = _read_marketplace_manifest(marketplace_root)
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise RuntimeError("marketplace manifest must contain a plugins array")

    rows: list[tuple[str, str, str, str]] = []
    for plugin in plugins:
        if not isinstance(plugin, MutableMapping):
            continue
        name = plugin.get("name")
        if not isinstance(name, str) or not name:
            continue
        try:
            _validate_plugin_segment(name, "plugin name")
        except ValueError:
            continue
        plugin_key = _plugin_key(name, marketplace)
        configured = plugin_config.get(plugin_key)
        installed = isinstance(configured, MutableMapping)
        enabled = not isinstance(configured, MutableMapping) or configured.get("enabled", True) is not False
        if installed and enabled:
            status = "installed, enabled"
        elif installed:
            status = "installed, disabled"
        else:
            status = "not installed"
        version = _installed_plugin_version(codex_home, marketplace, name) if installed else ""
        plugin_path = _local_marketplace_plugin_path(marketplace_root, plugin)
        rows.append((plugin_key, status, version, str(plugin_path) if plugin_path is not None else ""))

    plugin_width = max(["PLUGIN".__len__(), *(len(row[0]) for row in rows)] or [len("PLUGIN")])
    status_width = max(["STATUS".__len__(), *(len(row[1]) for row in rows)] or [len("STATUS")])
    version_width = max(["VERSION".__len__(), *(len(row[2]) for row in rows)] or [len("VERSION")])
    path_width = max(["PATH".__len__(), *(len(row[3]) for row in rows)] or [len("PATH")])

    print(f"Marketplace `{marketplace}`", file=stdout)
    print(marketplace_root / ".agents" / "plugins" / "marketplace.json", file=stdout)
    print("", file=stdout)
    print(
        f"{'PLUGIN':<{plugin_width}}  {'STATUS':<{status_width}}  {'VERSION':<{version_width}}  {'PATH':<{path_width}}",
        file=stdout,
    )
    for plugin_key, status, version, path in rows:
        print(
            f"{plugin_key:<{plugin_width}}  {status:<{status_width}}  {version:<{version_width}}  {path:<{path_width}}",
            file=stdout,
        )
    return True


def _parse_app_server_out_argument(args: tuple[str, ...]) -> str | None:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--out", "-o"}:
            if index + 1 >= len(args):
                return None
            return args[index + 1]
        index += 1
    return None


def _run_mcp_command(command_args: tuple[str, ...], *, stdout: TextIO, stderr: TextIO) -> int:
    if not command_args:
        print("Usage: codex mcp [OPTIONS] <SUBCOMMAND>", file=stdout)
        return 0

    try:
        codex_home = _safe_codex_home()
        auth_state = _read_json_state(codex_home / _MCP_STATE_FILE)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    subcommand = command_args[0]
    is_json = "--json" in command_args
    rest = tuple(arg for arg in command_args[1:] if arg != "--json")

    try:
        mcp_servers, base_config = _load_mcp_servers(codex_home)
    except (RuntimeError, OSError) as exc:
        print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
        return 2

    if subcommand == "list":
        if is_json:
            print(json.dumps(mcp_servers, indent=2, sort_keys=True), file=stdout)
        else:
            if not mcp_servers:
                print("No MCP servers configured.", file=stdout)
            else:
                for name in sorted(mcp_servers):
                    print(name, file=stdout)
        return 0

    if subcommand == "get":
        if not rest:
            print("mcp get requires MCP server name.", file=stderr)
            return 2
        name = rest[0]
        server = mcp_servers.get(name)
        if not isinstance(server, MutableMapping):
            print(f"pycodex: MCP server '{name}' not found.", file=stderr)
            return 2
        if is_json:
            print(json.dumps(server, indent=2, sort_keys=True), file=stdout)
        else:
            print(name, file=stdout)
            for key, value in sorted(dict(server).items()):
                print(f"{key}={value}", file=stdout)
        return 0

    if subcommand == "add":
        name = rest[0]
        try:
            definition = _parse_mcp_add_definition(command_args)
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

        if definition.get("url") is None and definition.get("command") is None:
            print("mcp add requires --url or command.", file=stderr)
            return 2
        mcp_servers[name] = definition
        try:
            _write_mcp_servers(codex_home, mcp_servers, base_config=base_config)
        except OSError as exc:
            print(f"pycodex: failed to write config: {exc}", file=stderr)
            return 2
        print(f"Added MCP server '{name}'.", file=stdout)
        return 0

    if subcommand == "remove":
        if not rest:
            print("mcp remove requires MCP server name.", file=stderr)
            return 2
        name = rest[0]
        try:
            _validate_mcp_server_name(name)
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        if name not in mcp_servers:
            print(f"pycodex: MCP server '{name}' not found.", file=stderr)
            return 2
        del mcp_servers[name]
        try:
            _write_mcp_servers(codex_home, mcp_servers, base_config=base_config)
        except OSError as exc:
            print(f"pycodex: failed to write config: {exc}", file=stderr)
            return 2
        if isinstance(auth_state.get("logins"), MutableMapping):
            auth_state["logins"] = dict(auth_state["logins"])
            if isinstance(auth_state["logins"], MutableMapping):
                auth_state["logins"].pop(name, None)
                try:
                    _write_json_state(codex_home / _MCP_STATE_FILE, auth_state)
                except OSError as exc:
                    print(f"pycodex: failed to update MCP login state: {exc}", file=stderr)
        print(f"Removed MCP server '{name}'.", file=stdout)
        return 0

    if subcommand in {"login", "logout"}:
        if not rest:
            print(f"{subcommand} requires MCP server name.", file=stderr)
            return 2
        name = rest[0]
        if subcommand == "login":
            if name not in mcp_servers:
                print(f"pycodex: MCP server '{name}' not found.", file=stderr)
                return 2
            scopes: list[str] = []
            index = 2
            while index < len(command_args):
                arg = command_args[index]
                if arg == "--scopes":
                    scopes.append(command_args[index + 1])
                    index += 2
                    continue
                index += 1
            logins = auth_state.get("logins")
            if not isinstance(logins, MutableMapping):
                logins = {}
            logins = dict(logins)
            logins[name] = {
                "state": "logged_in",
                "scopes": scopes,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            auth_state["logins"] = logins
            try:
                _write_json_state(codex_home / _MCP_STATE_FILE, auth_state)
            except OSError as exc:
                print(f"pycodex: failed to write MCP login state: {exc}", file=stderr)
                return 2
            print(f"Logged in to MCP server '{name}'.", file=stdout)
            return 0

        if subcommand == "logout":
            logins = auth_state.get("logins")
            if not isinstance(logins, MutableMapping):
                logins = {}
            else:
                logins = dict(logins)
            if name in logins:
                del logins[name]
            auth_state["logins"] = logins
            try:
                _write_json_state(codex_home / _MCP_STATE_FILE, auth_state)
            except OSError as exc:
                print(f"pycodex: failed to write MCP login state: {exc}", file=stderr)
                return 2
            print(f"Logged out MCP server '{name}'.", file=stdout)
            return 0

    print(f"Unrecognized mcp subcommand: {subcommand}", file=stderr)
    return 64


def _run_plugin_command(command_args: tuple[str, ...], *, stdout: TextIO, stderr: TextIO) -> int:
    if not command_args:
        print("Usage: codex plugin [OPTIONS] <SUBCOMMAND>", file=stdout)
        return 0

    if any(arg in {"-h", "--help"} for arg in command_args):
        print(_plugin_help_text(command_args), file=stdout)
        return 0

    try:
        codex_home = _safe_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    path = codex_home / _PLUGIN_STATE_FILE
    try:
        state = _read_json_state(path)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2
    subcommand = command_args[0]

    if subcommand == "marketplace":
        if len(command_args) < 2:
            print("plugin marketplace requires a subcommand.", file=stderr)
            return 2
        market_action = command_args[1]
        if market_action == "list":
            try:
                marketplaces, _config = _load_marketplace_config(codex_home)
            except OSError as exc:
                print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            rows: list[tuple[str, str]] = []
            for market, market_entry in sorted(marketplaces.items(), key=lambda item: item[0]):
                try:
                    root_display = _marketplace_root_display(market, market_entry)
                except RuntimeError as exc:
                    print(f"pycodex: failed to load marketplace(s): {exc}", file=stderr)
                    return 2
                rows.append((market, root_display))
            print("MARKETPLACE  ROOT", file=stdout)
            for market, root_display in rows:
                print(f"{market:<{len('MARKETPLACE')}}  {root_display}", file=stdout)
            return 0

        if market_action == "add":
            if len(command_args) < 3:
                print("plugin marketplace add requires source.", file=stderr)
                return 2
            source = command_args[2]
            index = 3
            sparse: list[str] = []
            ref: str | None = None
            while index < len(command_args):
                arg = command_args[index]
                if arg == "--ref":
                    ref = command_args[index + 1]
                    index += 2
                    continue
                if arg == "--sparse":
                    index += 1
                    while index < len(command_args) and not command_args[index].startswith("-"):
                        sparse.append(command_args[index])
                        index += 1
                    continue
                index += 1
            try:
                market_name = _plugin_marketplace_name_from_source(source)
                market_info = _marketplace_config_update(source, ref, sparse)
            except RuntimeError as exc:
                print(f"pycodex: {exc}", file=stderr)
                return 2
            try:
                markets, config = _load_marketplace_config(codex_home)
                already_added = market_name in markets
                markets[market_name] = market_info
                _write_marketplace_config(codex_home, markets, config)
            except OSError as exc:
                print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            if already_added:
                print(f"Marketplace '{market_name}' is already added from {source}.", file=stdout)
            else:
                print(f"Added marketplace '{market_name}' from {source}.", file=stdout)
            return 0

        if market_action == "upgrade":
            if len(command_args) > 3:
                print("plugin marketplace upgrade accepts at most one marketplace name.", file=stderr)
                return 2
            try:
                marketplaces, config = _load_marketplace_config(codex_home)
            except OSError as exc:
                print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            if len(command_args) == 2:
                updated = False
                for market_name, market_entry in marketplaces.items():
                    if isinstance(market_entry, MutableMapping) and market_entry.get("source_type") == "git":
                        market_entry["last_updated"] = datetime.now(timezone.utc).isoformat()
                        updated = True
                if not updated:
                    print("No configured Git marketplaces to upgrade.", file=stdout)
                    return 0
                try:
                    _write_marketplace_config(codex_home, marketplaces, config)
                except OSError as exc:
                    print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                    return 2
                print("Upgraded all marketplaces.", file=stdout)
                return 0
            market_name = command_args[2]
            market_entry = marketplaces.get(market_name)
            if not isinstance(market_entry, MutableMapping):
                print(f"pycodex: marketplace '{market_name}' not found.", file=stderr)
                return 2
            market_entry["last_updated"] = datetime.now(timezone.utc).isoformat()
            marketplaces[market_name] = market_entry
            try:
                _write_marketplace_config(codex_home, marketplaces, config)
            except OSError as exc:
                print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            print(f"Upgraded marketplace '{market_name}'.", file=stdout)
            return 0

        if market_action == "remove":
            if len(command_args) < 3:
                print("plugin marketplace remove requires marketplace name.", file=stderr)
                return 2
            if len(command_args) > 3:
                print("plugin marketplace remove requires marketplace name.", file=stderr)
                return 2
            market_name = command_args[2]
            try:
                marketplaces, config = _load_marketplace_config(codex_home)
            except OSError as exc:
                print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            if not marketplaces.pop(market_name, None):
                print(f"pycodex: marketplace '{market_name}' not found.", file=stderr)
                return 2
            try:
                _write_marketplace_config(codex_home, marketplaces, config)
            except OSError as exc:
                print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            print(f"Removed marketplace '{market_name}'.", file=stdout)
            return 0

        print(f"plugin marketplace {market_action} is not implemented.", file=stderr)
        return 64

    if subcommand in {"add", "remove"}:
        if len(command_args) < 2:
            print(f"plugin {subcommand} requires <plugin>[@<marketplace>].", file=stderr)
            return 2
        selector = command_args[1]
        explicit_marketplace = None
        if len(command_args) == 4 and command_args[2] in {"--marketplace", "-m"}:
            explicit_marketplace = command_args[3]
        try:
            plugin_name, marketplace = _parse_plugin_selector(selector, explicit_marketplace)
        except ValueError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        plugin_key = _plugin_key(plugin_name, marketplace)
        if subcommand == "add":
            try:
                marketplaces, _market_config = _load_marketplace_config(codex_home)
                if marketplace not in marketplaces:
                    print(f"pycodex: plugin `{plugin_name}` was not found in marketplace `{marketplace}`", file=stderr)
                    return 2
                marketplace_entry = marketplaces[marketplace]
                if not isinstance(marketplace_entry, MutableMapping):
                    print(f"pycodex: plugin `{plugin_name}` was not found in marketplace `{marketplace}`", file=stderr)
                    return 2
                try:
                    installed_version, installed_path = _copy_local_marketplace_plugin(
                        codex_home,
                        marketplace,
                        plugin_name,
                        marketplace_entry,
                    )
                except RuntimeError as exc:
                    print(f"pycodex: {exc}", file=stderr)
                    return 2
                plugin_list, config = _load_plugin_config(codex_home)
                plugin_entry = dict(plugin_list.get(plugin_key, {})) if isinstance(plugin_list.get(plugin_key), MutableMapping) else {}
                plugin_entry["enabled"] = True
                plugin_list[plugin_key] = plugin_entry
                _write_plugin_config(codex_home, plugin_list, config)
            except OSError as exc:
                print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
                return 2
            print(f"Added plugin `{plugin_name}` from marketplace `{marketplace}`.", file=stdout)
            print(f"Installed plugin root: {installed_path}", file=stdout)
            return 0

        try:
            plugin_list, config = _load_plugin_config(codex_home)
        except OSError as exc:
            print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        if plugin_key not in plugin_list:
            print(f"pycodex: plugin '{plugin_name}' not found.", file=stderr)
            return 2
        del plugin_list[plugin_key]
        try:
            _remove_installed_plugin_cache(codex_home, marketplace, plugin_name)
            _write_plugin_config(codex_home, plugin_list, config)
        except OSError as exc:
            print(f"pycodex: failed to write {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        print(f"Removed plugin `{plugin_name}` from marketplace `{marketplace}`.", file=stdout)
        return 0

    if subcommand == "list":
        try:
            plugin_list, _config = _load_plugin_config(codex_home)
            marketplaces, _market_config = _load_marketplace_config(codex_home)
        except OSError as exc:
            print(f"pycodex: failed to read {CONFIG_TOML_FILE}: {exc}", file=stderr)
            return 2
        selected_marketplace = None
        if len(command_args) == 3 and command_args[1] in {"--marketplace", "-m"}:
            selected_marketplace = command_args[2]
        rendered = False
        matched_marketplaces = [
            (name, entry)
            for name, entry in sorted(marketplaces.items(), key=lambda item: item[0])
            if selected_marketplace is None or name == selected_marketplace
        ]
        try:
            for index, (marketplace, marketplace_entry) in enumerate(matched_marketplaces):
                if index > 0:
                    print("", file=stdout)
                rendered = _render_plugin_table_for_marketplace(
                    codex_home,
                    marketplace,
                    marketplace_entry,
                    plugin_list,
                    stdout=stdout,
                ) or rendered
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        if not rendered:
            if selected_marketplace is not None:
                print(f"No plugins found in marketplace `{selected_marketplace}`.", file=stdout)
            else:
                print("No marketplace plugins found.", file=stdout)
            return 0
        return 0

    print(f"Unrecognized plugin subcommand: {subcommand}", file=stderr)
    return 64


def _plugin_help_text(command_args: tuple[str, ...]) -> str:
    positional = [arg for arg in command_args if not arg.startswith("-")]
    if not positional:
        return "\n".join(
            [
                "Manage Codex plugins.",
                "",
                "Usage: codex plugin <COMMAND>",
                "",
                "Commands:",
                "  list                         List configured plugins.",
                "  add <PLUGIN>[@<MARKETPLACE>] Add a plugin.",
                "  remove <PLUGIN>[@<MARKETPLACE>]",
                "                               Remove a plugin.",
                "  marketplace <COMMAND>        Manage plugin marketplaces.",
                "",
                "Options:",
                "  -h, --help                   Show this help message.",
            ]
        )

    subcommand = positional[0]
    if subcommand == "marketplace":
        if len(positional) == 1:
            return "\n".join(
                [
                    "Manage Codex plugin marketplaces.",
                    "",
                    "Usage: codex plugin marketplace <COMMAND>",
                    "",
                    "Commands:",
                    "  list                         List configured marketplaces.",
                    "  add <SOURCE> [--ref REF] [--sparse PATH...]",
                    "                               Add a marketplace from a source.",
                    "  upgrade [MARKETPLACE]        Upgrade one or all marketplaces.",
                    "  remove <MARKETPLACE>         Remove a marketplace.",
                    "",
                    "Options:",
                    "  -h, --help                   Show this help message.",
                ]
            )
        market_subcommand = positional[1]
        if market_subcommand == "add":
            return "\n".join(
                [
                    "Add a Codex plugin marketplace.",
                    "",
                    "Usage: codex plugin marketplace add <SOURCE> [--ref REF] [--sparse PATH...]",
                    "",
                    "Arguments:",
                    "  SOURCE        Local path, repository, or URL for the marketplace source.",
                    "",
                    "Options:",
                    "      --ref REF          Git ref to use for a git marketplace source.",
                    "      --sparse PATH...   Sparse checkout path(s) for git marketplace sources.",
                    "  -h, --help             Show this help message.",
                ]
            )
        if market_subcommand == "list":
            return "Usage: codex plugin marketplace list [--help]"
        if market_subcommand == "upgrade":
            return "Usage: codex plugin marketplace upgrade [MARKETPLACE] [--help]"
        if market_subcommand == "remove":
            return "Usage: codex plugin marketplace remove <MARKETPLACE> [--help]"
        return "Usage: codex plugin marketplace <COMMAND>"

    if subcommand in {"add", "remove"}:
        return "\n".join(
            [
                f"{'Add' if subcommand == 'add' else 'Remove'} a Codex plugin.",
                "",
                f"Usage: codex plugin {subcommand} <PLUGIN>[@<MARKETPLACE>] [--marketplace MARKETPLACE]",
                "",
                "Arguments:",
                "  PLUGIN        Plugin id or name, optionally suffixed with @marketplace.",
                "",
                "Options:",
                "  -m, --marketplace MARKETPLACE",
                "                Select the marketplace explicitly.",
                "  -h, --help    Show this help message.",
            ]
        )
    if subcommand == "list":
        return "\n".join(
            [
                "List configured Codex plugins.",
                "",
                "Usage: codex plugin list [--marketplace MARKETPLACE]",
                "",
                "Options:",
                "  -m, --marketplace MARKETPLACE",
                "                Filter plugins by marketplace.",
                "  -h, --help    Show this help message.",
            ]
        )

    return "Usage: codex plugin"


def _mcp_help_text(command_args: tuple[str, ...]) -> str:
    positional = [arg for arg in command_args if not arg.startswith("-")]
    if not positional:
        return "\n".join(
            [
                "Manage external MCP servers for Codex.",
                "",
                "Usage: codex mcp <COMMAND>",
                "",
                "Commands:",
                "  list [--json]                         List configured MCP servers.",
                "  get <NAME> [--json]                   Show one MCP server.",
                "  add <NAME> --url URL                  Add an HTTP MCP server.",
                "  add <NAME> [--env KEY=VALUE] -- CMD   Add a command MCP server.",
                "  remove <NAME>                         Remove an MCP server.",
                "  login <NAME> [--scopes SCOPES]        Log in to an MCP server.",
                "  logout <NAME>                         Log out from an MCP server.",
                "",
                "Options:",
                "  -h, --help                            Show this help message.",
            ]
        )

    subcommand = positional[0]
    if subcommand == "list":
        return "Usage: codex mcp list [--json] [--help]"
    if subcommand == "get":
        return "Usage: codex mcp get <NAME> [--json] [--help]"
    if subcommand == "remove":
        return "Usage: codex mcp remove <NAME> [--help]"
    if subcommand == "login":
        return "Usage: codex mcp login <NAME> [--scopes SCOPES] [--help]"
    if subcommand == "logout":
        return "Usage: codex mcp logout <NAME> [--help]"
    if subcommand == "add":
        return "\n".join(
            [
                "Add an external MCP server.",
                "",
                "Usage: codex mcp add <NAME> --url URL [OPTIONS]",
                "       codex mcp add <NAME> [--env KEY=VALUE] -- COMMAND [ARGS...]",
                "",
                "Arguments:",
                "  NAME                         MCP server name.",
                "  COMMAND [ARGS...]            Command-mode server process.",
                "",
                "Options:",
                "      --url URL                 HTTP MCP server URL.",
                "      --env KEY=VALUE           Environment variable for command mode.",
                "      --bearer-token-env-var ENV",
                "                                Environment variable containing a bearer token.",
                "      --oauth-client-id ID      OAuth client id.",
                "      --oauth-resource RESOURCE OAuth resource identifier.",
                "  -h, --help                    Show this help message.",
            ]
        )
    return "Usage: codex mcp <COMMAND>"


def _run_app_server_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not command_args:
        print(_app_server_help_text(()), file=stdout)
        return 0

    args = _app_server_command_args_for_help(command_args)
    if not args:
        print(_app_server_help_text(()), file=stdout)
        return 0

    try:
        codex_home = _safe_codex_home()
        state_path = codex_home / _APP_SERVER_STATE_FILE
        state = _read_json_state(state_path)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    daemon_state = state.get("daemon", {})
    if not isinstance(daemon_state, MutableMapping):
        daemon_state = {}

    if args[0] == "daemon":
        if len(args) < 2:
            print(_app_server_help_text(("daemon",)), file=stdout)
            return 2
        daemon_command = args[1]
        default_socket_path = _app_server_control_socket_path(codex_home)
        daemon_state.setdefault("socket_path", default_socket_path)
        daemon_state.setdefault("managed_codex_path", sys.executable)
        daemon_state.setdefault("managed_codex_version", __version__)
        daemon_state.setdefault("cli_version", __version__)
        daemon_state.setdefault("app_server_version", __version__)
        daemon_state.setdefault("backend", "pid")
        if daemon_command == "bootstrap":
            daemon_state.update(
                {
                    "bootstrap": True,
                    "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
                    "running": True,
                    "command": "bootstrap",
                    "status": "bootstrapped",
                    "pid": os.getpid(),
                    "backend": "pid",
                    "remote_control_enabled": "--remote-control" in args[2:],
                    "auto_update_enabled": True,
                    "socket_path": default_socket_path,
                }
            )
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_bootstrap_payload(
                        daemon_state,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "start":
            was_running = bool(daemon_state.get("running"))
            status = "alreadyRunning" if was_running else "started"
            daemon_state.update(
                {
                    "running": True,
                    "command": "start",
                    "status": status,
                    "pid": os.getpid() if not was_running else daemon_state.get("pid"),
                    "backend": "pid",
                    "socket_path": default_socket_path,
                    "remote_control_enabled": bool(daemon_state.get("remote_control_enabled")),
                }
            )
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_lifecycle_payload(
                        daemon_state,
                        status=status,
                        fallback_socket_path=default_socket_path,
                        include_pid=not was_running,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "restart":
            daemon_state.update(
                {
                    "running": True,
                    "command": "restart",
                    "status": "restarted",
                    "pid": os.getpid(),
                    "backend": "pid",
                    "socket_path": default_socket_path,
                    "remote_control_enabled": bool(daemon_state.get("remote_control_enabled")),
                }
            )
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_lifecycle_payload(
                        daemon_state,
                        status="restarted",
                        fallback_socket_path=default_socket_path,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "enable-remote-control":
            was_enabled = bool(daemon_state.get("remote_control_enabled"))
            daemon_state["remote_control_enabled"] = True
            status = (
                "alreadyEnabled"
                if was_enabled
                else "enabled"
            )
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_remote_control_output_payload(
                        daemon_state,
                        status=status,
                        mode=True,
                        fallback_socket_path=default_socket_path,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "disable-remote-control":
            was_enabled = bool(daemon_state.get("remote_control_enabled"))
            daemon_state["remote_control_enabled"] = False
            status = (
                "alreadyDisabled"
                if not was_enabled
                else "disabled"
            )
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_remote_control_output_payload(
                        daemon_state,
                        status=status,
                        mode=False,
                        fallback_socket_path=default_socket_path,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "stop":
            was_running = bool(daemon_state.get("running"))
            new_status = "stopped" if was_running else "notRunning"
            daemon_state.update(
                {
                    "command": "stop",
                    "status": new_status,
                    "running": was_running and False,
                    "backend": daemon_state.get("backend") if was_running else None,
                }
            )
            daemon_state.pop("pid", None)
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_lifecycle_payload(
                        daemon_state,
                        status=new_status,
                        fallback_socket_path=default_socket_path,
                        include_pid=False,
                        include_backend=was_running,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "version":
            is_running = bool(daemon_state.get("running"))
            if not is_running:
                print("app-server daemon is not running.", file=stderr)
                return 2

            daemon_state["command"] = "version"
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            print(
                json.dumps(
                    _app_server_lifecycle_payload(
                        daemon_state,
                        status="running",
                        fallback_socket_path=default_socket_path,
                        include_pid=False,
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=stdout,
            )
            return 0
        if daemon_command == "pid-update-loop":
            daemon_state["pid_update_loop"] = True
            daemon_state["pid_update_loop_at"] = datetime.now(timezone.utc).isoformat()
            state["daemon"] = daemon_state
            try:
                _write_json_state(state_path, state)
            except OSError as exc:
                print(f"pycodex: failed to write app-server state: {exc}", file=stderr)
                return 2
            return 0

        print(f"Unknown app-server daemon subcommand: {daemon_command}", file=stderr)
        return 64

    if args[0] == "proxy":
        sock = None
        index = 1
        while index < len(args):
            if args[index] == "--sock":
                sock = args[index + 1]
                break
            index += 1
        if sock is None:
            print("app-server proxy running with default socket.", file=stdout)
        else:
            print(f"app-server proxy running on {sock}.", file=stdout)
        return 0

    if args[0] in {"generate-ts", "generate-json-schema", "generate-internal-json-schema"}:
        out = _parse_app_server_out_argument(args[1:])
        if out is None:
            print(f"app-server {args[0]} requires --out.", file=stderr)
            return 2
        out_path = Path(out)
        if args[0] == "generate-ts":
            content = (
                "// Generated by pycodex.\n"
                "export interface AppServerManifest {\n"
                '  version: string;\n'
                "}\n"
            )
        elif args[0] == "generate-json-schema":
            content = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, indent=2)
        else:
            content = json.dumps({"app_server": {"internal": True}}, indent=2)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"pycodex: failed to write {out_path}: {exc}", file=stderr)
            return 2
        print(f"Wrote generated output to {out_path}.", file=stdout)
        return 0

    print(_app_server_help_text(args), file=stdout)
    return 0


def _run_remote_control_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    is_json = "--json" in command_args
    args = tuple(arg for arg in command_args if arg != "--json")

    if args:
        subcommand = args[0]
        if subcommand == "start":
            return _run_remote_control_start(
                mode="daemon",
                json_output=is_json,
                stdout=stdout,
                stderr=stderr,
            )
        if subcommand == "stop":
            return _run_remote_control_stop(json_output=is_json, stdout=stdout, stderr=stderr)
        print(f"pycodex: unrecognized remote-control subcommand: {subcommand}", file=stderr)
        return 2

    return _run_remote_control_start(
        mode="foreground",
        json_output=is_json,
        stdout=stdout,
        stderr=stderr,
    )


def _run_remote_control_start(
    *,
    mode: str,
    json_output: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    start_message = (
        "Starting app-server with remote control enabled..."
        if mode == "foreground"
        else "Starting app-server daemon with remote control enabled..."
    )
    if not json_output:
        print(start_message, file=stdout)

    try:
        codex_home = _safe_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    state_path = codex_home / _APP_SERVER_STATE_FILE
    try:
        state = _read_json_state(state_path)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    daemon_state = state.get("daemon")
    if not isinstance(daemon_state, MutableMapping):
        daemon_state = {}

    remote_control = state.get("remote_control")
    if not isinstance(remote_control, MutableMapping):
        remote_control = {}

    server_name = remote_control.get("server_name")
    if not isinstance(server_name, str) or not server_name:
        server_name = _remote_control_server_name()
    environment_id = remote_control.get("environment_id")
    if not isinstance(environment_id, str) or not environment_id:
        environment_id = f"{socket.gethostname()}:{os.getpid()}"

    status = "connected"
    socket_path = remote_control.get("socket_path")
    if not isinstance(socket_path, str) or not socket_path:
        socket_path = daemon_state.get("socket_path")
    if not isinstance(socket_path, str) or not socket_path:
        socket_path = str(state_path)

    if mode == "daemon":
        managed_codex_path = daemon_state.get("managed_codex_path")
        if not isinstance(managed_codex_path, str) or not managed_codex_path:
            managed_codex_path = sys.executable
        managed_codex_version = daemon_state.get("managed_codex_version")
        if not isinstance(managed_codex_version, str) or not managed_codex_version:
            managed_codex_version = __version__
        app_server_version = daemon_state.get("app_server_version")
        if not isinstance(app_server_version, str) or not app_server_version:
            app_server_version = __version__
        managed_cli_version = daemon_state.get("cli_version")
        if not isinstance(managed_cli_version, str) or not managed_cli_version:
            managed_cli_version = __version__

        daemon_state.update(
            {
                "running": True,
                "command": "start",
                "status": "started",
                "pid": os.getpid(),
                "remote_control_enabled": True,
                "socket_path": socket_path,
                "managed_codex_path": managed_codex_path,
                "managed_codex_version": managed_codex_version,
                "app_server_version": app_server_version,
                "cli_version": managed_cli_version,
                "backend": "pid",
            }
        )

    remote_control.update(
        {
            "mode": mode,
            "status": status,
            "server_name": server_name,
            "environment_id": environment_id,
            "socket_path": socket_path,
            "timed_out": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
    )
    state["daemon"] = daemon_state
    state["remote_control"] = remote_control

    try:
        _write_json_state(state_path, state)
    except OSError as exc:
        print(f"pycodex: failed to write remote-control state: {exc}", file=stderr)
        return 2

    if json_output:
        payload = _remote_control_start_json_payload(
            remote_control,
            mode=mode,
            daemon_state=daemon_state,
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=stdout)
        return 0

    for line in _remote_control_human_lines(remote_control, mode):
        print(line, file=stdout)
    return 0


def _run_remote_control_stop(
    *,
    json_output: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        codex_home = _safe_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    state_path = codex_home / _APP_SERVER_STATE_FILE
    try:
        state = _read_json_state(state_path)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    daemon_state = state.get("daemon")
    if not isinstance(daemon_state, MutableMapping):
        daemon_state = {}

    remote_control = state.get("remote_control")
    if not isinstance(remote_control, MutableMapping):
        remote_control = {}

    status = remote_control.get("status")
    is_daemon_running = bool(daemon_state.get("running"))
    was_running = status in {"connected", "connecting", "running"} or is_daemon_running
    if was_running:
        daemon_state.update(
            {
                "running": False,
                "command": "stop",
                "status": "stopped",
                "remote_control_enabled": False,
            }
        )
        remote_control.update(
            {
                "status": "disabled",
                "mode": remote_control.get("mode", "daemon"),
                "server_name": _remote_control_server_name(),
                "environment_id": remote_control.get("environment_id"),
                "timed_out": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    else:
        daemon_state.setdefault("remote_control_enabled", False)
        remote_control.update(
            {
                "status": "disabled",
                "mode": remote_control.get("mode", "daemon"),
            }
        )

    state["daemon"] = daemon_state
    state["remote_control"] = remote_control

    try:
        _write_json_state(state_path, state)
    except OSError as exc:
        print(f"pycodex: failed to write remote-control state: {exc}", file=stderr)
        return 2

    if json_output:
        print(
            json.dumps(
                _remote_control_stop_json_payload(
                    was_running=was_running,
                    daemon_state=daemon_state,
                    fallback_socket_path=str(state_path),
                ),
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=stdout,
        )
        return 0

    print("Remote control stopped." if was_running else "Remote control is not running.", file=stdout)
    return 0


def _app_server_control_socket_path(codex_home: Path) -> str:
    return str(
        codex_home
        / _APP_SERVER_CONTROL_SOCKET_DIR
        / _APP_SERVER_CONTROL_SOCKET_FILE
    )


def _app_server_lifecycle_payload(
    daemon_state: Mapping[str, object],
    *,
    status: str,
    fallback_socket_path: str,
    include_pid: bool = True,
    include_backend: bool = True,
) -> dict[str, object]:
    normalized_status = status
    if normalized_status not in {
        "alreadyRunning",
        "started",
        "restarted",
        "stopped",
        "notRunning",
        "running",
        "bootstrapped",
    }:
        normalized_status = "notRunning"

    payload: dict[str, object] = {
        "status": normalized_status,
        "managedCodexPath": _as_str(
            daemon_state.get("managed_codex_path"),
            fallback=sys.executable,
        ),
        "socketPath": _as_str(
            daemon_state.get("socket_path"),
            fallback=fallback_socket_path,
        ),
    }

    managed_codex_version = _as_optional_str(daemon_state.get("managed_codex_version"))
    if managed_codex_version is not None:
        payload["managedCodexVersion"] = managed_codex_version

    cli_version = _as_optional_str(daemon_state.get("cli_version"), fallback=__version__)
    if cli_version is not None:
        payload["cliVersion"] = cli_version

    app_server_version = _as_optional_str(daemon_state.get("app_server_version"))
    if app_server_version is not None:
        payload["appServerVersion"] = app_server_version

    if include_backend:
        backend = _as_optional_str(daemon_state.get("backend"), fallback="pid")
        if backend is not None:
            payload["backend"] = backend

    pid = daemon_state.get("pid")
    if include_pid and isinstance(pid, int) and normalized_status != "notRunning":
        payload["pid"] = pid

    return payload


def _app_server_bootstrap_payload(daemon_state: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "bootstrapped",
        "backend": "pid",
        "autoUpdateEnabled": True,
        "remoteControlEnabled": bool(daemon_state.get("remote_control_enabled")),
        "managedCodexPath": _as_str(
            daemon_state.get("managed_codex_path"),
            fallback=sys.executable,
        ),
        "socketPath": _as_str(
            daemon_state.get("socket_path"),
            fallback=_app_server_control_socket_path(
                _safe_codex_home(),
            ),
        ),
        "cliVersion": _as_str(
            daemon_state.get("cli_version"),
            fallback=__version__,
        ),
    }

    managed_codex_version = _as_optional_str(daemon_state.get("managed_codex_version"))
    if managed_codex_version is not None:
        payload["managedCodexVersion"] = managed_codex_version

    app_server_version = _as_optional_str(daemon_state.get("app_server_version"))
    if app_server_version is not None:
        payload["appServerVersion"] = app_server_version

    return payload


def _app_server_remote_control_output_payload(
    daemon_state: Mapping[str, object],
    *,
    status: str,
    mode: bool,
    fallback_socket_path: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "remoteControlEnabled": mode,
        "socketPath": _as_str(
            daemon_state.get("socket_path"),
            fallback=fallback_socket_path,
        ),
        "cliVersion": _as_optional_str(
            daemon_state.get("cli_version"),
            fallback=__version__,
        ),
    }

    if bool(daemon_state.get("running")):
        payload["backend"] = _as_optional_str(daemon_state.get("backend"), fallback="pid")
        app_server_version = _as_optional_str(daemon_state.get("app_server_version"))
        if app_server_version is not None:
            payload["appServerVersion"] = app_server_version

    return payload


def _remote_control_server_name() -> str:
    return socket.gethostname() or "codex-remote-control"


def _as_str(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _remote_control_start_json_payload(
    remote_control: Mapping[str, object],
    mode: str,
    daemon_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    server_name = remote_control.get("server_name")
    if not isinstance(server_name, str) or not server_name:
        server_name = _remote_control_server_name()
    environment_id = remote_control.get("environment_id")
    if not isinstance(environment_id, str) or not environment_id:
        environment_id = f"{socket.gethostname()}:{os.getpid()}"

    socket_path = remote_control.get("socket_path")
    if not isinstance(socket_path, str):
        socket_path = remote_control.get("socketPath")
    if not isinstance(socket_path, str):
        socket_path = ""

    payload: dict[str, object] = {
        "mode": "foreground" if mode == "foreground" else "daemon",
        "status": remote_control.get("status", "connected"),
        "serverName": server_name,
        "environmentId": environment_id,
        "timedOut": bool(remote_control.get("timed_out", False)),
    }
    if mode == "daemon":
        payload["daemon"] = _remote_control_lifecycle_payload(
            daemon_state or {},
            status="started",
            fallback_pid=os.getpid(),
            fallback_socket_path=socket_path,
            include_app_server_version=True,
        )
    return payload


def _remote_control_stop_json_payload(
    *,
    was_running: bool,
    daemon_state: Mapping[str, object],
    fallback_socket_path: str,
) -> dict[str, object]:
    return {
        "status": "stopped" if was_running else "notRunning",
        "daemon": _remote_control_lifecycle_payload(
            daemon_state,
            status="stopped" if was_running else "notRunning",
            fallback_pid=daemon_state.get("pid"),
            fallback_socket_path=fallback_socket_path,
            default_status="notRunning",
            include_pid=was_running,
            include_backend=was_running,
            include_cli_version=True,
            include_app_server_version=False,
        ),
    }


def _remote_control_lifecycle_payload(
    daemon_state: Mapping[str, object],
    *,
    status: str,
    fallback_pid: object,
    fallback_socket_path: str,
    default_status: str | None = None,
    include_pid: bool = True,
    include_backend: bool = True,
    include_cli_version: bool = True,
    include_app_server_version: bool = False,
) -> dict[str, object]:
    normalized_status = status
    if normalized_status not in {"alreadyRunning", "started", "restarted", "stopped", "notRunning", "running"}:
        normalized_status = default_status or "notRunning"

    payload: dict[str, object] = {
        "status": normalized_status,
        "managedCodexPath": _as_str(daemon_state.get("managed_codex_path"), fallback=sys.executable),
        "socketPath": _as_str(daemon_state.get("socket_path"), fallback=fallback_socket_path),
    }
    managed_codex_version = _as_optional_str(daemon_state.get("managed_codex_version"))
    if managed_codex_version is not None:
        payload["managedCodexVersion"] = managed_codex_version

    if include_cli_version:
        cli_version = _as_optional_str(daemon_state.get("cli_version"), fallback=__version__)
        if cli_version is not None:
            payload["cliVersion"] = cli_version

    if include_app_server_version:
        app_server_version = _as_optional_str(daemon_state.get("app_server_version"))
        if app_server_version is not None:
            payload["appServerVersion"] = app_server_version

    if include_backend:
        backend = _as_optional_str(daemon_state.get("backend"), fallback="pid")
        if backend is not None:
            payload["backend"] = backend

    pid = fallback_pid if isinstance(fallback_pid, int) else daemon_state.get("pid")
    if include_pid and isinstance(pid, int):
        payload["pid"] = pid

    if include_pid and normalized_status == "notRunning":
        payload.pop("pid", None)

    return payload


def _as_optional_str(value: object, fallback: str | None = None) -> str | None:
    if isinstance(value, str) and value:
        return value
    return fallback


def _remote_control_human_lines(
    remote_control: Mapping[str, object],
    mode: str,
) -> list[str]:
    server_name = remote_control.get("server_name")
    if not isinstance(server_name, str) or not server_name:
        server_name = _remote_control_server_name()

    lines = [_remote_control_start_human_message(remote_control.get("status"), server_name)]

    if mode == "foreground":
        lines.append("Press Ctrl-C to stop.")
    return lines


def _remote_control_start_human_message(status: object, server_name: str) -> str:
    if status == "connecting":
        return f"Remote control is enabled on {server_name} and still connecting."
    if status == "errored":
        return f"Remote control is enabled on {server_name} but the connection is errored."
    if status == "disabled":
        return f"Remote control is disabled on {server_name}."
    return f"This machine is available for remote control as {server_name}."


def _unimplemented_command_help_text(command: str) -> str:
    return f"Usage: codex {command} [OPTIONS]"


def _exec_help_text() -> str:
    return "\n".join(
        [
            "Run Codex non-interactively.",
            "",
            "Usage: codex exec [OPTIONS] [PROMPT]",
            "       codex exec [OPTIONS] resume [OPTIONS] [SESSION_ID] [PROMPT]",
            "       codex exec [OPTIONS] review [OPTIONS] [PROMPT]",
            "",
            "Options:",
            "  -c, --config key=value      Override a configuration value.",
            "  -i, --image PATH            Attach an image to the initial prompt.",
            "      --output-schema PATH    Validate the final answer against a JSON schema.",
            "      --color <always|never|auto>",
            "                              Control colored human-readable output.",
            "      --json                  Emit JSON events.",
            "  -o, --output-last-message PATH",
            "                              Write the final assistant message to a file.",
            "  -m, --model MODEL           Override the model.",
            "      --oss                   Use a local OSS provider preset.",
            "      --local-provider ID     Select a local provider.",
            "  -p, --profile PROFILE       Select a config profile.",
            "  -s, --sandbox MODE          Override sandbox mode.",
            "  -C, --cd DIR                Set the working directory.",
            "      --add-dir DIR           Add another writable/readable directory.",
            "      --skip-git-repo-check   Allow running outside a Git repository.",
            "      --ephemeral             Do not persist the session.",
            "      --ignore-user-config    Ignore user config.",
            "      --ignore-rules          Ignore repository/user instructions.",
            "      --full-auto             Deprecated alias for workspace-write behavior.",
            "      --dangerously-bypass-approvals-and-sandbox",
            "                              Disable approval and sandbox protections.",
            "      --dangerously-bypass-hook-trust",
            "                              Skip hook trust checks.",
            "  -h, --help                  Show this help message.",
            "",
            "Subcommands:",
            "  resume      Resume a previous session.",
            "  review      Run a code review through the exec pipeline.",
        ]
    )


def _exec_help_text_for_args(command_args: tuple[str, ...]) -> str:
    subcommand = _first_non_option_arg(command_args)
    if subcommand == "resume":
        return _exec_resume_help_text()
    if subcommand == "review":
        return _exec_review_help_text()
    return _exec_help_text()


def _exec_resume_help_text() -> str:
    return "\n".join(
        [
            "Resume a previous Codex session non-interactively.",
            "",
            "Usage: codex exec resume [OPTIONS] [SESSION_ID] [PROMPT]",
            "",
            "Arguments:",
            "  SESSION_ID       Session/thread id to resume. Omit with --last to resume the most recent session.",
            "  PROMPT           Optional prompt to send after resuming.",
            "",
            "Resume options:",
            "      --last       Resume the most recent session.",
            "      --all        Include all sessions when selecting a session.",
            "  -i, --image PATH Attach an image to the resumed turn.",
            "",
            "Shared exec options:",
            "  -c, --config key=value      Override a configuration value.",
            "      --json                  Emit JSON events.",
            "  -o, --output-last-message PATH",
            "                              Write the final assistant message to a file.",
            "  -m, --model MODEL           Override the model.",
            "      --skip-git-repo-check   Allow running outside a Git repository.",
            "      --ephemeral             Do not persist the session.",
            "      --ignore-user-config    Ignore user config.",
            "      --ignore-rules          Ignore repository/user instructions.",
            "  -h, --help                  Show this help message.",
        ]
    )


def _exec_review_help_text() -> str:
    return "\n".join(
        [
            "Run a code review through the exec pipeline.",
            "",
            "Usage: codex exec review [OPTIONS] [PROMPT]",
            "",
            "Review target options:",
            "      --uncommitted           Review uncommitted changes.",
            "      --base REF              Review changes relative to a base ref.",
            "      --commit SHA            Review a specific commit.",
            "      --title TITLE           Title for the commit review; requires --commit.",
            "",
            "Shared exec options:",
            "  -c, --config key=value      Override a configuration value.",
            "      --json                  Emit JSON events.",
            "  -o, --output-last-message PATH",
            "                              Write the final assistant message to a file.",
            "  -m, --model MODEL           Override the model.",
            "      --skip-git-repo-check   Allow running outside a Git repository.",
            "      --ephemeral             Do not persist the session.",
            "      --ignore-user-config    Ignore user config.",
            "      --ignore-rules          Ignore repository/user instructions.",
            "  -h, --help                  Show this help message.",
        ]
    )


def _review_help_text() -> str:
    return "\n".join(
        [
            "Run a code review non-interactively.",
            "",
            "Usage: codex review [OPTIONS] [PROMPT]",
            "",
            "Review target options:",
            "      --uncommitted           Review uncommitted changes.",
            "      --base REF              Review changes relative to a base ref.",
            "      --commit SHA            Review a specific commit.",
            "      --title TITLE           Title for the commit review; requires --commit.",
            "",
            "Shared exec options:",
            "  -c, --config key=value      Override a configuration value.",
            "      --output-schema PATH    Validate the final answer against a JSON schema.",
            "      --json                  Emit JSON events.",
            "  -o, --output-last-message PATH",
            "                              Write the final assistant message to a file.",
            "  -m, --model MODEL           Override the model.",
            "      --skip-git-repo-check   Allow running outside a Git repository.",
            "      --ephemeral             Do not persist the session.",
            "      --ignore-user-config    Ignore user config.",
            "      --ignore-rules          Ignore repository/user instructions.",
            "      --dangerously-bypass-approvals-and-sandbox",
            "                              Disable approval and sandbox protections.",
            "      --dangerously-bypass-hook-trust",
            "                              Skip hook trust checks.",
            "  -h, --help                  Show this help message.",
        ]
    )


def _features_help_text() -> str:
    return "\n".join(
        [
            "Inspect and update Codex feature flags.",
            "",
            "Usage: codex features <COMMAND>",
            "",
            "Commands:",
            "  list               List known feature flags, stages, and enabled state.",
            "  enable FEATURE     Enable a feature in config.toml.",
            "  disable FEATURE    Disable a feature in config.toml.",
            "",
            "Options:",
            "  -h, --help         Show this help message.",
        ]
    )


def _apply_help_text() -> str:
    return "\n".join(
        [
            "Apply the latest diff produced by a Codex Cloud task to the local working tree.",
            "",
            "Usage: codex apply <TASK_ID>",
            "",
            "Arguments:",
            "  TASK_ID        Codex Cloud task id whose latest available diff should be applied.",
            "",
            "Options:",
            "  -h, --help     Show this help message.",
            "",
            "This command fetches the task, selects the latest available diff, and applies it with git apply.",
        ]
    )


def _resume_help_text() -> str:
    return "\n".join(
        [
            "Resume a previous interactive Codex session.",
            "",
            "Usage: codex resume [OPTIONS] [SESSION_ID] [PROMPT]",
            "",
            "Arguments:",
            "  SESSION_ID       Session/thread id to resume. Omit with --last to resume the most recent session.",
            "  PROMPT           Optional prompt to send after resuming.",
            "",
            "Options:",
            "      --last       Resume the most recent session.",
            "      --all        Show all sessions when selecting a session.",
            "  -i, --image PATH Attach an image to the resumed turn.",
            "  -h, --help       Show this help message.",
        ]
    )


def _fork_help_text() -> str:
    return "\n".join(
        [
            "Fork a previous interactive Codex session into a new session.",
            "",
            "Usage: codex fork [OPTIONS] [SESSION_ID] [PROMPT]",
            "",
            "Arguments:",
            "  SESSION_ID       Session/thread id to fork. Omit it to choose interactively.",
            "  PROMPT           Optional prompt to send after forking.",
            "",
            "Options:",
            "      --all        Show all sessions when selecting a session.",
            "  -i, --image PATH Attach an image to the forked turn.",
            "  -h, --help       Show this help message.",
        ]
    )


def _read_responses_api_auth_header(
    stdin: object | None,
    *,
    stderr: TextIO,
) -> str:
    del stderr
    try:
        return read_auth_header_for_main(stdin)
    except ResponsesApiProxyError as exc:
        message = str(exc)
        if "must be provided" in message:
            raise RuntimeError("No API key provided via stdin.") from exc
        raise RuntimeError(message) from exc


def _run_responses_api_proxy(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
) -> int:
    return run_responses_api_proxy_main(
        command_args,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
    )


def _run_stdio_to_uds(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
) -> int:
    if any(arg in {"-h", "--help"} for arg in command_args):
        print(_unimplemented_command_help_text("stdio-to-uds"), file=stdout)
        return 0

    if not command_args:
        print("failed to connect to socket: missing socket path.", file=stderr)
        return 2

    if not hasattr(socket, "AF_UNIX"):
        print("Unix domain sockets are not supported on this platform.", file=stderr)
        return 2

    socket_path = command_args[0]

    try:
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.connect(socket_path)
    except OSError as exc:
        print(f"failed to connect to socket at {socket_path}: {exc}", file=stderr)
        return 2

    if stdin is None:
        input_stream = sys.stdin
    elif isinstance(stdin, bytes):
        input_stream = io.BytesIO(stdin)
    elif isinstance(stdin, str):
        input_stream = io.BytesIO(stdin.encode("utf-8"))
    else:
        input_stream = stdin

    stdin_obj = input_stream.buffer if hasattr(input_stream, "buffer") else input_stream
    stdout_obj = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout

    exceptions: list[BaseException] = []

    def _copy_stdin_to_socket() -> None:
        try:
            while True:
                chunk = stdin_obj.read(8192)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                if chunk:
                    stream.sendall(chunk)
            try:
                stream.shutdown(socket.SHUT_WR)
            except OSError as exc:
                if exc.errno != errno.ENOTCONN:
                    raise
        except BaseException as exc:
            exceptions.append(exc)

    def _copy_socket_to_stdout() -> None:
        try:
            while True:
                chunk = stream.recv(8192)
                if not chunk:
                    break
                stdout_obj.write(chunk)
                stdout_obj.flush()
        except BaseException as exc:
            exceptions.append(exc)

    stdin_thread = threading.Thread(target=_copy_stdin_to_socket)
    stdout_thread = threading.Thread(target=_copy_socket_to_stdout)
    stdin_thread.start()
    stdout_thread.start()
    stdin_thread.join()
    stdout_thread.join()

    stream.close()

    for exc in exceptions:
        print(f"failed to relay data between stdio and socket: {exc}", file=stderr)
        return 2

    return 0


def _run_unimplemented_management_command(command: str, *, stdout: TextIO, stderr: TextIO) -> int:
    del stdout
    if _fallback_enabled("PYCODEX_MANAGEMENT_COMMAND_FALLBACK"):
        print(
            f"pycodex: command '{command}' is recognized but not implemented yet; "
            "executed as fallback no-op in this Python port.",
            file=stderr,
        )
        return 0
    print(
        f"pycodex: command '{command}' is recognized but not implemented yet.",
        file=stderr,
    )
    return 64


_MCP_STUB_SESSION_COUNTER = 0
_MCP_STUB_SESSION_STORE: dict[str, dict[str, object]] = {}


def _next_stub_thread_id() -> str:
    global _MCP_STUB_SESSION_COUNTER
    _MCP_STUB_SESSION_COUNTER += 1
    return f"stub-{int(time.time() * 1000)}-{_MCP_STUB_SESSION_COUNTER}"


def _mcp_tool_schema() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return minimal codex and codex-reply tool schema definitions used by the stub runtime."""

    output_schema = {
        "type": "object",
        "properties": {
            "threadId": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["threadId", "content"],
        "type": "object",
    }

    codex_input_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prompt": {"type": "string", "description": "The *initial user prompt* to start the Codex conversation."},
            "model": {"type": "string", "description": "Optional override for the model name (e.g. 'gpt-5.3-codex', 'gpt-5.5')."},
            "cwd": {"type": "string", "description": "Working directory for the session. If relative, it is resolved against the server process's current working directory."},
            "approval-policy": {
                "type": "string",
                "description": "Approval policy for shell commands generated by the model: `untrusted`, `on-failure`, `on-request`, `never`.",
            },
            "sandbox": {
                "type": "string",
                "description": "Sandbox mode: `read-only`, `workspace-write`, or `danger-full-access`.",
            },
            "config": {"type": "object", "description": "Individual config settings that will override what is in CODEX_HOME/config.toml."},
            "base-instructions": {"type": "string", "description": "The set of instructions to use instead of the default ones."},
            "developer-instructions": {"type": "string", "description": "Developer instructions that should be injected as a developer role message."},
            "compact-prompt": {"type": "string", "description": "Prompt used when compacting the conversation."},
        },
        "required": ["prompt"],
    }

    codex_reply_input_schema = {
        "type": "object",
        "properties": {
            "threadId": {
                "type": "string",
                "description": "The thread id for this Codex session. This field is required, but we keep it optional here for backward compatibility for clients that still use conversationId.",
            },
            "conversationId": {"type": "string", "description": "DEPRECATED: use threadId instead."},
            "prompt": {"type": "string", "description": "The *next user prompt* to continue the Codex conversation."},
        },
        "required": ["prompt"],
        "additionalProperties": False,
    }

    codex_tool = {
        "name": "codex",
        "title": "Codex",
        "description": "Run a Codex session. Accepts configuration parameters matching the Codex Config struct.",
        "inputSchema": codex_input_schema,
        "outputSchema": output_schema,
    }
    codex_reply_tool = {
        "name": "codex-reply",
        "title": "Codex Reply",
        "description": "Continue a Codex conversation by providing the thread id and prompt.",
        "inputSchema": codex_reply_input_schema,
        "outputSchema": output_schema,
    }

    return [codex_tool, codex_reply_tool], [codex_input_schema, codex_reply_input_schema]


_MCP_STUB_CODEX_TOOL_ARGUMENT_KEYS = {
    "prompt",
    "model",
    "cwd",
    "approval-policy",
    "sandbox",
    "config",
    "base-instructions",
    "developer-instructions",
    "compact-prompt",
}


def _run_mcp_server_stdio_runtime(
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
) -> int:
    """Run a minimal MCP stdio loop using only the standard library."""

    if stdin is None:
        stdin_obj = sys.stdin
    elif isinstance(stdin, (bytes, bytearray)):
        stdin_obj = io.StringIO(stdin.decode("utf-8", errors="replace"))
    elif isinstance(stdin, str):
        stdin_obj = io.StringIO(stdin)
    else:
        stdin_obj = stdin

    if hasattr(stdin_obj, "buffer") and not isinstance(stdin_obj, io.TextIOBase):
        stdin_obj = io.TextIOWrapper(stdin_obj, encoding="utf-8", errors="replace")  # type: ignore[arg-type]

    if not hasattr(stdin_obj, "read"):
        print("pycodex: mcp-server requires a readable stdin object in runtime mode.", file=stderr)
        return 2

    initialized = False

    def _emit(message: dict[str, object]) -> None:
        try:
            stdout.write(json.dumps(message, ensure_ascii=False))
            stdout.write("\n")
            stdout.flush()
        except OSError as exc:
            print(f"failed to write mcp response: {exc}", file=stderr)

    def _error(request_id: object | None, method: str, code: int = -32601) -> None:
        _emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": code,
                    "message": f"method not found: {method}",
                    "data": {"method": method},
                },
            }
        )

    def _handle_initialize(request_id: object, params: dict[str, object] | None) -> None:
        nonlocal initialized
        if initialized:
            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32600,
                        "message": "initialize called more than once",
                    },
                }
            )
            return

        protocol_version = __version__
        if isinstance(params, dict):
            candidate = params.get("protocolVersion")
            if isinstance(candidate, str):
                protocol_version = candidate

        initialized = True
        _emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": True},
                    },
                    "serverInfo": {
                        "name": "codex-mcp-server",
                        "title": "Codex",
                        "version": __version__,
                        "user_agent": f"pycodex/{__version__}",
                    },
                },
            }
        )

    def _handle_tools_list(request_id: object) -> None:
        tools, _ = _mcp_tool_schema()

        _emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": tools,
                    "nextCursor": None,
                },
            }
        )

    def _handle_tools_call(request_id: object, params: dict[str, object] | None) -> None:
        if not isinstance(params, dict):
            _emit(
                {
                    "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": "Missing arguments for tools/call"}],
                    "isError": True,
                    },
                }
            )
            return

        name = params.get("name")
        arguments = params.get("arguments")

        if not isinstance(name, str):
            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Unknown tool '{name}'"}],
                        "isError": True,
                    },
                }
            )
            return

        if name == "codex":
            if not isinstance(arguments, dict):
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Missing arguments for codex tool-call; the `prompt` field is required.",
                                }
                            ],
                            "structuredContent": {
                                "threadId": "",
                                "content": "Missing arguments for codex tool-call; the `prompt` field is required.",
                            },
                            "isError": True,
                        },
                    }
                )
                return

            prompt = arguments.get("prompt")
            if not isinstance(prompt, str):
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Missing arguments for codex tool-call; the `prompt` field is required.",
                                }
                            ],
                            "structuredContent": {
                                "threadId": "",
                                "content": "Missing arguments for codex tool-call; the `prompt` field is required.",
                            },
                            "isError": True,
                        },
                    }
                )
                return

            unknown = sorted(str(key) for key in arguments if key not in _MCP_STUB_CODEX_TOOL_ARGUMENT_KEYS)
            if unknown:
                message = f"Failed to parse configuration for Codex tool: unknown field `{unknown[0]}`"
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{"type": "text", "text": message}],
                            "structuredContent": {
                                "threadId": "",
                                "content": message,
                            },
                            "isError": True,
                        },
                    }
                )
                return

            thread_id = _next_stub_thread_id()
            _MCP_STUB_SESSION_STORE[thread_id] = {
                "prompt": prompt,
                "model": arguments.get("model") if isinstance(arguments.get("model"), str) else None,
                "cwd": arguments.get("cwd") if isinstance(arguments.get("cwd"), str) else None,
                "approval_policy": arguments.get("approval-policy")
                if isinstance(arguments.get("approval-policy"), str)
                else None,
                "sandbox": arguments.get("sandbox")
                if isinstance(arguments.get("sandbox"), str)
                else None,
                "config": arguments.get("config") if isinstance(arguments.get("config"), dict) else None,
                "base_instructions": arguments.get("base-instructions")
                if isinstance(arguments.get("base-instructions"), str)
                else None,
                "developer_instructions": arguments.get("developer-instructions")
                if isinstance(arguments.get("developer-instructions"), str)
                else None,
                "compact_prompt": arguments.get("compact-prompt")
                if isinstance(arguments.get("compact-prompt"), str)
                else None,
                "reply_count": 0,
            }

            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Python MCP stub accepted codex prompt: {prompt[:80]}",
                            }
                        ],
                        "structuredContent": {
                            "threadId": thread_id,
                            "content": "stub started",
                        },
                        "isError": False,
                    },
                }
            )
            return

        if name == "codex-reply":
            if not isinstance(arguments, dict):
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                                }
                            ],
                            "structuredContent": {
                                "threadId": "",
                                "content": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                            },
                            "isError": True,
                        },
                    }
                )
                return

            thread_id = arguments.get("threadId") or arguments.get("conversationId")
            if not isinstance(thread_id, str):
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                                }
                            ],
                            "structuredContent": {
                                "threadId": "",
                                "content": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                            },
                            "isError": True,
                        },
                    }
                )
                return

            prompt = arguments.get("prompt")
            if not isinstance(prompt, str):
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                                }
                            ],
                            "structuredContent": {
                                "threadId": thread_id,
                                "content": "Missing arguments for codex-reply tool-call; the `thread_id` and `prompt` fields are required.",
                            },
                            "isError": True,
                        },
                    }
                )
                return

            session = _MCP_STUB_SESSION_STORE.get(thread_id)
            if session is None:
                _emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{
                                "type": "text",
                                "text": f"Session not found for thread_id: {thread_id}",
                            }],
                            "isError": True,
                        },
                    }
                )
                return

            session["reply_count"] = int(session.get("reply_count", 0)) + 1
            session["last_prompt"] = prompt

            _emit(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Python MCP stub continued thread {thread_id} with prompt: "
                                    f"{prompt[:80]}"
                                ),
                            }
                        ],
                        "structuredContent": {
                            "threadId": thread_id,
                            "content": "stub continuation accepted",
                            "replyCount": int(session.get("reply_count", 0)),
                        },
                        "isError": False,
                    },
                }
            )
            return

        _emit(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"Unknown tool '{name}'"}],
                    "isError": True,
                },
            }
        )

    for raw_line in stdin_obj:
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="replace")

        line = str(raw_line).strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"mcp-server received invalid JSON: {exc}", file=stderr)
            continue

        if not isinstance(request, dict):
            print("mcp-server received non-object JSON-RPC message", file=stderr)
            continue

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params")

        if not isinstance(method, str):
            continue

        if method == "initialize":
            if request_id is None:
                print("mcp-server initialize request missing id", file=stderr)
            else:
                _handle_initialize(request_id, params if isinstance(params, dict) else None)
            continue

        if method == "ping":
            if request_id is not None:
                _emit({"jsonrpc": "2.0", "id": request_id, "result": {}})
            continue

        if method == "initialized" or method.startswith("notifications/"):
            continue

        if request_id is None:
            # Notifications intentionally do not receive responses.
            continue

        if method == "tools/list":
            _handle_tools_list(request_id)
            continue

        if method == "tools/call":
            if isinstance(params, dict):
                _handle_tools_call(request_id, params)
            else:
                _error(request_id, "tools/call", code=-32602)
            continue

        _error(request_id, method)

    return 0


def _run_mcp_server_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
) -> int:
    del command_args
    if _fallback_enabled("PYCODEX_MCP_SERVER_RUNTIME"):
        print("pycodex: starting mcp-server stdio runtime.", file=stderr)
        return _run_mcp_server_stdio_runtime(
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
        )

    if _fallback_enabled("PYCODEX_MCP_SERVER_FALLBACK"):
        print("pycodex: starting mcp-server stub mode with stdio passthrough.", file=stderr)
        print("pycodex: MCP server behavior is a future work item in this Python port.", file=stderr)
        return 0

    print(
        "pycodex: command 'mcp-server' is not implemented in this Python port.",
        file=stderr,
    )
    print(
        "pycodex: launch the Rust `codex-mcp-server` binary for the full MCP stdio server.",
        file=stderr,
    )
    return 64


def _run_debug_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not command_args:
        print("pycodex: debug requires a subcommand.", file=stderr)
        return 2

    subcommand = command_args[0]
    if subcommand == "models":
        bundled = "--bundled" in command_args[1:]
        payload = {
            "models": ["gpt-5.3-codex", "gpt-5.5", "gpt-4o-mini"],
            "source": "bundled" if bundled else "online",
        }
        print(json.dumps(payload, indent=2), file=stdout)
        return 0

    if subcommand == "app-server":
        if len(command_args) < 3:
            print("debug app-server send-message-v2 requires USER_MESSAGE.", file=stderr)
            return 2
        message = command_args[2]
        print(
            json.dumps(
                {
                    "subcommand": "app-server send-message-v2",
                    "message": message,
                },
                indent=2,
            ),
            file=stdout,
        )
        return 0

    if subcommand == "prompt-input":
        prompt: str | None = None
        images: list[str] = []
        index = 1
        while index < len(command_args):
            arg = command_args[index]
            if arg in {"--image", "-i"}:
                images.append(command_args[index + 1])
                index += 2
                continue
            if prompt is None:
                prompt = arg
                index += 1
                continue
            print("Too many arguments for `debug prompt-input`.", file=stderr)
            return 2
        print(
            json.dumps(
                {
                    "prompt": prompt or "",
                    "images": images,
                },
                indent=2,
            ),
            file=stdout,
        )
        return 0

    if subcommand == "trace-reduce":
        output_path: str | None = None
        index = 1
        bundle_path = None
        while index < len(command_args):
            arg = command_args[index]
            if arg in {"--output", "-o"}:
                if index + 1 >= len(command_args):
                    print(f"Missing value for {arg}.", file=stderr)
                    return 2
                output_path = command_args[index + 1]
                index += 2
                continue
            bundle_path = arg
            index += 1
        if bundle_path is None:
            print("debug trace-reduce requires a trace bundle path.", file=stderr)
            return 2
        try:
            bundle = Path(bundle_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"debug trace-reduce failed: trace bundle not found: {bundle_path}", file=stderr)
            return 2
        except OSError as exc:
            print(f"debug trace-reduce failed: {exc}", file=stderr)
            return 2
        target = Path(output_path) if output_path is not None else Path(bundle_path).with_name("state.reduced.json")
        try:
            target.write_text(bundle, encoding="utf-8")
        except OSError as exc:
            print(f"debug trace-reduce failed to write output: {exc}", file=stderr)
            return 2
        print(str(target), file=stdout)
        return 0

    if subcommand == "clear-memories":
        print(
            "pycodex: debug clear-memories completed in stub mode (no local memory state was removed).",
            file=stdout,
        )
        return 0

    print(f"Unknown debug subcommand: {subcommand}", file=stderr)
    return 2


def _run_resume_or_fork_command(
    parsed: "ParsedCli",
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    command = parsed.command
    if command is None:
        return 2

    command_args = parsed.command_args

    session_id: str | None = None
    last = False
    include_all = False
    include_non_interactive = False
    index = 0
    while index < len(command_args):
        arg = command_args[index]
        if arg == "--last":
            last = True
            index += 1
            continue
        if arg == "--all":
            include_all = True
            index += 1
            continue
        if arg == "--include-non-interactive":
            include_non_interactive = True
            index += 1
            continue
        if arg.startswith("-"):
            print(f"Unknown argument for {command}: {arg}", file=stderr)
            return 2
        if session_id is None:
            session_id = arg
            index += 1
            continue
        print(f"Too many arguments for `{command}`.", file=stderr)
        return 2

    if command == "resume" and _fallback_enabled("PYCODEX_RESUME_EXEC_FALLBACK"):
        filtered_args = tuple(arg for arg in command_args if arg != "--include-non-interactive")
        return _run_noninteractive_exec(
            replace(
                parsed,
                command="resume",
                command_args=filtered_args,
                command_spec=COMMANDS_BY_NAME.get("resume"),
            ),
            stdout=stdout,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )

    if command == "fork" and _fallback_enabled("PYCODEX_FORK_EXEC_FALLBACK"):
        return _run_noninteractive_exec(
            replace(
                parsed,
                command="resume",
                command_args=command_args,
                command_spec=COMMANDS_BY_NAME.get("resume"),
            ),
            stdout=stdout,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )

    if command == "resume":
        print(
            f"pycodex: resume request parsed with session_id={session_id!r}, last={last}, "
            f"all={include_all}, include_non_interactive={include_non_interactive}.",
            file=stderr,
        )
    else:
        print(
            f"pycodex: fork request parsed with session_id={session_id!r}, last={last}, "
            f"all={include_all}.",
            file=stderr,
        )

    tui_parsed = _with_startup_session_options(
        parsed,
        action=command,
        session_id=session_id,
        last=last,
        show_all=include_all,
        include_non_interactive=include_non_interactive if command == "resume" else False,
    )
    return _run_tui(
        tui_parsed,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        stdin_is_terminal=stdin_is_terminal,
    )


def _with_startup_session_options(
    parsed: ParsedCli,
    *,
    action: str,
    session_id: str | None,
    last: bool,
    show_all: bool,
    include_non_interactive: bool,
) -> ParsedCli:
    """Mirror Rust ``finalize_resume_interactive`` / ``finalize_fork_interactive``.

    Rust converts ``codex resume`` and ``codex fork`` into a normal TUI launch
    with startup-session fields set on ``TuiCli``.  Python keeps the parsed
    top-level command for diagnostics, but stores the same launch intent in
    ``root_options`` so the TUI runtime can project the startup picker.
    """

    root_options = dict(parsed.root_options)
    if action == "fork":
        root_options.update(
            {
                "tui_startup_session_action": "fork",
                "tui_startup_session_picker": session_id is None and not last,
                "tui_startup_session_last": bool(last),
                "tui_startup_session_id": session_id,
                "tui_startup_session_show_all": bool(show_all),
                "tui_startup_session_include_non_interactive": False,
            }
        )
    else:
        root_options.update(
            {
                "tui_startup_session_action": "resume",
                "tui_startup_session_picker": session_id is None and not last,
                "tui_startup_session_last": bool(last),
                "tui_startup_session_id": session_id,
                "tui_startup_session_show_all": bool(show_all),
                "tui_startup_session_include_non_interactive": bool(include_non_interactive),
            }
        )
    return replace(parsed, root_options=root_options)


def _run_apply_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        task_id = _parse_cloud_task_id(command_args[0])
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2
    try:
        token = _cloud_auth_token()
        payload = _cloud_request_json(
            url=f"{_CLOUD_BASE_URL}/wham/tasks/{task_id}",
            method="GET",
            token=token,
        )
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    if not isinstance(payload, dict):
        print("pycodex: unexpected response format from cloud task endpoint.", file=stderr)
        return 2

    try:
        attempts = _collect_cloud_attempt_diffs(payload, token=token, task_id=task_id)
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2
    diff = _select_cloud_attempt_diff(attempts, None)
    if not diff:
        print(f"No diff available for task {task_id}.", file=stderr)
        return 1

    return _apply_task_diff_with_git(diff, stdout=stdout, stderr=stderr)


@dataclass(frozen=True)
class _ExecPolicyRule:
    pattern: tuple[str | tuple[str, ...], ...]
    decision: str
    justification: str | None = None


_RULE_DECISION_PRIORITY = {
    "allow": 0,
    "prompt": 1,
    "forbidden": 2,
}


def _normalize_execpolicy_source(source: str) -> str:
    normalized_tokens: list[tuple[int, str]] = []

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME:
            if token.string == "match":
                normalized_tokens.append((token.type, "__match"))
                continue
            if token.string == "not_match":
                normalized_tokens.append((token.type, "__not_match"))
                continue
        if token.type == tokenize.STRING:
            normalized_tokens.append((token.type, _normalize_execpolicy_string_token(token.string)))
            continue

        normalized_tokens.append((token.type, token.string))

    return tokenize.untokenize(normalized_tokens)


def _normalize_execpolicy_string_token(raw: str) -> str:
    try:
        ast.literal_eval(raw)
        return raw
    except (SyntaxError, ValueError):
        if "\\" not in raw:
            return raw
        return raw.replace("\\", "\\\\")


def _parse_execpolicy_decision(value: object, *, path: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"invalid decision in {path}: expected allow|prompt|forbidden")
    decision = value.lower()
    if decision not in _RULE_DECISION_PRIORITY:
        raise RuntimeError(f"invalid decision in {path}: expected allow|prompt|forbidden")
    return decision


def _parse_execpolicy_pattern_tokens(raw: object, *, path: str) -> tuple[str | tuple[str, ...], ...]:
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"invalid pattern in {path}: pattern must be a non-empty list")

    parsed: list[str | tuple[str, ...]] = []
    for token in raw:
        if isinstance(token, str):
            parsed.append(token)
            continue

        if isinstance(token, list):
            if not token or not all(isinstance(item, str) for item in token):
                raise RuntimeError(
                    f"invalid pattern token in {path}: alternatives must be a non-empty list of strings"
                )
            parsed.append(tuple(token))
            continue

        raise RuntimeError(f"invalid pattern token in {path}: {type(token)!r}")

    return tuple(parsed)


def _parse_execpolicy_example(raw: object, *, path: str, context: str) -> tuple[str, ...]:
    if isinstance(raw, str):
        if not raw:
            raise RuntimeError(f"invalid {context} example in {path}: example string cannot be empty")
        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            raise RuntimeError(f"invalid {context} example in {path}: {exc}")
        if not tokens:
            raise RuntimeError(f"invalid {context} example in {path}: example string cannot be empty")
        return tuple(tokens)

    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"invalid {context} example in {path}: example cannot be empty")
    if not all(isinstance(item, str) for item in raw):
        raise RuntimeError(f"invalid {context} example in {path}: example tokens must be strings")
    return tuple(raw)


def _parse_execpolicy_examples(raw: object, *, path: str, context: str) -> list[tuple[str, ...]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError(f"invalid {context} in {path}: expected list")
    return [_parse_execpolicy_example(item, path=path, context=context) for item in raw]


def _execpolicy_lookup_key(raw: str) -> str:
    if os.name == "nt":
        lowered = raw.lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if lowered.endswith(suffix):
                return lowered[: -len(suffix)]
        return lowered
    return raw


def _parse_execpolicy_host_executable(
    value: object,
    *,
    path: str,
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid host_executable in {path}: expected keyword arguments")

    name = value.get("name")
    paths = value.get("paths")
    if not isinstance(name, str) or not name:
        raise RuntimeError(f"invalid host_executable in {path}: name must be a non-empty string")
    if not isinstance(paths, list) or not paths:
        raise RuntimeError(
            f"invalid host_executable in {path}: paths must be a non-empty list of absolute paths"
        )

    key = _execpolicy_lookup_key(name)
    basename = os.path.basename(name)
    if basename != name:
        raise RuntimeError(
            f"invalid host_executable name in {path}: host_executable name must be a bare executable name"
        )

    normalized_paths: list[str] = []
    for raw_path in paths:
        if not isinstance(raw_path, str) or not raw_path:
            raise RuntimeError(f"invalid host_executable path in {path}: each path must be a string")
        if not os.path.isabs(raw_path):
            raise RuntimeError(f"host_executable path must be absolute: {raw_path}")

        path_name = _execpolicy_lookup_key(os.path.basename(raw_path))
        if path_name != key:
            raise RuntimeError(
                f"invalid host_executable path in {path}: {raw_path} must have basename {name}"
            )
        if raw_path not in normalized_paths:
            normalized_paths.append(raw_path)

    return key, tuple(normalized_paths)


def _execpolicy_network_protocol(raw: object, *, path: str) -> str:
    if not isinstance(raw, str):
        raise RuntimeError(f"invalid network_rule in {path}: protocol must be a string")

    normalized = raw.lower()
    if normalized in {"http", "https", "https_connect", "http-connect", "socks5_tcp", "socks5_udp"}:
        if normalized in {"https_connect", "http-connect"}:
            return "https"
        return normalized
    raise RuntimeError(f"invalid network_rule in {path}: unsupported protocol {raw}")


def _execpolicy_network_host(raw: object, *, path: str) -> str:
    if not isinstance(raw, str):
        raise RuntimeError(f"invalid network_rule in {path}: host must be a string")

    host = raw.strip()
    if not host:
        raise RuntimeError("network_rule host cannot be empty")
    if any(token in host for token in ("://", "/", "?", "#")):
        raise RuntimeError("network_rule host must be a hostname or IP literal (without scheme or path)")
    if host.count(":") == 1:
        candidate, port = host.rsplit(":", 1)
        if candidate and port.isdigit():
            host = candidate
    host = host.strip("[]").strip().strip(".").lower()
    if not host:
        raise RuntimeError("network_rule host cannot be empty")
    if "*" in host:
        raise RuntimeError("network_rule host must be a specific host; wildcards are not allowed")
    if any(ch.isspace() for ch in host):
        raise RuntimeError("network_rule host cannot contain whitespace")
    return host


def _parse_execpolicy_file(path: str) -> tuple[
    dict[str, list[_ExecPolicyRule]],
    dict[str, tuple[str, ...]],
    list[tuple[list[_ExecPolicyRule], list[tuple[str, ...]], list[tuple[str, ...]], int]],
]:
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to read policy at {path}: {exc}")

    try:
        normalized_source = _normalize_execpolicy_source(source)
        module = ast.parse(normalized_source)
    except (SyntaxError, tokenize.TokenError) as exc:
        raise RuntimeError(f"failed to parse policy at {path}: {exc}")

    rules_by_program: dict[str, list[_ExecPolicyRule]] = {}
    host_executables: dict[str, tuple[str, ...]] = {}
    validations: list[tuple[list[_ExecPolicyRule], list[tuple[str, ...]], list[tuple[str, ...]], int]] = []

    for node in module.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if not isinstance(call.func, ast.Name):
                raise RuntimeError(
                    f"unsupported expression in {path}: only prefix_rule(), host_executable(), and network_rule() calls are supported"
                )

            kwargs: dict[str, object] = {}
            for keyword in call.keywords:
                if keyword.arg is None:
                    raise RuntimeError(f"unsupported call in {path}: positional arguments are not supported")
                key = keyword.arg
                if key == "__match":
                    key = "match"
                elif key == "__not_match":
                    key = "not_match"
                try:
                    value = ast.literal_eval(keyword.value)
                except Exception as exc:
                    raise RuntimeError(f"invalid value for {key} in {path}: {exc}")
                kwargs[key] = value

            if call.func.id == "prefix_rule":
                allowed_keys = {"pattern", "decision", "match", "not_match", "justification"}
                unknown = set(kwargs) - allowed_keys
                if unknown:
                    unknown_key = next(iter(unknown))
                    raise RuntimeError(
                        f"unsupported keyword for prefix_rule in {path}: {unknown_key}"
                    )

                pattern_raw = kwargs.get("pattern")
                if pattern_raw is None:
                    raise RuntimeError(f"prefix_rule in {path} requires pattern")
                pattern = _parse_execpolicy_pattern_tokens(pattern_raw, path=path)
                decision = _parse_execpolicy_decision(kwargs.get("decision", "allow"), path=path)

                justification = None
                if "justification" in kwargs:
                    justification_raw = kwargs["justification"]
                    if not isinstance(justification_raw, str) or not justification_raw.strip():
                        raise RuntimeError(f"invalid justification in {path}: justification cannot be empty")
                    justification = justification_raw

                first, *rest = pattern
                first_alternatives: tuple[str, ...]
                if isinstance(first, str):
                    first_alternatives = (first,)
                else:
                    first_alternatives = first

                created_rules: list[_ExecPolicyRule] = []
                for first_token in first_alternatives:
                    expanded = _ExecPolicyRule(
                        pattern=(first_token, *tuple(rest)),
                        decision=decision,
                        justification=justification,
                    )
                    created_rules.append(expanded)
                    rules_by_program.setdefault(first_token, []).append(expanded)

                match_examples = _parse_execpolicy_examples(
                    kwargs.get("match"), path=path, context="match"
                )
                not_match_examples = _parse_execpolicy_examples(
                    kwargs.get("not_match"), path=path, context="not_match"
                )
                validations.append((created_rules, match_examples, not_match_examples, node.lineno))
                continue

            if call.func.id == "host_executable":
                allowed_keys = {"name", "paths"}
                unknown = set(kwargs) - allowed_keys
                if unknown:
                    unknown_key = next(iter(unknown))
                    raise RuntimeError(
                        f"unsupported keyword for host_executable in {path}: {unknown_key}"
                    )

                name, paths = _parse_execpolicy_host_executable(kwargs, path=path)
                host_executables[name] = paths
                continue

            if call.func.id == "network_rule":
                allowed_keys = {"host", "protocol", "decision", "justification"}
                unknown = set(kwargs) - allowed_keys
                if unknown:
                    unknown_key = next(iter(unknown))
                    raise RuntimeError(f"unsupported keyword for network_rule in {path}: {unknown_key}")

                _execpolicy_network_host(kwargs.get("host"), path=path)
                _execpolicy_network_protocol(kwargs.get("protocol"), path=path)
                _parse_execpolicy_decision(kwargs.get("decision"), path=path)
                justification = kwargs.get("justification")
                if justification is not None:
                    if not isinstance(justification, str) or not justification.strip():
                        raise RuntimeError(f"invalid justification in {path}: justification cannot be empty")
                continue

            raise RuntimeError(f"unsupported command in {path}: {call.func.id}")

        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue

        raise RuntimeError(
            f"unsupported statement in {path}: only prefix_rule(), host_executable(), and network_rule() calls are supported"
        )

    return rules_by_program, host_executables, validations


def _iter_execpolicy_rules(rules_by_program: dict[str, list[_ExecPolicyRule]]) -> list[_ExecPolicyRule]:
    rules: list[_ExecPolicyRule] = []
    for program in rules_by_program:
        rules.extend(rules_by_program[program])
    return rules


def _rule_matches_command(rule: _ExecPolicyRule, command: tuple[str, ...]) -> tuple[str, ...] | None:
    if len(command) < len(rule.pattern):
        return None

    for index, token in enumerate(rule.pattern):
        command_token = command[index]
        if isinstance(token, str):
            if command_token != token:
                return None
            continue
        if command_token not in token:
            return None

    return command[: len(rule.pattern)]


def _resolve_execpolicy_rules(
    rules_by_program: dict[str, list[_ExecPolicyRule]],
    host_executables: dict[str, tuple[str, ...]],
    command: tuple[str, ...],
    *,
    resolve_host_executables: bool,
) -> list[tuple[_ExecPolicyRule, tuple[str, ...], str | None]]:
    if not command:
        return []

    first = command[0]
    results: list[tuple[_ExecPolicyRule, tuple[str, ...], str | None]] = []

    for rule in rules_by_program.get(first, ()):  # exact-first-token matching
        matched = _rule_matches_command(rule, command)
        if matched is not None:
            results.append((rule, matched, None))

    if results or not resolve_host_executables or not os.path.isabs(first):
        return results

    resolved_first = _execpolicy_lookup_key(os.path.basename(first))
    paths = host_executables.get(resolved_first)
    if paths is not None and first not in paths:
        return []

    fallback_command = (resolved_first, *command[1:])
    for rule in rules_by_program.get(resolved_first, ()):
        matched = _rule_matches_command(rule, fallback_command)
        if matched is not None:
            results.append((rule, matched, first))

    return results


def _collect_execpolicy_matches(
    rules_by_program: dict[str, list[_ExecPolicyRule]],
    host_executables: dict[str, tuple[str, ...]],
    command: tuple[str, ...],
) -> list[tuple[_ExecPolicyRule, tuple[str, ...], str | None]]:
    return _resolve_execpolicy_rules(
        rules_by_program,
        host_executables,
        command,
        resolve_host_executables=True,
    )


def _validate_execpolicy_examples(
    rules_by_program: dict[str, list[_ExecPolicyRule]],
    validations: list[tuple[list[_ExecPolicyRule], list[tuple[str, ...]], list[tuple[str, ...]], int]],
    path: str,
) -> None:
    # PolicyRule matching uses exact and host-executable fallback disabled by design.
    def _matches_any(command: tuple[str, ...]) -> bool:
        if not command:
            return False
        return bool(_resolve_execpolicy_rules(rules_by_program, {}, command, resolve_host_executables=False))

    for rules, matches, not_matches, line_no in validations:
        for example in matches:
            if not _matches_any(example):
                raise RuntimeError(
                    f"invalid match example in {path}:{line_no}: {' '.join(example)} did not match any rule"
                )
        for example in not_matches:
            if _matches_any(example):
                raise RuntimeError(
                    f"invalid not_match example in {path}:{line_no}: {' '.join(example)} unexpectedly matched"
                )
        del rules


def _load_execpolicy_rules(
    rule_paths: tuple[str, ...] | list[str],
) -> tuple[dict[str, list[_ExecPolicyRule]], dict[str, tuple[str, ...]]]:
    rules_by_program: dict[str, list[_ExecPolicyRule]] = {}
    host_executables: dict[str, tuple[str, ...]] = {}
    validations: list[tuple[list[_ExecPolicyRule], list[tuple[str, ...]], list[tuple[str, ...]], int]] = []

    for path in rule_paths:
        file_rules, file_hosts, file_validations = _parse_execpolicy_file(path)
        for program, rules in file_rules.items():
            rules_by_program.setdefault(program, []).extend(rules)
        host_executables.update(file_hosts)
        validations.extend(file_validations)

    if validations:
        # Examples are validated after collecting all rules so cross-file precedence
        # remains the same as full merged rule order.
        _validate_execpolicy_examples(rules_by_program, validations, str(rule_paths[0]))

    return rules_by_program, host_executables


def _collect_execpolicy_rule_files_from_dir(rules_dir: Path | str) -> tuple[str, ...]:
    path = Path(rules_dir)
    if not path.exists():
        return ()
    if not path.is_dir():
        raise RuntimeError(f"failed to read rules files from {path}: not a directory")
    try:
        return tuple(str(child) for child in sorted(path.iterdir()) if child.is_file() and child.suffix == ".rules")
    except OSError as exc:
        raise RuntimeError(f"failed to read rules files from {path}: {exc}") from exc


def _default_execpolicy_rule_paths(codex_home: Path | str, cwd: Path | str) -> tuple[str, ...]:
    paths: list[str] = []
    for rules_dir in (Path(codex_home) / "rules", Path(cwd) / ".codex" / "rules"):
        paths.extend(_collect_execpolicy_rule_files_from_dir(rules_dir))
    return tuple(paths)


def _execpolicy_rules_for_local_http_exec(
    codex_home: Path | str,
    cwd: Path | str,
    *,
    ignore_rules: bool,
) -> tuple[ExecPolicyPrefixRule, ...]:
    if ignore_rules:
        return ()
    rule_paths = _default_execpolicy_rule_paths(codex_home, cwd)
    if not rule_paths:
        return ()
    rules_by_program, _host_executables = _load_execpolicy_rules(rule_paths)
    return tuple(
        ExecPolicyPrefixRule.new(rule.pattern, rule.decision, rule.justification)
        for rule in _iter_execpolicy_rules(rules_by_program)
    )


def _render_execpolicy_output(
    matched_rules: list[tuple[_ExecPolicyRule, tuple[str, ...], str | None]],
    *,
    pretty: bool,
) -> str:
    output_rules: list[dict[str, object]] = []
    for rule, prefix, resolved_program in matched_rules:
        rule_body: dict[str, object] = {
            "matchedPrefix": list(prefix),
            "decision": rule.decision,
        }
        if resolved_program is not None:
            rule_body["resolvedProgram"] = resolved_program
        if rule.justification is not None:
            rule_body["justification"] = rule.justification
        output_rules.append({"prefixRuleMatch": rule_body})

    output: dict[str, object] = {"matchedRules": output_rules}
    if output_rules:
        winner = max(output_rules, key=lambda item: _RULE_DECISION_PRIORITY[item["prefixRuleMatch"]["decision"]])
        output["decision"] = winner["prefixRuleMatch"]["decision"]

    if pretty:
        return json.dumps(output, ensure_ascii=False, indent=2)
    return json.dumps(output, ensure_ascii=False, separators=(",", ":"))


def _run_execpolicy_check(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if not command_args or command_args[0] != "check":
        print("pycodex: unknown execpolicy subcommand.", file=stderr)
        return 2

    args = command_args[1:]
    pretty = False
    resolve_host_executables = False
    rules: list[str] = []
    command: tuple[str, ...] = ()

    index = 0
    while index < len(args):
        arg = args[index]

        if arg in {"-h", "--help"}:
            print(_unimplemented_command_help_text("execpolicy"), file=stdout)
            return 0
        if arg == "--pretty":
            pretty = True
            index += 1
            continue
        if arg == "--resolve-host-executables":
            resolve_host_executables = True
            index += 1
            continue
        if arg in {"--rules", "-r"}:
            if index + 1 >= len(args):
                print("execpolicy check requires --rules.", file=stderr)
                return 2
            rules.append(args[index + 1])
            index += 2
            continue

        if arg == "--":
            command = tuple(args[index + 1 :])
            index = len(args)
            break

        command = tuple(args[index:])
        break

    if not command:
        print("execpolicy check requires COMMAND.", file=stderr)
        return 2
    if not rules:
        print("execpolicy check requires --rules.", file=stderr)
        return 2

    try:
        rules_by_program, host_executables = _load_execpolicy_rules(rules)
    except RuntimeError as exc:
        print(f"{exc}", file=stderr)
        return 2

    matched_rules = _resolve_execpolicy_rules(
        rules_by_program,
        host_executables,
        command,
        resolve_host_executables=resolve_host_executables,
    )

    print(
        _render_execpolicy_output(matched_rules, pretty=pretty),
        file=stdout,
    )
    return 0


def _run_cloud_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    if any(arg in {"-h", "--help"} for arg in command_args):
        if not command_args or command_args[0] in {"-h", "--help"}:
            print(_cloud_help_text(None), file=stdout)
        elif command_args[0] in {"exec", "status", "list", "apply", "diff"}:
            print(_cloud_help_text(command_args[0]), file=stdout)
        else:
            print(_unimplemented_command_help_text("cloud"), file=stdout)
        return 0

    if not command_args:
        if _fallback_enabled("PYCODEX_CLOUD_FALLBACK"):
            print(
                "No cloud subcommand provided. Falling back to `cloud list`.",
                file=stderr,
            )
            command_args = ("list",)
        else:
            print(
                "pycodex: command 'cloud' is currently parsed but the interactive browser is not implemented yet.",
                file=stderr,
            )
            return 64

    subcommand = command_args[0]
    try:
        token = _cloud_auth_token()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    if subcommand == "exec":
        args = command_args[1:]
        query: str | None = None
        env: str | None = None
        attempts = 1
        branch: str | None = None

        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "--env":
                if index + 1 >= len(args):
                    raise RuntimeError("Missing value for --env.")
                env = args[index + 1]
                index += 2
                continue
            if arg == "--attempts":
                if index + 1 >= len(args):
                    raise RuntimeError("Missing value for --attempts.")
                parse_cloud_attempts_value(args[index + 1], "--attempts")
                attempts = int(args[index + 1])
                index += 2
                continue
            if arg == "--branch":
                if index + 1 >= len(args):
                    raise RuntimeError("Missing value for --branch.")
                branch = args[index + 1]
                index += 2
                continue
            if arg == "--":
                query = args[index + 1] if index + 1 < len(args) else None
                index += 2
                continue
            if arg.startswith("-"):
                print(f"Unknown argument for cloud exec: {arg}", file=stderr)
                return 2
            if query is not None:
                print("Too many arguments for `cloud exec`.", file=stderr)
                return 2
            query = arg
            index += 1

        if env is None:
            print("cloud exec requires --env.", file=stderr)
            return 2

        query = _resolve_query_input(
            query,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        if query is None:
            return 2

        git_ref = _resolve_cloud_git_ref(branch)
        input_items = [
            {
                "type": "message",
                "role": "user",
                "content": [{"content_type": "text", "text": query}],
            }
        ]
        payload: dict[str, object] = {
            "new_task": {
                "environment_id": env,
                "branch": git_ref,
                "run_environment_in_qa_mode": False,
            },
            "input_items": input_items,
        }
        if attempts > 1:
            payload["metadata"] = {"best_of_n": attempts}

        try:
            response = _cloud_request_json(
                url=f"{_CLOUD_BASE_URL}/wham/tasks",
                method="POST",
                token=token,
                payload=payload,
            )
            created_task_id = _created_task_id_from_payload(response)
            print(_cloud_task_url(created_task_id), file=stdout)
            return 0
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2


    if subcommand == "status":
        try:
            task_id = _parse_cloud_task_id(command_args[1])
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        try:
            payload = _cloud_request_json(
                url=f"{_CLOUD_BASE_URL}/wham/tasks/{task_id}",
                method="GET",
                token=token,
            )
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

        if not isinstance(payload, dict):
            print("pycodex: unexpected response format from cloud task endpoint.", file=stderr)
            return 2

        status = _task_status_from_payload(payload)
        task_obj = payload.get("task") if isinstance(payload.get("task"), dict) else payload
        title = task_obj.get("title") if isinstance(task_obj, dict) else None
        if title and isinstance(title, str):
            print(f"title: {title}", file=stdout)
        print(f"status: {status or 'unknown'}", file=stdout)
        if status is None:
            return 1
        return 0 if _is_ready_status(status) else 1

    if subcommand == "list":
        env: str | None = None
        cursor: str | None = None
        limit = _CLOUD_DEFAULT_LIST_LIMIT
        json_output = False
        args = command_args[1:]

        index = 0
        while index < len(args):
            arg = args[index]
            if arg == "--env":
                env = args[index + 1]
                index += 2
                continue
            if arg == "--limit":
                limit = int(args[index + 1])
                index += 2
                continue
            if arg == "--cursor":
                cursor = args[index + 1]
                index += 2
                continue
            if arg == "--json":
                json_output = True
                index += 1
                continue
            index += 1

        try:
            tasks, next_cursor = _list_cloud_tasks(
                token,
                env=env,
                limit=limit,
                cursor=cursor,
            )
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

        _print_cloud_list_output(
            tasks,
            next_cursor,
            stdout=stdout,
            json_output=json_output,
        )
        return 0

    if subcommand in {"apply", "diff"}:
        try:
            task_id, attempt = _cloud_task_id_and_attempt(subcommand, command_args[1:])
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

        try:
            payload = _cloud_request_json(
                url=f"{_CLOUD_BASE_URL}/wham/tasks/{task_id}",
                method="GET",
                token=token,
            )
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

        if not isinstance(payload, dict):
            print("pycodex: unexpected response format from cloud task endpoint.", file=stderr)
            return 2

        try:
            attempts = _collect_cloud_attempt_diffs(payload, token=token, task_id=task_id)
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2
        diff = _select_cloud_attempt_diff(attempts, attempt)
        if diff is None:
            if not attempts:
                print(f"No diff available for task {task_id}.", file=stderr)
                return 1
            print(
                f"Attempt {attempt} not available for task {task_id}; only {len(attempts)} attempt(s) found.",
                file=stderr,
            )
            return 2

        if not diff:
            print(f"No diff available for task {task_id}.", file=stderr)
            return 1

        if subcommand == "diff":
            print(diff, file=stdout)
            return 0

        return _apply_task_diff_with_git(diff, stdout=stdout, stderr=stderr)

    print(
        f"pycodex: command 'cloud {subcommand}' is currently not implemented yet.",
        file=stderr,
    )
    if _fallback_enabled("PYCODEX_CLOUD_FALLBACK"):
        print("Falling back with no-op result.", file=stderr)
        return 0
    return 64


def _cloud_help_text(subcommand: str | None = None) -> str:
    if subcommand is None:
        return "Usage: codex cloud [OPTIONS] <COMMAND>"
    if subcommand == "exec":
        return "Usage: codex cloud exec [OPTIONS] [QUERY]"
    if subcommand == "status":
        return "Usage: codex cloud status <TASK_ID>"
    if subcommand == "list":
        return "Usage: codex cloud list [OPTIONS]"
    if subcommand == "apply":
        return "Usage: codex cloud apply [OPTIONS] <TASK_ID>"
    if subcommand == "diff":
        return "Usage: codex cloud diff [OPTIONS] <TASK_ID>"
    return _unimplemented_command_help_text("cloud")


def _remote_control_help_text(command_args: tuple[str, ...]) -> str:
    for arg in command_args:
        if arg.startswith("-"):
            continue
        if arg in {"start", "stop"}:
            return f"Usage: codex remote-control {arg}"
        break
    return "Usage: codex remote-control [OPTIONS]"


def _app_server_help_text(command_args: tuple[str, ...]) -> str:
    command_args = _app_server_command_args_for_help(command_args)
    if not command_args:
        return "Usage: codex app-server [OPTIONS] [COMMAND]"
    subcommand = command_args[0]
    if subcommand == "daemon":
        if len(command_args) == 1:
            return "Usage: codex app-server daemon <COMMAND>"
        daemon_command = command_args[1]
        if daemon_command in _APP_SERVER_DAEMON_SUBCOMMANDS:
            return f"Usage: codex app-server daemon {daemon_command}"
        return "Usage: codex app-server daemon <COMMAND>"
    if subcommand == "proxy":
        return "Usage: codex app-server proxy [OPTIONS]"
    if subcommand == "generate-ts":
        return "Usage: codex app-server generate-ts [OPTIONS]"
    if subcommand == "generate-json-schema":
        return "Usage: codex app-server generate-json-schema [OPTIONS]"
    if subcommand == "generate-internal-json-schema":
        return "Usage: codex app-server generate-internal-json-schema [OPTIONS]"
    return "Usage: codex app-server"


def _app_server_command_args_for_help(command_args: tuple[str, ...]) -> tuple[str, ...]:
    root_bool_options = {"--strict-config", "--remote-control", "--analytics-default-enabled"}
    root_value_options = {
        "--listen",
        "--ws-auth",
        "--ws-token-file",
        "--ws-token-sha256",
        "--ws-shared-secret-file",
        "--ws-issuer",
        "--ws-audience",
        "--ws-max-clock-skew-seconds",
    }

    args = list(command_args)
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            index += 1
            break
        if arg in {"-h", "--help"}:
            index += 1
            continue
        if arg in root_bool_options:
            index += 1
            continue
        if arg in root_value_options:
            if index + 1 >= len(args):
                return ()
            index += 2
            continue
        break
    return tuple(args[index:])


def _run_completion(parsed: "ParsedCli", *, stdout: TextIO, stderr: TextIO) -> int:
    args = list(parsed.command_args)
    shell = "bash"
    remaining: list[str] = []
    index = 0

    while index < len(args):
        arg = args[index]
        if arg in {"-h", "--help"}:
            print(_completion_help_text(), file=stdout)
            return 0
        if arg.startswith("--shell="):
            shell = arg[len("--shell=") :]
            index += 1
            continue
        if arg in {"--shell", "-s"}:
            if index + 1 >= len(args):
                print("Missing value for option --shell", file=stderr)
                return 2
            shell = args[index + 1]
            index += 2
            continue
        remaining.append(arg)
        index += 1

    if remaining:
        print(f"Unsupported completion argument: {remaining[0]}", file=stderr)
        return 2

    if shell not in _COMPLETION_SHELLS:
        print(
            f"Unsupported shell '{shell}'. Supported values: {', '.join(_COMPLETION_SHELLS)}",
            file=stderr,
        )
        return 2

    print(_completion_script(shell), file=stdout)
    return 0


def _completion_help_text() -> str:
    return (
        "Usage: codex completion [--shell <bash|zsh|fish|powershell|pwsh>] [--help]\n"
        "Generate shell completion scripts."
    )


def _completion_script(shell: str) -> str:
    if shell == "bash":
        return """# pycodex completion (bash)
_pycodex_completion() {
    COMPREPLY=()
}
complete -F _pycodex_completion codex"""
    if shell == "zsh":
        return """# pycodex completion (zsh)
#compdef codex"""
    if shell == "fish":
        return """# pycodex completion (fish)
complete -c codex"""
    if shell == "powershell":
        return """# pycodex completion (powershell)
Set-Alias -Name codex-completion -Value codex"""
    return """# pycodex completion (pwsh)
Register-ArgumentCompleter -CommandName codex"""


def _run_login(
    parsed: "ParsedCli",
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    try:
        mode = _parse_login_mode(parsed.command_args)
    except CliParseError as exc:
        print(str(exc), file=stderr)
        return 2

    if mode["help"]:
        if mode["status"]:
            print("Usage: codex login status", file=stdout)
        else:
            print(_login_help_text(), file=stdout)
        return 0

    if mode["status"]:
        return _run_login_status(stderr=stderr)

    if mode["api_key"] is not None:
        print(
            "The --api-key flag is no longer supported. Pipe the key instead, "
            "e.g. `printenv OPENAI_API_KEY | codex login --with-api-key`.",
            file=stderr,
        )
        return 2

    if mode["with_api_key"] and mode["with_access_token"]:
        print(
            "Choose one login credential source: --with-api-key or --with-access-token.",
            file=stderr,
        )
        return 2

    if mode["device_auth"] and (mode["with_api_key"] or mode["with_access_token"]):
        print(
            "Choose one login credential source: --with-api-key or --with-access-token.",
            file=stderr,
        )
        return 2

    if mode["device_auth"]:
        try:
            return _run_device_auth_login(
                issuer=mode["experimental_issuer"],
                client_id=mode["experimental_client_id"],
                stdout=stdout,
                stderr=stderr,
            )
        except RuntimeError as exc:
            print(f"pycodex: {exc}", file=stderr)
            return 2

    if mode["with_api_key"]:
        token = _read_stdin_text(
            stdin,
            required=True,
            command="--with-api-key",
            stderr=stderr,
            stdin_is_terminal=stdin_is_terminal,
        )
        if token is None:
            return 2
        auth = AuthDotJson(
            auth_mode=AUTH_MODE_API_KEY,
            openai_api_key=token,
        )
        try:
            write_auth_json(auth)
        except (ValueError, OSError) as exc:
            print(f"Error saving login: {exc}", file=stderr)
            return 2
        print("Successfully logged in", file=stderr)
        return 0

    if mode["with_access_token"]:
        token = _read_stdin_text(
            stdin,
            required=True,
            command="--with-access-token",
            stderr=stderr,
            stdin_is_terminal=stdin_is_terminal,
        )
        if token is None:
            return 2
        if not _is_valid_access_token(token):
            print("Error logging in with access token: invalid access token format.", file=stderr)
            return 2
        auth = AuthDotJson(
            auth_mode=AUTH_MODE_AGENT_IDENTITY,
            agent_identity=token,
        )
        try:
            write_auth_json(auth)
        except (ValueError, OSError) as exc:
            print(f"Error saving login: {exc}", file=stderr)
            return 2
        print("Successfully logged in", file=stderr)
        return 0

    return run_chatgpt_login(
        stdout=stdout,
        stderr=stderr,
        issuer=mode["experimental_issuer"],  # type: ignore[arg-type]
        client_id=mode["experimental_client_id"],  # type: ignore[arg-type]
    )


def _run_device_auth_login(
    *,
    issuer: object,
    client_id: object,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    chosen_issuer = _resolve_device_auth_issuer(issuer)
    chosen_client_id = _resolve_device_auth_client_id(client_id)
    base_url = chosen_issuer.rstrip("/")
    api_base_url = f"{base_url}/api/accounts"

    try:
        user_code_data = _request_device_auth_user_code(api_base_url, chosen_client_id)
        verification_url = f"{base_url}/codex/device"
    except RuntimeError as exc:
        print(f"Error requesting device authorization: {exc}", file=stderr)
        return 2

    print(
        "\nFollow these steps to sign in with ChatGPT using device code authorization:\n",
        file=stderr,
    )
    print(f"1. Open this link in your browser and sign in:\n   {verification_url}", file=stderr)
    print(
        f"2. Enter this one-time code (expires in 15 minutes): {user_code_data['user_code']}",
        file=stderr,
    )
    print("Waiting for authorization in browser...", file=stderr)

    try:
        code_payload = _poll_device_auth_token(
            api_base_url,
            user_code_data["device_auth_id"],
            user_code_data["user_code"],
            user_code_data["interval"],
            stdout=stdout,
            stderr=stderr,
        )
        tokens = _exchange_device_auth_code(
            chosen_issuer,
            chosen_client_id,
            code_payload["authorization_code"],
            code_payload["code_verifier"],
        )
        id_token = tokens.get("id_token")
        if isinstance(id_token, str):
            claims = _extract_auth_claims_from_jwt(id_token)
            account_id = claims.get("chatgpt_account_id")
            if isinstance(account_id, str) and account_id:
                tokens["account_id"] = account_id
    except RuntimeError as exc:
        print(f"Device auth failed: {exc}", file=stderr)
        return 2

    now = datetime.now(timezone.utc).isoformat()
    auth = AuthDotJson(
        auth_mode=AUTH_MODE_CHATGPT_AUTH_TOKENS,
        tokens=tokens,
        last_refresh=now,
    )
    try:
        write_auth_json(auth)
    except (ValueError, OSError) as exc:
        print(f"Error saving login: {exc}", file=stderr)
        return 2

    print("Successfully logged in", file=stderr)
    return 0


def _resolve_device_auth_issuer(issuer: object) -> str:
    if isinstance(issuer, str) and issuer.strip():
        return issuer.strip()
    return _DEVICE_AUTH_DEFAULT_ISSUER


def _resolve_device_auth_client_id(client_id: object) -> str:
    if isinstance(client_id, str) and client_id.strip():
        return client_id.strip()
    return _DEVICE_AUTH_DEFAULT_CLIENT_ID


def _request_device_auth_user_code(api_base_url: str, client_id: str) -> dict[str, str | int]:
    try:
        response = request_user_code(api_base_url, client_id, opener=urlopen)
    except FileNotFoundError as exc:
        raise RuntimeError(DEVICE_CODE_NOT_ENABLED_MESSAGE) from exc
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc

    return {
        "device_auth_id": response.device_auth_id,
        "user_code": response.user_code,
        "interval": response.interval if response.interval > 0 else 5,
    }


def _poll_device_auth_token(
    api_base_url: str,
    device_auth_id: str,
    user_code: str,
    interval: int,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> dict[str, str]:
    del stdout
    try:
        token_payload = poll_for_token(
            api_base_url,
            device_auth_id,
            user_code,
            interval,
            opener=urlopen,
            sleep=time.sleep,
            clock=time.time,
            max_wait_seconds=_DEVICE_AUTH_MAX_WAIT_SECONDS,
        )
    except TimeoutError as exc:
        print("Device auth timed out after 15 minutes.", file=stderr)
        raise RuntimeError(str(exc)) from exc
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc

    return {
        "authorization_code": token_payload.authorization_code,
        "code_verifier": token_payload.code_verifier,
    }


def _exchange_device_auth_code(
    issuer: str,
    client_id: str,
    authorization_code: str,
    code_verifier: str,
) -> dict[str, str]:
    redirect_uri = f"{issuer.rstrip('/')}/deviceauth/callback"
    form_data = urlencode(
        {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "pycodex",
    }
    request = Request(
        url=f"{issuer.rstrip('/')}/oauth/token",
        data=form_data,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        _drain_http_error(exc)
        message = body.strip() or exc.reason
        raise RuntimeError(f"device auth token exchange failed with status {exc.code}: {message}")
    except URLError as exc:
        raise RuntimeError(f"device auth token exchange failed: {exc}")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"device auth token exchange returned invalid JSON: {exc}")

    if not isinstance(payload, dict):
        raise RuntimeError("device auth token exchange returned an unexpected response.")

    id_token = payload.get("id_token")
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")

    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("device auth token exchange did not return an access token.")

    tokens: dict[str, str] = {"access_token": access_token.strip()}
    if isinstance(id_token, str) and id_token.strip():
        tokens["id_token"] = id_token.strip()
    if isinstance(refresh_token, str) and refresh_token.strip():
        tokens["refresh_token"] = refresh_token.strip()
    return tokens


def _run_logout(*, parsed: "ParsedCli", stdout: TextIO, stderr: TextIO) -> int:
    if any(arg in {"-h", "--help"} for arg in parsed.command_args):
        print(_unimplemented_command_help_text("logout"), file=stdout)
        return 0

    try:
        removed = delete_auth_file()
    except OSError as exc:
        print(f"Error logging out: {exc}", file=stderr)
        return 2
    print("Successfully logged out" if removed else "Not logged in", file=stderr)
    return 0


def _drain_http_error(error: HTTPError) -> None:
    fp = getattr(error, "fp", None)
    if fp is None:
        return
    closer = getattr(fp, "close", None)
    if callable(closer):
        try:
            closer()
        except OSError:
            pass
        except Exception:
            # Best effort; avoid masking the original HTTP error semantics.
            pass
    setattr(error, "fp", None)


def _run_app_command(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    del stdout

    workspace_arg = "."
    download_url: str | None = None
    index = 0
    while index < len(command_args):
        arg = command_args[index]
        if arg == "--download-url":
            if index + 1 >= len(command_args):
                print("Missing value for --download-url.", file=stderr)
                return 2
            download_url = command_args[index + 1]
            index += 2
            continue
        if not arg.startswith("-"):
            workspace_arg = arg
        index += 1

    workspace = workspace_for_app_command(workspace_arg)

    if sys.platform == "darwin":
        return _run_app_command_macos(
            workspace=workspace,
            download_url=download_url,
            stderr=stderr,
        )

    if sys.platform.startswith("win"):
        return _run_app_command_windows(
            workspace=workspace,
            download_url=download_url,
            stderr=stderr,
        )

    return 0


def _run_app_command_macos(
    *,
    workspace: Path,
    download_url: str | None,
    stderr: TextIO,
) -> int:
    for app_path in candidate_codex_app_paths(os.environ.get("HOME")):
        if app_path.is_dir():
            return _open_codex_app_macos(app_path, workspace, stderr=stderr, announce_app=True)

    print("Codex Desktop not found; downloading installer...", file=stderr)
    installer_url = download_url if download_url is not None else _default_macos_dmg_url()
    try:
        installed_app = _download_and_install_codex_to_user_applications_macos(
            installer_url,
            stderr=stderr,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"failed to download/install Codex Desktop: {exc}", file=stderr)
        return 2

    print(f"Launching Codex Desktop from {installed_app}...", file=stderr)
    return _open_codex_app_macos(installed_app, workspace, stderr=stderr, announce_app=False)


def _default_macos_dmg_url() -> str:
    return default_mac_dmg_url(
        platform.machine(),
        translated=_macos_sysctl_flag("sysctl.proc_translated") or False,
        arm64_optional=_macos_sysctl_flag("hw.optional.arm64") or False,
    )


def _macos_sysctl_flag(name: str) -> bool | None:
    try:
        result = subprocess.run(
            ("sysctl", "-in", name),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    if value == "0":
        return False
    if value:
        return True
    return None


def _open_codex_app_macos(app_path: Path, workspace: Path, *, stderr: TextIO, announce_app: bool) -> int:
    if announce_app:
        print(f"Opening Codex Desktop at {app_path}...", file=stderr)
    print(f"Opening workspace {workspace}...", file=stderr)
    try:
        result = subprocess.run(
            mac_open_app_command(app_path, workspace),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to launch Codex Desktop: {exc}", file=stderr)
        return 2

    if result.returncode == 0:
        return 0

    print(
        f"open command returned {result.returncode} while launching Codex Desktop.",
        file=stderr,
    )
    if result.stderr:
        print(result.stderr.strip(), file=stderr)
    return 2


def _download_and_install_codex_to_user_applications_macos(
    dmg_url: str,
    *,
    stderr: TextIO,
) -> Path:
    plan = mac_app_install_plan(dmg_url)
    with tempfile.TemporaryDirectory(prefix=plan.temp_dir_prefix) as tmp_root:
        dmg_path = Path(tmp_root) / plan.dmg_filename

        print("Downloading installer...", file=stderr)
        _run_macos_status_command(
            mac_download_dmg_command(plan.dmg_url, dmg_path),
            invoke_error="failed to invoke `curl`",
            status_error="curl download failed",
        )

        print(plan.mount_message, file=stderr)
        mount_point = _mount_codex_dmg_macos(dmg_path)
        print(f"Installer mounted at {mount_point}.", file=stderr)

        try:
            app_in_volume = find_codex_app_in_mount(mount_point)
            return _install_codex_app_bundle_macos(app_in_volume, stderr=stderr)
        finally:
            try:
                _run_macos_status_command(
                    mac_detach_dmg_command(mount_point),
                    invoke_error="failed to invoke `hdiutil detach`",
                    status_error="hdiutil detach failed",
                )
            except (OSError, RuntimeError) as exc:
                print(f"warning: failed to detach dmg at {mount_point}: {exc}", file=stderr)


def _mount_codex_dmg_macos(dmg_path: Path) -> Path:
    try:
        result = subprocess.run(
            mac_mount_dmg_command(dmg_path),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise OSError("failed to invoke `hdiutil attach`") from exc

    if result.returncode != 0:
        raise RuntimeError(
            "`hdiutil attach` failed with "
            f"exit status {result.returncode}: {result.stderr}"
        )

    mount_point = parse_hdiutil_attach_mount_point(result.stdout)
    if mount_point is None:
        raise RuntimeError(f"failed to parse mount point from hdiutil output:\n{result.stdout}")
    return Path(mount_point)


def _install_codex_app_bundle_macos(app_in_volume: Path, *, stderr: TextIO) -> Path:
    home = os.environ.get("HOME")
    if not home:
        raise RuntimeError("HOME is not set")

    for applications_dir in candidate_applications_dirs(home):
        print(f"Installing Codex Desktop into {applications_dir}...", file=stderr)
        try:
            applications_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OSError(f"failed to create applications dir {applications_dir}") from exc

        dest_app = applications_dir / "Codex.app"
        if dest_app.is_dir():
            return dest_app

        try:
            _run_macos_status_command(
                mac_copy_app_bundle_command(app_in_volume, dest_app),
                invoke_error="failed to invoke `ditto`",
                status_error="ditto copy failed",
            )
        except (OSError, RuntimeError) as exc:
            print(f"warning: failed to install Codex.app to {applications_dir}: {exc}", file=stderr)
            continue
        return dest_app

    raise RuntimeError("failed to install Codex.app to any applications directory")


def _run_macos_status_command(
    command: tuple[str, ...],
    *,
    invoke_error: str,
    status_error: str,
) -> None:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise OSError(invoke_error) from exc

    if result.returncode != 0:
        stderr_text = f": {result.stderr.strip()}" if result.stderr.strip() else ""
        raise RuntimeError(f"{status_error} with exit status {result.returncode}{stderr_text}")


def _run_app_command_windows(
    *,
    workspace: Path,
    download_url: str | None,
    stderr: TextIO,
) -> int:
    workspace_text = display_windows_workspace_path(workspace)
    print("Checking for installed Codex Desktop on Windows...", file=stderr)
    powershell_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "Get-StartApps -Name 'Codex' | Select-Object -First 1 -ExpandProperty AppID",
    ]
    app_id: str = ""
    try:
        result = subprocess.run(
            powershell_cmd,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        print(f"Failed to detect installed Codex app: {exc}", file=stderr)
        result = None

    if result is not None and result.returncode == 0:
        app_id = result.stdout.strip()

    if app_id:
        print("Opening Codex Desktop...", file=stderr)
        try:
            subprocess.run(
                ("explorer.exe", f"shell:AppsFolder\\{app_id}"),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            print(f"Failed to open Codex Desktop: {exc}", file=stderr)
            return 2
        print(f"In Codex Desktop, open workspace {workspace_text}.", file=stderr)
        return 0

    print("Codex Desktop not found; opening Windows installer...", file=stderr)
    installer = download_url if download_url is not None else _APP_WINDOWS_INSTALLER_URL
    print(f"Opening installer: {installer}", file=stderr)
    if not _open_in_browser(installer, stderr=stderr) and download_url is None:
        print("Opening Microsoft Store URL fallback...", file=stderr)
        _open_in_browser(_APP_MICROSOFT_STORE_URL, stderr=stderr)
    print(f"After installing Codex Desktop, open workspace {workspace_text}.", file=stderr)
    return 0


def _open_in_browser(url: str, *, stderr: TextIO) -> bool:
    try:
        if webbrowser.open(url):
            return True
    except Exception as exc:
        print(f"Failed to open URL: {exc}", file=stderr)
        return False
    print("Could not open URL in a browser.", file=stderr)
    return False


def _app_help_text() -> str:
    return "Usage: codex app [OPTIONS] [PATH]"


def _run_update(*, parsed: "ParsedCli", stdout: TextIO, stderr: TextIO) -> int:
    if any(arg in {"-h", "--help"} for arg in parsed.command_args):
        print(_unimplemented_command_help_text("update"), file=stdout)
        return 0

    if parsed.command_args:
        unknown = parsed.command_args[0]
        print(f"Unknown argument for update: {unknown}", file=stderr)
        return 2

    if _fallback_enabled("PYCODEX_UPDATE_FALLBACK"):
        print(
            "pycodex: update command is configured for fallback mode; "
            "skipping updater execution in this port.",
            file=stderr,
        )
        return 0

    print("pycodex: update command is not implemented in this Python port yet.", file=stdout)
    print(
        "Run `git pull` in the repository or reinstall from your distribution channel",
        file=stdout,
    )
    return 0


def _run_doctor(*, parsed: "ParsedCli", stdout: TextIO, stderr: TextIO) -> int:
    if any(arg in {"-h", "--help"} for arg in parsed.command_args):
        print(_unimplemented_command_help_text("doctor"), file=stdout)
        return 0

    checks: dict[str, dict[str, object]] = {}
    config: Mapping[str, Any] = {}
    stored_auth: dict[str, Any] | None = None
    checks["system"] = _timed_doctor_mapping(lambda: doctor_system_check().to_mapping())

    try:
        codex_home_path: Path | None = find_codex_home()
        codex_home_error: str | None = None
    except Exception as exc:
        codex_home_path = None
        codex_home_error = str(exc)

    checks["installation"] = _timed_doctor_mapping(
        lambda: _doctor_installation_mapping(
            codex_home=codex_home_path,
            show_details="--all" in parsed.command_args,
        )
    )
    checks["runtime"] = _timed_doctor_mapping(
        lambda: doctor_runtime_check(
            current_version=__version__,
            codex_home=codex_home_path,
        ).to_mapping()
    )
    checks["search"] = _timed_doctor_mapping(lambda: doctor_search_check(codex_home=codex_home_path).to_mapping())

    config_error: str | None = None
    if codex_home_path is None:
        config_error = codex_home_error or "CODEX_HOME unavailable"
    else:
        try:
            config = read_toml_mapping(codex_home_path / CONFIG_TOML_FILE)
        except Exception as exc:
            config = {}
            config_error = str(exc)

    if config_error is None and codex_home_path is not None:
        checks["state"] = _timed_doctor_mapping(lambda: doctor_state_check(codex_home=codex_home_path).to_mapping())
        checks["config"] = _timed_doctor_mapping(
            lambda: doctor_config_check(codex_home=codex_home_path, config=dict(config)).to_mapping()
        )
        try:
            auth = read_auth_json(codex_home=codex_home_path)
            stored_auth = auth.to_mapping() if auth is not None else None
        except Exception:
            stored_auth = None
        checks["auth"] = _timed_doctor_mapping(lambda: doctor_auth_check(codex_home=codex_home_path).to_mapping())
        checks["sandbox"] = _timed_doctor_mapping(lambda: doctor_sandbox_check(config=dict(config)).to_mapping())
        checks["terminal_title"] = _timed_doctor_mapping(
            lambda: doctor_terminal_title_check(cwd=Path.cwd(), config=dict(config)).to_mapping()
        )
        checks["updates"] = _timed_doctor_mapping(
            lambda: _doctor_updates_mapping(
                config=dict(config),
                codex_home=codex_home_path,
            )
        )
        checks["mcp"] = _timed_doctor_mapping(lambda: doctor_mcp_check(config=dict(config)).to_mapping())
        checks["websocket"] = _timed_doctor_mapping(lambda: doctor_websocket_check(config=dict(config)).to_mapping())
        checks["background_server"] = _timed_doctor_mapping(
            lambda: doctor_background_server_check(codex_home=codex_home_path).to_mapping()
        )
        checks["thread_inventory"] = _timed_doctor_mapping(
            lambda: doctor_thread_inventory_check(
                codex_home=codex_home_path,
                default_provider=str(config.get("model_provider_id", "openai")),
            ).to_mapping()
        )
    else:
        checks["config"] = _timed_doctor_mapping(
            lambda: {
                "status": "fail",
                "summary": "config could not be loaded",
                "details": [config_error or "unknown config error"],
                "remediation": "Fix the reported config error, then rerun codex doctor.",
            }
        )
        if codex_home_path is not None:
            checks["state"] = _timed_doctor_mapping(
                lambda: doctor_fallback_state_check(codex_home=codex_home_path).to_mapping()
            )
        else:
            checks["state"] = _timed_doctor_mapping(lambda: doctor_fallback_state_check(error=config_error).to_mapping())

    checks["network"] = _timed_doctor_mapping(lambda: doctor_network_check().to_mapping())
    checks["terminal"] = _timed_doctor_mapping(
        lambda: doctor_terminal_check(no_color_flag="--no-color" in parsed.command_args).to_mapping()
    )
    reachability_plan = (
        default_reachability_plan()
        if config_error is not None
        else provider_reachability_plan_from_config(config=dict(config), stored_auth=stored_auth)
    )
    checks["provider_reachability"] = _timed_doctor_mapping(
        lambda: doctor_provider_reachability_check(plan=reachability_plan).to_mapping()
    )

    checks["git"] = _timed_doctor_mapping(lambda: doctor_git_check(cwd=Path.cwd()).to_mapping())

    check_statuses = [_doctor_cli_status(value.get("status")) for value in checks.values()]
    passed_count = sum(1 for status in check_statuses if status == "ok")
    failed_count = sum(1 for status in check_statuses if status == "fail")
    warning_count = sum(1 for status in check_statuses if status == "warn")
    overall_status = "fail" if failed_count else "ok" if warning_count == 0 else "warn"
    exit_code = 1 if failed_count else 0
    if "--json" in parsed.command_args:
        print(
            json.dumps(
                redacted_doctor_report_mapping(
                    checks=checks,
                    overall_status=overall_status,
                    codex_version=__version__,
                ),
                ensure_ascii=False,
                indent=2,
            ),
            file=stdout,
        )
        return exit_code

    if "--summary" in parsed.command_args or "--all" in parsed.command_args:
        print(
            "doctor: "
            f"{overall_status} "
            f"({passed_count} checks passed, "
            f"{warning_count} warnings, "
            f"{failed_count} failed)",
            file=stdout,
        )
        return exit_code

    print("doctor: checking local environment", file=stdout)
    display_checks = redacted_doctor_checks_mapping(checks)
    for key, data in display_checks.items():
        state = data.get("status", "warn")
        details = ", ".join(f"{name}={value}" for name, value in data.items() if name != "status")
        print(f"  - {key}: {state} ({details})", file=stdout)
    return exit_code


def _doctor_cli_status(status: object) -> str:
    normalized = str(status).strip().lower()
    if normalized == "warning":
        return "warn"
    if normalized in {"ok", "warn", "fail"}:
        return normalized
    return "warn"


def _timed_doctor_mapping(builder: Callable[[], dict[str, object]]) -> dict[str, object]:
    start = time.perf_counter()
    mapping = builder()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    mapping["duration_ms"] = max(elapsed_ms, 0)
    return mapping


def _doctor_installation_mapping(
    *,
    codex_home: Path | None,
    show_details: bool,
) -> dict[str, object]:
    return doctor_installation_check(
        codex_home=codex_home,
        show_details=show_details,
    ).to_mapping()


def _doctor_updates_mapping(
    *,
    config: dict[str, object],
    codex_home: Path,
) -> dict[str, object]:
    return doctor_updates_check_from_config(
        config,
        codex_home=codex_home,
        current_version=__version__,
    ).to_mapping()


def _run_sandbox(
    command_args: tuple[str, ...],
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    if any(arg in {"-h", "--help"} for arg in command_args):
        print(_unimplemented_command_help_text("sandbox"), file=stdout)
        return 0

    cwd: str | None = None
    permissions_profile: str | None = None
    include_managed_config = False
    index = 0
    command_start = None
    while index < len(command_args):
        arg = command_args[index]
        if arg == "--":
            command_start = index + 1
            break
        if arg == "--permissions-profile":
            permissions_profile = command_args[index + 1]
            index += 2
            continue
        if arg in {"--profile", "-p"}:
            index += 2
            continue
        if arg in {"--cd", "-C"}:
            cwd = command_args[index + 1]
            index += 2
            continue
        if arg == "--allow-unix-socket":
            index += 2
            continue
        if arg == "--include-managed-config":
            include_managed_config = True
            index += 1
            continue
        if arg == "--log-denials":
            index += 1
            continue
        if arg.startswith("-"):
            raise RuntimeError(f"Unexpected argument for sandbox: {arg}")
        command_start = index
        break

    command = command_args[command_start:] if command_start is not None else tuple()
    if not command:
        print(
            "pycodex: sandbox command not provided. Use `codex sandbox -- COMMAND...`.",
            file=stderr,
        )
        return 2

    if sys.platform == "darwin":
        sandbox_type = "seatbelt"
    elif sys.platform.startswith("win"):
        sandbox_type = "windows"
    else:
        sandbox_type = "landlock"

    try:
        plan = build_debug_sandbox_execution_plan(
            command,
            cwd=cwd,
            permissions_profile=permissions_profile,
            include_managed_config=include_managed_config,
            sandbox_type=sandbox_type,
            base_env=os.environ,
        )
    except RuntimeError as exc:
        print(f"pycodex: sandbox unavailable: {exc}", file=stderr)
        return 2
    except ValueError as exc:
        print(f"pycodex: sandbox execution failed: {exc}", file=stderr)
        return 2

    try:
        process = subprocess.run(
            list(debug_sandbox_subprocess_argv(plan)),
            cwd=plan.cwd,
            env=plan.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        print(f"pycodex: sandbox command not found: {command[0]}", file=stderr)
        if str(exc):
            print(f"details: {exc}", file=stderr)
        return 127
    except OSError as exc:
        print(f"pycodex: sandbox execution failed: {exc}", file=stderr)
        return 2

    if process.stdout:
        print(process.stdout, end="", file=stdout)
    if process.stderr:
        print(process.stderr, end="", file=stderr)
    return process.returncode


def _run_exec_server(*, parsed: "ParsedCli", stdout: TextIO, stderr: TextIO) -> int:
    if any(arg in {"-h", "--help"} for arg in parsed.command_args):
        print(_unimplemented_command_help_text("exec-server"), file=stdout)
        return 0

    listen = None
    remote = None
    environment_id = None
    name = None
    use_agent_identity_auth = False

    index = 0
    while index < len(parsed.command_args):
        arg = parsed.command_args[index]
        if arg == "--strict-config":
            index += 1
            continue
        if arg == "--listen":
            if index + 1 >= len(parsed.command_args):
                print("Missing value for --listen.", file=stderr)
                return 2
            listen = parsed.command_args[index + 1]
            index += 2
            continue
        if arg == "--remote":
            if index + 1 >= len(parsed.command_args):
                print("Missing value for --remote.", file=stderr)
                return 2
            remote = parsed.command_args[index + 1]
            index += 2
            continue
        if arg == "--environment-id":
            if index + 1 >= len(parsed.command_args):
                print("Missing value for --environment-id.", file=stderr)
                return 2
            environment_id = parsed.command_args[index + 1]
            index += 2
            continue
        if arg == "--name":
            if index + 1 >= len(parsed.command_args):
                print("Missing value for --name.", file=stderr)
                return 2
            name = parsed.command_args[index + 1]
            index += 2
            continue
        if arg == "--use-agent-identity-auth":
            use_agent_identity_auth = True
            index += 1
            continue
        print(f"pycodex: exec-server ignores unexpected positional argument: {arg}", file=stderr)
        return 2

    if remote is not None and listen is not None:
        print("pycodex: --listen cannot be used with --remote.", file=stderr)
        return 2

    if remote is not None and environment_id is None:
        print("pycodex: --environment-id is required when --remote is set.", file=stderr)
        return 2

    if use_agent_identity_auth and not os.environ.get("CODEX_ACCESS_TOKEN"):
        print(
            "CODEX_ACCESS_TOKEN is required when --use-agent-identity-auth is set.",
            file=stderr,
        )
        return 2

    payload = {
        "name": name or "default",
        "listen": listen,
        "remote": remote,
        "environment_id": environment_id,
        "use_agent_identity_auth": use_agent_identity_auth,
    }
    print("pycodex: exec-server config:", file=stdout)
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
    print(
        "pycodex: exec-server is not fully implemented in this Python port yet; command was accepted.",
        file=stderr,
    )
    return 0


def _run_login_status(*, stderr: TextIO) -> int:
    try:
        auth = read_auth_json()
        if auth is None:
            print("Not logged in", file=stderr)
            return 1
        resolved = resolve_auth_mode(auth)
    except (ValueError, OSError) as exc:
        print(f"Error checking login status: {exc}", file=stderr)
        return 2

    if resolved == AUTH_MODE_API_KEY:
        if not auth.openai_api_key:
            print("Error checking login status: API key auth is missing a key.", file=stderr)
            return 2
        print(f"Logged in using an API key - {safe_format_key(auth.openai_api_key)}", file=stderr)
    elif resolved in {AUTH_MODE_CHATGPT, AUTH_MODE_CHATGPT_AUTH_TOKENS}:
        print("Logged in using ChatGPT", file=stderr)
    else:
        print("Logged in using access token", file=stderr)
    return 0


def _parse_login_args(command_args: tuple[str, ...]) -> tuple[str, ...]:
    _parse_login_mode(command_args)
    return command_args


def _parse_login_mode(command_args: tuple[str, ...]) -> dict[str, object]:
    options = {
        "status": False,
        "with_api_key": False,
        "with_access_token": False,
        "api_key": None,
        "device_auth": False,
        "experimental_issuer": None,
        "experimental_client_id": None,
        "help": False,
    }
    i = 0
    while i < len(command_args):
        arg = command_args[i]
        if options["status"] and arg in {"-h", "--help"}:
            options["help"] = True
            i += 1
            continue
        if arg in {"-h", "--help"}:
            options["help"] = True
            i += 1
            continue
        if arg == "status":
            if options["status"]:
                raise CliParseError("login status was already specified")
            options["status"] = True
            i += 1
            continue
        if options["status"]:
            raise CliParseError("`status` does not accept extra login arguments.")
        if arg == "--with-api-key":
            options["with_api_key"] = True
            i += 1
            continue
        if arg == "--with-access-token":
            options["with_access_token"] = True
            i += 1
            continue
        if arg == "--api-key":
            if i + 1 < len(command_args) and not command_args[i + 1].startswith("-"):
                options["api_key"] = command_args[i + 1]
                i += 2
            else:
                options["api_key"] = ""
                i += 1
            continue
        if arg.startswith("--api-key="):
            options["api_key"] = arg[len("--api-key=") :]
            i += 1
            continue
        if arg == "--device-auth":
            options["device_auth"] = True
            i += 1
            continue
        if arg == "--experimental_issuer":
            if i + 1 >= len(command_args):
                raise CliParseError("Missing value for --experimental_issuer")
            options["experimental_issuer"] = command_args[i + 1]
            i += 2
            continue
        if arg.startswith("--experimental_issuer="):
            options["experimental_issuer"] = arg[len("--experimental_issuer=") :]
            i += 1
            continue
        if arg == "--experimental_client-id":
            if i + 1 >= len(command_args):
                raise CliParseError("Missing value for --experimental_client-id")
            options["experimental_client_id"] = command_args[i + 1]
            i += 2
            continue
        if arg.startswith("--experimental_client-id="):
            options["experimental_client_id"] = arg[len("--experimental_client-id=") :]
            i += 1
            continue
        raise CliParseError(f"Unknown argument for login: {arg}")

    if options["status"]:
        # status is a subcommand and takes precedence over login credential options when specified.
        return options

    if options["with_api_key"] and options["with_access_token"]:
        raise CliParseError("Choose one login credential source: --with-api-key or --with-access-token.")

    if options["device_auth"] and (options["with_api_key"] or options["with_access_token"]):
        raise CliParseError("Choose one login credential source: --with-api-key or --with-access-token.")

    if not options["with_api_key"] and not options["with_access_token"] and not options["status"] and options["api_key"] is not None:
        raise CliParseError(
            "The --api-key flag is no longer supported. Pipe the key instead, "
            "e.g. `printenv OPENAI_API_KEY | codex login --with-api-key`."
        )
    return options


def _read_stdin_text(
    stdin: object | None,
    *,
    required: bool,
    command: str,
    stderr: TextIO,
    stdin_is_terminal: bool | None = None,
) -> str | None:
    if stdin_is_terminal is None:
        if stdin is not None and hasattr(stdin, "isatty"):
            try:
                stdin_is_terminal = bool(stdin.isatty())  # type: ignore[union-attr]
            except Exception:
                stdin_is_terminal = False
        else:
            stdin_is_terminal = False

    if stdin is None:
        if required:
            print(f"{command} requires value from stdin.", file=stderr)
        return None

    if stdin_is_terminal:
        if command == "--with-api-key":
            print(
                "--with-api-key expects the API key on stdin. "
                "Try piping it, e.g. `printenv OPENAI_API_KEY | codex login --with-api-key`.",
                file=stderr,
            )
        elif command == "--with-access-token":
            print(
                "--with-access-token expects the access token on stdin. "
                "Try piping it, e.g. `printenv CODEX_ACCESS_TOKEN | codex login --with-access-token`.",
                file=stderr,
            )
        else:
            print(f"{command} requires value from stdin.", file=stderr)
        return None

    if command == "--with-api-key":
        print("Reading API key from stdin...", file=stderr)
    elif command == "--with-access-token":
        print("Reading access token from stdin...", file=stderr)

    if isinstance(stdin, str):
        value = stdin
    elif isinstance(stdin, bytes):
        value = stdin
    elif hasattr(stdin, "read"):
        try:
            value = stdin.read()  # type: ignore[union-attr]
        except Exception as exc:
            print(f"Failed to read stdin: {exc}", file=stderr)
            return None
    else:
        value = str(stdin)
    if value is None:
        value = ""
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            print(f"Failed to decode stdin as UTF-8: {exc}", file=stderr)
            return None
    text = value.strip()
    if required and not text:
        if command == "--with-api-key":
            print("No API key provided via stdin.", file=stderr)
        elif command == "--with-access-token":
            print("No access token provided via stdin.", file=stderr)
        else:
            print(f"{command} received empty stdin.", file=stderr)
        return None
    return text


def _is_valid_access_token(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False

    for index, part in enumerate(parts[:2]):
        padded = part + ("=" * ((4 - len(part) % 4) % 4))
        try:
            payload = base64.urlsafe_b64decode(padded)
        except Exception:
            return False
        if not payload:
            return False
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return False

        if index == 1:
            try:
                json.loads(text)
            except json.JSONDecodeError:
                return False

    return True


def _login_help_text() -> str:
    return (
        "Usage: codex login [status] [--with-api-key | --with-access-token | --device-auth]\n"
        "Manage login."
    )


def _build_exec_session_config(
    bootstrap: ExecConfigBootstrapPlan,
    *,
    exec_policy_rules: Iterable[ExecPolicyPrefixRule] = (),
) -> ExecSessionConfig:
    """Build the minimal session config for remote execution startup."""

    return replace(
        exec_session_config_from_bootstrap_plan(bootstrap),
        exec_policy_rules=tuple(exec_policy_rules),
    )


def _build_resume_args(exec_cli: ExecCli) -> tuple[dict[str, object] | None, str | None]:
    if exec_cli.command != "resume" or exec_cli.resume is None:
        return None, None

    resume_args: dict[str, object] = {
        "last": exec_cli.resume.last,
        "all": exec_cli.resume.all,
    }
    if exec_cli.resume.session_id is not None:
        resume_args["sessionId"] = exec_cli.resume.session_id

    return resume_args, direct_resume_thread_id(exec_cli.resume.session_id)


def _build_noninteractive_exec_event_processor(exec_cli: ExecCli) -> HumanEventProcessor | JsonEventProcessor:
    if exec_cli.json:
        return JsonEventProcessor(last_message_path=exec_cli.last_message_file)
    return HumanEventProcessor(last_message_path=exec_cli.last_message_file)


def _resolve_exec_remote_endpoint(
    parsed: "ParsedCli", bootstrap_plan: ExecConfigBootstrapPlan
) -> tuple[str, RemoteAppServerEndpoint, Path]:
    codex_home = Path(find_codex_home())
    remote_arg = parsed.remote
    if remote_arg is None:
        remote_arg = f"unix://{app_server_control_socket_path(codex_home)}"

    endpoint = resolve_remote_endpoint(
        remote_arg,
        remote_auth_token_env=parsed.remote_auth_token_env,
        codex_home=codex_home,
        cwd=bootstrap_plan.config_cwd,
    )
    if endpoint is None:
        raise ValueError("failed to resolve a usable execution endpoint")
    return remote_arg, endpoint, Path(codex_home)


def _print_local_app_server_connect_hint(
    endpoint: RemoteAppServerEndpoint,
    codex_home: Path,
    connect_error: str | None = None,
    *,
    stderr: TextIO,
) -> None:
    if endpoint.kind != "unix_socket" or endpoint.socket_path is None:
        print(
            f"pycodex: failed to connect to remote execution endpoint `{endpoint.endpoint}`.",
            file=stderr,
        )
        if connect_error:
            print(f"pycodex: {connect_error}", file=stderr)
        print("pycodex: ensure the remote endpoint is reachable and running.", file=stderr)
        return

    state_path = codex_home / _APP_SERVER_STATE_FILE
    state_summary = "state file missing"
    if state_path.exists():
        try:
            state = _read_json_state(state_path)
        except RuntimeError as exc:
            state_summary = f"failed to read state: {exc}"
        else:
            daemon_state = state.get("daemon")
            if isinstance(daemon_state, MutableMapping):
                if bool(daemon_state.get("running")):
                    state_summary = "state says running"
                else:
                    state_summary = "state says not running"
            else:
                state_summary = "state file invalid"

    print(
        f"pycodex: app-server state: {state_summary}. CODEX_HOME={codex_home}.",
        file=stderr,
    )

    normalized_error = connect_error.lower() if connect_error is not None else ""
    if endpoint.socket_path.exists():
        if "permission denied" in normalized_error:
            print(
                "pycodex: cannot access local app-server socket due to permissions.",
                file=stderr,
            )
        elif "connection refused" in normalized_error:
            print(
                "pycodex: local app-server socket exists but the app-server is not accepting connections yet.",
                file=stderr,
            )
        elif "timed out" in normalized_error:
            print(
                "pycodex: local app-server socket connection timed out while waiting for startup.",
                file=stderr,
            )
        else:
            print(
                f"pycodex: cannot connect to local app-server socket `{endpoint.socket_path}`.",
                file=stderr,
            )

    if not endpoint.socket_path.exists():
        print(
            f"pycodex: local app-server socket not found at `{endpoint.socket_path}`.",
            file=stderr,
        )
        print(
            "pycodex: ensure app-server has started and created the socket path.",
            file=stderr,
        )
        if state_summary == "state says running":
            print(
                "pycodex: app-server state still reports running; socket may be stale or permission-limited.",
                file=stderr,
            )
    print("pycodex: start the local app-server first, for example:", file=stderr)
    print("  codex app-server daemon start", file=stderr)
    print("  codex app-server daemon bootstrap", file=stderr)


def _run_noninteractive_exec(
    parsed: "ParsedCli",
    *,
    stdout: TextIO | None = None,
    stderr: TextIO,
    stdin: object | None = None,
    stdin_is_terminal: bool | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    try:
        if parsed.command == "exec":
            if (
                parsed.remote is not None or parsed.remote_auth_token_env is not None
            ) and not local_http_exec_enabled(os.environ):
                exec_cli = parse_exec_args(
                    parsed.command_args,
                    root_config_overrides=parsed.config_overrides_with_feature_toggles(),
                )
                exec_cli = _inherit_exec_root_options(exec_cli, parsed)
            else:
                exec_cli = parsed.exec_cli()
        elif parsed.command in {"review", "resume"}:
            if parsed.command == "review":
                reject_remote_mode_for_subcommand(parsed.remote, parsed.remote_auth_token_env, "review")
            # Top-level `codex review` and `codex resume` are aliases for `codex exec` subcommands.
            exec_cli = parse_exec_args(
                (parsed.command, *parsed.command_args),
                root_config_overrides=parsed.config_overrides_with_feature_toggles(),
            )
            exec_cli = _inherit_exec_root_options(exec_cli, parsed)
        else:
            print(
                f"pycodex: unsupported non-interactive command: {parsed.command}",
                file=stderr,
            )
            return 2
    except (CliParseError, ExecCliParseError) as exc:
        print(str(exc), file=stderr)
        return 2

    if warning := exec_cli.removed_full_auto_warning():
        print(warning, file=stderr)

    try:
        codex_home = Path(find_codex_home())
        config_toml = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
        migration_status = maybe_migrate_personality(
            codex_home,
            config_toml,
            override_profile=str(exec_cli.profile) if exec_cli.profile is not None else None,
        )
        if migration_status == PersonalityMigrationStatus.APPLIED:
            config_toml = read_toml_mapping(codex_home / CONFIG_TOML_FILE)
        bootstrap_plan = build_exec_config_bootstrap_plan(exec_cli, config_toml=config_toml)
        plan = prepare_exec_run_plan(
            exec_cli,
            stdin=stdin,
            stdin_is_terminal=stdin_is_terminal,
            stderr=stderr,
        )
        ensure_exec_trusted_directory(
            exec_trusted_directory_check(exec_cli, bootstrap_plan.config_cwd)
        )
    except (ExecConfigPlanError, ExecRunError, ValueError) as exc:
        print(str(exc), file=stderr)
        return 2

    command_name = parsed.command
    print(f"pycodex: prepared non-interactive {command_name} plan.", file=stderr)
    if command_name == "review" and not (local_http_exec_enabled() or core_exec_enabled()):
        return 0

    if core_exec_enabled():
        processor = _build_noninteractive_exec_event_processor(exec_cli)
        try:
            exec_policy_rules = _execpolicy_rules_for_local_http_exec(
                codex_home,
                bootstrap_plan.config_cwd,
                ignore_rules=exec_cli.ignore_rules,
            )
            session_config = _build_exec_session_config(
                bootstrap_plan,
                exec_policy_rules=exec_policy_rules,
            )
            if isinstance(processor, HumanEventProcessor):
                processor.configure_from_config(session_config)
            auth_json = read_auth_json()
            model_client, provider, model_info, resolved_auth = build_default_core_exec_runtime(
                session_config,
                auth=auth_json,
                config_toml=config_toml,
            )
            resolved_resume_rollout_path = None
            if exec_cli.command == "resume":
                resume_target = resolve_core_exec_resume_target(
                    codex_home,
                    session_config,
                    model_client,
                    exec_cli.resume,
                )
                if resume_target is not None:
                    resolved_resume_rollout_path = resume_target.rollout_path
            emit_core_exec_config_summary(
                processor,
                session_config,
                plan,
                model_client,
                model_info,
                rollout_path=resolved_resume_rollout_path,
                stdout=out,
                stderr=stderr,
                version=__version__,
            )
            local_result = asyncio.run(
                run_core_exec_command(
                    exec_cli.command,
                    codex_home,
                    session_config,
                    plan,
                    model_client,
                    provider,
                    model_info,
                    resume_args=exec_cli.resume,
                    resume_target=resume_target if exec_cli.command == "resume" else None,
                    resume_target_resolved=exec_cli.command == "resume",
                    auth=resolved_auth,
                    max_tool_followups=local_http_exec_max_tool_rounds(),
                    cli_version=__version__,
                )
            )
        except ValueError as exc:
            emit_local_http_exec_error(processor, str(exc), stdout=out, stderr=stderr)
            return 2
        except (OSError, RuntimeError) as exc:
            emit_local_http_exec_error(processor, str(exc), stdout=out, stderr=stderr)
            return 1

        emit_core_exec_result(
            command_name,
            processor,
            local_result,
            session_config,
            stdout=out,
            stderr=stderr,
        )
        return 0

    if local_http_exec_enabled():
        processor = _build_noninteractive_exec_event_processor(exec_cli)
        try:
            exec_policy_rules = _execpolicy_rules_for_local_http_exec(
                codex_home,
                bootstrap_plan.config_cwd,
                ignore_rules=exec_cli.ignore_rules,
            )
            session_config = _build_exec_session_config(
                bootstrap_plan,
                exec_policy_rules=exec_policy_rules,
            )
            if isinstance(processor, HumanEventProcessor):
                processor.configure_from_config(session_config)
            auth_json = read_auth_json()
            model_client, provider, model_info, resolved_auth = build_default_local_http_exec_runtime(
                session_config,
                auth=auth_json,
                config_toml=config_toml,
            )
            resolved_thread_id = None
            session_name = None
            use_shell_tools = False
            resolved_resume_rollout_path = None
            if exec_cli.command == "resume":
                if exec_cli.resume is None:
                    raise ValueError("resume command is missing resume arguments")
                resolved_thread_id = direct_resume_thread_id(exec_cli.resume.session_id)
                session_name = (
                    exec_cli.resume.session_id
                    if exec_cli.resume.session_id is not None and resolved_thread_id is None
                    else None
                )
                resolved_resume_rollout_path = align_local_http_exec_resume_model_client(
                    codex_home,
                    session_config,
                    model_client,
                    thread_id=resolved_thread_id,
                    session_name=session_name,
                    resume_last=exec_cli.resume.last,
                    include_all=exec_cli.resume.all,
                )
                if resolved_resume_rollout_path is None:
                    raise ValueError("no local rollout found for resume")
                use_shell_tools = local_http_exec_shell_tools_enabled()
            summary_config, summary_session = local_http_exec_config_summary(
                session_config,
                model=model_info.slug,
                provider_id=session_config.model_provider_id or "openai",
                session_id=str(model_client.state.session_id),
                thread_id=str(model_client.state.thread_id),
                initial_messages=(
                    local_http_exec_initial_messages_from_rollout(resolved_resume_rollout_path)
                    if resolved_resume_rollout_path is not None
                    else None
                ),
                rollout_path=resolved_resume_rollout_path,
            )
            if isinstance(processor, JsonEventProcessor):
                processor.print_config_summary(summary_config, plan.prompt_summary, summary_session, output=out)
            else:
                processor.print_config_summary(
                    summary_config,
                    plan.prompt_summary,
                    summary_session,
                    stderr=stderr,
                    version=__version__,
                )
            if exec_cli.command == "review":
                use_shell_tools = local_http_exec_shell_tools_enabled()
                local_result = asyncio.run(
                    run_exec_review_http_sampling(
                        session_config,
                        plan,
                        model_client,
                        provider,
                        model_info,
                        auth=resolved_auth,
                        use_shell_tools=use_shell_tools,
                        max_tool_rounds=local_http_exec_max_tool_rounds() if use_shell_tools else 1,
                        tool_output_max_chars=local_http_exec_tool_output_max_chars() if use_shell_tools else None,
                    )
                )
                persist_local_http_exec_rollout(
                    codex_home,
                    session_config,
                    local_result,
                    model_client,
                    input_items=local_http_review_rollout_input_items(local_result),
                    cli_version=__version__,
                )
            elif exec_cli.command == "resume":
                local_result = asyncio.run(
                    run_exec_resume_user_turn_http_sampling(
                        codex_home,
                        session_config,
                        plan,
                        model_client,
                        provider,
                        model_info,
                        thread_id=resolved_thread_id,
                        session_name=session_name,
                        resume_last=exec_cli.resume.last,
                        include_all=exec_cli.resume.all,
                        auth=resolved_auth,
                        use_shell_tools=use_shell_tools,
                        max_tool_rounds=local_http_exec_max_tool_rounds() if use_shell_tools else 1,
                        tool_output_max_chars=local_http_exec_tool_output_max_chars() if use_shell_tools else None,
                        resolved_rollout_path=resolved_resume_rollout_path,
                    )
                )
            else:
                run_local_http_sampling = (
                    run_exec_user_turn_with_shell_tools_http_sampling
                    if local_http_exec_shell_tools_enabled()
                    else run_exec_user_turn_http_sampling
                )
                sampling_kwargs = {"auth": resolved_auth}
                if run_local_http_sampling is run_exec_user_turn_with_shell_tools_http_sampling:
                    sampling_kwargs["max_tool_rounds"] = local_http_exec_max_tool_rounds()
                    sampling_kwargs["tool_output_max_chars"] = local_http_exec_tool_output_max_chars()
                local_result = asyncio.run(
                    run_local_http_sampling(
                        session_config,
                        plan,
                        model_client,
                        provider,
                        model_info,
                        **sampling_kwargs,
                    )
                )
                persist_local_http_exec_rollout(
                    codex_home,
                    session_config,
                    local_result,
                    model_client,
                    input_items=plan.initial_operation.items if plan.initial_operation.kind == "user_turn" else (),
                    cli_version=__version__,
                )
        except ValueError as exc:
            emit_local_http_exec_error(processor, str(exc), stdout=out, stderr=stderr)
            return 2
        except (OSError, RuntimeError) as exc:
            emit_local_http_exec_error(processor, str(exc), stdout=out, stderr=stderr)
            return 1

        emit_local_http_exec_result(
            processor,
            local_result,
            config=session_config,
            stdout=out,
            stderr=stderr,
        )
        print(f"pycodex: completed local HTTP non-interactive {command_name} execution.", file=stderr)
        return 0

    try:
        remote_arg, endpoint, codex_home = _resolve_exec_remote_endpoint(parsed, bootstrap_plan)
        if parsed.remote is None:
            print(
                f"pycodex: no --remote provided; attempting local app-server endpoint {remote_arg}.",
                file=stderr,
            )
        connect_args = RemoteAppServerConnectArgs(
            endpoint=endpoint,
            client_name="codex-python",
            client_version=__version__,
        )
        session_config = _build_exec_session_config(bootstrap_plan)
        resume_args, resolved_thread_id = _build_resume_args(exec_cli)
        processor = _build_noninteractive_exec_event_processor(exec_cli)
        if isinstance(processor, HumanEventProcessor):
            processor.configure_from_config(session_config)
        result = remote_exec_session_connect_and_run(
            connect_args,
            session_config,
            plan,
            processor=processor,
            resume_args=resume_args,
            resolved_thread_id=resolved_thread_id,
            json_mode=exec_cli.json,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        print(str(exc), file=stderr)
        return 1

    if result.error_message is not None:
        if parsed.remote is not None:
            print(
                f"pycodex: failed to connect to remote execution endpoint `{remote_arg}`.",
                file=stderr,
            )
        print(result.error_message, file=stderr)
    if not result.ok and parsed.remote is None:
        _print_local_app_server_connect_hint(
            endpoint,
            codex_home,
            connect_error=result.error_message,
            stderr=stderr,
        )
    if not result.ok:
        return result.exit_code

    print(f"pycodex: completed non-interactive {command_name} execution.", file=stderr)
    return result.exit_code


def _reject_unsupported_strict_config_command(command: str | None, command_args: tuple[str, ...]) -> None:
    if command == "remote-control":
        strict_name = _remote_control_strict_subcommand_name(command_args)
        raise CliParseError(f"`--strict-config` is not supported for `codex {strict_name}`")

    if command in _UNSUPPORTED_STRICT_CONFIG_COMMANDS:
        command_name = command.replace("_", "-")
        raise CliParseError(f"`--strict-config` is not supported for `codex {command_name}`")
    if command == "app-server":
        strict_name = _app_server_strict_subcommand_name(command_args)
        if strict_name is not None:
            raise CliParseError(f"`--strict-config` is not supported for `codex {strict_name}`")


def _reject_profile_v2_for_subcommand(command: str, command_args: tuple[str, ...]) -> None:
    if command in {"exec", "review", "resume", "fork", "mcp", "sandbox"}:
        return
    if command == "debug" and command_args and command_args[0] == "prompt-input":
        return
    raise CliParseError(_PROFILE_V2_UNSUPPORTED_MESSAGE)


def _remote_command_name_for_subcommand(command: str, command_args: tuple[str, ...]) -> str:
    if command == "features":
        first = _first_non_option_arg(command_args)
        if first in {"list", "enable", "disable"}:
            return f"features {first}"
        return "features"

    if command == "app-server":
        return _app_server_strict_subcommand_name(command_args) or "app-server"

    if command == "remote-control":
        first = _first_non_option_arg(command_args)
        if first in {"start", "stop"}:
            return f"remote-control {first}"
        return "remote-control"

    if command == "debug":
        first = _first_non_option_arg(command_args)
        if first in {
            "models",
            "app-server",
            "prompt-input",
            "trace-reduce",
            "clear-memories",
        }:
            return f"debug {first}"
        return "debug"

    if command == "execpolicy":
        first = _first_non_option_arg(command_args)
        if first == "check":
            return "execpolicy check"
        return "execpolicy"

    return command


def _app_server_strict_subcommand_name(command_args: tuple[str, ...]) -> str | None:
    if not command_args:
        return None

    command_args = _app_server_command_args_for_help(command_args)
    if not command_args:
        return None

    first = command_args[0]
    if first == "daemon":
        return _app_server_daemon_subcommand_name(command_args[1:])
    if first == "proxy":
        return "app-server proxy"
    if first == "generate-ts":
        return "app-server generate-ts"
    if first == "generate-json-schema":
        return "app-server generate-json-schema"
    if first == "generate-internal-json-schema":
        return "app-server generate-internal-json-schema"
    return "app-server"


def _remote_control_strict_subcommand_name(command_args: tuple[str, ...]) -> str:
    for arg in command_args:
        if arg.startswith("-"):
            continue
        if arg in {"start", "stop"}:
            return f"remote-control {arg}"
        break
    return "remote-control"


def _app_server_daemon_subcommand_name(args: tuple[str, ...]) -> str:
    if not args:
        return "app-server daemon"

    daemon_command = args[0]
    if daemon_command == "bootstrap":
        return "app-server daemon bootstrap"
    if daemon_command == "start":
        return "app-server daemon start"
    if daemon_command == "restart":
        return "app-server daemon restart"
    if daemon_command == "enable-remote-control":
        return "app-server daemon enable-remote-control"
    if daemon_command == "disable-remote-control":
        return "app-server daemon disable-remote-control"
    if daemon_command == "stop":
        return "app-server daemon stop"
    if daemon_command == "version":
        return "app-server daemon version"
    if daemon_command == "pid-update-loop":
        return "app-server daemon pid-update-loop"
    return "app-server daemon"


_REMOTE_ROOT_OPTION_SUBCOMMANDS = {"resume", "fork", "exec", "review"}


def reject_remote_mode_for_subcommand(
    remote: str | None,
    remote_auth_token_env: str | None,
    subcommand: str,
) -> None:
    if remote is not None:
        raise CliParseError(
            f"`--remote {remote}` is only supported for interactive TUI commands, not `codex {subcommand}`"
        )
    if remote_auth_token_env is not None:
        raise CliParseError(
            "`--remote-auth-token-env` is only supported for interactive TUI commands, "
            f"not `codex {subcommand}`"
        )


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
        approval_policy=exec_cli.approval_policy
        if exec_cli.approval_policy is not None
        else _typed_root_value(root, "approval_policy", AskForApproval),
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



