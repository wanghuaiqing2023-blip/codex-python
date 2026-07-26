"""Rust-aligned implementation of codex-cli::mcp_cmd."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, TextIO
from pycodex.core.config.edit import CONFIG_TOML_FILE, read_toml_mapping, write_toml_mapping
from pycodex.utils.home_dir import find_codex_home
from .main.spec import CliParseError

def _find_codex_home() -> Path:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise RuntimeError(f"failed to resolve CODEX_HOME: {exc}") from exc


def _read_mcp_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read {path}: {exc}") from exc
    if isinstance(raw, dict):
        return raw
    raise RuntimeError(f"invalid state format in {path}: expected object")


def _write_mcp_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

def parse_args(args: tuple[str, ...]) -> tuple[str, ...]:
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

_MCP_SUBCOMMANDS = {"list", "get", "add", "remove", "login", "logout"}

_MCP_STATE_FILE = "mcp-state.json"

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
    validate_server_name(name)

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
            key, value = parse_env_pair(env_pair)
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

def parse_env_pair(raw: str) -> tuple[str, str]:
    key, separator, value = raw.partition("=")
    key = key.strip()
    if not separator or not key:
        raise RuntimeError("environment entries must be in KEY=VALUE form")
    return key, value

def validate_server_name(name: str) -> None:
    if name and all(ch.isascii() and (ch.isalnum() or ch in {"-", "_"}) for ch in name):
        return
    raise RuntimeError(f"invalid server name '{name}' (use letters, numbers, '-', '_')")

def run(command_args: tuple[str, ...], *, stdout: TextIO, stderr: TextIO) -> int:
    if not command_args:
        print("Usage: codex mcp [OPTIONS] <SUBCOMMAND>", file=stdout)
        return 0

    try:
        codex_home = _find_codex_home()
        auth_state = _read_mcp_state(codex_home / _MCP_STATE_FILE)
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
            validate_server_name(name)
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
                    _write_mcp_state(codex_home / _MCP_STATE_FILE, auth_state)
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
                _write_mcp_state(codex_home / _MCP_STATE_FILE, auth_state)
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
                _write_mcp_state(codex_home / _MCP_STATE_FILE, auth_state)
            except OSError as exc:
                print(f"pycodex: failed to write MCP login state: {exc}", file=stderr)
                return 2
            print(f"Logged out MCP server '{name}'.", file=stdout)
            return 0

    print(f"Unrecognized mcp subcommand: {subcommand}", file=stderr)
    return 64

def help_text(command_args: tuple[str, ...]) -> str:
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

