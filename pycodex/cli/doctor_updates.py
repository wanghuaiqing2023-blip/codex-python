"""Doctor update diagnostic helpers.

Ported from ``codex/codex-rs/cli/src/doctor/updates.rs``.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import locale
import os
import platform
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

from .update_action import UpdateAction, update_action_label
from .update_versions import is_newer

GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/openai/codex/releases/latest"
HOMEBREW_CASK_API_URL = "https://formulae.brew.sh/api/cask/codex.json"
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

    def to_mapping(self) -> dict[str, Any]:
        mapping: dict[str, Any] = {
            "status": self.status,
            "summary": self.summary,
            "details": list(self.details),
        }
        if self.remediation is not None:
            mapping["remediation"] = self.remediation
        return mapping


def redact_doctor_detail(detail: str) -> str:
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    if "env var" in label:
        return _redact_urls(detail)
    if ": " in detail:
        _name, value = detail.split(": ", 1)
        if value.strip().lower() in {"true", "false", "yes", "no", "present", "absent", "missing", "not set"}:
            return _redact_urls(detail)
    secret_keys = (
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    )
    if any(key in lower for key in secret_keys):
        name = detail.split(":", 1)[0]
        return f"{name}: <redacted>"
    return _redact_urls(detail)


def _doctor_json_status(status: Any) -> str:
    value = str(status)
    normalized = value.strip().lower()
    if normalized == "warn":
        return "warning"
    if normalized in {"ok", "warning", "fail"}:
        return normalized
    return "warning"


def _doctor_duration_ms(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return min(max(value, 0), U64_MAX)
    if isinstance(value, str):
        try:
            return min(max(int(value), 0), U64_MAX)
        except ValueError:
            return 0
    return 0


def _doctor_json_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _redacted_doctor_issue_mapping(issue: Mapping[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields", [])
    if not isinstance(fields, list):
        fields = []
    return {
        "severity": _doctor_json_status(issue.get("severity", "warn")),
        "cause": redact_doctor_detail(str(issue.get("cause", ""))),
        "measured": redact_doctor_detail(str(issue["measured"])) if issue.get("measured") is not None else None,
        "expected": redact_doctor_detail(str(issue["expected"])) if issue.get("expected") is not None else None,
        "remedy": redact_doctor_detail(str(issue["remedy"])) if issue.get("remedy") is not None else None,
        "fields": [redact_doctor_detail(str(field)) for field in fields],
    }


def _redacted_doctor_issues(issues: Any) -> list[dict[str, Any]]:
    if not isinstance(issues, list):
        return []
    return [_redacted_doctor_issue_mapping(issue) for issue in issues if isinstance(issue, Mapping)]


def redacted_doctor_check_mapping(check: dict[str, Any], *, check_key: str | None = None) -> dict[str, Any]:
    details, notes = _structured_redacted_details(check.get("details", []))
    default_id, default_category = _doctor_check_identity(check_key)
    mapping: dict[str, Any] = {
        "id": _doctor_json_string(check.get("id"), default_id),
        "category": _doctor_json_string(check.get("category"), default_category),
        "status": _doctor_json_status(check.get("status", "warn")),
        "summary": _doctor_json_string(check.get("summary")),
        "details": details,
    }
    issues = _redacted_doctor_issues(check.get("issues"))
    if issues:
        mapping["issues"] = issues
    if notes:
        mapping["notes"] = notes
    remediation = check.get("remediation")
    if isinstance(remediation, str):
        mapping["remediation"] = redact_doctor_detail(remediation)
    else:
        mapping["remediation"] = None
    mapping["durationMs"] = _doctor_duration_ms(check.get("durationMs", check.get("duration_ms", 0)))
    return mapping


def redacted_doctor_checks_mapping(checks: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    redacted: dict[str, dict[str, Any]] = {}
    for key, value in checks.items():
        check = redacted_doctor_check_mapping(value, check_key=key)
        redacted[str(check.get("id", key))] = check
    return dict(sorted(redacted.items()))


def redacted_doctor_report_mapping(
    *,
    checks: dict[str, dict[str, Any]],
    overall_status: str,
    codex_version: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": _doctor_json_string(generated_at, _doctor_generated_at()),
        "overallStatus": _doctor_json_status(overall_status),
        "codexVersion": _doctor_json_string(codex_version),
        "checks": redacted_doctor_checks_mapping(checks),
    }


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
class VersionInfo:
    latest_version: str
    dismissed_version: str | None = None
    last_checked_at: str | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> "VersionInfo":
        if not isinstance(value, dict):
            raise TypeError("version info must be an object")
        latest_version = value.get("latest_version")
        if not isinstance(latest_version, str):
            raise TypeError("latest_version must be a string")
        dismissed_version = value.get("dismissed_version")
        if dismissed_version is not None and not isinstance(dismissed_version, str):
            raise TypeError("dismissed_version must be a string or null")
        last_checked_at = value.get("last_checked_at")
        if last_checked_at is not None and not isinstance(last_checked_at, str):
            raise TypeError("last_checked_at must be a string or null")
        return cls(
            latest_version=latest_version,
            dismissed_version=dismissed_version,
            last_checked_at=last_checked_at,
        )


@dataclass(frozen=True)
class SystemCheckInputs:
    os: str
    os_type: str
    os_version: str
    os_language: str | None = None
    locale_env: dict[str, str] | None = None


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
class GitCheckInputs:
    selected_git: Path | None = None
    git_candidates: tuple[Path, ...] = ()
    git_version: str | None = None
    git_exec_path: str | None = None
    git_build_options: str | None = None
    repo_root: Path | None = None
    git_entry: str | None = None
    branch: str | None = None
    core_fsmonitor: str | None = None


@dataclass(frozen=True)
class TerminalTitleCheckInputs:
    configured_items: tuple[str, ...] | None = None
    cwd: Path = Path(".")
    project_root: Path | None = None
    project_source: str | None = None


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


def doctor_system_check(
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    inputs: SystemCheckInputs | None = None,
) -> DoctorUpdateCheck:
    if inputs is None:
        environment = os.environ if env is None else env
        detected_language = locale.getlocale()[0]
        inputs = SystemCheckInputs(
            os=platform.platform(),
            os_type=platform.system().lower() or "unknown",
            os_version=platform.version() or "unknown",
            os_language=detected_language,
            locale_env={name: environment[name] for name in LOCALE_ENV_VARS if name in environment},
        )
    locale_env = inputs.locale_env or {}
    details = [
        f"os: {inputs.os}",
        f"os type: {inputs.os_type}",
        f"os version: {inputs.os_version}",
    ]
    if inputs.os_language is None:
        details.append("os language: unavailable")
        summary = "OS language unavailable"
    else:
        details.append(f"os language: {inputs.os_language}")
        summary = f"OS language {inputs.os_language}"
    for name in LOCALE_ENV_VARS:
        value = locale_env.get(name)
        if value is not None:
            details.append(f"{name}: {value}")
    return DoctorUpdateCheck(status="ok", summary=summary, details=tuple(details))


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
            details=tuple(details + [str(exc)]),
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
            f"stored API key: {_bool_text(_optional_str(auth.get('OPENAI_API_KEY')) is not None)}",
            f"stored ChatGPT tokens: {_bool_text(isinstance(auth.get('tokens'), dict))}",
            f"stored agent identity: {_bool_text(_optional_str(auth.get('agent_identity')) is not None)}",
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


def doctor_background_server_check(
    *,
    codex_home: str | Path,
    socket_path: str | Path | None = None,
    version_probe: AppServerVersionProbe | None = None,
) -> DoctorUpdateCheck:
    home = Path(codex_home)
    state_dir = home / "app-server-daemon"
    details = [f"daemon state dir: {state_dir}"]
    _push_file_detail(details, "settings", state_dir / "settings.json")
    _push_file_detail(details, "pid file", state_dir / "app-server.pid")
    _push_file_detail(details, "update-loop pid file", state_dir / "app-server-updater.pid")

    control_socket = Path(socket_path) if socket_path is not None else home / "app-server-control" / "app-server-control.sock"
    details.append(f"control socket: {control_socket}")
    if not control_socket.exists():
        details.append("status: not running")
        details.append(f"mode: {_background_server_mode(state_dir)}")
        return DoctorUpdateCheck(
            status="ok",
            summary="background server is not running",
            details=tuple(details),
        )

    probe = version_probe or _default_app_server_version_probe
    try:
        app_server_version = probe(control_socket)
    except Exception as exc:
        details.append("status: stale or unreachable")
        details.append(f"app-server version: unavailable ({_concise_probe_error(exc, control_socket)})")
        details.append(f"mode: {_background_server_mode(state_dir)}")
        return DoctorUpdateCheck(
            status="warn",
            summary="background server socket is stale or unreachable",
            details=tuple(details),
            remediation="Run codex app-server daemon version for more details.",
        )
    details.append("status: running")
    details.append(f"app-server version: {app_server_version}")
    details.append(f"mode: {_background_server_mode(state_dir)}")
    return DoctorUpdateCheck(
        status="ok",
        summary="background server is running",
        details=tuple(details),
    )


def doctor_thread_inventory_check(
    *,
    codex_home: str | Path,
    sqlite_home: str | Path | None = None,
    default_provider: str = "openai",
) -> DoctorUpdateCheck:
    home = Path(codex_home)
    sqlite_root = Path(sqlite_home) if sqlite_home is not None else home
    scan = _scan_rollout_inventory(home)
    state_db_path = sqlite_root / "state_5.sqlite"
    details = [
        f"default model provider: {default_provider}",
        f"rollout DB active files: {sum(1 for item in scan['files'] if not item['archived'])}",
        f"rollout DB archived files: {sum(1 for item in scan['files'] if item['archived'])}",
        f"rollout DB scan errors: {len(scan['scan_errors'])}",
        f"rollout DB malformed file names: {len(scan['malformed_names'])}",
        f"rollout DB scan cap reached: {_bool_text(scan['reached_scan_cap'])}",
    ]
    _push_samples(details, "rollout DB scan error sample", scan["scan_errors"])
    _push_samples(details, "rollout DB malformed file sample", [str(path) for path in scan["malformed_names"]])

    if not state_db_path.is_file():
        details.append("rollout DB rows: skipped (state DB missing)")
        if not scan["files"] and not scan["scan_errors"] and not scan["malformed_names"] and not scan["reached_scan_cap"]:
            return DoctorUpdateCheck(
                status="ok",
                summary="no rollout/state DB inventory to compare",
                details=tuple(details),
            )
        summary = "state DB is missing while rollout files exist" if scan["files"] else "rollout scan was incomplete or found bad files"
        return DoctorUpdateCheck(
            status="warn",
            summary=summary,
            details=tuple(details),
            remediation=(
                "Start Codex with no state DB present so startup backfill can create it from rollout files."
                if scan["files"]
                else None
            ),
        )

    try:
        rows = _read_thread_inventory_rows(state_db_path)
    except Exception as exc:
        details.append(f"rollout DB read error: {exc}")
        return DoctorUpdateCheck(
            status="warn",
            summary="state database thread inventory could not be read",
            details=tuple(details),
        )

    return _thread_inventory_parity_check(home, scan, rows, details)


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


def doctor_git_check(
    *,
    cwd: str | Path | None = None,
    inputs: GitCheckInputs | None = None,
    selected_git: str | Path | None = None,
    git_candidates: tuple[str | Path, ...] | None = None,
    command_runner: GitCommandRunner | None = None,
    is_windows: bool | None = None,
) -> DoctorUpdateCheck:
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    if inputs is None:
        selected_git_path = Path(selected_git) if selected_git is not None else _selected_git()
        candidates = (
            tuple(Path(path) for path in git_candidates)
            if git_candidates is not None
            else tuple(_git_candidates())
        )
        runner = _run_git_output if command_runner is None else command_runner
        if selected_git_path is None:
            git_version = None
            git_exec_path = None
            git_build_options = None
            branch = None
            core_fsmonitor = None
        else:
            git_version = runner(selected_git_path, ("--version",), cwd_path)
            git_exec_path = runner(selected_git_path, ("--exec-path",), cwd_path)
            git_build_options = runner(selected_git_path, ("version", "--build-options"), cwd_path)
            branch = runner(selected_git_path, ("rev-parse", "--abbrev-ref", "HEAD"), cwd_path)
            core_fsmonitor = runner(selected_git_path, ("config", "--get", "core.fsmonitor"), cwd_path)
        repo_root = _git_repo_root(cwd_path)
        inputs = GitCheckInputs(
            selected_git=selected_git_path,
            git_candidates=candidates,
            git_version=git_version,
            git_exec_path=git_exec_path,
            git_build_options=git_build_options,
            repo_root=repo_root,
            git_entry=_git_entry_summary(repo_root) if repo_root is not None else None,
            branch=branch,
            core_fsmonitor=core_fsmonitor,
        )
    details: list[str] = []
    details.append(f"selected git: {inputs.selected_git}" if inputs.selected_git is not None else "selected git: not found")
    details.append(f"PATH git entries: {len(inputs.git_candidates)}")
    for index, path in enumerate(inputs.git_candidates, start=1):
        details.append(f"PATH git #{index}: {path}")
    _push_optional_detail(details, "git version", inputs.git_version)
    _push_optional_detail(details, "git exec path", inputs.git_exec_path)
    _push_optional_detail(details, "git build options", inputs.git_build_options)
    if inputs.repo_root is None:
        details.append("repo detected: false")
    else:
        details.append("repo detected: true")
        details.append(f"repo root: {inputs.repo_root}")
    _push_optional_detail(details, ".git entry", inputs.git_entry)
    _push_optional_detail(details, "git branch", _normalized_git_branch(inputs.branch))
    _push_optional_detail(details, "core.fsmonitor", inputs.core_fsmonitor or None)

    status = "ok"
    summary = _git_summary(inputs)
    remediation = None
    if inputs.selected_git is not None and inputs.git_version is None:
        status = "warn"
        summary = "Git executable found but could not be run"
        remediation = "Fix the selected Git executable or PATH so Codex can inspect Git metadata."
    elif inputs.selected_git is None and inputs.repo_root is not None:
        status = "warn"
        summary = "Git repository detected but git executable was not found"
        remediation = "Install Git or fix PATH so Codex can inspect repository metadata."
    else:
        warning = _old_windows_git_warning(inputs.git_version, os.name == "nt" if is_windows is None else is_windows)
        if warning is not None:
            status = "warn"
            summary = warning
            remediation = "Update Git for Windows or the bundled Git executable Codex resolves first."
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)


def doctor_terminal_title_check(
    *,
    cwd: str | Path | None = None,
    config: dict[str, Any] | None = None,
    inputs: TerminalTitleCheckInputs | None = None,
    project_root: str | Path | None = None,
    project_source: str | None = None,
) -> DoctorUpdateCheck:
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    if inputs is None:
        configured_items = _configured_terminal_title_items(config or {})
        root = Path(project_root) if project_root is not None else _git_repo_root(cwd_path)
        source = project_source if project_source is not None else ("git repo root" if root is not None else None)
        inputs = TerminalTitleCheckInputs(
            configured_items=configured_items,
            cwd=cwd_path,
            project_root=root,
            project_source=source,
        )
    if inputs.configured_items is None:
        source = "default"
        items = list(_DEFAULT_TERMINAL_TITLE_ITEMS)
        invalid_items: list[str] = []
    elif not inputs.configured_items:
        source = "disabled"
        items = []
        invalid_items = []
    else:
        source = "configured"
        items, invalid_items = _parse_terminal_title_items(inputs.configured_items)
    details = [
        f"terminal title source: {source}",
        f"terminal title items: {_display_list(items)}",
        f"terminal title activity: {_bool_text('activity' in items)}",
    ]
    if invalid_items:
        details.append(f"terminal title invalid items: {', '.join(invalid_items)}")
    if "project-name" in items:
        project_source_value, project_value = _terminal_title_project_candidate(
            inputs.project_root,
            inputs.cwd,
            inputs.project_source,
        )
        details.append(f"terminal title project source: {project_source_value}")
        details.append(f"terminal title project value: {project_value}")
    status = "warn" if invalid_items else "ok"
    summary = (
        f"terminal title {source} with invalid items"
        if invalid_items
        else f"terminal title {source}"
    )
    remediation = "Remove or replace the unknown entries in [tui].terminal_title." if invalid_items else None
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)


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
    if inputs.connect_timeout_ms is not None:
        details.append(f"connect timeout: {inputs.connect_timeout_ms} ms")
    details.append(f"auth mode: {inputs.auth_mode or 'none'}")
    if inputs.endpoint:
        details.append(f"endpoint: {inputs.endpoint}")
    if inputs.probe_error:
        return _websocket_probe_warning(
            "Responses WebSocket failed; HTTPS fallback may still work",
            details,
            inputs.probe_error,
        )
    return _websocket_probe_warning(
        "Responses WebSocket probe not run; HTTPS fallback may still work",
        details,
        "handshake probe not implemented in Python port",
    )


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
                details.append(
                    f"{endpoint.label} route probe: {endpoint.route_probe_url} {_http_probe_error_text(exc)} (required)"
                )
                route_failures.append(endpoint.route_probe_url)
                continue
            route_label = f"HTTP {route_status}"
            if 200 <= route_status < 300 or route_status in (401, 403):
                details.append(f"{endpoint.label} route probe: {endpoint.route_probe_url} route exists ({route_label})")
            elif route_status == 404:
                details.append(f"{endpoint.label} route probe: {endpoint.route_probe_url} returned {route_label} (required)")
                route_failures.append(endpoint.route_probe_url)
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
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            return "request timed out"
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
            env={name: environment[name] for name in _TERMINAL_ENV_NAMES if name in environment},
            present_env={name for name in _TERMINAL_ENV_NAMES if name in environment},
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
    for name in ("COLUMNS", "LINES"):
        if name in env_values:
            details.append(f"{name}: {env_values[name]}")
    details.append(f"color output: {_color_output_summary(inputs, env_values, present_env)}")
    for name in ("COLORTERM", "NO_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "FORCE_COLOR", "COLORFGBG"):
        if name in env_values:
            details.append(f"{name}: {env_values[name]}")
        elif name in present_env:
            details.append(f"{name}: present")
    terminfo_warning = _push_terminfo_details(details, env_values, present_env)
    locale_value = _effective_locale(env_values)
    if locale_value is not None:
        details.append(f"effective locale: {locale_value}")
    for name in ("SSH_TTY", "SSH_CONNECTION", "SSH_CLIENT", "MOSH_IP", "WSL_DISTRO_NAME", "WSL_INTEROP", "VSCODE_INJECTION", "VSCODE_IPC_HOOK_CLI", "WAYLAND_DISPLAY", "DISPLAY", "WT_SESSION"):
        if name in present_env:
            details.append(f"{name}: present")
    details.extend(inputs.tmux_details)
    details.extend(inputs.windows_console_details)

    issues: list[tuple[str, str]] = []
    if inputs.terminal == "dumb" or inputs.term == "dumb":
        issues.append(("fail", "TERM=dumb - colors and cursor control are disabled"))
    if locale_value is not None and _is_non_utf8_locale(locale_value):
        issues.append(("warn", "locale is not UTF-8 - unicode glyphs may render incorrectly"))
    if terminfo_warning:
        issues.append(("fail", "TERMINFO unreadable - terminal capabilities are unknown"))
    issues.extend(_terminal_size_issues(inputs, env_values))

    if any(status == "fail" for status, _summary in issues):
        status = "fail"
    elif issues:
        status = "warn"
    else:
        status = "ok"
    summary = issues[0][1] if issues else "terminal metadata was detected"
    remediation = _terminal_remediation(summary)
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)


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
    elif "TERMINFO" in present_env:
        details.append("TERMINFO: present")
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
                with path.open("rb") as handle:
                    handle.read(1)
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
        issues.append(f"{name}: stdio command {command!r} is not resolvable")
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
    if command_path.is_absolute() or command_path.parent != Path("."):
        return command_path.exists()
    search_path = None
    if isinstance(server_env, dict):
        env_path = server_env.get("PATH")
        if isinstance(env_path, str):
            search_path = env_path
    resolved = shutil.which(command, path=search_path)
    if resolved is not None:
        return True
    if cwd is not None:
        return (Path(cwd) / command).exists()
    return False


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


def _push_file_detail(details: list[str], label: str, path: Path) -> None:
    try:
        if path.is_file():
            details.append(f"{label}: {path} (file)")
        elif path.exists():
            details.append(f"{label}: {path} (not a file)")
        else:
            details.append(f"{label}: {path} (missing)")
    except OSError as exc:
        details.append(f"{label}: {path} ({exc})")


def _background_server_mode(state_dir: Path) -> str:
    return "persistent" if (state_dir / "settings.json").is_file() else "ephemeral"


def _default_app_server_version_probe(_socket_path: Path) -> str:
    raise RuntimeError("version probe not implemented in Python port")


def _concise_probe_error(exc: BaseException, socket_path: Path) -> str:
    message = str(exc).replace(str(socket_path), "control socket")
    message = " ".join(message.split())
    if not message:
        message = "unknown error"
    if len(message) > 120:
        return message[:120] + "..."
    return message


def _scan_rollout_inventory(codex_home: Path) -> dict[str, Any]:
    scan: dict[str, Any] = {
        "files": [],
        "scan_errors": [],
        "malformed_names": [],
        "reached_scan_cap": False,
    }
    _scan_rollout_inventory_root(codex_home / "sessions", False, scan)
    _scan_rollout_inventory_root(codex_home / "archived_sessions", True, scan)
    return scan


def _scan_rollout_inventory_root(root: Path, archived: bool, scan: dict[str, Any]) -> None:
    stack = [root]
    while stack:
        if _rollout_scan_candidate_count(scan) >= 10_000:
            scan["reached_scan_cap"] = True
            return
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except FileNotFoundError:
            continue
        except OSError as exc:
            scan["scan_errors"].append(f"{directory} ({exc})")
            continue
        for entry in entries:
            if _rollout_scan_candidate_count(scan) >= 10_000:
                scan["reached_scan_cap"] = True
                return
            try:
                if entry.is_dir():
                    stack.append(entry)
                    continue
                if not entry.is_file() or entry.suffix != ".jsonl" or not entry.name.startswith("rollout-"):
                    continue
            except OSError as exc:
                scan["scan_errors"].append(f"{entry} ({exc})")
                continue
            thread_id, unusable_reason = _thread_id_from_rollout(entry)
            if thread_id is None:
                if unusable_reason is None:
                    scan["malformed_names"].append(entry)
                else:
                    scan["scan_errors"].append(f"{entry} ({unusable_reason})")
                continue
            scan["files"].append(
                {
                    "path": entry,
                    "key": _path_key(entry),
                    "archived": archived,
                    "thread_id": thread_id,
                }
            )


def _rollout_scan_candidate_count(scan: dict[str, Any]) -> int:
    return len(scan["files"]) + len(scan["scan_errors"]) + len(scan["malformed_names"])


def _thread_id_from_rollout(path: Path) -> tuple[str | None, str | None]:
    jsonl_thread_id, error = _thread_id_from_rollout_jsonl(path)
    if jsonl_thread_id is not None:
        return jsonl_thread_id, None
    if error is not None:
        return None, error
    filename_thread_id = _thread_id_from_rollout_filename(path)
    if filename_thread_id is not None:
        return filename_thread_id, None
    return None, None


def _thread_id_from_rollout_jsonl(path: Path) -> tuple[str | None, str | None]:
    saw_parseable_line = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                saw_parseable_line = True
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    return None, str(exc)
                thread_id = _session_meta_thread_id(item)
                if thread_id is not None:
                    return thread_id, None
    except OSError as exc:
        return None, str(exc)
    if saw_parseable_line:
        return None, None
    return None, "no parseable rollout items"


def _session_meta_thread_id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    candidates: list[Any] = []
    if item.get("type") == "session_meta":
        candidates.append(item.get("payload"))
    nested_item = item.get("item")
    if isinstance(nested_item, dict) and nested_item.get("type") == "session_meta":
        candidates.append(nested_item.get("payload"))
    candidates.append(item.get("session_meta"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        thread_id = _optional_str(candidate.get("id"))
        if thread_id is not None and _is_uuid_like(thread_id):
            return thread_id.lower()
        meta = candidate.get("meta")
        if isinstance(meta, dict):
            thread_id = _optional_str(meta.get("id"))
            if thread_id is not None and _is_uuid_like(thread_id):
                return thread_id.lower()
    return None


def _thread_id_from_rollout_filename(path: Path) -> str | None:
    stem = path.stem
    prefix = "rollout-"
    if not stem.startswith(prefix):
        return None
    thread_id = stem[-36:]
    return thread_id.lower() if _is_uuid_like(thread_id) else None


def _is_uuid_like(value: str) -> bool:
    if len(value) != 36:
        return False
    parts = value.split("-")
    if [len(part) for part in parts] != [8, 4, 4, 4, 12]:
        return False
    return all(all(char in "0123456789abcdefABCDEF" for char in part) for part in parts)


def _read_thread_inventory_rows(state_db_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(state_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, rollout_path, archived, model_provider, source FROM threads"
        ).fetchall()
    return [
        {
            "id": str(row["id"]).lower(),
            "rollout_path": Path(str(row["rollout_path"])),
            "archived": bool(row["archived"]),
            "model_provider": str(row["model_provider"]),
            "source": str(row["source"]),
        }
        for row in rows
    ]


def _thread_inventory_parity_check(
    codex_home: Path,
    scan: dict[str, Any],
    rows: list[dict[str, Any]],
    details: list[str],
) -> DoctorUpdateCheck:
    files = scan["files"]
    rows_by_key: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_key.setdefault(_path_key(row["rollout_path"]), []).append(row)

    missing_active = _missing_rollout_paths(files, rows_by_key, archived=False)
    missing_archived = _missing_rollout_paths(files, rows_by_key, archived=True)
    scan_complete = not scan["reached_scan_cap"]
    stale_rows = [row for row in rows if not row["rollout_path"].is_file()] if scan_complete else []
    archive_mismatches = _archive_mismatch_rows(codex_home, files, rows) if scan_complete else []
    duplicate_rollout_thread_ids = _duplicate_values(str(item["thread_id"]) for item in files)
    duplicate_db_paths = _duplicate_values(str(_path_key(row["rollout_path"])) for row in rows)
    archived_rows = sum(1 for row in rows if row["archived"])
    active_rows = len(rows) - archived_rows

    details.extend(
        [
            f"rollout DB rows: {len(rows)}",
            f"rollout DB active rows: {active_rows}",
            f"rollout DB archived rows: {archived_rows}",
            f"rollout DB missing active rows: {len(missing_active)}",
            f"rollout DB missing archived rows: {len(missing_archived)}",
            f"rollout DB stale rows: {_count_or_skipped(len(stale_rows), scan_complete)}",
            f"rollout DB archive mismatches: {_count_or_skipped(len(archive_mismatches), scan_complete)}",
            f"rollout DB duplicate rollout thread ids: {len(duplicate_rollout_thread_ids)}",
            f"rollout DB duplicate DB paths: {len(duplicate_db_paths)}",
            f"rollout DB model providers: {_count_summary(row['model_provider'] for row in rows)}",
            f"rollout DB sources: {_count_summary(_source_category(row['source']) for row in rows)}",
        ]
    )
    _push_samples(details, "rollout DB missing active sample", [str(path) for path in missing_active])
    _push_samples(details, "rollout DB missing archived sample", [str(path) for path in missing_archived])
    _push_samples(details, "rollout DB stale row sample", [str(row["rollout_path"]) for row in stale_rows])
    _push_samples(details, "rollout DB archive mismatch sample", [str(row["rollout_path"]) for row in archive_mismatches])
    _push_samples(details, "rollout DB duplicate rollout thread id sample", duplicate_rollout_thread_ids)
    _push_samples(details, "rollout DB duplicate DB path sample", duplicate_db_paths)

    clean = (
        not scan["scan_errors"]
        and not scan["malformed_names"]
        and not scan["reached_scan_cap"]
        and not missing_active
        and not missing_archived
        and not stale_rows
        and not archive_mismatches
        and not duplicate_rollout_thread_ids
        and not duplicate_db_paths
    )
    return DoctorUpdateCheck(
        status="ok" if clean else "warn",
        summary=(
            "rollout files and state DB thread inventory agree"
            if clean
            else "rollout files and state DB thread inventory differ"
        ),
        details=tuple(details),
    )


def _missing_rollout_paths(files: list[dict[str, Any]], rows_by_key: dict[Path, list[dict[str, Any]]], *, archived: bool) -> list[Path]:
    missing: list[Path] = []
    for file in files:
        if file["archived"] != archived:
            continue
        rows = rows_by_key.get(file["key"], [])
        if not any(row["id"] == file["thread_id"] for row in rows):
            missing.append(file["path"])
    return missing


def _archive_mismatch_rows(codex_home: Path, files: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    archived_by_key = {file["key"]: file["archived"] for file in files}
    mismatches: list[dict[str, Any]] = []
    for row in rows:
        key = _path_key(row["rollout_path"])
        expected = archived_by_key.get(key)
        if expected is None:
            expected = _archived_from_rollout_path(codex_home, row["rollout_path"])
        if expected is not None and expected != row["archived"]:
            mismatches.append(row)
    return mismatches


def _archived_from_rollout_path(codex_home: Path, path: Path) -> bool | None:
    key = _path_key(path)
    if _path_is_relative_to(key, _path_key(codex_home / "archived_sessions")):
        return True
    if _path_is_relative_to(key, _path_key(codex_home / "sessions")):
        return False
    return None


def _path_key(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _duplicate_values(values: Any) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return sorted(value for value, count in counts.items() if count > 1)


def _count_or_skipped(count: int, complete: bool) -> str:
    return str(count) if complete else "skipped (scan cap reached)"


def _count_summary(values: Any) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    if not counts:
        return "none"
    entries = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    omitted = entries[8:]
    parts = [f"{key}={count}" for key, count in entries[:8]]
    if omitted:
        omitted_rows = sum(count for _key, count in omitted)
        parts.append(f"other={omitted_rows} across {len(omitted)} categories")
    return ", ".join(parts)


def _source_category(source: str) -> str:
    parsed: Any = source
    try:
        parsed = json.loads(source)
    except Exception:
        pass
    if isinstance(parsed, str):
        normalized = parsed.strip().lower()
        return {
            "cli": "cli",
            "vscode": "vscode",
            "exec": "exec",
            "mcp": "mcp",
            "unknown": "unknown",
        }.get(normalized, "unparsable")
    if not isinstance(parsed, dict):
        return "unparsable"
    source_type = _optional_str(parsed.get("type"))
    if source_type == "custom":
        return "custom"
    if source_type == "internal":
        internal_type = _optional_str(parsed.get("internal_source")) or _optional_str(parsed.get("source"))
        if internal_type == "memory_consolidation":
            return "internal:memory_consolidation"
        return "unparsable"
    if source_type == "subagent":
        subagent_source = parsed.get("subagent_source")
        if isinstance(subagent_source, str):
            return {
                "review": "subagent:review",
                "compact": "subagent:compact",
                "memory_consolidation": "subagent:memory_consolidation",
            }.get(subagent_source, "subagent:other")
        if isinstance(subagent_source, dict):
            subagent_type = _optional_str(subagent_source.get("type"))
            return {
                "review": "subagent:review",
                "compact": "subagent:compact",
                "thread_spawn": "subagent:thread_spawn",
                "memory_consolidation": "subagent:memory_consolidation",
                "other": "subagent:other",
            }.get(subagent_type or "", "subagent:other")
        return "subagent:other"
    return "unparsable"


def _push_samples(details: list[str], label: str, values: list[str]) -> None:
    for value in values[:5]:
        details.append(f"{label}: {value}")
    omitted = len(values) - 5
    if omitted > 0:
        details.append(f"{label}: {omitted} more omitted")


def _push_feature_flag_details(details: list[str], config: dict[str, Any]) -> None:
    features = config.get("features")
    if not isinstance(features, dict):
        enabled: list[str] = []
        overrides: list[str] = []
    else:
        enabled = sorted(key for key, value in features.items() if value is True)
        overrides = sorted(f"{key}={_bool_text(value)}" for key, value in features.items() if isinstance(value, bool))
    details.append(f"feature flags enabled: {len(enabled)}")
    details.append(f"enabled feature flags: {_display_list(enabled)}")
    details.append(f"feature flag overrides: {_display_list(overrides)}")


def _display_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _structured_redacted_details(raw_details: Any) -> tuple[dict[str, Any], list[str]]:
    details: dict[str, Any] = {}
    notes: list[str] = []
    if not isinstance(raw_details, list):
        return details, notes
    for raw_detail in raw_details:
        redacted = redact_doctor_detail(str(raw_detail))
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
    if _optional_str(auth.get("OPENAI_API_KEY")) is not None:
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
            if _optional_str(tokens.get("account_id")) is None:
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
    return name in env


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


def _push_optional_path_detail(details: list[str], label: str, path: Path | None) -> None:
    if path is None:
        details.append(f"{label}: none")
    else:
        details.append(f"{label}: {path}")


def _push_optional_detail(details: list[str], label: str, value: str | None) -> None:
    if value is not None:
        details.append(f"{label}: {value}")


def _selected_git() -> Path | None:
    selected = shutil.which("git")
    return Path(selected) if selected else None


def _git_candidates() -> list[Path]:
    seen: set[Path] = set()
    candidates: list[Path] = []
    path_exts = [""]
    if os.name == "nt":
        path_exts = [ext.lower() for ext in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if ext]
    for raw_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_dir:
            continue
        directory = Path(raw_dir)
        names = ["git"] if os.name != "nt" else [f"git{ext}" for ext in path_exts]
        for name in names:
            candidate = directory / name
            if candidate.exists() and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return candidates


def _run_git_output(git_path: Path, args: tuple[str, ...], cwd: Path) -> str | None:
    try:
        output = subprocess.run(
            [str(git_path), *args],
            cwd=cwd,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if output.returncode != 0:
        return None
    normalized = "; ".join(
        line.strip()
        for line in output.stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    )
    return normalized or None


def _git_repo_root(cwd: Path) -> Path | None:
    current = cwd if cwd.is_dir() else cwd.parent
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _git_entry_summary(repo_root: Path) -> str:
    entry = repo_root / ".git"
    try:
        if entry.is_dir():
            return "directory"
        if entry.is_file():
            try:
                contents = entry.read_text(encoding="utf-8")
            except OSError:
                return "file"
            if contents.startswith("gitdir:"):
                return f"file -> {contents.removeprefix('gitdir:').strip()}"
            return "file"
        if entry.exists():
            return "other"
        return "missing"
    except OSError as exc:
        return f"unreadable ({exc})"


def _normalized_git_branch(branch: str | None) -> str | None:
    if branch == "HEAD":
        return "detached HEAD"
    if branch:
        return branch
    return None


def _git_summary(inputs: GitCheckInputs) -> str:
    if inputs.git_version is not None:
        return inputs.git_version
    if inputs.selected_git is not None:
        return "git executable found; version unavailable"
    return "git executable not found"


def _old_windows_git_warning(version: str | None, is_windows: bool) -> str | None:
    if not is_windows or version is None:
        return None
    if "msysgit" in version.lower():
        return "old msysgit installation may corrupt Windows TUI rendering"
    parsed = _parse_git_version(version)
    if parsed is not None:
        major, minor, _patch = parsed
        if major < 2 or (major == 2 and minor <= 34):
            return "old Git for Windows may corrupt Windows TUI rendering"
    return None


def _parse_git_version(version: str) -> tuple[int, int, int] | None:
    if not version.startswith("git version "):
        return None
    numeric = version.removeprefix("git version ").split()[0].split(".windows.")[0]
    parts = numeric.split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2] if len(parts) > 2 else "0")
    except ValueError:
        return None


def _configured_terminal_title_items(config: dict[str, Any]) -> tuple[str, ...] | None:
    tui = config.get("tui")
    if isinstance(tui, dict):
        raw_items = tui.get("terminal_title")
    else:
        raw_items = config.get("terminal_title")
    if raw_items is None:
        return None
    if isinstance(raw_items, list):
        return tuple(str(item) for item in raw_items)
    return (str(raw_items),)


def _parse_terminal_title_items(raw_items: tuple[str, ...]) -> tuple[list[str], list[str]]:
    items: list[str] = []
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    for item in raw_items:
        parsed = _TERMINAL_TITLE_ITEM_ALIASES.get(item)
        if parsed is None:
            if item not in invalid_seen:
                invalid_seen.add(item)
                invalid.append(f'"{item}"')
        else:
            items.append(parsed)
    return items, invalid


def _terminal_title_project_candidate(
    project_root: Path | None,
    cwd: Path,
    project_source: str | None,
) -> tuple[str, str]:
    if project_root is not None:
        return project_source or "git repo root", _truncate_title_part(_path_display_name(project_root))
    return "cwd", _truncate_title_part(_path_display_name(cwd))


def _path_display_name(path: Path) -> str:
    return path.name or str(path)


def _truncate_title_part(value: str) -> str:
    if len(value) <= _PROJECT_TITLE_MAX_CHARS:
        return value
    return value[: _PROJECT_TITLE_MAX_CHARS - 3] + "..."


def _should_probe_models_route(provider_name: str, base_url: str, is_amazon_bedrock: bool) -> bool:
    return not is_amazon_bedrock and not _is_azure_responses_provider(provider_name, base_url)


def _is_amazon_bedrock_provider(provider_id: str, provider_name: str) -> bool:
    lowered = f"{provider_id} {provider_name}".lower()
    return "bedrock" in lowered


def _is_azure_responses_provider(provider_name: str, base_url: str) -> bool:
    lowered = f"{provider_name} {base_url}".lower()
    return "azure" in lowered and "openai.azure.com" in lowered


def _provider_url_for_path(base_url: str, path: str, query_params: dict[str, str] | None) -> str:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if path else base_url.rstrip("/")
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
            details.append(f"{label}: {path} (missing)")
            return
    except OSError as exc:
        details.append(f"{label}: {path} ({exc})")
        return
    details.append(f"{label}: {path} ({kind})")


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
        uri = path.absolute().as_posix()
        with sqlite3.connect(f"file:{uri}?mode=ro", uri=True) as connection:
            rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
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
                elif entry.is_file() and entry.suffix == ".jsonl" and entry.name.startswith("rollout-"):
                    files += 1
                    total_bytes += entry.stat().st_size
            except OSError as exc:
                return files, total_bytes, str(exc)
    return files, total_bytes, None


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
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if isinstance(inputs.terminal_size, tuple):
        columns, rows = inputs.terminal_size
        if 0 < columns < 80:
            issues.append(("warn", f"width {columns} cols - output may wrap (recommended >=80)"))
        if 0 < rows < 24:
            issues.append(("warn", f"height {rows} rows - content may scroll off (recommended >=24)"))
    columns_env = env_values.get("COLUMNS")
    if columns_env is not None:
        try:
            columns = int(columns_env)
        except ValueError:
            columns = 0
        if 0 < columns < 80:
            issues.append(("warn", f"COLUMNS={columns} - output may wrap (recommended >=80)"))
    lines_env = env_values.get("LINES")
    if lines_env is not None:
        try:
            rows = int(lines_env)
        except ValueError:
            rows = 0
        if 0 < rows < 24:
            issues.append(("warn", f"LINES={rows} - content may scroll off (recommended >=24)"))
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


def doctor_runtime_check(
    *,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    codex_home: str | Path | None = None,
) -> DoctorUpdateCheck:
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    environment = os.environ if env is None else env
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    platform_name = f"{_rust_os_name()}-{platform.machine().lower() or 'unknown'}"
    update_action = detect_update_action(exe, env=environment, codex_home=codex_home)
    install_method = _runtime_install_method_name(update_action)
    commit = environment.get("CODEX_BUILD_COMMIT") or environment.get("GIT_COMMIT") or "unknown"
    details = (
        f"version: {current_version}",
        f"platform: {platform_name}",
        f"install method: {describe_install_context(exe, env=environment, codex_home=codex_home)}",
        f"commit: {commit}",
        f"current executable: {exe}",
    )
    return DoctorUpdateCheck(
        status="ok",
        summary=f"running {install_method} on {platform_name}",
        details=details,
    )


def doctor_search_check(
    *,
    current_exe: str | Path | None = None,
    codex_home: str | Path | None = None,
    command_runner: CommandRunner | None = None,
    rg_command: str | Path | None = None,
    provider: str | None = None,
) -> DoctorUpdateCheck:
    exe = Path(sys.executable) if current_exe is None else Path(current_exe)
    selected_command, selected_provider = _select_rg_command_and_provider(exe, codex_home)
    command_path = Path(rg_command) if rg_command is not None else selected_command
    search_provider = selected_provider if provider is None else provider
    details = [
        f"search command: {command_path}",
        f"search provider: {search_provider}",
    ]
    status = "ok"
    if len(command_path.parts) > 1:
        if command_path.is_file():
            details.append("search command readiness: file exists")
        elif command_path.exists():
            status = "warn"
            details.append("search command readiness: path is not a file")
        else:
            status = "warn"
            details.append(f"search command readiness: {command_path} not found")
    else:
        runner = run_command if command_runner is None else command_runner
        try:
            output = runner(str(command_path), ("--version",))
        except Exception as exc:
            status = "warn"
            details.append(f"search command readiness: {exc}")
        else:
            first_line = next((line for line in output.splitlines() if line), "rg version unknown")
            details.append(f"search command readiness: {first_line}")
    summary = f"search is OK ({search_provider})" if status == "ok" else "search command could not be verified"
    remediation = None if status == "ok" else "Install ripgrep or repair the bundled Codex package."
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)


def _select_rg_command_and_provider(current_exe: Path, codex_home: str | Path | None) -> tuple[Path, str]:
    package_layout = _package_layout_from_exe(current_exe)
    if package_layout is not None:
        _package_dir, _bin_dir, _resources_dir, path_dir = package_layout
        if path_dir is not None:
            bundled_rg = path_dir / _default_rg_command()
            if bundled_rg.is_file():
                return bundled_rg, "bundled"
    standalone = _standalone_release_info(current_exe, codex_home)
    if standalone is not None:
        _release_dir, resources_dir, _layout = standalone
        if resources_dir is not None:
            bundled_rg = resources_dir / _default_rg_command()
            if bundled_rg.is_file():
                return bundled_rg, "bundled"
    return Path(_default_rg_command()), "system"


def _default_rg_command() -> str:
    return "rg.exe" if os.name == "nt" else "rg"


def _runtime_install_method_name(update_action: UpdateAction | None) -> str:
    if update_action is UpdateAction.NPM_GLOBAL_LATEST:
        return "npm"
    if update_action is UpdateAction.BUN_GLOBAL_LATEST:
        return "bun"
    if update_action is UpdateAction.BREW_UPGRADE:
        return "brew"
    if update_action in {UpdateAction.STANDALONE_UNIX, UpdateAction.STANDALONE_WINDOWS}:
        return "standalone"
    return "local build"


def _rust_os_name() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def cached_version_details(version_file: str | Path) -> list[str]:
    details: list[str] = []
    push_cached_version_details(details, version_file)
    return details


def push_cached_version_details(details: list[str], version_file: str | Path) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    path = Path(version_file)
    details.append(f"version cache: {path}")
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        details.append("version cache: missing")
        return
    except (OSError, UnicodeDecodeError) as exc:
        details.append(f"version cache read: {exc}")
        return

    try:
        info = VersionInfo.from_mapping(json.loads(contents))
    except (json.JSONDecodeError, TypeError) as exc:
        details.append(f"version cache parse: {exc}")
        return

    details.append(f"cached latest version: {info.latest_version}")
    if info.last_checked_at is not None:
        details.append(f"last checked at: {info.last_checked_at}")
    if info.dismissed_version is not None:
        details.append(f"dismissed version: {info.dismissed_version}")


def latest_version_details(latest_version: str, current_version: str) -> list[str]:
    details: list[str] = []
    push_latest_version_details(details, latest_version, current_version)
    return details


def push_latest_version_details(details: list[str], latest_version: str, current_version: str) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    if not isinstance(latest_version, str):
        raise TypeError("latest_version must be a string")
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    details.append(f"latest version: {latest_version}")
    if is_newer(latest_version, current_version) is True:
        details.append("latest version status: newer version is available")
    else:
        details.append("latest version status: current version is not older")


def latest_version_probe_error_details(error: str) -> list[str]:
    details: list[str] = []
    push_latest_version_probe_error_details(details, error)
    return details


def push_latest_version_probe_error_details(details: list[str], error: str) -> None:
    if not isinstance(details, list):
        raise TypeError("details must be a list")
    if not isinstance(error, str):
        raise TypeError("error must be a string")
    details.append(f"latest version probe: {error}")


def http_get_json(url: str, *, command_runner: CommandRunner | None = None) -> Any:
    if not isinstance(url, str):
        raise TypeError("url must be a string")
    runner = run_command if command_runner is None else command_runner
    try:
        body = runner("curl", ("-fsSL", "--max-time", "5", url))
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(str(exc)) from exc


def fetch_latest_version(
    update_action: UpdateAction | None,
    *,
    json_getter: JsonGetter | None = None,
) -> str:
    if update_action is not None and not isinstance(update_action, UpdateAction):
        raise TypeError("update_action must be an UpdateAction or None")
    getter = http_get_json if json_getter is None else json_getter
    if update_action is UpdateAction.BREW_UPGRADE:
        return fetch_homebrew_cask_version(json_getter=getter)
    return fetch_latest_github_release_version(json_getter=getter)


def fetch_latest_github_release_version(*, json_getter: JsonGetter | None = None) -> str:
    getter = http_get_json if json_getter is None else json_getter
    info = getter(GITHUB_LATEST_RELEASE_URL)
    if not isinstance(info, dict):
        raise TypeError("release info must be an object")
    tag_name = info.get("tag_name")
    if not isinstance(tag_name, str):
        raise TypeError("tag_name must be a string")
    prefix = "rust-v"
    if not tag_name.startswith(prefix):
        raise ValueError(f"failed to parse latest tag {tag_name}")
    return tag_name[len(prefix) :]


def fetch_homebrew_cask_version(*, json_getter: JsonGetter | None = None) -> str:
    getter = http_get_json if json_getter is None else json_getter
    info = getter(HOMEBREW_CASK_API_URL)
    if not isinstance(info, dict):
        raise TypeError("homebrew cask info must be an object")
    version = info.get("version")
    if not isinstance(version, str):
        raise TypeError("version must be a string")
    return version


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


def build_doctor_update_check(
    *,
    check_for_update_on_startup: bool,
    update_action: UpdateAction | None,
    version_file: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    if not isinstance(check_for_update_on_startup, bool):
        raise TypeError("check_for_update_on_startup must be a bool")
    if not isinstance(current_version, str):
        raise TypeError("current_version must be a string")
    if latest_version is not None and not isinstance(latest_version, str):
        raise TypeError("latest_version must be a string or None")
    if latest_error is not None and not isinstance(latest_error, str):
        raise TypeError("latest_error must be a string or None")

    details = [
        f"check for update on startup: {'true' if check_for_update_on_startup else 'false'}",
        f"update action: {update_action_label(update_action)}",
    ]
    push_cached_version_details(details, version_file)
    status = "ok"
    summary = "update configuration is locally consistent"
    remediation = None
    if npm_root_check is None and doctor_managed_by_npm(current_exe, env=env):
        npm_root_check = npm_global_root_check(env=env, command_runner=command_runner)
    if npm_root_check is not None:
        if not isinstance(npm_root_check, NpmRootCheck):
            raise TypeError("npm_root_check must be an NpmRootCheck or None")
        if npm_root_check.kind == "match":
            details.append(f"npm update target: {npm_root_check.package_root}")
        elif npm_root_check.kind == "mismatch":
            status = "fail"
            summary = "update would target a different npm install"
            details.append(f"running package root: {npm_root_check.running_package_root}")
            details.append(f"npm package root: {npm_root_check.npm_package_root}")
            remediation = (
                "Fix PATH or npm prefix so the running package root "
                f"({npm_root_check.running_package_root}) matches the npm global package root "
                f"({npm_root_check.npm_package_root})."
            )
        elif npm_root_check.kind == "missing_package_root":
            status = "warn"
            summary = "npm update target could not be proven"
            remediation = "Reinstall or update Codex so the JS shim provides CODEX_MANAGED_PACKAGE_ROOT."
        elif npm_root_check.kind == "npm_unavailable":
            status = "warn"
            summary = "npm update target could not be inspected"
            details.append(f"npm root -g failed: {npm_root_check.error}")
        else:
            raise ValueError(f"unknown npm root check kind: {npm_root_check.kind}")
    if latest_version is None and latest_error is None:
        try:
            latest_version = fetch_latest_version(update_action)
        except Exception as exc:
            latest_error = str(exc)
    if latest_version is not None:
        push_latest_version_details(details, latest_version, current_version)
    elif latest_error is not None:
        if status == "ok":
            status = "warn"
        push_latest_version_probe_error_details(details, latest_error)
    return DoctorUpdateCheck(status=status, summary=summary, details=tuple(details), remediation=remediation)


def doctor_updates_check(
    *,
    check_for_update_on_startup: bool,
    codex_home: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    version_file: str | Path | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    resolved_version_file = Path(codex_home) / "version.json" if version_file is None else version_file
    update_action = detect_update_action(current_exe, env=env, codex_home=codex_home)
    return build_doctor_update_check(
        check_for_update_on_startup=check_for_update_on_startup,
        update_action=update_action,
        version_file=resolved_version_file,
        current_version=current_version,
        current_exe=current_exe,
        env=env,
        npm_root_check=npm_root_check,
        command_runner=command_runner,
        latest_version=latest_version,
        latest_error=latest_error,
    )


def doctor_updates_check_from_config(
    config: Mapping[str, Any],
    *,
    codex_home: str | Path,
    current_version: str,
    current_exe: str | Path | None = None,
    env: dict[str, str] | os._Environ[str] | None = None,
    version_file: str | Path | None = None,
    npm_root_check: NpmRootCheck | None = None,
    command_runner: CommandRunner | None = None,
    latest_version: str | None = None,
    latest_error: str | None = None,
) -> DoctorUpdateCheck:
    check_for_update = config.get("check_for_update_on_startup")
    if not isinstance(check_for_update, bool):
        check_for_update = True
    return doctor_updates_check(
        check_for_update_on_startup=check_for_update,
        codex_home=codex_home,
        current_version=current_version,
        current_exe=current_exe,
        env=env,
        version_file=version_file,
        npm_root_check=npm_root_check,
        command_runner=command_runner,
        latest_version=latest_version,
        latest_error=latest_error,
    )
