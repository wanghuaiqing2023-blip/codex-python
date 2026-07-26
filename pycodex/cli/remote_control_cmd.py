"""Rust-aligned implementation of codex-cli::remote_control_cmd."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import socket
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, TextIO
from pycodex import __version__
from pycodex.utils.home_dir import find_codex_home
from .main.spec import CliParseError

def _find_codex_home() -> Path:
    try:
        return find_codex_home()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise RuntimeError(f"failed to resolve CODEX_HOME: {exc}") from exc


def _read_remote_control_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read {path}: {exc}") from exc
    if isinstance(raw, dict):
        return raw
    raise RuntimeError(f"invalid state format in {path}: expected object")


def _write_remote_control_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

def parse_args(args: tuple[str, ...]) -> tuple[str, ...]:
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

_APP_SERVER_STATE_FILE = "app-server-state.json"

def run(
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
        codex_home = _find_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    state_path = codex_home / _APP_SERVER_STATE_FILE
    try:
        state = _read_remote_control_state(state_path)
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
        _write_remote_control_state(state_path, state)
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
        codex_home = _find_codex_home()
    except RuntimeError as exc:
        print(f"pycodex: {exc}", file=stderr)
        return 2

    state_path = codex_home / _APP_SERVER_STATE_FILE
    try:
        state = _read_remote_control_state(state_path)
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
        _write_remote_control_state(state_path, state)
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

def help_text(command_args: tuple[str, ...]) -> str:
    for arg in command_args:
        if arg.startswith("-"):
            continue
        if arg in {"start", "stop"}:
            return f"Usage: codex remote-control {arg}"
        break
    return "Usage: codex remote-control [OPTIONS]"

