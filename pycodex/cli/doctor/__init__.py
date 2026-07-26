"""Rust-aligned implementation for codex-cli doctor::parent."""



from __future__ import annotations

import ctypes

from dataclasses import dataclass

import gc

import json

import locale

import os

import platform

import socket

import stat

from pathlib import Path

import shutil

import sqlite3

import subprocess

import sys

import time

import tomllib

from typing import Any, Callable, Mapping

from urllib.error import HTTPError, URLError

from urllib.request import Request, urlopen

from urllib.parse import parse_qsl

from urllib.parse import urlparse

from contextlib import suppress

from pycodex.exec.session import UDS_WEBSOCKET_HANDSHAKE_URL

from pycodex.codex_api.error import ApiError

from pycodex.codex_api.endpoint.responses_websocket import (
    ResponsesWebsocketClient,
    connect_websocket as responses_connect_websocket,
)

from pycodex.codex_api.provider import Provider, RetryConfig

from pycodex.core import OPENAI_BETA_HEADER, RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE

from pycodex.exec.websocket import (
    StdlibWebSocket,
    websocket_frame_event,
)

from pycodex.model_provider.auth import unauthenticated_auth_provider

from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider

from pycodex.tui.update_action import UpdateAction

from pycodex.tui.update_versions import is_newer



PACKAGE_METADATA_FILENAME = "codex-package.json"

LOCALE_ENV_VARS = ("LC_ALL", "LC_CTYPE", "LANG")

AUTH_ENV_VARS = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")

PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)

CA_ENV_VARS = ("CODEX_CA_CERTIFICATE", "SSL_CERT_FILE")

U64_MAX = (1 << 64) - 1

_DEFAULT_WEBSOCKET_ENDPOINT = "wss://api.openai.com/v1/responses"

_DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS = 15_000

_WEBSOCKET_IMMEDIATE_CLOSE_GRACE_SECONDS = 0.25

_WS_REASONING_HEADER = "x-reasoning-included"

_WS_MODELS_ETAG_HEADER = "x-models-etag"

_WS_OPENAI_MODEL_HEADER = "openai-model"

def _dns_address_family_details(host: str, port: int) -> tuple[str, ...]:
    try:
        addresses = socket.getaddrinfo(host, port)
    except Exception as exc:
        return (f"DNS: lookup failed ({exc})",)
    ipv4_count = sum(1 for family, *_ in addresses if family == socket.AF_INET)
    ipv6_count = sum(1 for family, *_ in addresses if family == socket.AF_INET6)
    if addresses:
        first_address = addresses[0][0]
        first_family = (
            "IPv4"
            if first_address == socket.AF_INET
            else "IPv6" if first_address == socket.AF_INET6 else "other"
        )
    else:
        first_family = "none"
    return (f"DNS: {ipv4_count} IPv4, {ipv6_count} IPv6, first {first_family}",)

JsonGetter = Callable[[str], Any]

CommandRunner = Callable[[str, tuple[str, ...]], str]

GitCommandRunner = Callable[[Path, tuple[str, ...], Path], str | None]

HttpStatusProbe = Callable[[str, str], int]

AppServerVersionProbe = Callable[[Path], str]

DOCTOR_CHECK_METADATA = {
    "auth": ("auth.credentials", "auth"),
    "background_server": ("app_server.status", "app-server"),
    "config": ("config.load", "config"),
    "git": ("git.environment", "git"),
    "installation": ("installation", "install"),
    "mcp": ("mcp.config", "mcp"),
    "network": ("network.env", "network"),
    "provider_reachability": ("network.provider_reachability", "reachability"),
    "runtime": ("runtime.provenance", "runtime"),
    "sandbox": ("sandbox.helpers", "sandbox"),
    "search": ("runtime.search", "search"),
    "state": ("state.paths", "state"),
    "system": ("system.environment", "system"),
    "terminal": ("terminal.env", "terminal"),
    "terminal_title": ("terminal.title", "title"),
    "thread_inventory": ("state.rollout_db_parity", "threads"),
    "updates": ("updates.status", "updates"),
    "websocket": ("network.websocket_reachability", "websocket"),
}

@dataclass(frozen=True)
class DoctorUpdateCheck:
    status: str
    summary: str
    details: tuple[str, ...]
    remediation: str | None = None
    issues: tuple[dict[str, Any], ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        mapping: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
        }
        if self.remediation is not None:
            mapping["remediation"] = self.remediation
        if self.issues:
            mapping["issues"] = [dict(issue) for issue in self.issues]
        return mapping

@dataclass(frozen=True)
class NpmRootCheck:
    kind: str
    package_root: Path | None = None
    running_package_root: Path | None = None
    npm_package_root: Path | None = None
    error: str | None = None

    @classmethod
    def match(cls, package_root: str | Path) -> "NpmRootCheck":
        return cls(kind="match", package_root=Path(package_root))

    @classmethod
    def mismatch(cls, running_package_root: str | Path, npm_package_root: str | Path) -> "NpmRootCheck":
        return cls(
            kind="mismatch",
            running_package_root=Path(running_package_root),
            npm_package_root=Path(npm_package_root),
        )

    @classmethod
    def missing_package_root(cls) -> "NpmRootCheck":
        return cls(kind="missing_package_root")

    @classmethod
    def npm_unavailable(cls, error: str) -> "NpmRootCheck":
        return cls(kind="npm_unavailable", error=error)

@dataclass(frozen=True)
class DoctorInteractiveConfigOverrides:
    model: str | None = None
    model_provider: str | None = None
    cwd: Path | None = None
    approval_policy: Any = None
    sandbox_mode: Any = None
    show_raw_agent_reasoning: bool | None = None
    additional_writable_roots: tuple[Path, ...] = ()
    codex_self_exe: Path | None = None
    codex_linux_sandbox_exe: Path | None = None
    main_execve_wrapper_exe: Path | None = None

def doctor_config_overrides_from_interactive(
    interactive: Any,
    arg0_paths: Mapping[str, Any] | Any | None = None,
) -> DoctorInteractiveConfigOverrides:
    options = getattr(interactive, "root_options", interactive)
    if not isinstance(options, Mapping):
        options = {}
    arg0 = arg0_paths or {}

    def arg0_path(name: str) -> Path | None:
        value = arg0.get(name) if isinstance(arg0, Mapping) else getattr(arg0, name, None)
        return Path(value) if value is not None else None

    add_dirs = options.get("add_dir", ())
    if isinstance(add_dirs, (str, Path)):
        add_dirs = (add_dirs,)

    return DoctorInteractiveConfigOverrides(
        model=_optional_str(options.get("model")),
        model_provider=_optional_str(options.get("local_provider")),
        cwd=Path(options["cwd"]) if options.get("cwd") is not None else None,
        approval_policy=options.get("approval_policy"),
        sandbox_mode=options.get("sandbox"),
        show_raw_agent_reasoning=True if options.get("oss") else None,
        additional_writable_roots=tuple(Path(path) for path in add_dirs),
        codex_self_exe=arg0_path("codex_self_exe"),
        codex_linux_sandbox_exe=arg0_path("codex_linux_sandbox_exe"),
        main_execve_wrapper_exe=arg0_path("main_execve_wrapper_exe"),
    )

def doctor_cli_overrides_for_load_config(root_config_overrides: Any, interactive: Any) -> tuple[str, ...]:
    options = getattr(interactive, "root_options", interactive)
    if not isinstance(options, Mapping):
        options = {}
    overrides = tuple(str(value) for value in (root_config_overrides or ()))
    if options.get("search"):
        overrides = (*overrides, "web_search=live")
    return overrides

@dataclass(frozen=True)
class TerminalCheckInputs:
    terminal: str = "unknown"
    term_program: str | None = None
    version: str | None = None
    term: str | None = None
    multiplexer: str | None = None
    stdin_is_terminal: bool = False
    stdout_is_terminal: bool = False
    stderr_is_terminal: bool = False
    stream_supports_color: bool = False
    terminal_size: tuple[int, int] | str = "unavailable"
    env: dict[str, str] | None = None
    present_env: set[str] | None = None
    no_color_flag: bool = False
    tmux_details: tuple[str, ...] = ()
    windows_console_details: tuple[str, ...] = ()

@dataclass(frozen=True)
class StateCheckInputs:
    codex_home: Path
    log_dir: Path
    sqlite_home: Path
    standalone_releases_dir: Path | None = None

@dataclass(frozen=True)
class FallbackStateCheckInputs:
    codex_home: Path | None = None
    error: str | None = None

@dataclass(frozen=True)
class ConfigCheckInputs:
    codex_home: Path
    cwd: Path
    log_dir: Path
    sqlite_home: Path
    config: dict[str, Any]
    startup_warnings: tuple[str, ...] = ()

@dataclass(frozen=True)
class AuthCheckInputs:
    codex_home: Path
    auth_storage_mode: str = "file"
    provider_requires_openai_auth: bool = True
    provider_env_key: str | None = None
    provider_env_key_instructions: str | None = None
    env: dict[str, str] | None = None

@dataclass(frozen=True)
class NetworkCheckInputs:
    env: dict[str, str]

@dataclass(frozen=True)
class SandboxCheckInputs:
    approval_policy: str = "unknown"
    filesystem_sandbox: str = "unknown"
    network_sandbox: str = "unknown"
    codex_linux_sandbox_helper: Path | None = None
    execve_wrapper_helper: Path | None = None

@dataclass(frozen=True)
class WebsocketCheckInputs:
    model_provider_id: str = "openai"
    provider_name: str = "OpenAI"
    wire_api: str = "responses"
    supports_websockets: bool = False
    connect_timeout_ms: int | None = None
    auth_mode: str | None = None
    endpoint: str | None = None
    env: dict[str, str] | None = None
    probe_error: str | None = None

@dataclass(frozen=True)
class ReachabilityEndpoint:
    label: str
    url: str
    required: bool = True
    route_probe_url: str | None = None

@dataclass(frozen=True)
class ReachabilityPlan:
    description: str
    endpoints: tuple[ReachabilityEndpoint, ...]

def doctor_config_check(
    *,
    codex_home: str | Path,
    cwd: str | Path | None = None,
    log_dir: str | Path | None = None,
    sqlite_home: str | Path | None = None,
    config: dict[str, Any] | None = None,
    startup_warnings: tuple[str, ...] = (),
) -> DoctorUpdateCheck:
    codex_home_path = Path(codex_home)
    inputs = ConfigCheckInputs(
        codex_home=codex_home_path,
        cwd=Path.cwd() if cwd is None else Path(cwd),
        log_dir=codex_home_path / "log" if log_dir is None else Path(log_dir),
        sqlite_home=codex_home_path if sqlite_home is None else Path(sqlite_home),
        config={} if config is None else config,
        startup_warnings=startup_warnings,
    )
    details = [
        f"cwd: {inputs.cwd}",
        f"model: {_config_string(inputs.config, 'model', '<default>')}",
        f"model provider: {_config_string(inputs.config, 'model_provider', 'openai')}",
        f"log dir: {inputs.log_dir}",
        f"sqlite home: {inputs.sqlite_home}",
        f"mcp servers: {_mapping_len(inputs.config.get('mcp_servers'))}",
    ]
    _push_feature_flag_details(details, inputs.config)
    _push_config_toml_details(details, inputs.codex_home)
    if inputs.startup_warnings:
        _push_startup_warning_counts(details, inputs.startup_warnings)
        details.extend(f"startup warning: {warning}" for warning in inputs.startup_warnings)
        return DoctorUpdateCheck(status="warn", summary="config loaded", details=tuple(details))
    return DoctorUpdateCheck(status="ok", summary="config loaded", details=tuple(details))

def doctor_fallback_state_check(
    *,
    codex_home: str | Path | None = None,
    error: str | None = None,
    resolver: Callable[[], str | Path] | None = None,
) -> DoctorUpdateCheck:
    if codex_home is None and error is None:
        try:
            if resolver is None:
                raw_home = os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
            else:
                raw_home = resolver()
            codex_home = Path(raw_home)
        except Exception as exc:
            error = str(exc)
    if codex_home is not None:
        path = Path(codex_home)
        return DoctorUpdateCheck(
            status="ok",
            summary="CODEX_HOME was resolved without config",
            details=(f"CODEX_HOME: {path}",),
        )
    return DoctorUpdateCheck(
        status="warn",
        summary="CODEX_HOME could not be resolved",
        details=(error or "unknown error",),
    )

def doctor_auth_check(
    *,
    codex_home: str | Path,
    auth_storage_mode: str = "file",
    provider_requires_openai_auth: bool = True,
    provider_env_key: str | None = None,
    provider_env_key_instructions: str | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> DoctorUpdateCheck:
    inputs = AuthCheckInputs(
        codex_home=Path(codex_home),
        auth_storage_mode=auth_storage_mode,
        provider_requires_openai_auth=provider_requires_openai_auth,
        provider_env_key=provider_env_key,
        provider_env_key_instructions=provider_env_key_instructions,
        env=dict(os.environ if env is None else env),
    )
    environment = inputs.env or {}
    auth_path = inputs.codex_home / "auth.json"
    details = [
        f"auth storage mode: {inputs.auth_storage_mode}",
        f"auth file: {auth_path}",
    ]
    env_auth_vars = [name for name in AUTH_ENV_VARS if _env_var_present(environment, name)]
    if env_auth_vars:
        details.append(f"auth env vars present: {', '.join(env_auth_vars)}")
    provider_check = _provider_specific_auth_check(
        inputs.provider_requires_openai_auth,
        inputs.provider_env_key,
        inputs.provider_env_key_instructions,
        details,
        environment,
    )
    if provider_check is not None:
        return provider_check
    try:
        auth = _read_auth_mapping(auth_path)
    except Exception as exc:
        return DoctorUpdateCheck(
            status="fail",
            summary="stored credentials could not be read",
            details=(str(exc),),
            remediation="Fix auth storage access or run codex login again.",
        )
    if auth is None:
        if env_auth_vars:
            return DoctorUpdateCheck(status="ok", summary="auth is provided by environment", details=tuple(details))
        return DoctorUpdateCheck(
            status="fail",
            summary="no Codex credentials were found",
            details=tuple(details),
            remediation="Run codex login or provide an API key through a supported auth env var.",
        )
    mode = _stored_auth_mode(auth)
    details.extend(
        [
            f"stored auth mode: {mode}",
            f"stored API key: {_bool_text(isinstance(auth.get('OPENAI_API_KEY'), str))}",
            f"stored ChatGPT tokens: {_bool_text(isinstance(auth.get('tokens'), dict))}",
            f"stored agent identity: {_bool_text(isinstance(auth.get('agent_identity'), str))}",
        ]
    )
    auth_issues = _stored_auth_issues(auth, environment)
    details.extend(f"stored auth issue: {issue}" for issue in auth_issues)
    if auth_issues and not env_auth_vars:
        return DoctorUpdateCheck(
            status="fail",
            summary="stored credentials are incomplete",
            details=tuple(details),
            remediation="Run codex login again or provide a supported auth env var.",
        )
    if auth_issues:
        return DoctorUpdateCheck(
            status="warn",
            summary="auth is provided by environment, but stored credentials are incomplete",
            details=tuple(details),
        )
    if len(env_auth_vars) > 1:
        return DoctorUpdateCheck(
            status="warn",
            summary="auth is configured, but multiple auth env vars are present",
            details=tuple(details),
        )
    return DoctorUpdateCheck(status="ok", summary="auth is configured", details=tuple(details))

def doctor_network_check(
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> DoctorUpdateCheck:
    environment = dict(os.environ if env is None else env)
    details: list[str] = []
    _push_proxy_env_details(details, environment)
    status = "ok"
    summary = "network-related environment looks readable"
    for name in CA_ENV_VARS:
        raw = environment.get(name)
        if raw is None:
            continue
        path = Path(raw)
        try:
            if path.is_file():
                try:
                    with path.open("rb") as handle:
                        handle.read(1)
                except OSError as exc:
                    status = "warn"
                    summary = "custom CA env var points at an unreadable file"
                    details.append(f"{name}: {path} ({exc})")
                else:
                    details.append(f"{name}: readable file {path}")
            elif path.exists():
                status = "warn"
                summary = "custom CA env var does not point at a file"
                details.append(f"{name}: not a file {path}")
            else:
                status = "warn"
                summary = "custom CA env var points at an unreadable path"
                details.append(f"{name}: {path} (missing)")
        except OSError as exc:
            status = "warn"
            summary = "custom CA env var points at an unreadable path"
            details.append(f"{name}: {path} ({exc})")
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details))

def doctor_mcp_check(
    *,
    config: dict[str, Any] | None = None,
    servers: dict[str, Any] | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    http_status_probe: HttpStatusProbe | None = None,
) -> DoctorUpdateCheck:
    environment = dict(os.environ if env is None else env)
    configured_servers = servers if servers is not None else _mcp_servers_from_config(config or {})
    if not configured_servers:
        return DoctorUpdateCheck(status="ok", summary="no MCP servers configured", details=())

    details: list[str] = []
    transport_counts: dict[str, int] = {}
    disabled = 0
    missing_env: list[str] = []
    unreachable_required_http: list[str] = []
    unreachable_optional_http: list[str] = []
    probe = http_status_probe or _default_http_status_probe

    for name, raw_server in configured_servers.items():
        server = raw_server if isinstance(raw_server, dict) else {}
        server_name = str(name)
        disabled_server = server.get("enabled") is False or server.get("disabled_reason") is not None
        required = server.get("required") is True
        if disabled_server:
            disabled += 1
        if _optional_str(server.get("url")) is not None:
            transport_counts["streamable_http"] = transport_counts.get("streamable_http", 0) + 1
            if disabled_server:
                continue
            _push_mcp_http_env_issues(missing_env, server_name, server, environment)
            url = _optional_str(server.get("url"))
            if url is not None:
                try:
                    _mcp_http_probe(url, probe)
                except Exception as exc:
                    detail = f"{server_name}: {url} ({_http_probe_error_text(exc)})"
                    if required:
                        unreachable_required_http.append(detail)
                    else:
                        unreachable_optional_http.append(detail)
            continue

        transport_counts["stdio"] = transport_counts.get("stdio", 0) + 1
        if disabled_server:
            continue
        _push_mcp_stdio_issues(missing_env, server_name, server, environment)

    details.append(f"configured servers: {len(configured_servers)}")
    details.append(f"disabled servers: {disabled}")
    for transport in sorted(transport_counts):
        details.append(f"{transport} servers: {transport_counts[transport]}")
    details.extend(missing_env)
    details.extend(f"required reachability failed: {detail}" for detail in unreachable_required_http)
    details.extend(f"optional reachability failed: {detail}" for detail in unreachable_optional_http)

    required_missing = any(
        _mcp_server_required(raw_server) and any(issue.startswith(f"{name}:") for issue in missing_env)
        for name, raw_server in configured_servers.items()
    )
    if required_missing or unreachable_required_http:
        status = "fail"
        summary = "MCP configuration has failing required inputs or reachability"
    elif missing_env or unreachable_optional_http:
        status = "warn"
        summary = "MCP configuration has optional issues"
    else:
        status = "ok"
        summary = "MCP configuration is locally consistent"
    remediation = "Set the missing MCP env vars or disable the affected server." if status != "ok" else None
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def doctor_sandbox_check(
    *,
    approval_policy: str = "unknown",
    filesystem_sandbox: str = "unknown",
    network_sandbox: str = "unknown",
    codex_linux_sandbox_helper: str | Path | None = None,
    execve_wrapper_helper: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> DoctorUpdateCheck:
    config_values = config or {}
    inputs = SandboxCheckInputs(
        approval_policy=_sandbox_config_string(config_values, "approval_policy", approval_policy),
        filesystem_sandbox=_sandbox_config_string(config_values, "sandbox_mode", filesystem_sandbox),
        network_sandbox=_sandbox_config_string(config_values, "network_sandbox", network_sandbox),
        codex_linux_sandbox_helper=Path(codex_linux_sandbox_helper) if codex_linux_sandbox_helper is not None else None,
        execve_wrapper_helper=Path(execve_wrapper_helper) if execve_wrapper_helper is not None else None,
    )
    details = [
        f"approval policy: {inputs.approval_policy}",
        f"filesystem sandbox: {inputs.filesystem_sandbox}",
        f"network sandbox: {inputs.network_sandbox}",
    ]
    _push_optional_path_detail(details, "codex-linux-sandbox helper", inputs.codex_linux_sandbox_helper)
    _push_optional_path_detail(details, "execve wrapper helper", inputs.execve_wrapper_helper)
    if inputs.codex_linux_sandbox_helper is not None and not inputs.codex_linux_sandbox_helper.exists():
        return DoctorUpdateCheck(
            status="warn",
            summary="Linux sandbox helper path does not exist",
            details=tuple(details),
        )
    return DoctorUpdateCheck(
        status="ok",
        summary="sandbox configuration is readable",
        details=tuple(details),
    )

def doctor_websocket_check(
    *,
    config: dict[str, Any] | None = None,
    inputs: WebsocketCheckInputs | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> DoctorUpdateCheck:
    if inputs is None:
        config_values = config or {}
        provider = config_values.get("model_provider")
        provider_mapping = provider if isinstance(provider, dict) else {}
        provider_id = _config_string(config_values, "model_provider_id", _config_string(config_values, "model_provider", "openai"))
        inputs = WebsocketCheckInputs(
            model_provider_id=provider_id,
            provider_name=_config_string(provider_mapping, "name", provider_id),
            wire_api=_config_string(provider_mapping, "wire_api", _config_string(config_values, "wire_api", "responses")),
            supports_websockets=_config_bool(provider_mapping, "supports_websockets", _config_bool(config_values, "supports_websockets", False)),
            connect_timeout_ms=_config_int(provider_mapping, "websocket_connect_timeout_ms", None),
            auth_mode=_config_string(config_values, "auth_mode", "none"),
            endpoint=_config_string(provider_mapping, "websocket_endpoint", ""),
            env=dict(os.environ if env is None else env),
        )
    environment = inputs.env or {}
    details = [
        f"model provider: {inputs.model_provider_id}",
        f"provider name: {inputs.provider_name}",
        f"wire API: {inputs.wire_api}",
        f"supports websockets: {_bool_text(inputs.supports_websockets)}",
    ]
    _push_proxy_env_details(details, environment)
    if not inputs.supports_websockets:
        return DoctorUpdateCheck(
            status="ok",
            summary="Responses WebSocket is not enabled for the active provider",
            details=tuple(details),
        )
    timeout_ms = inputs.connect_timeout_ms if inputs.connect_timeout_ms is not None else _DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS
    if timeout_ms <= 0:
        timeout_ms = _DEFAULT_WEBSOCKET_CONNECT_TIMEOUT_MS
    details.append(f"connect timeout: {timeout_ms} ms")
    details.append(f"auth mode: {inputs.auth_mode or 'none'}")
    endpoint = inputs.endpoint
    if not endpoint:
        endpoint = _DEFAULT_WEBSOCKET_ENDPOINT
    parsed_endpoint = urlparse(endpoint)
    if parsed_endpoint.scheme not in {"ws", "wss"} or not parsed_endpoint.hostname:
        return _websocket_probe_warning(
            "Responses WebSocket endpoint could not be built",
            details,
            "invalid websocket endpoint",
        )
    if endpoint:
        details.append(f"endpoint: {endpoint}")
        port = parsed_endpoint.port
        if port is None:
            port = 443 if parsed_endpoint.scheme == "wss" else 80
        details.extend(_dns_address_family_details(parsed_endpoint.hostname, port))
    if inputs.probe_error:
        return _websocket_probe_warning(
            "Responses WebSocket failed; HTTPS fallback may still work",
            details,
            inputs.probe_error,
        )
    timeout_seconds = max(timeout_ms, 1) / 1000
    auth_mode = inputs.auth_mode or "none"
    auth_token = (
        environment.get("OPENAI_API_KEY") or environment.get("CODEX_API_KEY")
        if auth_mode == "api_key"
        else None
    )
    provider = _responses_websocket_provider_from_endpoint(
        provider_name=inputs.provider_name,
        endpoint=endpoint,
    )
    auth = BearerAuthProvider.new(auth_token) if auth_token else unauthenticated_auth_provider()

    def connector(url: str, headers: dict[str, str], turn_state: object):
        return responses_connect_websocket(
            url,
            headers,
            turn_state,
            timeout=timeout_seconds,
        )

    client = ResponsesWebsocketClient.new(provider, auth, connector)
    try:
        probe = client.probe_handshake(
            extra_headers={OPENAI_BETA_HEADER: RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE},
            default_headers={},
            immediate_close_timeout=_WEBSOCKET_IMMEDIATE_CLOSE_GRACE_SECONDS,
        )
    except (socket.timeout, TimeoutError):
        return _websocket_probe_warning(
            "Responses WebSocket timed out; HTTPS fallback may still work",
            details,
            "handshake timed out",
        )
    except Exception as exc:  # pragma: no cover - cross-platform socket/protocol exceptions.
        return _websocket_probe_warning(
            "Responses WebSocket failed; HTTPS fallback may still work",
            details,
            _websocket_error_detail(exc),
        )

    details.extend(
        [
            f"handshake result: HTTP {probe.status}",
            f"reasoning header: {_bool_text(probe.reasoning_included)}",
            f"models etag present: {_bool_text(probe.models_etag_present)}",
            f"server model present: {_bool_text(probe.server_model_present)}",
        ]
    )
    if probe.immediate_close is not None:
        details.extend(
            [
                f"immediate close code: {probe.immediate_close.code}",
                f"immediate close reason: {probe.immediate_close.reason}",
            ]
        )
        return DoctorUpdateCheck(
            status="warn",
            summary="Responses WebSocket closed immediately after handshake",
            details=tuple(details),
            remediation="Check proxy, VPN, firewall, DNS, custom CA, and WebSocket policy support.",
        )
    return DoctorUpdateCheck(
        status="ok",
        summary="Responses WebSocket handshake succeeded",
        details=tuple(details),
    )

def _responses_websocket_provider_from_endpoint(
    *,
    provider_name: str,
    endpoint: str,
) -> Provider:
    parsed = urlparse(endpoint)
    scheme = "https" if parsed.scheme == "wss" else "http"
    path = parsed.path or "/"
    if path.rstrip("/").endswith("/responses"):
        base_path = path.rstrip("/")[: -len("/responses")] or "/"
    else:
        base_path = path.rstrip("/") or "/"
    base_url = parsed._replace(scheme=scheme, path=base_path, query="", fragment="").geturl()
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True)) or None
    return Provider(
        name=provider_name,
        base_url=base_url,
        query_params=query_params,
        headers={},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0.0,
            retry_429=False,
            retry_5xx=False,
            retry_transport=False,
        ),
        stream_idle_timeout=0.0,
    )

def _websocket_error_detail(error: Exception) -> str:
    if isinstance(error, ApiError):
        if error.kind == "transport":
            return f"handshake transport error: {error.transport}"
        if error.kind == "api":
            return f"handshake API error: {error.status} {error.message}"
        if error.kind == "stream":
            return f"handshake stream error: {error.message}"
        return f"handshake error: {error}"
    return str(error)

def provider_auth_reachability_mode_from_auth(
    *,
    requires_openai_auth: bool,
    env: dict[str, str] | os._Environ[str] | None = None,
    stored_auth: dict[str, Any] | None = None,
) -> str:
    environment = dict(os.environ if env is None else env)
    if not requires_openai_auth:
        return "provider auth"
    if _env_var_present(environment, "OPENAI_API_KEY") or _env_var_present(environment, "CODEX_API_KEY"):
        return "API key auth"
    if _env_var_present(environment, "CODEX_ACCESS_TOKEN"):
        return "ChatGPT auth"
    if stored_auth is not None and _stored_auth_mode(stored_auth) == "api_key":
        return "API key auth"
    return "ChatGPT auth"

def provider_reachability_plan_from_parts(
    *,
    mode: str,
    provider_id: str,
    provider_name: str,
    provider_base_url: str | None = None,
    provider_query_params: dict[str, str] | None = None,
    is_amazon_bedrock: bool = False,
    chatgpt_base_url: str = "https://chatgpt.com/backend-api/",
) -> ReachabilityPlan:
    provider_route_probe_url = None
    base_for_route = provider_base_url or ("https://api.openai.com/v1" if mode == "API key auth" else None)
    if base_for_route is not None and _should_probe_models_route(provider_name, base_for_route, is_amazon_bedrock):
        provider_route_probe_url = _provider_url_for_path(base_for_route, "models", provider_query_params)
    if mode == "API key auth":
        endpoints = (
            ReachabilityEndpoint(
                label=f"{provider_id} API",
                url=provider_base_url or "https://api.openai.com/v1",
                required=True,
                route_probe_url=provider_route_probe_url,
            ),
        )
    elif mode == "ChatGPT auth":
        endpoints = (ReachabilityEndpoint(label="ChatGPT", url=chatgpt_base_url, required=True),)
    elif provider_base_url is not None:
        endpoints = (
            ReachabilityEndpoint(
                label=f"{provider_id} API",
                url=provider_base_url,
                required=True,
                route_probe_url=provider_route_probe_url,
            ),
        )
    else:
        endpoints = ()
    return ReachabilityPlan(description=mode, endpoints=endpoints)

def default_reachability_plan() -> ReachabilityPlan:
    return provider_reachability_plan_from_parts(
        mode="ChatGPT auth",
        provider_id="openai",
        provider_name="OpenAI",
        chatgpt_base_url="https://chatgpt.com/backend-api/",
    )

def provider_reachability_plan_from_config(
    *,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    stored_auth: dict[str, Any] | None = None,
) -> ReachabilityPlan:
    config_values = config or {}
    provider = config_values.get("model_provider")
    provider_mapping = provider if isinstance(provider, dict) else {}
    provider_id = _config_string(config_values, "model_provider_id", _config_string(config_values, "model_provider", "openai"))
    provider_name = _config_string(provider_mapping, "name", provider_id)
    requires_openai_auth = _config_bool(
        provider_mapping,
        "requires_openai_auth",
        _config_bool(config_values, "requires_openai_auth", True),
    )
    mode = provider_auth_reachability_mode_from_auth(
        requires_openai_auth=requires_openai_auth,
        env=env,
        stored_auth=stored_auth,
    )
    return provider_reachability_plan_from_parts(
        mode=mode,
        provider_id=provider_id,
        provider_name=provider_name,
        provider_base_url=_optional_str(provider_mapping.get("base_url")) or _optional_str(config_values.get("provider_base_url")),
        provider_query_params=_string_mapping(provider_mapping.get("query_params")),
        is_amazon_bedrock=_config_bool(provider_mapping, "is_amazon_bedrock", _is_amazon_bedrock_provider(provider_id, provider_name)),
        chatgpt_base_url=_config_string(config_values, "chatgpt_base_url", "https://chatgpt.com/backend-api/"),
    )

def doctor_provider_reachability_check(
    *,
    plan: ReachabilityPlan,
    http_status_probe: HttpStatusProbe | None = None,
) -> DoctorUpdateCheck:
    details = [f"reachability mode: {plan.description}"]
    if not plan.endpoints:
        details.append("active provider endpoint: none configured")
        return DoctorUpdateCheck(
            status="ok",
            summary="active provider has no HTTP endpoint to probe",
            details=tuple(details),
        )
    probe = http_status_probe or _default_http_status_probe
    failures: list[str] = []
    optional_failures: list[str] = []
    route_failures: list[str] = []
    route_warnings: list[str] = []
    issues: list[dict[str, Any]] = []
    for endpoint in plan.endpoints:
        requirement = "required" if endpoint.required else "optional"
        try:
            status = probe(endpoint.url, "HEAD")
        except Exception as exc:  # pragma: no cover - exact stdlib exceptions vary by platform.
            details.append(f"{endpoint.label} base URL: {endpoint.url} {_http_probe_error_text(exc)} ({requirement})")
            if endpoint.required:
                failures.append(endpoint.url)
            else:
                optional_failures.append(endpoint.url)
            continue
        details.append(f"{endpoint.label} base URL: {endpoint.url} reachable (HTTP {status})")
        if endpoint.route_probe_url is not None:
            try:
                route_status = probe(endpoint.route_probe_url, "GET")
            except Exception as exc:  # pragma: no cover - exact stdlib exceptions vary by platform.
                error_text = _http_probe_error_text(exc)
                details.append(
                    f"{endpoint.label} route probe: {endpoint.route_probe_url} {error_text} (required)"
                )
                route_failures.append(endpoint.route_probe_url)
                issues.append(
                    {
                        "severity": "fail",
                        "cause": "provider route probe could not connect - verify network access to the provider API",
                        "measured": f"{endpoint.route_probe_url} {error_text}",
                        "expected": "GET /models completes",
                        "remedy": "Check proxy, VPN, firewall, DNS, and custom CA configuration.",
                        "fields": ["route probe"],
                    }
                )
                continue
            route_label = f"HTTP {route_status}"
            if 200 <= route_status < 300 or route_status in (401, 403):
                details.append(f"{endpoint.label} route probe: {endpoint.route_probe_url} route exists ({route_label})")
            elif route_status == 404:
                details.append(f"{endpoint.label} route probe: {endpoint.route_probe_url} returned {route_label} (required)")
                route_failures.append(endpoint.route_probe_url)
                issues.append(
                    {
                        "severity": "fail",
                        "cause": "provider base URL route returned 404 - verify the configured API prefix",
                        "measured": f"{endpoint.route_probe_url} returned {route_label}",
                        "expected": "GET /models returns 2xx, 401, or 403",
                        "remedy": "Set base_url to the provider API root, for example https://api.openai.com/v1",
                        "fields": ["route probe"],
                    }
                )
            else:
                details.append(f"{endpoint.label} route probe: {endpoint.route_probe_url} returned {route_label} (warning)")
                route_warnings.append(endpoint.route_probe_url)
    status, summary = _provider_reachability_outcome(
        len(failures) + len(route_failures),
        len(optional_failures) + len(route_warnings),
    )
    remediation = None
    if status != "ok":
        remediation = "Check proxy, VPN, firewall, DNS, and custom CA configuration."
    return DoctorUpdateCheck(
        status=status,
        summary=summary,
        details=tuple(details),
        remediation=remediation,
        issues=tuple(issues),
    )

def _provider_reachability_outcome(required_failures: int, warnings: int) -> tuple[str, str]:
    if required_failures == 0 and warnings == 0:
        return "ok", "active provider endpoints are reachable over HTTP"
    if required_failures == 0:
        return "warn", "provider endpoint checks returned warnings"
    return "fail", "one or more required provider endpoints are unreachable over HTTP"

def _default_http_status_probe(url: str, method: str) -> int:
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=3) as response:
            return int(response.status)
    except HTTPError as exc:
        return int(exc.code)

def _http_probe_error_text(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "request timed out"
    if isinstance(exc, ValueError):
        return "request could not be built"
    if isinstance(exc, ConnectionError):
        return "connect failed"
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            return "request timed out"
        if isinstance(reason, ConnectionError):
            return "connect failed"
        text = str(reason)
        if text:
            return text
        return str(exc)
    text = str(exc)
    return text or exc.__class__.__name__

def doctor_terminal_check(
    *,
    no_color_flag: bool = False,
    env: dict[str, str] | os._Environ[str] | None = None,
    inputs: TerminalCheckInputs | None = None,
) -> DoctorUpdateCheck:
    if inputs is None:
        environment = os.environ if env is None else env
        term = environment.get("TERM")
        size = shutil.get_terminal_size(fallback=(80, 24))
        multiplexer = "tmux" if environment.get("TMUX") else None
        env_snapshot, present_snapshot = _collect_env_snapshot(_terminal_env_names(), environment)
        inputs = TerminalCheckInputs(
            terminal="dumb" if term == "dumb" else "unknown",
            term_program=environment.get("TERM_PROGRAM"),
            version=environment.get("TERM_PROGRAM_VERSION"),
            term=term,
            multiplexer=multiplexer,
            stdin_is_terminal=sys.stdin.isatty(),
            stdout_is_terminal=sys.stdout.isatty(),
            stderr_is_terminal=sys.stderr.isatty(),
            stream_supports_color=bool(term and term != "dumb"),
            terminal_size=(size.columns, size.lines),
            env=env_snapshot,
            present_env=present_snapshot,
            no_color_flag=no_color_flag,
            tmux_details=_tmux_diagnostic_details() if multiplexer == "tmux" else (),
            windows_console_details=_windows_console_details(),
        )
    env_values = inputs.env or {}
    present_env = inputs.present_env or set(env_values)
    details = [f"terminal: {inputs.terminal}"]
    if inputs.term_program is not None:
        details.append(f"TERM_PROGRAM: {inputs.term_program}")
    if inputs.version is not None:
        details.append(f"terminal version: {inputs.version}")
    if inputs.term is not None:
        details.append(f"TERM: {inputs.term}")
    if inputs.multiplexer is not None:
        details.append(f"multiplexer: {inputs.multiplexer}")
    details.append(f"stdin is terminal: {_bool_text(inputs.stdin_is_terminal)}")
    details.append(f"stdout is terminal: {_bool_text(inputs.stdout_is_terminal)}")
    details.append(f"stderr is terminal: {_bool_text(inputs.stderr_is_terminal)}")
    if isinstance(inputs.terminal_size, tuple):
        columns, rows = inputs.terminal_size
        details.append(f"terminal size: {columns}x{rows}")
    else:
        details.append(f"terminal size: unavailable ({inputs.terminal_size})")
    _push_terminal_env_values(details, env_values, present_env, ("COLUMNS", "LINES"))
    details.append(f"color output: {_color_output_summary(inputs, env_values, present_env)}")
    _push_terminal_env_values(
        details,
        env_values,
        present_env,
        ("COLORTERM", "NO_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "FORCE_COLOR", "COLORFGBG"),
    )
    terminfo_warning = _push_terminfo_details(details, env_values, present_env)
    locale_value = _effective_locale(env_values)
    if locale_value is not None:
        details.append(f"effective locale: {locale_value}")
    _push_presence_env_values(
        details,
        present_env,
        (
            "SSH_TTY",
            "SSH_CONNECTION",
            "SSH_CLIENT",
            "MOSH_IP",
            "WSL_DISTRO_NAME",
            "WSL_INTEROP",
            "VSCODE_INJECTION",
            "VSCODE_IPC_HOOK_CLI",
            "WAYLAND_DISPLAY",
            "DISPLAY",
            "WT_SESSION",
        ),
    )
    details.extend(inputs.tmux_details)
    details.extend(inputs.windows_console_details)

    issues: list[dict[str, Any]] = []
    if inputs.terminal == "dumb" or inputs.term == "dumb":
        issues.append(
            {
                "status": "fail",
                "summary": "TERM=dumb - colors and cursor control are disabled",
                "remedy": "set TERM to a real value, for example xterm-256color",
            }
        )
    if locale_value is not None and _is_non_utf8_locale(locale_value):
        issues.append(
            {
                "status": "warn",
                "summary": "locale is not UTF-8 - unicode glyphs may render incorrectly",
                "expected": "UTF-8 locale, for example en_US.UTF-8",
                "remedy": "export LANG=en_US.UTF-8 or another UTF-8 locale",
                "fields": ["effective locale"],
            }
        )
    if terminfo_warning:
        issues.append(
            {
                "status": "fail",
                "summary": "TERMINFO unreadable - terminal capabilities are unknown",
                "expected": "readable terminfo file or directory",
                "remedy": "check that $TERMINFO points to a readable directory",
                "fields": ["TERMINFO"],
            }
        )
    issues.extend(_terminal_size_issues(inputs, env_values))

    if any(issue["status"] == "fail" for issue in issues):
        status = "fail"
    elif issues:
        status = "warn"
    else:
        status = "ok"
    summary = issues[0]["summary"] if issues else "terminal metadata was detected"
    remediation = _terminal_remediation(summary)
    return DoctorUpdateCheck(
        status=status,
        summary=summary,
        details=tuple(details),
        remediation=remediation,
        issues=tuple(issues),
    )

def doctor_state_check(
    *,
    codex_home: str | Path,
    log_dir: str | Path | None = None,
    sqlite_home: str | Path | None = None,
    standalone_releases_dir: str | Path | None = None,
) -> DoctorUpdateCheck:
    inputs = StateCheckInputs(
        codex_home=Path(codex_home),
        log_dir=Path(log_dir) if log_dir is not None else Path(codex_home) / "log",
        sqlite_home=Path(sqlite_home) if sqlite_home is not None else Path(codex_home),
        standalone_releases_dir=Path(standalone_releases_dir) if standalone_releases_dir is not None else None,
    )
    details: list[str] = []
    _push_path_readiness(details, "CODEX_HOME", inputs.codex_home)
    _push_path_readiness(details, "log dir", inputs.log_dir)
    _push_path_readiness(details, "sqlite home", inputs.sqlite_home)
    integrity_failures: list[str] = []
    for label, path in _runtime_db_paths(inputs.sqlite_home):
        _push_path_readiness(details, label, path)
        _push_sqlite_integrity_detail(details, integrity_failures, label, path)
    _push_rollout_stats_details(details, inputs.codex_home)
    if inputs.standalone_releases_dir is not None:
        _push_standalone_release_cache_details(details, inputs.standalone_releases_dir)
    if integrity_failures:
        return DoctorUpdateCheck(
            status="fail",
            summary="state database integrity check failed",
            details=tuple(details),
            remediation="Back up CODEX_HOME, then remove or repair the affected SQLite database.",
        )
    return DoctorUpdateCheck(
        status="ok",
        summary="state paths and databases are inspectable",
        details=tuple(details),
    )

_TERMINAL_ENV_NAMES = (
    "TERM",
    "TERM_PROGRAM",
    "TERM_PROGRAM_VERSION",
    "COLUMNS",
    "LINES",
    "COLORTERM",
    "NO_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "FORCE_COLOR",
    "COLORFGBG",
    "TERMINFO",
    "TERMINFO_DIRS",
    "LC_ALL",
    "LC_CTYPE",
    "LANG",
    "SSH_TTY",
    "SSH_CONNECTION",
    "SSH_CLIENT",
    "MOSH_IP",
    "WSL_DISTRO_NAME",
    "WSL_INTEROP",
    "VSCODE_INJECTION",
    "VSCODE_IPC_HOOK_CLI",
    "WAYLAND_DISPLAY",
    "DISPLAY",
    "WT_SESSION",
    "TMUX",
)

def _terminal_env_names() -> tuple[str, ...]:
    return tuple(sorted(set(_TERMINAL_ENV_NAMES)))

def _collect_env_snapshot(
    names: tuple[str, ...],
    environment: Mapping[str, str],
) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    present: set[str] = set()
    for name in names:
        if name not in environment:
            continue
        present.add(name)
        value = str(environment[name]).strip()
        if value:
            values[name] = value
    return values, present

def _push_terminal_env_values(
    details: list[str],
    env_values: Mapping[str, str],
    present_env: set[str],
    names: tuple[str, ...],
) -> None:
    for name in names:
        if name in env_values:
            details.append(f"{name}: {env_values[name]}")
        elif name in present_env:
            details.append(f"{name}: present")

def _push_presence_env_values(
    details: list[str],
    present_env: set[str],
    names: tuple[str, ...],
) -> None:
    for name in names:
        if name in present_env:
            details.append(f"{name}: present")

_TMUX_OPTION_NAMES = (
    "extended-keys",
    "xterm-keys",
    "allow-passthrough",
    "set-clipboard",
    "focus-events",
)

_RUNTIME_DB_FILENAMES = (
    ("state DB", "state_5.sqlite"),
    ("log DB", "logs_2.sqlite"),
    ("goals DB", "goals_1.sqlite"),
    ("memories DB", "memories_1.sqlite"),
)

_DEFAULT_TERMINAL_TITLE_ITEMS = ("activity", "project-name")

_TERMINAL_TITLE_ITEM_ALIASES = {
    "app-name": "app-name",
    "project-name": "project-name",
    "project": "project-name",
    "current-dir": "current-dir",
    "activity": "activity",
    "spinner": "activity",
    "run-state": "run-state",
    "status": "run-state",
    "thread-title": "thread-title",
    "thread": "thread-title",
    "git-branch": "git-branch",
    "context-remaining": "context-remaining",
    "context-used": "context-used",
    "context-usage": "context-used",
    "five-hour-limit": "five-hour-limit",
    "weekly-limit": "weekly-limit",
    "codex-version": "codex-version",
    "used-tokens": "used-tokens",
    "total-input-tokens": "total-input-tokens",
    "total-output-tokens": "total-output-tokens",
    "thread-id": "thread-id",
    "session-id": "thread-id",
    "fast-mode": "fast-mode",
    "model": "model",
    "model-name": "model",
    "model-with-reasoning": "model-with-reasoning",
    "task-progress": "task-progress",
}

_PROJECT_TITLE_MAX_CHARS = 24

def _bool_text(value: bool) -> str:
    return "true" if value else "false"

def _color_output_summary(
    inputs: TerminalCheckInputs,
    env_values: dict[str, str],
    present_env: set[str],
) -> str:
    if (
        not inputs.no_color_flag
        and "NO_COLOR" not in present_env
        and env_values.get("TERM") != "dumb"
        and inputs.stdout_is_terminal
        and inputs.stream_supports_color
    ):
        return "enabled"
    if inputs.no_color_flag:
        reason = "--no-color"
    elif "NO_COLOR" in present_env:
        reason = "NO_COLOR"
    elif env_values.get("TERM") == "dumb":
        reason = "TERM=dumb"
    elif not inputs.stdout_is_terminal:
        reason = "stdout is not a terminal"
    elif not inputs.stream_supports_color:
        reason = "terminal color support not detected"
    else:
        reason = "disabled"
    return f"disabled ({reason})"

def _human_output_options_from_flags(
    *,
    summary: bool,
    all: bool,
    ascii: bool,
    no_color: bool,
    no_color_env: bool,
    term: str | None,
    stdout_is_terminal: bool,
    stream_supports_color: bool,
) -> dict[str, bool]:
    color_enabled = (
        not no_color
        and not no_color_env
        and term != "dumb"
        and stdout_is_terminal
        and stream_supports_color
    )
    return {
        "show_details": not summary,
        "show_all": all,
        "ascii": ascii,
        "color_enabled": color_enabled,
    }

def _effective_locale(env_values: dict[str, str]) -> str | None:
    for name in LOCALE_ENV_VARS:
        value = env_values.get(name)
        if value is not None:
            return value
    return None

def _push_terminfo_details(details: list[str], env_values: dict[str, str], present_env: set[str]) -> bool:
    has_warning = False
    raw_terminfo = env_values.get("TERMINFO")
    if raw_terminfo:
        path = Path(raw_terminfo)
        status, warning = _terminal_path_readiness(path)
        details.append(f"TERMINFO: {path} ({status})")
        has_warning = has_warning or warning
    raw_terminfo_dirs = env_values.get("TERMINFO_DIRS")
    if raw_terminfo_dirs is not None:
        for raw_path in _split_env_paths(raw_terminfo_dirs):
            path = Path(raw_path)
            status, warning = _terminal_path_readiness(path)
            details.append(f"TERMINFO_DIRS entry: {path} ({status})")
            has_warning = has_warning or warning
    elif "TERMINFO_DIRS" in present_env:
        details.append("TERMINFO_DIRS: present")
    return has_warning

def _split_env_paths(raw_paths: str) -> list[str]:
    return [path for path in raw_paths.split(os.pathsep) if path]

def _read_probe_file(path: Path) -> None:
    with path.open("rb") as handle:
        handle.read(1)

def _terminal_path_readiness(path: Path) -> tuple[str, bool]:
    try:
        if path.is_dir():
            try:
                next(path.iterdir(), None)
            except OSError as exc:
                return f"dir unreadable: {exc}", True
            return "dir", False
        if path.is_file():
            try:
                _read_probe_file(path)
            except OSError as exc:
                return f"file unreadable: {exc}", True
            return "file", False
        if path.exists():
            return "not a file or directory", True
        return "missing", True
    except OSError as exc:
        return str(exc), True

def _tmux_diagnostic_details(command_runner: CommandRunner | None = None) -> tuple[str, ...]:
    runner = run_command if command_runner is None else command_runner
    details: list[str] = []
    for label, tmux_format in (
        ("tmux client termtype", "#{client_termtype}"),
        ("tmux client termname", "#{client_termname}"),
    ):
        value = _tmux_display_message(tmux_format, runner)
        if value is not None:
            details.append(f"{label}: {value}")
    for option in _TMUX_OPTION_NAMES:
        value = _tmux_option_value(option, runner)
        details.append(f"tmux {option}: {value if value is not None else 'unavailable'}")
    return tuple(details)

def _tmux_display_message(tmux_format: str, command_runner: CommandRunner) -> str | None:
    try:
        output = command_runner("tmux", ("display-message", "-p", tmux_format))
    except Exception:
        return None
    return _non_empty_trimmed(output)

def _tmux_option_value(option: str, command_runner: CommandRunner) -> str | None:
    try:
        output = command_runner("tmux", ("show-options", "-gqv", option))
    except Exception:
        return None
    return _non_empty_trimmed(output)

def _non_empty_trimmed(value: str) -> str | None:
    value = value.strip()
    return value or None

def _windows_console_details() -> tuple[str, ...]:
    if os.name != "nt":
        return ()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    stdout_handle = kernel32.GetStdHandle(-11)
    stderr_handle = kernel32.GetStdHandle(-12)
    return (
        f"console input code page: {kernel32.GetConsoleCP()}",
        f"console output code page: {kernel32.GetConsoleOutputCP()}",
        _windows_console_mode_detail(kernel32, "stdout console mode", stdout_handle),
        _windows_console_mode_detail(kernel32, "stderr console mode", stderr_handle),
    )

def _windows_console_mode_detail(kernel32: Any, label: str, handle: int) -> str:
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (0, invalid_handle):
        return f"{label}: unavailable"
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
        return f"{label}: unavailable"
    vt_enabled = bool(mode.value & 0x0004)
    return f"{label}: 0x{mode.value:08x} (VT processing: {_bool_text(vt_enabled)})"

def _runtime_db_paths(sqlite_home: Path) -> tuple[tuple[str, Path], ...]:
    return tuple((label, sqlite_home / filename) for label, filename in _RUNTIME_DB_FILENAMES)

def _config_string(config: dict[str, Any], key: str, default: str) -> str:
    value = config.get(key)
    return value if isinstance(value, str) and value else default

def _config_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key)
    return value if isinstance(value, bool) else default

def _config_int(config: dict[str, Any], key: str, default: int | None) -> int | None:
    value = config.get(key)
    return value if isinstance(value, int) else default

def _mapping_len(value: Any) -> int:
    return len(value) if isinstance(value, dict) else 0

def _string_mapping(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}

def _mcp_servers_from_config(config: dict[str, Any]) -> dict[str, Any]:
    servers = config.get("mcp_servers")
    if isinstance(servers, dict):
        return servers
    servers = config.get("mcpServers")
    if isinstance(servers, dict):
        return servers
    return {}

def _mcp_server_required(raw_server: Any) -> bool:
    return isinstance(raw_server, dict) and raw_server.get("required") is True

def _push_mcp_stdio_issues(
    issues: list[str],
    name: str,
    server: dict[str, Any],
    env: dict[str, str],
) -> None:
    cwd = _optional_str(server.get("cwd"))
    if cwd is not None and not Path(cwd).exists():
        issues.append(f"{name}: cwd does not exist ({cwd})")
    command = _optional_str(server.get("command"))
    if command is None:
        issues.append(f"{name}: stdio command is empty")
    elif not _stdio_command_resolves(command, cwd, server.get("env")):
        issues.append(f"{name}: stdio command {json.dumps(command)} is not resolvable")
    server_env = server.get("env")
    if isinstance(server_env, dict):
        for key in server_env:
            if str(key).strip() == "":
                issues.append(f"{name}: empty env key {key}")
    for env_var in _mcp_env_var_entries(server.get("env_vars")):
        env_name = env_var.get("name")
        if env_name is None:
            continue
        if env_var.get("source") == "remote":
            issues.append(
                f"{name}: env_vars entry `{env_name}` uses source `remote`, which requires remote MCP stdio"
            )
        elif not _env_var_present(env, env_name):
            issues.append(f"{name}: env var {env_name} is not set")

def _push_mcp_http_env_issues(
    issues: list[str],
    name: str,
    server: dict[str, Any],
    env: dict[str, str],
) -> None:
    bearer = _optional_str(server.get("bearer_token_env_var"))
    if bearer is not None and not _env_var_present(env, bearer):
        issues.append(f"{name}: bearer token env var {bearer} is not set")
    headers = server.get("env_http_headers")
    if isinstance(headers, dict):
        for env_var in headers.values():
            env_name = _optional_str(env_var)
            if env_name is not None and not _env_var_present(env, env_name):
                issues.append(f"{name}: header env var {env_name} is not set")

def _mcp_env_var_entries(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, str | None]] = []
    for item in value:
        if isinstance(item, str):
            entries.append({"name": item, "source": None})
        elif isinstance(item, dict):
            name = _optional_str(item.get("name"))
            source = _optional_str(item.get("source"))
            entries.append({"name": name, "source": source})
    return entries

def _stdio_command_resolves(command: str, cwd: str | None, server_env: Any) -> bool:
    command_path = Path(command)
    if command_path.is_absolute():
        return _executable_path_exists(command_path) is None
    if command_path.parent != Path("."):
        base = Path(cwd) if cwd is not None else Path.cwd()
        return _executable_path_exists(base / command_path) is None
    search_path = None
    if isinstance(server_env, dict):
        env_path = server_env.get("PATH")
        if isinstance(env_path, str):
            search_path = env_path
    resolved = shutil.which(command, path=search_path)
    if resolved is not None:
        return True
    return False

def _executable_path_exists(path: Path) -> str | None:
    try:
        metadata = path.stat()
    except OSError as exc:
        return str(exc)
    if not stat.S_ISREG(metadata.st_mode):
        return "path is not a file"
    if os.name != "nt" and metadata.st_mode & 0o111 == 0:
        return f"{path} is not executable"
    return None

def _mcp_http_probe(url: str, probe: HttpStatusProbe) -> int:
    try:
        return probe(url, "HEAD")
    except Exception as head_exc:
        try:
            return probe(url, "GET")
        except Exception as get_exc:
            raise RuntimeError(
                f"HEAD {_http_probe_error_text(head_exc)}; GET {_http_probe_error_text(get_exc)}"
            ) from get_exc

def _display_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"

def _structured_redacted_details(raw_details: Any) -> tuple[dict[str, Any], list[str]]:
    details: dict[str, Any] = {}
    notes: list[str] = []
    if not isinstance(raw_details, list):
        return details, notes
    for raw_detail in raw_details:
        redacted = redact_detail(str(raw_detail))
        if ": " not in redacted:
            notes.append(redacted)
            continue
        key, value = redacted.split(": ", 1)
        key = key.strip()
        if not key:
            notes.append(redacted)
            continue
        existing = details.get(key)
        if existing is None:
            details[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            details[key] = [existing, value]
    return dict(sorted(details.items())), notes

def _doctor_check_identity(check_key: str | None) -> tuple[str, str]:
    if check_key is None:
        return "unknown", "unknown"
    return DOCTOR_CHECK_METADATA.get(check_key, (check_key, check_key))

def _doctor_generated_at() -> str:
    try:
        return f"{int(time.time())}s since unix epoch"
    except Exception:
        return "unknown"

def _redact_urls(detail: str) -> str:
    return "".join(_redact_url_token(token) for token in _split_inclusive_whitespace(detail))

def _split_inclusive_whitespace(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for index, char in enumerate(value):
        if char.isspace():
            parts.append(value[start : index + 1])
            start = index + 1
    if start < len(value):
        parts.append(value[start:])
    return parts

def _redact_url_token(token: str) -> str:
    scheme_end = token.find("://")
    if scheme_end < 0:
        return token
    suffix_start = len(token)
    while suffix_start > scheme_end + 3 and token[suffix_start - 1] in " \t\n\r.,;:)]":
        suffix_start -= 1
    body = token[:suffix_start]
    suffix = token[suffix_start:]
    scheme_prefix_end = scheme_end + 3
    rest = body[scheme_prefix_end:]
    authority_relative_end = len(rest)
    for marker in ("/", "?", "#"):
        marker_index = rest.find(marker)
        if marker_index >= 0:
            authority_relative_end = min(authority_relative_end, marker_index)
    authority_end = scheme_prefix_end + authority_relative_end
    authority = body[scheme_prefix_end:authority_end]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    path = body[authority_end:]
    path_end = len(path)
    for marker in ("?", "#"):
        marker_index = path.find(marker)
        if marker_index >= 0:
            path_end = min(path_end, marker_index)
    path = _redact_url_path(path[:path_end])
    return f"{body[:scheme_prefix_end]}{authority}{path}{suffix}"

def _redact_url_path(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) > 1:
        return f"/{segments[0]}/<redacted>"
    return path

def _push_config_toml_details(details: list[str], codex_home: Path) -> None:
    config_path = codex_home / "config.toml"
    details.append(f"config.toml: {config_path}")
    try:
        contents = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        details.append("config.toml: missing")
        return
    except OSError as exc:
        details.append(f"config.toml read: {exc}")
        return
    try:
        tomllib.loads(contents)
    except tomllib.TOMLDecodeError as exc:
        details.append(f"config.toml parse: {exc}")
        return
    details.append("config.toml parse: ok")

def _push_startup_warning_counts(details: list[str], warnings: tuple[str, ...]) -> None:
    details.append(f"startup warnings: {len(warnings)}")
    for label, needle in (
        ("startup warning skills", "skill"),
        ("startup warning hooks", "hook"),
        ("startup warning plugins", "plugin"),
        ("startup warning MCP", "mcp"),
        ("startup warning deprecated", "deprecated"),
    ):
        count = sum(1 for warning in warnings if needle in warning.lower())
        details.append(f"{label}: {count}")

def _provider_specific_auth_check(
    requires_openai_auth: bool,
    provider_env_key: str | None,
    provider_env_key_instructions: str | None,
    details: list[str],
    env: dict[str, str],
) -> DoctorUpdateCheck | None:
    provider_details = list(details)
    provider_details.append(f"model provider requires OpenAI auth: {_bool_text(requires_openai_auth)}")
    if requires_openai_auth:
        return None
    if provider_env_key and _env_var_present(env, provider_env_key):
        provider_details.append(f"provider auth env var: {provider_env_key} (present)")
        return DoctorUpdateCheck(
            status="ok",
            summary="auth is provided by the active model provider",
            details=tuple(provider_details),
        )
    if provider_env_key:
        provider_details.append(f"provider auth env var: {provider_env_key} (missing)")
        remediation = provider_env_key_instructions or f"Set {provider_env_key} for the active model provider."
        return DoctorUpdateCheck(
            status="fail",
            summary="active model provider auth env var is missing",
            details=tuple(provider_details),
            remediation=remediation,
        )
    return DoctorUpdateCheck(
        status="ok",
        summary="OpenAI auth is not required for the active model provider",
        details=tuple(provider_details),
    )

def _read_auth_mapping(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid auth file format.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Invalid auth file format.")
    return raw

def _stored_auth_mode(auth: dict[str, Any]) -> str:
    mode = _optional_str(auth.get("auth_mode"))
    if mode is not None:
        normalized = mode.replace("-", "").replace("_", "").lower()
        if normalized == "apikey":
            return "api_key"
        if normalized == "chatgpt":
            return "chatgpt"
        if normalized == "chatgptauthtokens":
            return "chatgpt_auth_tokens"
        if normalized == "agentidentity":
            return "agent_identity"
    if isinstance(auth.get("OPENAI_API_KEY"), str):
        return "api_key"
    return "chatgpt"

def _stored_auth_issues(auth: dict[str, Any], env: dict[str, str]) -> list[str]:
    mode = _stored_auth_mode(auth)
    tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else None
    issues: list[str] = []
    if mode == "api_key":
        stored_key_present = _optional_str(auth.get("OPENAI_API_KEY")) is not None
        env_key_present = _env_var_present(env, "OPENAI_API_KEY") or _env_var_present(env, "CODEX_API_KEY")
        if not stored_key_present and not env_key_present:
            issues.append("API key auth is missing an API key")
    elif mode == "chatgpt":
        if tokens is None:
            issues.append("ChatGPT auth is missing token data")
        else:
            if _optional_str(tokens.get("access_token")) is None:
                issues.append("ChatGPT auth is missing an access token")
            if _optional_str(tokens.get("refresh_token")) is None:
                issues.append("ChatGPT auth is missing a refresh token")
        if _optional_str(auth.get("last_refresh")) is None:
            issues.append("ChatGPT auth is missing refresh metadata")
    elif mode == "chatgpt_auth_tokens":
        if tokens is None:
            issues.append("external ChatGPT auth is missing token data")
        else:
            if _optional_str(tokens.get("access_token")) is None:
                issues.append("external ChatGPT auth is missing an access token")
            id_token = tokens.get("id_token") if isinstance(tokens.get("id_token"), dict) else {}
            id_token_account_id = _optional_str(id_token.get("chatgpt_account_id"))
            if _optional_str(tokens.get("account_id")) is None and id_token_account_id is None:
                issues.append("external ChatGPT auth is missing a ChatGPT account id")
        if _optional_str(auth.get("last_refresh")) is None:
            issues.append("external ChatGPT auth is missing refresh metadata")
    elif mode == "agent_identity" and _optional_str(auth.get("agent_identity")) is None:
        issues.append("agent identity auth is missing an agent identity token")
    return issues

def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None

def _env_var_present(env: dict[str, str], name: str) -> bool:
    value = env.get(name)
    return value is not None and value != ""

def _push_proxy_env_details(details: list[str], env: dict[str, str]) -> None:
    present_proxy_vars = [name for name in PROXY_ENV_VARS if _env_var_present(env, name)]
    if present_proxy_vars:
        details.append(f"proxy env vars present: {', '.join(present_proxy_vars)}")
    else:
        details.append("proxy env vars: none")

def _websocket_probe_warning(summary: str, details: list[str], error_detail: str) -> DoctorUpdateCheck:
    return DoctorUpdateCheck(
        status="warn",
        summary=summary,
        details=tuple([*details, error_detail]),
        remediation="Check proxy, VPN, firewall, DNS, custom CA, and WebSocket policy support.",
    )

def _sandbox_config_string(config: dict[str, Any], key: str, default: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value:
        return value
    if isinstance(value, bool):
        return _bool_text(value)
    return default

def _doctor_path_text(path: Path) -> str:
    if os.name == "nt" and path.drive == "" and path.anchor == "\\":
        return path.as_posix()
    return str(path)

def _push_optional_path_detail(details: list[str], label: str, path: Path | None) -> None:
    if path is None:
        details.append(f"{label}: none")
    else:
        details.append(f"{label}: {_doctor_path_text(path)}")

def _push_env_path_detail(
    details: list[str],
    label: str,
    name: str,
    env: Mapping[str, str] | os._Environ[str] | None = None,
) -> None:
    environment = os.environ if env is None else env
    value = environment.get(name)
    if value is None:
        details.append(f"{label}: not set")
    else:
        details.append(f"{label}: {_doctor_path_text(Path(value))}")

def _should_probe_models_route(provider_name: str, base_url: str, is_amazon_bedrock: bool) -> bool:
    return not is_amazon_bedrock and not _is_azure_responses_provider(provider_name, base_url)

def _is_amazon_bedrock_provider(provider_id: str, provider_name: str) -> bool:
    lowered = f"{provider_id} {provider_name}".lower()
    return "bedrock" in lowered

def _is_azure_responses_provider(provider_name: str, base_url: str) -> bool:
    lowered = f"{provider_name} {base_url}".lower()
    return "azure" in lowered and "openai.azure.com" in lowered

def _provider_url_for_path(base_url: str, path: str, query_params: dict[str, str] | None) -> str:
    base = base_url.rstrip("/")
    trimmed_path = path.lstrip("/")
    url = f"{base}/{trimmed_path}" if trimmed_path else base
    if query_params:
        separator = "&" if "?" in url else "?"
        url += separator + "&".join(f"{key}={value}" for key, value in query_params.items())
    return url

def _push_path_readiness(details: list[str], label: str, path: Path) -> None:
    try:
        if path.is_dir():
            kind = "dir"
        elif path.is_file():
            kind = "file"
        elif path.exists():
            kind = "other"
        else:
            details.append(f"{label}: {_doctor_path_text(path)} (missing)")
            return
    except OSError as exc:
        details.append(f"{label}: {_doctor_path_text(path)} ({exc})")
        return
    details.append(f"{label}: {_doctor_path_text(path)} ({kind})")

def _push_sqlite_integrity_detail(
    details: list[str],
    integrity_failures: list[str],
    label: str,
    path: Path,
) -> None:
    if not path.is_file():
        details.append(f"{label} integrity: skipped (missing)")
        return
    try:
        connection = sqlite3.connect(path)
        try:
            rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
        finally:
            connection.close()
    except Exception as exc:
        message = f"{label} integrity: {exc}"
        integrity_failures.append(message)
        details.append(message)
        return
    if rows and all(row == "ok" for row in rows):
        details.append(f"{label} integrity: ok")
        return
    message = f"{label} integrity: {'; '.join(rows)}"
    integrity_failures.append(message)
    details.append(message)

def _push_rollout_stats_details(details: list[str], codex_home: Path) -> None:
    active = _collect_rollout_stats(codex_home / "sessions")
    archived = _collect_rollout_stats(codex_home / "archived_sessions")
    _push_rollout_stats_detail(details, "active rollout files", active)
    _push_rollout_stats_detail(details, "archived rollout files", archived)

def _push_rollout_stats_detail(details: list[str], label: str, stats: tuple[int, int, str | None]) -> None:
    files, total_bytes, error = stats
    if error is not None:
        details.append(f"{label}: scan failed ({error})")
        return
    average = total_bytes // files if files else 0
    details.append(f"{label}: {files} files, {total_bytes} total bytes, {average} average bytes")

def _collect_rollout_stats(root: Path) -> tuple[int, int, str | None]:
    files = 0
    total_bytes = 0
    stack = [root]
    while stack:
        path = stack.pop()
        try:
            entries = list(path.iterdir())
        except FileNotFoundError:
            continue
        except OSError as exc:
            return files, total_bytes, str(exc)
        for entry in entries:
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file() and _is_rollout_file(entry):
                    files += 1
                    total_bytes = min(U64_MAX, total_bytes + entry.stat().st_size)
            except OSError as exc:
                return files, total_bytes, str(exc)
    return files, total_bytes, None

def _is_rollout_file(path: Path) -> bool:
    return path.suffix == ".jsonl" and path.name.startswith("rollout-")

def _push_standalone_release_cache_details(details: list[str], releases_dir: Path) -> None:
    try:
        release_count = sum(1 for _entry in releases_dir.iterdir())
    except OSError:
        return
    details.append(f"standalone release cache: {release_count} entries in {releases_dir}")

def _is_non_utf8_locale(locale_value: str) -> bool:
    value = locale_value.lower()
    return "utf-8" not in value and "utf8" not in value

def _terminal_size_issues(
    inputs: TerminalCheckInputs,
    env_values: dict[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if isinstance(inputs.terminal_size, tuple):
        columns, rows = inputs.terminal_size
        if 0 < columns < 80:
            issues.append(
                {
                    "status": "warn",
                    "summary": f"width {columns} cols - output may wrap (recommended >=80)",
                    "measured": f"{columns} x {rows}",
                    "expected": ">= 80 columns",
                    "remedy": "resize the window to at least 80 columns",
                    "fields": ["terminal size"],
                }
            )
        if 0 < rows < 24:
            issues.append(
                {
                    "status": "warn",
                    "summary": f"height {rows} rows - content may scroll off (recommended >=24)",
                    "measured": f"{columns} x {rows}",
                    "expected": ">= 24 rows",
                    "remedy": "resize the window to at least 24 rows",
                    "fields": ["terminal size"],
                }
            )
    columns_env = env_values.get("COLUMNS")
    if columns_env is not None:
        try:
            columns = int(columns_env)
        except ValueError:
            columns = 0
        if 0 < columns < 80:
            issues.append(
                {
                    "status": "warn",
                    "summary": f"COLUMNS={columns} - output may wrap (recommended >=80)",
                    "measured": f"{columns} columns",
                    "expected": ">= 80 columns",
                    "remedy": "resize the window to at least 80 columns",
                    "fields": ["COLUMNS"],
                }
            )
    lines_env = env_values.get("LINES")
    if lines_env is not None:
        try:
            rows = int(lines_env)
        except ValueError:
            rows = 0
        if 0 < rows < 24:
            issues.append(
                {
                    "status": "warn",
                    "summary": f"LINES={rows} - content may scroll off (recommended >=24)",
                    "measured": f"{rows} rows",
                    "expected": ">= 24 rows",
                    "remedy": "resize the window to at least 24 rows",
                    "fields": ["LINES"],
                }
            )
    return issues

def _terminal_remediation(summary: str) -> str | None:
    if summary == "TERM=dumb - colors and cursor control are disabled":
        return "set TERM to a real value, for example xterm-256color"
    if summary.startswith("width ") or summary.startswith("COLUMNS="):
        return "resize the window to at least 80 columns"
    if summary.startswith("height ") or summary.startswith("LINES="):
        return "resize the window to at least 24 rows"
    if summary == "locale is not UTF-8 - unicode glyphs may render incorrectly":
        return "export LANG=en_US.UTF-8 or another UTF-8 locale"
    if summary == "TERMINFO unreadable - terminal capabilities are unknown":
        return "check that $TERMINFO points to a readable directory"
    return None

def inherited_managed_env_for_cargo_binary(
    current_exe: str | Path | None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> bool:
    environment = os.environ if env is None else env
    if "CODEX_MANAGED_BY_NPM" not in environment and "CODEX_MANAGED_BY_BUN" not in environment:
        return False
    if current_exe is None:
        return False
    components = Path(current_exe).parts
    return any(left == "target" and right in {"debug", "release"} for left, right in zip(components, components[1:]))

def doctor_managed_by_npm(
    current_exe: str | Path | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> bool:
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else current_exe
    return "CODEX_MANAGED_BY_NPM" in environment and not inherited_managed_env_for_cargo_binary(exe, env=environment)

def detect_update_action(
    current_exe: str | Path | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    codex_home: str | Path | None = None,
    is_macos: bool | None = None,
) -> UpdateAction | None:
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    if inherited_managed_env_for_cargo_binary(exe, env=environment):
        return None
    if "CODEX_MANAGED_BY_NPM" in environment:
        return UpdateAction.NPM_GLOBAL_LATEST
    if "CODEX_MANAGED_BY_BUN" in environment:
        return UpdateAction.BUN_GLOBAL_LATEST
    if _is_standalone_release_exe(exe, codex_home):
        return UpdateAction.STANDALONE_WINDOWS if os.name == "nt" else UpdateAction.STANDALONE_UNIX
    macos = sys.platform == "darwin" if is_macos is None else is_macos
    normalized = str(exe).replace("\\", "/")
    if macos and (normalized.startswith("/opt/homebrew") or normalized.startswith("/usr/local")):
        return UpdateAction.BREW_UPGRADE
    return None

def describe_install_context(
    current_exe: str | Path | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    codex_home: str | Path | None = None,
    is_macos: bool | None = None,
) -> str:
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    package_layout = _package_layout_from_exe(exe)
    if inherited_managed_env_for_cargo_binary(exe, env=environment):
        return _describe_method_with_package_layout("other", package_layout)
    if "CODEX_MANAGED_BY_NPM" in environment:
        return _describe_method_with_package_layout("npm", package_layout)
    if "CODEX_MANAGED_BY_BUN" in environment:
        return _describe_method_with_package_layout("bun", package_layout)

    standalone = _standalone_release_info(exe, codex_home)
    if standalone is not None:
        release_dir, resources_dir, standalone_layout = standalone
        platform = "windows" if os.name == "nt" else "unix"
        layout = standalone_layout or package_layout
        if layout is not None:
            package_dir, bin_dir, layout_resources_dir, path_dir = layout
            resources = _display_optional_path(layout_resources_dir)
            path = _display_optional_path(path_dir)
            return f"standalone ({platform}, package {package_dir}, bin {bin_dir}, resources {resources}, path {path})"
        resources = _display_optional_path(resources_dir)
        return f"standalone ({platform}, release {release_dir}, resources {resources})"

    macos = sys.platform == "darwin" if is_macos is None else is_macos
    normalized = str(exe).replace("\\", "/")
    if macos and (normalized.startswith("/opt/homebrew") or normalized.startswith("/usr/local")):
        return _describe_method_with_package_layout("brew", package_layout)
    return _describe_method_with_package_layout("other", package_layout)

def doctor_installation_check(
    *,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    codex_home: str | Path | None = None,
    show_details: bool = False,
    path_entries: list[str] | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
) -> DoctorUpdateCheck:
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    inherited = inherited_managed_env_for_cargo_binary(exe, env=environment)
    details = [
        f"current executable: {exe}",
        f"install context: {describe_install_context(exe, env=environment, codex_home=codex_home)}",
    ]
    if inherited:
        details.append("ignored inherited package-manager launch env for cargo-built binary")
    managed_by_npm = doctor_managed_by_npm(exe, env=environment)
    details.append(f"managed by npm: {'true' if managed_by_npm else 'false'}")
    details.append(f"managed by bun: {'true' if 'CODEX_MANAGED_BY_BUN' in environment else 'false'}")
    managed_package_root = environment.get("CODEX_MANAGED_PACKAGE_ROOT")
    if managed_package_root is None:
        details.append("managed package root: not set")
    else:
        details.append(f"managed package root: {Path(managed_package_root)}")
    entries = codex_path_entries(command_runner=command_runner) if path_entries is None else path_entries
    if len(entries) > 1:
        details.append(f"PATH codex entries: {len(entries)}")
    if show_details or len(entries) > 1:
        details.extend(f"PATH codex #{index}: {path}" for index, path in enumerate(entries, start=1))
    status = "ok"
    summary = "installation looks consistent"
    remediation = None
    if npm_root_check is None and managed_by_npm:
        npm_root_check = npm_global_root_check(env=environment, command_runner=command_runner)
    if npm_root_check is not None:
        if not isinstance(npm_root_check, NpmRootCheck):
            raise TypeError("npm_root_check must be an NpmRootCheck or None")
        if npm_root_check.kind == "match":
            details.append(f"npm update target: {npm_root_check.package_root}")
        elif npm_root_check.kind == "mismatch":
            status = "fail"
            summary = "npm install -g @openai/codex would update a different install"
            details.append(f"running package root: {npm_root_check.running_package_root}")
            details.append(f"npm package root: {npm_root_check.npm_package_root}")
            remediation = (
                "Fix PATH or npm prefix so the running package root "
                f"({npm_root_check.running_package_root}) matches the npm global package root "
                f"({npm_root_check.npm_package_root})."
            )
        elif npm_root_check.kind == "missing_package_root":
            status = "warn"
            summary = "npm-managed launch is missing package-root provenance"
            remediation = "Reinstall or update Codex so the JS shim provides CODEX_MANAGED_PACKAGE_ROOT."
        elif npm_root_check.kind == "npm_unavailable":
            status = "warn"
            summary = "npm-managed launch could not inspect npm global root"
            details.append(f"npm root -g failed: {npm_root_check.error}")
        else:
            raise ValueError(f"unknown npm root check kind: {npm_root_check.kind}")
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)

def codex_path_entries(*, command_runner: CommandRunner | None = None) -> list[str]:
    runner = run_command if command_runner is None else command_runner
    program = "where" if os.name == "nt" else "which"
    args = ("codex",) if os.name == "nt" else ("-a", "codex")
    try:
        output = runner(program, args)
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]

def _display_optional_path(path: Path | None) -> str:
    return str(path) if path is not None else "none"

def _describe_method_with_package_layout(
    method: str,
    package_layout: tuple[Path, Path, Path | None, Path | None] | None,
) -> str:
    if package_layout is None:
        return method
    package_dir, bin_dir, resources_dir, path_dir = package_layout
    resources = _display_optional_path(resources_dir)
    path = _display_optional_path(path_dir)
    return f"{method} (package {package_dir}, bin {bin_dir}, resources {resources}, path {path})"

def _package_layout_from_exe(current_exe: Path) -> tuple[Path, Path, Path | None, Path | None] | None:
    try:
        canonical_exe = current_exe.resolve(strict=True)
    except OSError:
        return None
    package_dir = _package_layout_root_from_exe(canonical_exe)
    if package_dir is None:
        return None
    bin_dir = canonical_exe.parent
    resources_dir = package_dir / "codex-resources"
    path_dir = package_dir / "codex-path"
    return (
        package_dir,
        bin_dir,
        resources_dir if resources_dir.is_dir() else None,
        path_dir if path_dir.is_dir() else None,
    )

def _standalone_release_info(
    current_exe: Path,
    codex_home: str | Path | None,
) -> tuple[Path, Path | None, tuple[Path, Path, Path | None, Path | None] | None] | None:
    if codex_home is None:
        return None
    try:
        canonical_home = Path(codex_home).resolve(strict=True)
        canonical_exe = current_exe.resolve(strict=True)
    except OSError:
        return None
    package_layout = _package_layout_from_exe(canonical_exe)
    release_dir = package_layout[0] if package_layout is not None else canonical_exe.parent
    releases_root = canonical_home / "packages" / "standalone" / "releases"
    try:
        release_dir.relative_to(releases_root)
    except ValueError:
        return None
    resources_dir = release_dir / "codex-resources"
    return (release_dir, resources_dir if resources_dir.is_dir() else None, package_layout)

def _is_standalone_release_exe(current_exe: Path, codex_home: str | Path | None) -> bool:
    return _standalone_release_info(current_exe, codex_home) is not None

def _package_layout_root_from_exe(current_exe: Path) -> Path | None:
    bin_dir = current_exe.parent
    if bin_dir.name != "bin":
        return None
    package_dir = bin_dir.parent
    if not (package_dir / PACKAGE_METADATA_FILENAME).is_file():
        return None
    return package_dir

def normalize_path_for_compare(path: str | Path) -> str:
    raw_path = Path(path)
    try:
        normalized = raw_path.resolve(strict=True)
    except OSError:
        normalized = raw_path
    raw = str(normalized).replace("\\", "/")
    if os.name == "nt":
        return raw.lower()
    return raw

def compare_npm_package_roots(running_package_root: str | Path, npm_root: str | Path) -> NpmRootCheck:
    npm_package_root = Path(npm_root) / "@openai" / "codex"
    running = normalize_path_for_compare(running_package_root)
    target = normalize_path_for_compare(npm_package_root)
    if running == target:
        return NpmRootCheck.match(npm_package_root)
    return NpmRootCheck.mismatch(running_package_root, npm_package_root)

def _git_command_output_text(stdout: str | bytes, *, success: bool = True) -> str | None:
    if not success:
        return None
    text = stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)
    normalized = "; ".join(line.strip() for line in text.splitlines() if line.strip())
    return normalized or None

def run_command(program: str, args: tuple[str, ...]) -> str:
    try:
        completed = subprocess.run(
            (program, *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if stderr:
            raise RuntimeError(stderr)
        raise RuntimeError(f"exited with status exit status {completed.returncode}")
    return completed.stdout

def npm_global_root_check(
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    command_runner: CommandRunner | None = None,
) -> NpmRootCheck:
    environment = os.environ if env is None else env
    running_package_root = environment.get("CODEX_MANAGED_PACKAGE_ROOT")
    if running_package_root is None:
        return NpmRootCheck.missing_package_root()

    runner = run_command if command_runner is None else command_runner
    try:
        output = runner("npm", ("root", "-g"))
    except Exception as exc:
        return NpmRootCheck.npm_unavailable(str(exc))
    npm_root = next((line.strip() for line in output.splitlines() if line.strip()), None)
    if npm_root is None:
        return NpmRootCheck.npm_unavailable("empty output from npm root -g")
    return compare_npm_package_roots(Path(running_package_root), Path(npm_root))

_DOCTOR_DETAIL_LIST_LIMIT = 7

_DOCTOR_DETAIL_PATH_LIMIT = 48


from pycodex.cli.doctor.system import SystemCheckInputs, system_check
from pycodex.cli.doctor.background import _background_server_mode, _concise_probe_error, _default_app_server_version_probe, _extract_user_agent, _parse_version_from_user_agent, _probe_websocket_immediate_close, _push_file_detail, background_server_check
from pycodex.cli.doctor.thread_inventory import _archive_mismatch_rows, _archived_from_rollout_path, _close_sqlite_connections_for_path, _count_or_skipped, _count_summary, _duplicate_values, _is_uuid_like, _missing_rollout_paths, _path_is_relative_to, _path_key, _push_feature_flag_details, _push_samples, _read_thread_inventory_rows, _rollout_scan_candidate_count, _scan_rollout_inventory, _scan_rollout_inventory_root, _session_meta_thread_id, _source_category, _thread_id_from_rollout, _thread_id_from_rollout_filename, _thread_id_from_rollout_jsonl, _thread_inventory_parity_check, _thread_inventory_scan_issue, thread_inventory_check
from pycodex.cli.doctor.git import GitCheckInputs, _git_candidates, _git_entry_summary, _git_repo_root, _git_summary, _normalized_git_branch, _old_windows_git_warning, _parse_git_version, _push_optional_detail, _run_git_output, _selected_git, git_check
from pycodex.cli.doctor.title import TerminalTitleInputs, _configured_terminal_title_items, _parse_terminal_title_items, _path_display_name, _terminal_title_project_candidate, _truncate_title_part, terminal_title_check
from pycodex.cli.doctor.runtime import _default_rg_command, _runtime_install_method_name, _rust_os_name, _select_rg_command_and_provider, runtime_check, search_check
from pycodex.cli.doctor.updates import GITHUB_LATEST_RELEASE_URL, HOMEBREW_CASK_API_URL, VersionInfo, build_doctor_update_check, cached_version_details, updates_check, updates_check_from_config, fetch_homebrew_cask_version, fetch_latest_github_release_version, fetch_latest_version, http_get_json, latest_version_details, latest_version_probe_error_details, push_cached_version_details, push_latest_version_details, push_latest_version_probe_error_details, update_action_label
from pycodex.cli.doctor.output.detail import _doctor_detail_attach_issue_expected, _doctor_detail_config_rows, _doctor_detail_database_row_value, _doctor_detail_display_label, _doctor_detail_feature_flags_summary_value, format_bytes, _doctor_detail_format_count, _doctor_detail_generic_kind_and_label, _doctor_detail_git_rows, _doctor_detail_home_shortened_path, _doctor_detail_humanize_detail, _doctor_detail_humanize_timestamp, _doctor_detail_humanize_value, _doctor_detail_install_rows, _doctor_detail_is_falsy, _doctor_detail_issue_expected_for_label, _doctor_detail_issue_remedies, _doctor_detail_lines_for_check, _doctor_detail_list_items, _doctor_detail_list_limit, _doctor_detail_looks_like_path, _doctor_detail_managed_by_value, _doctor_detail_middle_truncate, _doctor_detail_model_row_value, _doctor_detail_numbered_values, _doctor_detail_override_names, _doctor_detail_parse_detail, _doctor_detail_path_entry_values, _doctor_detail_path_limit, _doctor_detail_push_list_row_value, _doctor_detail_remaining_details, _doctor_detail_rollout_files_and_bytes, _doctor_detail_rollout_summary, _doctor_detail_rows_for_category, _doctor_detail_runtime_rows, _doctor_detail_shorten_path_prefix, _doctor_detail_state_rows, _doctor_detail_system_rows, _doctor_detail_title_rows, _doctor_detail_value, _doctor_detail_value_from_details, _doctor_detail_yes_no
from pycodex.cli.doctor.output import _doctor_duration_ms, _doctor_json_status, _doctor_json_string, _doctor_output_actionable_note_summary, _doctor_output_amber_no_color, _doctor_output_ascii_detail_marker, separator, _doctor_output_ascii_status_marker, _doctor_output_ascii_status_marker_slot, _doctor_output_auth_reachability_note_summary, _doctor_output_bold_no_color, _doctor_output_checks_for_group, _doctor_output_color256_no_color, _doctor_output_column_widths, _doctor_output_count_label_no_color, _doctor_output_cyan_no_color, _doctor_output_detail_label_no_color, _doctor_output_detail_value_no_color, _doctor_output_detailed_all_no_color_unicode_options, _doctor_output_detailed_color_unicode_options, _doctor_output_detailed_no_color_unicode_options, _doctor_output_dim_no_color, _doctor_output_display_status, _doctor_output_footer_lines, _doctor_output_green_no_color, _doctor_output_groups, _doctor_output_header_suffix, _doctor_output_highlight_actions_no_color, _doctor_output_highlight_flags_no_color, _doctor_output_is_safe_presence_value, _doctor_output_issue_summary, _doctor_output_looks_copyable, _doctor_output_non_ok_notes, _doctor_output_notes_order, _doctor_output_orange_no_color, _doctor_output_overall_status_label, _doctor_output_promoted_notes_without_status_change_lines, _doctor_output_red_no_color, _doctor_output_redact_detail, _doctor_output_redact_detail_env_var_branch, _doctor_output_redact_detail_fallback_branch, _doctor_output_redact_detail_safe_presence_branch, _doctor_output_redact_detail_secret_key_branch, _doctor_output_redact_url_path, _doctor_output_redact_url_token, _doctor_output_redact_urls, _doctor_output_rollout_note_summary, _doctor_output_row_description, _doctor_output_sample_report_check_metadata, _doctor_output_sample_report_detail_metadata, _doctor_output_sample_report_non_ok_notes, _doctor_output_sample_report_redacted_detail_lines, _doctor_output_sample_report_status_counts, _doctor_output_sample_report_summary_ascii_rendered, _doctor_output_sample_report_summary_background_server_lines, _doctor_output_sample_report_summary_configuration_lines, _doctor_output_sample_report_summary_connectivity_lines, _doctor_output_sample_report_summary_environment_lines, _doctor_output_sample_report_summary_footer_summary_line, _doctor_output_sample_report_summary_line, _doctor_output_sample_report_summary_no_color_rendered, _doctor_output_sample_report_summary_notes_lines, _doctor_output_sample_report_summary_section_blocks, _doctor_output_sample_report_summary_section_headings, _doctor_output_sample_report_summary_title_line, _doctor_output_sample_report_summary_updates_lines, _doctor_output_sandbox_note_summary, _doctor_output_state_health_summary_with_memories_db_lines, _doctor_output_status_counts_from_display_statuses, _doctor_output_style_description_no_color, _doctor_output_style_description_note_warning_fail_no_color, _doctor_output_style_description_ok_idle_no_color, _doctor_output_style_description_update_no_color, _doctor_output_style_detail_bare_token_copyable_no_color, _doctor_output_style_detail_bare_token_empty, _doctor_output_style_detail_bare_token_fallback_no_color, _doctor_output_style_detail_bare_token_falsy_no_color, _doctor_output_style_detail_bare_token_label_falsy_no_color, _doctor_output_style_detail_bare_token_no_color, _doctor_output_style_detail_bare_token_ok_no_color, _doctor_output_style_detail_bare_token_redacted_no_color, _doctor_output_style_detail_bare_token_unit_no_color, _doctor_output_style_detail_plain_text_no_color, _doctor_output_style_detail_plain_text_plain_no_color, _doctor_output_style_detail_text_no_color, _doctor_output_style_detail_text_plain_no_color, _doctor_output_style_detail_token_no_color, _doctor_output_style_detail_token_plain_no_color, _doctor_output_style_note_summary_non_update_no_color, _doctor_output_style_update_note_summary_from_note_no_color, _doctor_output_style_update_note_summary_no_color, _doctor_output_styled_overall_status_no_color, _doctor_output_summary_environment_threads_row, _doctor_output_summary_line_text, _doctor_output_summary_mode_footer_lines, _doctor_output_summary_no_color_unicode_options, _doctor_output_terminal_warning_issue_forbidden_summary, _doctor_output_terminal_warning_issue_lines, _doctor_output_update_note_summary, _doctor_output_very_dim_no_color, _doctor_overall_status, _redacted_doctor_issue_mapping, _redacted_doctor_issues, redact_detail, redacted_doctor_check_mapping, redacted_doctor_checks_mapping, redacted_doctor_report_mapping
from pycodex.cli.doctor.progress import _doctor_progress_status_label, _doctor_run_async_check, _doctor_run_sync_check, should_show_progress
