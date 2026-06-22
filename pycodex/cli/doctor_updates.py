"""Doctor update diagnostic helpers.

Ported from ``codex/codex-rs/cli/src/doctor/updates.rs``.
"""

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


def _should_show_doctor_progress(*, json_output: bool, term: str | None, stderr_is_tty: bool) -> bool:
    return not json_output and stderr_is_tty and term != "dumb"


def _doctor_output_ascii_status_marker(status: str) -> str:
    normalized = status.replace("-", "_").lower()
    if normalized == "ok":
        return "[ok]"
    if normalized == "update":
        return "[up]"
    if normalized in {"note", "warning", "warn"}:
        return "[!!]"
    if normalized == "fail":
        return "[XX]"
    if normalized == "idle":
        return "[--]"
    raise ValueError(f"Unknown doctor output status: {status}")


def _doctor_output_ascii_separator() -> str:
    return "-" * 61


def _doctor_output_column_widths() -> dict[str, int]:
    return {"name": 12, "detail_label": 24}


def _doctor_detail_format_bytes(byte_count: int) -> str:
    kib = 1024.0
    mib = kib * 1024.0
    gib = mib * 1024.0
    value = float(byte_count)
    if value >= gib:
        return f"{value / gib:.2f} GB"
    if value >= mib:
        return f"{value / mib:.2f} MB"
    if value >= kib:
        return f"{value / kib:.2f} KB"
    return f"{int(value)} B"


def _doctor_detail_format_count(count: int) -> str:
    return f"{count:,}"


def _doctor_detail_rollout_summary(value: str) -> str | None:
    try:
        files_text, rest = value.split(" files, ", 1)
        total_text, rest = rest.split(" total bytes, ", 1)
        average_text, _suffix = rest.split(" average bytes", 1)
        files = int(files_text.strip())
        total_bytes = int(total_text.strip())
        average_bytes = int(average_text.strip())
    except (ValueError, AttributeError):
        return None
    return (
        f"{_doctor_detail_format_count(files)} files "
        f"\u00b7 {_doctor_detail_format_bytes(total_bytes)} "
        f"(avg {_doctor_detail_format_bytes(average_bytes)})"
    )


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


def redact_doctor_detail(detail: str) -> str:
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    if "env var" in label:
        return _redact_urls(detail)
    if ": " in detail:
        name, value = detail.split(": ", 1)
        normalized_name = name.strip().lower()
        secret_keys = (
            "openai_api_key",
            "codex_api_key",
            "codex_access_token",
            "authorization",
            "bearer_token",
            "token",
            "secret",
        )
        if any(key in normalized_name for key in secret_keys):
            return f"{name}: <redacted>"
        if value.strip().lower() in {"true", "false", "yes", "no", "present", "absent", "missing", "not set"}:
            return _redact_urls(detail)
    return _redact_urls(detail)


def _doctor_json_status(status: Any) -> str:
    value = str(status)
    normalized = value.strip().lower()
    if normalized == "warn":
        return "warning"
    if normalized in {"ok", "warning", "fail"}:
        return normalized
    return "warning"


def _doctor_overall_status(checks: Any) -> str:
    statuses: list[str] = []
    for check in checks if isinstance(checks, list | tuple) else []:
        if isinstance(check, Mapping):
            statuses.append(_doctor_json_status(check.get("status", "warning")))
        else:
            statuses.append(_doctor_json_status(getattr(check, "status", "warning")))
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "warning" for status in statuses):
        return "warning"
    return "ok"


def _doctor_progress_status_label(check: Any) -> str:
    status = _doctor_json_status(
        check.get("status", "warning") if isinstance(check, Mapping) else getattr(check, "status", "warning")
    )
    return {"ok": "Ok", "warning": "Warning", "fail": "Fail"}[status]


def _doctor_run_sync_check(label: str, progress: Any, callback: Callable[[], Any]) -> Any:
    progress.begin(label)
    check = callback()
    progress.finish(label, _doctor_progress_status_label(check))
    return check


async def _doctor_run_async_check(label: str, progress: Any, awaitable: Any) -> Any:
    progress.begin(label)
    check = await awaitable
    progress.finish(label, _doctor_progress_status_label(check))
    return check


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
    _push_samples(
        details,
        "rollout DB malformed file sample",
        [_doctor_path_text(path) for path in scan["malformed_names"]],
    )

    if not state_db_path.is_file():
        details.append("rollout DB rows: skipped (state DB missing)")
        if not scan["files"] and not scan["scan_errors"] and not scan["malformed_names"] and not scan["reached_scan_cap"]:
            return DoctorUpdateCheck(
                status="ok",
                summary="no rollout/state DB inventory to compare",
                details=tuple(details),
            )
        summary = "state DB is missing while rollout files exist" if scan["files"] else "rollout scan was incomplete or found bad files"
        issues: list[dict[str, Any]] = []
        if scan["files"]:
            issues.append(
                {
                    "severity": "warn",
                    "cause": "rollout files exist but the state DB is missing",
                    "measured": f"{len(scan['files'])} rollout files",
                    "expected": "state DB contains matching thread rows",
                    "remedy": "Start Codex with no state DB present so startup backfill can create it from rollout files.",
                    "fields": [],
                }
            )
        if scan["scan_errors"] or scan["malformed_names"] or scan["reached_scan_cap"]:
            issues.append(_thread_inventory_scan_issue(scan))
        return DoctorUpdateCheck(
            status="warn",
            summary=summary,
            details=tuple(details),
            remediation=(
                "Start Codex with no state DB present so startup backfill can create it from rollout files."
                if scan["files"]
                else None
            ),
            issues=tuple(issues),
        )

    try:
        rows = _read_thread_inventory_rows(state_db_path)
    except Exception as exc:
        details.append(f"rollout DB read error: {exc}")
        return DoctorUpdateCheck(
            status="warn",
            summary="state database thread inventory could not be read",
            details=tuple(details),
            issues=(
                {
                    "severity": "warn",
                    "cause": "state DB thread rows could not be queried",
                    "measured": str(exc),
                    "expected": "readable threads table",
                    "remedy": None,
                    "fields": [],
                },
            ),
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
    details.append(
        f"selected git: {_doctor_path_text(inputs.selected_git)}"
        if inputs.selected_git is not None
        else "selected git: not found"
    )
    details.append(f"PATH git entries: {len(inputs.git_candidates)}")
    for index, path in enumerate(inputs.git_candidates, start=1):
        details.append(f"PATH git #{index}: {_doctor_path_text(path)}")
    _push_optional_detail(details, "git version", inputs.git_version)
    _push_optional_detail(details, "git exec path", inputs.git_exec_path)
    _push_optional_detail(details, "git build options", inputs.git_build_options)
    if inputs.repo_root is None:
        details.append("repo detected: false")
    else:
        details.append("repo detected: true")
        details.append(f"repo root: {_doctor_path_text(inputs.repo_root)}")
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
    websocket = StdlibWebSocket.connect_unix_socket(
        _socket_path,
        websocket_url=UDS_WEBSOCKET_HANDSHAKE_URL,
        timeout=10.0,
    )
    try:
        websocket.send_text(
            json.dumps(
                {
                    "id": 1,
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "codex", "title": "Codex Python", "version": "0.0.0"}},
                }
            )
        )
        frames = 0
        while True:
            if frames > 32:
                raise RuntimeError("timed out waiting for app-server initialize response")
            frames += 1
            response = websocket.recv_text(expect_masked=False)
            message = json.loads(response)
            if not isinstance(message, dict):
                raise RuntimeError(f"invalid initialize response: {type(message).__name__}")
            if "id" in message and message["id"] != 1:
                continue
            if "error" in message:
                error = message["error"]
                if isinstance(error, Mapping) and "message" in error:
                    raise RuntimeError(f"initialize failed: {error['message']}")
                raise RuntimeError(f"initialize failed: {error}")
            if "result" not in message:
                raise RuntimeError(f"invalid initialize response: {message!r}")
            result = message["result"]
            if not isinstance(result, Mapping):
                raise RuntimeError(f"invalid initialize result: {type(result).__name__}")
            user_agent = _extract_user_agent(result)
            if not user_agent:
                raise RuntimeError("initialize response missing user-agent")
            version = _parse_version_from_user_agent(user_agent)
            if not version:
                raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
            return version
    finally:
        with suppress(Exception):
            websocket.close()


def _extract_user_agent(result: Mapping[str, Any]) -> str | None:
    value = result.get("userAgent")
    if value is None:
        value = result.get("user_agent")
    if isinstance(value, str):
        return value
    return None


def _parse_version_from_user_agent(user_agent: str) -> str:
    parts = user_agent.split("/", 1)
    if len(parts) != 2:
        raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
    _, rest = parts
    version = rest.split()[0].strip()
    if not version:
        raise RuntimeError(f"invalid app-server user-agent: {user_agent}")
    return version


def _probe_websocket_immediate_close(websocket: StdlibWebSocket) -> tuple[int, str] | None:
    sock = getattr(websocket, "_sock", None)
    if sock is None or not hasattr(sock, "settimeout"):
        return None
    sock.settimeout(_WEBSOCKET_IMMEDIATE_CLOSE_GRACE_SECONDS)
    try:
        frame = websocket.recv_frame(expect_masked=False)
    except (socket.timeout, TimeoutError, EOFError):
        return None
    event = websocket_frame_event(frame)
    if event.kind != "close":
        return None
    if event.close_code is None:
        return None
    return event.close_code, event.close_reason or "connection closed"


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
            scan["scan_errors"].append(f"{_doctor_path_text(directory)} ({exc})")
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
                scan["scan_errors"].append(f"{_doctor_path_text(entry)} ({exc})")
                continue
            thread_id, unusable_reason = _thread_id_from_rollout(entry)
            if thread_id is None:
                if unusable_reason is None:
                    scan["malformed_names"].append(entry)
                else:
                    scan["scan_errors"].append(f"{_doctor_path_text(entry)} ({unusable_reason})")
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
    connection = sqlite3.connect(state_db_path)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, rollout_path, archived, model_provider, source FROM threads"
        ).fetchall()
    finally:
        connection.close()
    _close_sqlite_connections_for_path(state_db_path)
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


def _close_sqlite_connections_for_path(db_path: Path) -> None:
    target = str(db_path)
    try:
        normalized_target = str(db_path.resolve())
    except OSError:
        normalized_target = target
    for candidate in list(gc.get_objects()):
        if candidate.__class__.__name__ != "Connection":
            continue
        try:
            databases = candidate.execute("PRAGMA database_list").fetchall()
        except Exception:
            continue
        for _, _, filename in databases:
            if not isinstance(filename, str):
                continue
            normalized_filename = filename
            try:
                normalized_filename = str(Path(filename).resolve())
            except OSError:
                normalized_filename = filename
            if filename == target or normalized_filename == normalized_target:
                with suppress(Exception):
                    candidate.close()
                break


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
    _push_samples(details, "rollout DB missing active sample", [_doctor_path_text(path) for path in missing_active])
    _push_samples(details, "rollout DB missing archived sample", [_doctor_path_text(path) for path in missing_archived])
    _push_samples(
        details,
        "rollout DB stale row sample",
        [_doctor_path_text(row["rollout_path"]) for row in stale_rows],
    )
    _push_samples(
        details,
        "rollout DB archive mismatch sample",
        [_doctor_path_text(row["rollout_path"]) for row in archive_mismatches],
    )
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
    issues: list[dict[str, Any]] = []
    if missing_active or missing_archived:
        issues.append(
            {
                "severity": "warn",
                "cause": "rollout files are missing from the state DB",
                "measured": f"{len(missing_active)} active, {len(missing_archived)} archived",
                "expected": "every rollout file has a matching threads row",
                "remedy": None,
                "fields": [],
            }
        )
    if stale_rows:
        issues.append(
            {
                "severity": "warn",
                "cause": "state DB rows point at missing or unusable rollout files",
                "measured": f"{len(stale_rows)} stale rows",
                "expected": "every state DB rollout path is a file on disk",
                "remedy": None,
                "fields": [],
            }
        )
    if archive_mismatches:
        issues.append(
            {
                "severity": "warn",
                "cause": "state DB archive flags disagree with rollout file locations",
                "measured": f"{len(archive_mismatches)} mismatched rows",
                "expected": "rows under archived_sessions are archived and rows under sessions are active",
                "remedy": None,
                "fields": [],
            }
        )
    if duplicate_rollout_thread_ids or duplicate_db_paths:
        issues.append(
            {
                "severity": "warn",
                "cause": "duplicate thread inventory entries found",
                "measured": (
                    f"{len(duplicate_rollout_thread_ids)} duplicate rollout thread ids, "
                    f"{len(duplicate_db_paths)} duplicate DB paths"
                ),
                "expected": "one rollout path and thread id per thread",
                "remedy": "Attach the doctor report to a bug report so support can inspect samples.",
                "fields": [],
            }
        )
    if scan["scan_errors"] or scan["malformed_names"] or scan["reached_scan_cap"]:
        issues.append(_thread_inventory_scan_issue(scan))

    return DoctorUpdateCheck(
        status="ok" if clean else "warn",
        summary=(
            "rollout files and state DB thread inventory agree"
            if clean
            else "rollout files and state DB thread inventory differ"
        ),
        details=tuple(details),
        issues=tuple(issues),
    )


def _thread_inventory_scan_issue(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": "warn",
        "cause": "rollout scan was incomplete or found bad files",
        "measured": (
            f"{len(scan['scan_errors'])} scan errors, "
            f"{len(scan['malformed_names'])} malformed names, "
            f"scan cap reached: {_bool_text(scan['reached_scan_cap'])}"
        ),
        "expected": "rollout directories are fully scannable",
        "remedy": "Check file permissions and unexpected files under CODEX_HOME sessions.",
        "fields": [],
    }


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
    for usage in config.get("legacy_feature_usages", ()):
        if not isinstance(usage, dict):
            continue
        alias = _optional_str(usage.get("alias"))
        feature = _optional_str(usage.get("feature_key")) or _optional_str(usage.get("feature"))
        if alias and feature:
            details.append(f"legacy feature flag: {alias} -> {feature}")


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

_DOCTOR_DETAIL_LIST_LIMIT = 7
_DOCTOR_DETAIL_PATH_LIMIT = 48


def _doctor_detail_list_limit() -> int:
    return _DOCTOR_DETAIL_LIST_LIMIT


def _doctor_detail_path_limit() -> int:
    return _DOCTOR_DETAIL_PATH_LIMIT


def _doctor_detail_humanize_timestamp(value: str) -> str | None:
    if len(value) < 17 or not value.endswith("Z"):
        return None
    if "T" not in value:
        return None
    date, time_part = value.split("T", 1)
    hour_minute = time_part[:5]
    if len(hour_minute) < 5:
        return None
    return f"{date} {hour_minute} UTC"


def _doctor_detail_looks_like_path(value: str) -> bool:
    return (
        value.startswith("/")
        or value.startswith("~/")
        or value.startswith("./")
        or value.startswith("../")
    )


def _doctor_detail_middle_truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    head_len = max_chars // 2
    tail_len = max(max_chars - (head_len + 1), 0)
    head = value[:head_len]
    tail = value[len(value) - tail_len:] if tail_len else ""
    return f"{head}\u2026{tail}"


def _doctor_detail_home_shortened_path(path: str, home: str | None = None) -> str:
    resolved_home = os.environ.get("HOME") if home is None else home
    if not resolved_home:
        return path
    if path == resolved_home:
        return "~"
    prefix = f"{resolved_home}/"
    if path.startswith(prefix):
        return f"~/{path[len(prefix):]}"
    return path


def _doctor_detail_shorten_path_prefix(value: str, home: str | None = None) -> str:
    if " (" in value:
        path, suffix_tail = value.split(" (", 1)
        suffix = f" ({suffix_tail}"
    else:
        path = value
        suffix = ""
    shortened_home = _doctor_detail_home_shortened_path(path, home)
    shortened = _doctor_detail_middle_truncate(shortened_home, _DOCTOR_DETAIL_PATH_LIMIT)
    return f"{shortened}{suffix}"


def _doctor_detail_humanize_value(value: str, home: str | None = None) -> str:
    if _doctor_detail_looks_like_path(value):
        return _doctor_detail_shorten_path_prefix(value, home)
    timestamp = _doctor_detail_humanize_timestamp(value)
    if timestamp is not None:
        return timestamp
    return value


def _doctor_detail_display_label(label: str) -> str:
    if label == "codex-linux-sandbox helper":
        return "linux helper"
    if label == "optional reachability failed":
        return "optional reachability"
    if label == "check for update on startup":
        return "startup update check"
    return label


def _doctor_detail_yes_no(value: str) -> str:
    return "yes" if value == "true" else "no"


def _doctor_detail_is_falsy(value: str) -> bool:
    return value.strip().lower() in {
        "",
        "false",
        "none",
        "not set",
        "unknown",
        "missing",
        "absent",
        "no",
        "-",
    }


def _doctor_detail_list_items(value: str) -> list[str]:
    if _doctor_detail_is_falsy(value):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _doctor_detail_override_names(items: list[str]) -> list[str]:
    return [item.split("=", 1)[0] for item in items]


def _doctor_detail_rollout_files_and_bytes(value: str) -> tuple[int, int] | None:
    try:
        files_text, rest = value.split(" files, ", 1)
        total_text, _rest = rest.split(" total bytes, ", 1)
        return (int(files_text.strip()), int(total_text.strip()))
    except (ValueError, AttributeError):
        return None


def _doctor_detail_parse_detail(detail: str) -> tuple[str, str]:
    if ": " in detail:
        label, value = detail.split(": ", 1)
        return (label, value)
    return ("", detail)


def _doctor_detail_numbered_values(parsed: list[tuple[str, str]], prefix: str) -> list[str]:
    return [value for label, value in parsed if label.startswith(prefix)]


def _doctor_detail_value(parsed: list[tuple[str, str]], label: str) -> str | None:
    for detail_label, value in parsed:
        if detail_label == label:
            return value
    return None


def _doctor_detail_push_list_row_value(items: list[str], *, show_all: bool) -> str:
    limit = len(items) if show_all else min(len(items), _DOCTOR_DETAIL_LIST_LIMIT)
    value = ", ".join(items[:limit])
    if limit < len(items):
        value += ", \u2026 (full list with --all)"
    return value


def _doctor_detail_database_row_value(path: str, integrity: str | None = None) -> str:
    if integrity is None:
        return path
    return f"{path} \u00b7 integrity {integrity}"


def _doctor_detail_feature_flags_summary_value(
    enabled_count_value: str | None,
    override_value: str | None,
    *,
    show_all: bool,
) -> str:
    try:
        enabled_count = int(enabled_count_value) if enabled_count_value is not None else 0
    except ValueError:
        enabled_count = 0
    overrides = _doctor_detail_list_items("none" if override_value is None else override_value)
    hint = " (full list with --all)" if not show_all and enabled_count > 0 else ""
    return f"{enabled_count} enabled \u00b7 {len(overrides)} overridden{hint}"


def _doctor_detail_managed_by_value(managed_by_npm: str, managed_by_bun: str, package_root: str) -> str:
    root = "\u2014" if _doctor_detail_is_falsy(package_root) else package_root
    return (
        f"npm: {_doctor_detail_yes_no(managed_by_npm)} "
        f"\u00b7 bun: {_doctor_detail_yes_no(managed_by_bun)} "
        f"\u00b7 package root {root}"
    )


def _doctor_detail_model_row_value(model: str, provider: str | None = None) -> str:
    if provider is None:
        return model
    return f"{model} \u00b7 {provider}"


def _doctor_detail_issue_remedies(remedies: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for remedy in remedies:
        if remedy is None or remedy in seen:
            continue
        seen.add(remedy)
        out.append(remedy)
    return out


def _doctor_detail_issue_expected_for_label(
    issues: list[dict[str, object]],
    label: str,
) -> str | None:
    for issue in issues:
        fields = issue.get("fields", [])
        if not isinstance(fields, list):
            continue
        for field in fields:
            field_text = str(field)
            if _doctor_detail_display_label(field_text) == label or field_text == label:
                expected = issue.get("expected")
                return None if expected is None else str(expected)
    return None


def _doctor_detail_attach_issue_expected(
    label: str,
    expected: str | None,
    issues: list[dict[str, object]],
) -> str | None:
    if expected is not None:
        return expected
    return _doctor_detail_issue_expected_for_label(issues, label)


def _doctor_detail_generic_kind_and_label(label: str, value: str) -> tuple[str, str | None, str]:
    if label == "":
        return ("bullet", None, value)
    return ("row", _doctor_detail_display_label(label), value)


def _doctor_detail_remaining_details(
    parsed: list[tuple[str, str]],
    consumed_labels: list[str],
    consumed_prefixes: list[str],
) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for label, value in parsed:
        if value == "ignored inherited package-manager launch env for cargo-built binary":
            continue
        if label in consumed_labels:
            continue
        if any(label.startswith(prefix) for prefix in consumed_prefixes):
            continue
        out.append(_doctor_detail_generic_kind_and_label(label, value))
    return out


def _doctor_detail_path_entry_values(entries: list[str], *, show_all: bool) -> list[tuple[str, str]]:
    if not entries:
        return []
    total = len(entries)
    shown = total if show_all else min(total, 3)
    out: list[tuple[str, str]] = [(f"PATH entries ({total})", entries[0])]
    out.extend(("continuation", entry) for entry in entries[1:shown])
    if shown < total:
        out.append(("continuation", "\u2026 (full list with --all)"))
    return out


def _doctor_detail_system_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("os", "os"),
        ("os language", "OS language"),
        ("LC_ALL", "LC_ALL"),
        ("LC_CTYPE", "LC_CTYPE"),
        ("LANG", "LANG"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            ["os", "os type", "os version", "os language", "LC_ALL", "LC_CTYPE", "LANG"],
            [],
        )
    )
    return out


def _doctor_detail_runtime_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("version", "version"),
        ("install method", "install method"),
        ("commit", "commit"),
        ("current executable", "executable"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            ["version", "platform", "install method", "commit", "current executable"],
            [],
        )
    )
    return out


def _doctor_detail_title_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("terminal title source", "title source"),
        ("terminal title items", "title items"),
        ("terminal title activity", "activity item"),
        ("terminal title project source", "project source"),
        ("terminal title project value", "project value"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "terminal title source",
                "terminal title items",
                "terminal title activity",
                "terminal title project source",
                "terminal title project value",
            ],
            [],
        )
    )
    return out


def _doctor_detail_state_rows(parsed: list[tuple[str, str]]) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("CODEX_HOME", "CODEX_HOME"),
        ("log dir", "log dir"),
        ("sqlite home", "sqlite home"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    for label in ("state DB", "log DB", "goals DB", "memories DB"):
        path = _doctor_detail_value(parsed, label)
        if path is not None:
            out.append(("row", label, _doctor_detail_database_row_value(path, _doctor_detail_value(parsed, f"{label} integrity"))))
    for source_label, display in (
        ("active rollout files", "active rollouts"),
        ("archived rollout files", "archived rollouts"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, _doctor_detail_rollout_summary(value) or value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "CODEX_HOME",
                "log dir",
                "sqlite home",
                "state DB",
                "log DB",
                "goals DB",
                "state DB integrity",
                "log DB integrity",
                "goals DB integrity",
                "memories DB",
                "memories DB integrity",
                "active rollout files",
                "archived rollout files",
            ],
            [],
        )
    )
    return out


def _doctor_detail_git_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    for source_label, display in (
        ("selected git", "selected git"),
        ("git version", "version"),
        ("git exec path", "exec path"),
        ("repo detected", "repo detected"),
        ("repo root", "repo root"),
        (".git entry", ".git entry"),
        ("git branch", "branch"),
        ("core.fsmonitor", "core.fsmonitor"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.extend(("row", label, value) if label.startswith("PATH entries") else (label, None, value) for label, value in _doctor_detail_path_entry_values(_doctor_detail_numbered_values(parsed, "PATH git #"), show_all=show_all))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "selected git",
                "PATH git entries",
                "git version",
                "git exec path",
                "git build options",
                "repo detected",
                "repo root",
                ".git entry",
                "git branch",
                "core.fsmonitor",
            ],
            ["PATH git #"],
        )
    )
    return out


def _doctor_detail_install_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    context = _doctor_detail_value(parsed, "install context")
    if context is not None:
        out.append(("row", "context", context))
    if any(value == "ignored inherited package-manager launch env for cargo-built binary" for _label, value in parsed):
        out.append(("bullet", None, "ignored inherited package-manager launch env for cargo-built binary"))
    npm = _doctor_detail_value(parsed, "managed by npm") or "false"
    bun = _doctor_detail_value(parsed, "managed by bun") or "false"
    package_root = _doctor_detail_value(parsed, "managed package root") or "not set"
    out.append(("row", "managed by", _doctor_detail_managed_by_value(npm, bun, package_root)))
    out.extend(("row", label, value) if label.startswith("PATH entries") else (label, None, value) for label, value in _doctor_detail_path_entry_values(_doctor_detail_numbered_values(parsed, "PATH codex #"), show_all=show_all))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "current executable",
                "install context",
                "managed by npm",
                "managed by bun",
                "managed package root",
                "PATH codex entries",
            ],
            ["PATH codex #"],
        )
    )
    return out


def _doctor_detail_config_rows(parsed: list[tuple[str, str]], *, show_all: bool) -> list[tuple[str, str | None, str]]:
    out: list[tuple[str, str | None, str]] = []
    model = _doctor_detail_value(parsed, "model")
    if model is not None:
        out.append(("row", "model", _doctor_detail_model_row_value(model, _doctor_detail_value(parsed, "model provider"))))
    for source_label, display in (
        ("cwd", "cwd"),
        ("config.toml", "config.toml"),
        ("config.toml parse", "config.toml parse"),
        ("config.toml read", "config.toml read"),
        ("mcp servers", "MCP servers"),
    ):
        value = _doctor_detail_value(parsed, source_label)
        if value is not None:
            out.append(("row", display, value))
    out.append(("row", "feature flags", _doctor_detail_feature_flags_summary_value(
        _doctor_detail_value(parsed, "feature flags enabled"),
        _doctor_detail_value(parsed, "feature flag overrides"),
        show_all=show_all,
    )))
    for label, value in parsed:
        if label == "legacy feature flag":
            out.append(("row", "legacy alias", value))
    out.extend(
        _doctor_detail_remaining_details(
            parsed,
            [
                "CODEX_HOME",
                "cwd",
                "model",
                "model provider",
                "log dir",
                "sqlite home",
                "mcp servers",
                "feature flags enabled",
                "enabled feature flags",
                "feature flag overrides",
                "legacy feature flag",
                "config.toml",
                "config.toml parse",
                "config.toml read",
            ],
            [],
        )
    )
    return out


def _doctor_detail_rows_for_category(
    category: str,
    parsed: list[tuple[str, str]],
    *,
    show_all: bool = False,
) -> list[tuple[str, str | None, str]]:
    if category == "system":
        return _doctor_detail_system_rows(parsed)
    if category == "runtime":
        return _doctor_detail_runtime_rows(parsed)
    if category == "install":
        return _doctor_detail_install_rows(parsed, show_all=show_all)
    if category == "git":
        return _doctor_detail_git_rows(parsed, show_all=show_all)
    if category == "title":
        return _doctor_detail_title_rows(parsed)
    if category == "config":
        return _doctor_detail_config_rows(parsed, show_all=show_all)
    if category == "state":
        return _doctor_detail_state_rows(parsed)
    return [_doctor_detail_generic_kind_and_label(label, value) for label, value in parsed]


def _doctor_detail_value_from_details(details: list[str], label: str) -> str | None:
    parsed = [_doctor_detail_parse_detail(redact_doctor_detail(detail)) for detail in details]
    return _doctor_detail_value(parsed, label)


def _doctor_detail_humanize_detail(kind: str, label: str | None, value: str, home: str | None = None) -> tuple[str, str | None, str]:
    if kind == "remedy":
        return (kind, label, value)
    return (kind, label, _doctor_detail_humanize_value(value, home))


def _doctor_detail_lines_for_check(
    category: str,
    details: list[str],
    issues: list[dict[str, object]],
    *,
    show_all: bool = False,
    home: str | None = None,
) -> list[tuple[str, str | None, str | None, str]]:
    parsed = [_doctor_detail_parse_detail(redact_doctor_detail(detail)) for detail in details]
    rows = _doctor_detail_rows_for_category(category, parsed, show_all=show_all)
    out: list[tuple[str, str | None, str | None, str]] = []
    for kind, label, value in rows:
        expected = _doctor_detail_attach_issue_expected(label or "", None, issues) if kind == "row" else None
        humanized_kind, humanized_label, humanized_value = _doctor_detail_humanize_detail(kind, label, value, home)
        out.append((humanized_kind, humanized_label, humanized_value, expected))
    for remedy in _doctor_detail_issue_remedies([issue.get("remedy") if isinstance(issue.get("remedy"), str) else None for issue in issues]):
        out.append(("remedy", None, remedy, None))
    return out


def _doctor_output_groups() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("Environment", ("system", "runtime", "install", "search", "git", "terminal", "title", "state", "threads")),
        ("Configuration", ("config", "auth", "mcp", "sandbox")),
        ("Updates", ("updates",)),
        ("Connectivity", ("network", "websocket", "reachability")),
        ("Background Server", ("app-server",)),
    ]


def _doctor_output_display_status(category: str, status: str, details: list[str]) -> str:
    normalized = status.strip().lower()
    if category == "app-server" and normalized == "ok" and "status: not running" in details:
        return "idle"
    if normalized in {"ok", "warning", "fail"}:
        return normalized
    if normalized == "warn":
        return "warning"
    return "warning"


def _doctor_output_overall_status_label(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "ok":
        return "ok"
    if normalized in {"warning", "warn"}:
        return "degraded"
    if normalized == "fail":
        return "failed"
    return "degraded"


def _doctor_output_issue_summary(check_summary: str, issue_causes: list[str]) -> str:
    if not issue_causes:
        return check_summary
    if len(issue_causes) == 1:
        return issue_causes[0]
    return f"{len(issue_causes)} issues - {'; '.join(issue_causes[:2])}"


def _doctor_output_row_description(
    status: str,
    summary: str,
    issue_causes: list[str],
    remediation: str | None = None,
    *,
    ascii_output: bool = False,
) -> str:
    normalized = status.strip().lower()
    is_problem = normalized in {"warning", "warn", "fail"}
    if is_problem and issue_causes:
        return _doctor_output_issue_summary(summary, issue_causes)
    if is_problem and remediation is not None:
        dash = " - " if ascii_output else " \u2014 "
        return f"{summary}{dash}{remediation}"
    return summary


def _doctor_output_update_note_summary(details: list[str], codex_version: str) -> str | None:
    latest_status = _doctor_detail_value_from_details(details, "latest version status")
    if latest_status is None or "newer version is available" not in latest_status:
        return None
    latest = (
        _doctor_detail_value_from_details(details, "latest version")
        or _doctor_detail_value_from_details(details, "cached latest version")
        or "newer version"
    )
    parenthetical = f"current {codex_version}"
    dismissed = _doctor_detail_value_from_details(details, "dismissed version")
    if dismissed is not None and not _doctor_detail_is_falsy(dismissed):
        parenthetical += f", dismissed {dismissed}"
    return f"{latest} available ({parenthetical})"


def _doctor_output_rollout_note_summary(details: list[str]) -> str | None:
    active = _doctor_detail_value_from_details(details, "active rollout files")
    if active is None:
        return None
    parsed = _doctor_detail_rollout_files_and_bytes(active)
    if parsed is None:
        return None
    files, bytes_on_disk = parsed
    if files < 1000 and bytes_on_disk < 1024 * 1024 * 1024:
        return None
    return f"{_doctor_detail_format_count(files)} active files \u00b7 {_doctor_detail_format_bytes(bytes_on_disk)} on disk"


def _doctor_output_sandbox_note_summary(details: list[str]) -> str | None:
    filesystem = _doctor_detail_value_from_details(details, "filesystem sandbox")
    network = _doctor_detail_value_from_details(details, "network sandbox")
    if filesystem is None or network is None:
        return None
    if filesystem == "restricted" and network == "restricted":
        return None
    return f"filesystem {filesystem} \u00b7 network {network}"


def _doctor_output_auth_reachability_note_summary(websocket_details: list[str], reachability_details: list[str]) -> str | None:
    auth_mode = _doctor_detail_value_from_details(websocket_details, "auth mode")
    reachability_mode = _doctor_detail_value_from_details(reachability_details, "reachability mode")
    if auth_mode is None or reachability_mode is None:
        return None
    if "chatgpt" in auth_mode.lower() and "api key" in reachability_mode.lower():
        return "mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode"
    return None


def _doctor_output_notes_order(categories: list[str]) -> list[str]:
    ordered: list[str] = []
    if "updates" in categories:
        ordered.append("updates")
    if "state" in categories:
        ordered.append("rollouts")
    if "sandbox" in categories:
        ordered.append("sandbox")
    ordered.extend(f"non-ok:{category}" for category in categories)
    if "websocket" in categories and "reachability" in categories:
        ordered.append("auth")
    return ordered


def _doctor_output_footer_lines(*, show_details: bool) -> list[str]:
    if show_details:
        return [
            "--summary compact output --all expand truncated lists",
            "--json redacted report",
        ]
    return [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists --json redacted report",
    ]


def _doctor_output_header_suffix(codex_version: str, runtime_details: list[str] | None = None) -> str:
    version = f"v{codex_version}"
    if runtime_details is None:
        return version
    platform_value = _doctor_detail_value_from_details(runtime_details, "platform")
    if platform_value is None:
        return version
    return f"{version} \u00b7 {platform_value}"


def _doctor_output_summary_line_text(
    *,
    ok: int,
    idle: int,
    notes: int,
    warning: int,
    fail: int,
    overall_status: str,
    ascii_output: bool = False,
) -> str:
    parts = [f"{ok} ok"]
    if idle > 0:
        parts.append(f"{idle} idle")
    if notes > 0:
        parts.append(f"{notes} notes")
    parts.append(f"{warning} warn")
    parts.append(f"{fail} fail")
    separator = " | " if ascii_output else " \u00b7 "
    return f"{separator.join(parts)} {_doctor_output_overall_status_label(overall_status)}"


def _doctor_output_checks_for_group(
    checks: list[tuple[str, str]],
    group_keys: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Return checks matching group keys in Rust output.rs group-key order."""
    return [check for key in group_keys for check in checks if check[0] == key]


def _doctor_output_actionable_note_summary(
    summary: str,
    *,
    issue_summary: str | None = None,
    remediation: str | None = None,
) -> str:
    """Mirror Rust output.rs actionable_note_summary text precedence."""
    if issue_summary is not None:
        return issue_summary
    if remediation is not None:
        return f"{summary} - {remediation}"
    return summary


def _doctor_output_non_ok_notes(checks: list[dict[str, str | None]]) -> list[tuple[str, str]]:
    """Mirror Rust output.rs non_ok_notes warning/fail filtering."""
    notes: list[tuple[str, str]] = []
    for check in checks:
        status = check.get("status")
        if status not in {"warning", "fail"}:
            continue
        summary = check.get("summary") or ""
        notes.append(
            (
                _doctor_output_display_status("", str(status), {}),
                _doctor_output_actionable_note_summary(
                    summary,
                    issue_summary=check.get("issue_summary"),
                    remediation=check.get("remediation"),
                ),
            )
        )
    return notes



def _doctor_output_ascii_status_marker_slot(status: str) -> str:
    """Mirror Rust output.rs status_marker_slot for ascii status markers."""
    return f"{_doctor_output_ascii_status_marker(status)} "


def _doctor_output_ascii_detail_marker(is_issue: bool) -> str:
    """Mirror Rust output.rs detail_marker for ascii output."""
    return ">" if is_issue else " "


def _doctor_output_style_update_note_summary_no_color(summary: str) -> str:
    """Mirror Rust output.rs style_update_note_summary when color is disabled."""
    return summary


def _doctor_output_count_label_no_color(count: int, label: str, status: str) -> str:
    """Mirror Rust output.rs count_label text when color styling is disabled."""
    if status not in {"ok", "update", "note", "warning", "fail", "idle"}:
        raise ValueError(f"unknown display status: {status}")
    return f"{count} {label}"


def _doctor_output_styled_overall_status_no_color(label: str, status: str) -> str:
    """Mirror Rust output.rs styled_overall_status when color is disabled."""
    if status not in {"ok", "warning", "fail"}:
        raise ValueError(f"unknown check status: {status}")
    return label


def _doctor_output_style_update_note_summary_from_note_no_color(
    status: str, summary: str
) -> str:
    """Mirror Rust output.rs style_note_summary update/no-color path."""
    if status != "update":
        raise ValueError("this helper only covers the update status no-color path")
    return _doctor_output_style_update_note_summary_no_color(summary)


def _doctor_output_highlight_actions_no_color(text: str) -> str:
    """Mirror Rust output.rs highlight_actions when color is disabled."""
    return text


def _doctor_output_highlight_flags_no_color(text: str) -> str:
    """Mirror Rust output.rs highlight_flags when styling has no visible effect."""
    return text


def _doctor_output_is_safe_presence_value(value: str) -> bool:
    """Mirror Rust output.rs is_safe_presence_value."""
    return value.strip().lower() in {
        "true",
        "false",
        "yes",
        "no",
        "present",
        "absent",
        "missing",
        "not set",
    }


def _doctor_output_redact_url_path(path: str) -> str:
    """Mirror Rust output.rs redact_url_path."""
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return path
    first_segment = segments[0]
    if len(segments) > 1:
        return f"/{first_segment}/<redacted>"
    return path


def _doctor_output_redact_url_token(token: str) -> str:
    """Mirror Rust output.rs redact_url_token for a single token."""
    scheme_end = token.find("://")
    if scheme_end == -1:
        return token
    suffix_start = len(token)
    trailing = set(" \t\n\r.,;:)]")
    while suffix_start > scheme_end + 3 and token[suffix_start - 1] in trailing:
        suffix_start -= 1
    body = token[:suffix_start]
    suffix = token[suffix_start:]
    scheme_prefix_end = scheme_end + 3
    rest = body[scheme_prefix_end:]
    authority_end_offset = len(rest)
    for separator in ("/", "?", "#"):
        index = rest.find(separator)
        if index != -1:
            authority_end_offset = min(authority_end_offset, index)
    authority_end = scheme_prefix_end + authority_end_offset
    authority = body[scheme_prefix_end:authority_end]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    path = body[authority_end:]
    query_index = len(path)
    for separator in ("?", "#"):
        index = path.find(separator)
        if index != -1:
            query_index = min(query_index, index)
    path = _doctor_output_redact_url_path(path[:query_index])
    return f"{body[:scheme_prefix_end]}{authority}{path}{suffix}"


def _doctor_output_redact_urls(detail: str) -> str:
    """Mirror Rust output.rs redact_urls over whitespace-inclusive tokens."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(detail):
        if char.isspace():
            out.append(_doctor_output_redact_url_token(detail[start : index + 1]))
            start = index + 1
    if start < len(detail):
        out.append(_doctor_output_redact_url_token(detail[start:]))
    return "".join(out)


def _doctor_output_redact_detail_env_var_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail branch for labels containing env var."""
    label = detail.lower().split(":", 1)[0]
    if "env var" not in label:
        raise ValueError("this helper only covers redact_detail env var labels")
    return _doctor_output_redact_urls(detail)


def _doctor_output_redact_detail_safe_presence_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail safe-presence value branch."""
    if ": " not in detail:
        raise ValueError("this helper only covers redact_detail details with ': '")
    _, value = detail.split(": ", 1)
    if not _doctor_output_is_safe_presence_value(value):
        raise ValueError("this helper only covers safe presence values")
    return _doctor_output_redact_urls(detail)


def _doctor_output_redact_detail_secret_key_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail secret-key branch."""
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    lower = detail.lower()
    if not any(key in lower for key in secret_keys):
        raise ValueError("this helper only covers redact_detail secret-key details")
    name = detail.split(":", 1)[0]
    return f"{name}: <redacted>"


def _doctor_output_redact_detail_fallback_branch(detail: str) -> str:
    """Mirror Rust output.rs redact_detail fallback branch."""
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    if "env var" in label:
        raise ValueError("env var branch is not the fallback branch")
    if ": " in detail:
        _, value = detail.split(": ", 1)
        if _doctor_output_is_safe_presence_value(value):
            raise ValueError("safe presence branch is not the fallback branch")
    if any(key in lower for key in secret_keys):
        raise ValueError("secret-key branch is not the fallback branch")
    return _doctor_output_redact_urls(detail)


def _doctor_output_status_counts_from_display_statuses(
    statuses: list[str], *, notes: int
) -> dict[str, int]:
    """Mirror Rust output.rs StatusCounts::from_report counting rules."""
    counts = {"ok": 0, "idle": 0, "notes": notes, "warning": 0, "fail": 0}
    for status in statuses:
        if status == "ok":
            counts["ok"] += 1
        elif status == "idle":
            counts["idle"] += 1
        elif status == "warning":
            counts["warning"] += 1
        elif status == "fail":
            counts["fail"] += 1
        elif status in {"update", "note"}:
            continue
        else:
            raise ValueError(f"unknown display status: {status}")
    return counts


def _doctor_output_bold_no_color(text: str) -> str:
    """Mirror Rust output.rs bold when color is disabled."""
    return text


def _doctor_output_dim_no_color(text: str) -> str:
    """Mirror Rust output.rs dim when color is disabled."""
    return text


def _doctor_output_detail_value_no_color(text: str) -> str:
    """Mirror Rust output.rs detail_value when color is disabled."""
    return text


def _doctor_output_color256_no_color(text: str, code: int) -> str:
    """Mirror Rust output.rs color256 when color is disabled."""
    if not 0 <= code <= 255:
        raise ValueError(f"xterm color code out of range: {code}")
    return text


def _doctor_output_green_no_color(text: str) -> str:
    """Mirror Rust output.rs green when color is disabled."""
    return _doctor_output_color256_no_color(text, 10)


def _doctor_output_amber_no_color(text: str) -> str:
    """Mirror Rust output.rs amber when color is disabled."""
    return _doctor_output_color256_no_color(text, 220)


def _doctor_output_orange_no_color(text: str) -> str:
    """Mirror Rust output.rs orange when color is disabled."""
    return _doctor_output_color256_no_color(text, 214)


def _doctor_output_red_no_color(text: str) -> str:
    """Mirror Rust output.rs red when color is disabled."""
    return _doctor_output_color256_no_color(text, 196)


def _doctor_output_cyan_no_color(text: str) -> str:
    """Mirror Rust output.rs cyan when color is disabled."""
    return _doctor_output_color256_no_color(text, 117)


def _doctor_output_very_dim_no_color(text: str) -> str:
    """Mirror Rust output.rs very_dim when color is disabled."""
    return _doctor_output_color256_no_color(text, 238)


def _doctor_output_detail_label_no_color(text: str) -> str:
    """Mirror Rust output.rs detail_label when color is disabled."""
    return _doctor_output_color256_no_color(text, 240)


def _doctor_output_looks_copyable(text: str) -> bool:
    """Mirror Rust output.rs looks_copyable."""
    return text.startswith(("http://", "https://", "wss://", "~/", "/", "./", "../"))


def _doctor_output_style_detail_token_plain_no_color(token: str) -> str:
    """Mirror Rust output.rs style_detail_token for plain bare tokens without styling branches."""
    trimmed = token.rstrip()
    suffix = token[len(trimmed) :]
    bare = trimmed.rstrip(",.:;)")
    punctuation = trimmed[len(bare) :]
    if not bare:
        return f"{punctuation}{suffix}"
    if (
        bare == "<redacted>"
        or "(missing)" in bare
        or bare.startswith("--")
        or _doctor_output_looks_copyable(bare)
        or bare in {"ok", "B", "KB", "MB", "GB", "TB", "files", "file"}
    ):
        raise ValueError("this helper only covers plain unstyled detail tokens")
    return f"{bare}{punctuation}{suffix}"


def _doctor_output_style_detail_plain_text_plain_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_plain_text for plain unstyled text."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char.isspace():
            out.append(_doctor_output_style_detail_token_plain_no_color(text[start : index + 1]))
            start = index + 1
    if start < len(text):
        out.append(_doctor_output_style_detail_token_plain_no_color(text[start:]))
    return "".join(out)


def _doctor_output_style_detail_text_plain_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_text for plain/no-color text."""
    parts = text.split("`")
    if not parts:
        return ""
    out = [_doctor_output_style_detail_plain_text_plain_no_color(parts[0])]
    in_code = True
    for part in parts[1:]:
        if in_code:
            out.append(_doctor_output_cyan_no_color(part))
        else:
            out.append(_doctor_output_style_detail_plain_text_plain_no_color(part))
        in_code = not in_code
    return "".join(out)



def _doctor_output_style_detail_bare_token_unit_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token unit-token no-color branch."""
    if bare not in {"B", "KB", "MB", "GB", "TB", "files", "file"}:
        raise ValueError("this helper only covers unit detail tokens")
    return _doctor_output_dim_no_color(bare)


def _doctor_output_style_detail_bare_token_ok_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token ok-token no-color branch."""
    if bare != "ok":
        raise ValueError("this helper only covers the ok detail token")
    return _doctor_output_green_no_color(bare)


def _doctor_output_style_detail_bare_token_copyable_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token flag/copyable no-color branch."""
    if not (bare.startswith("--") or _doctor_output_looks_copyable(bare)):
        raise ValueError("this helper only covers flag or copyable detail tokens")
    return _doctor_output_cyan_no_color(bare)


def _doctor_output_style_detail_bare_token_empty(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token empty-token branch."""
    if bare != "":
        raise ValueError("this helper only covers the empty detail token")
    return ""


def _doctor_output_style_detail_bare_token_redacted_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token <redacted> no-color branch."""
    if bare != "<redacted>":
        raise ValueError("this helper only covers the <redacted> detail token")
    return _doctor_output_color256_no_color(bare, 244)


def _doctor_output_style_detail_bare_token_falsy_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token falsy/missing no-color branch."""
    if "(missing)" not in bare and not _doctor_detail_is_falsy(bare):
        raise ValueError("this helper only covers falsy or missing detail tokens")
    return _doctor_output_color256_no_color(bare, 240)


def _doctor_output_style_detail_bare_token_label_falsy_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token label:falsy no-color branch."""
    if ":" not in bare:
        raise ValueError("this helper only covers label:value detail tokens")
    label, value = bare.split(":", 1)
    if not _doctor_detail_is_falsy(value):
        raise ValueError("this helper only covers falsy detail token values")
    return f"{label}:{_doctor_output_color256_no_color(value, 240)}"


def _doctor_output_style_detail_bare_token_fallback_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token fallback branch."""
    if (
        bare == ""
        or bare == "<redacted>"
        or "(missing)" in bare
        or _doctor_detail_is_falsy(bare)
        or bare == "ok"
        or bare.startswith("--")
        or _doctor_output_looks_copyable(bare)
        or bare in {"B", "KB", "MB", "GB", "TB", "files", "file"}
    ):
        raise ValueError("this helper only covers fallback detail tokens")
    if ":" in bare:
        _, value = bare.split(":", 1)
        if _doctor_detail_is_falsy(value):
            raise ValueError("label:falsy branch is not the fallback branch")
    return bare


def _doctor_output_style_description_ok_idle_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Ok/Idle branch with color disabled."""
    if status not in {"ok", "idle"}:
        raise ValueError("this helper only covers ok/idle description styling")
    return _doctor_output_dim_no_color(_doctor_output_highlight_actions_no_color(description))


def _doctor_output_style_description_update_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Update branch with color disabled."""
    if status != "update":
        raise ValueError("this helper only covers update description styling")
    return _doctor_output_amber_no_color(_doctor_output_highlight_actions_no_color(description))


def _doctor_output_style_description_note_warning_fail_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description Note/Warning/Fail branch with color disabled."""
    if status not in {"note", "warning", "fail"}:
        raise ValueError("this helper only covers note/warning/fail description styling")
    return _doctor_output_highlight_actions_no_color(description)


def _doctor_output_style_note_summary_non_update_no_color(status: str, summary: str) -> str:
    """Mirror Rust output.rs style_note_summary non-update path with color disabled."""
    if status == "update":
        raise ValueError("update status uses style_update_note_summary")
    if status in {"ok", "idle"}:
        return _doctor_output_style_description_ok_idle_no_color(summary, status)
    if status in {"note", "warning", "fail"}:
        return _doctor_output_style_description_note_warning_fail_no_color(summary, status)
    raise ValueError(f"unknown display status: {status}")


def _doctor_output_style_detail_bare_token_no_color(bare: str) -> str:
    """Mirror Rust output.rs style_detail_bare_token branch order with color disabled."""
    if bare == "":
        return _doctor_output_style_detail_bare_token_empty(bare)
    if bare == "<redacted>":
        return _doctor_output_style_detail_bare_token_redacted_no_color(bare)
    if "(missing)" in bare or _doctor_detail_is_falsy(bare):
        return _doctor_output_style_detail_bare_token_falsy_no_color(bare)
    if ":" in bare:
        _, value = bare.split(":", 1)
        if _doctor_detail_is_falsy(value):
            return _doctor_output_style_detail_bare_token_label_falsy_no_color(bare)
    if bare == "ok":
        return _doctor_output_style_detail_bare_token_ok_no_color(bare)
    if bare.startswith("--") or _doctor_output_looks_copyable(bare):
        return _doctor_output_style_detail_bare_token_copyable_no_color(bare)
    if bare in {"B", "KB", "MB", "GB", "TB", "files", "file"}:
        return _doctor_output_style_detail_bare_token_unit_no_color(bare)
    return _doctor_output_style_detail_bare_token_fallback_no_color(bare)


def _doctor_output_style_detail_token_no_color(token: str) -> str:
    """Mirror Rust output.rs style_detail_token with full no-color bare-token dispatch."""
    trimmed = token.rstrip()
    suffix = token[len(trimmed) :]
    bare = trimmed.rstrip(",.:;)")
    punctuation = trimmed[len(bare) :]
    styled = _doctor_output_style_detail_bare_token_no_color(bare)
    return f"{styled}{punctuation}{suffix}"


def _doctor_output_style_detail_plain_text_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_plain_text with full no-color token dispatch."""
    out: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char.isspace():
            out.append(_doctor_output_style_detail_token_no_color(text[start : index + 1]))
            start = index + 1
    if start < len(text):
        out.append(_doctor_output_style_detail_token_no_color(text[start:]))
    return "".join(out)


def _doctor_output_style_detail_text_no_color(text: str) -> str:
    """Mirror Rust output.rs style_detail_text with full no-color plain/code dispatch."""
    parts = text.split("`")
    if not parts:
        return ""
    out = [_doctor_output_style_detail_plain_text_no_color(parts[0])]
    in_code = True
    for part in parts[1:]:
        if in_code:
            out.append(_doctor_output_cyan_no_color(part))
        else:
            out.append(_doctor_output_style_detail_plain_text_no_color(part))
        in_code = not in_code
    return "".join(out)


def _doctor_output_redact_detail(detail: str) -> str:
    """Mirror Rust output.rs redact_detail branch order."""
    lower = detail.lower()
    label = lower.split(":", 1)[0]
    if "env var" in label:
        return _doctor_output_redact_detail_env_var_branch(detail)
    if ": " in detail:
        _, value = detail.split(": ", 1)
        if _doctor_output_is_safe_presence_value(value):
            return _doctor_output_redact_detail_safe_presence_branch(detail)
    secret_keys = {
        "openai_api_key",
        "codex_api_key",
        "codex_access_token",
        "authorization",
        "bearer_token",
        "token",
        "secret",
    }
    if any(key in lower for key in secret_keys):
        return _doctor_output_redact_detail_secret_key_branch(detail)
    return _doctor_output_redact_detail_fallback_branch(detail)


def _doctor_output_style_description_no_color(description: str, status: str) -> str:
    """Mirror Rust output.rs style_description branch order with color disabled."""
    if status in {"ok", "idle"}:
        return _doctor_output_style_description_ok_idle_no_color(description, status)
    if status == "update":
        return _doctor_output_style_description_update_no_color(description, status)
    if status in {"note", "warning", "fail"}:
        return _doctor_output_style_description_note_warning_fail_no_color(description, status)
    raise ValueError(f"unknown display status: {status}")


def _doctor_output_detailed_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_no_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }


def _doctor_output_summary_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs summary_no_color_unicode_options test fixture."""
    return {
        "show_details": False,
        "show_all": False,
        "ascii": False,
        "color_enabled": False,
    }


def _doctor_output_detailed_all_no_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_all_no_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": True,
        "ascii": False,
        "color_enabled": False,
    }


def _doctor_output_detailed_color_unicode_options() -> dict[str, bool]:
    """Mirror Rust output.rs detailed_color_unicode_options test fixture."""
    return {
        "show_details": True,
        "show_all": False,
        "ascii": False,
        "color_enabled": True,
    }


def _doctor_output_sample_report_check_metadata() -> dict[str, object]:
    """Mirror Rust output.rs sample_report lightweight check metadata."""
    return {
        "schema_version": 1,
        "generated_at": "0s since unix epoch",
        "overall_status": "fail",
        "codex_version": "0.0.0",
        "checks": [
            ("system.environment", "system", "ok"),
            ("runtime.provenance", "runtime", "ok"),
            ("installation", "install", "ok"),
            ("runtime.search", "search", "ok"),
            ("git.environment", "git", "ok"),
            ("terminal.env", "terminal", "warning"),
            ("terminal.title", "title", "ok"),
            ("state.paths", "state", "ok"),
            ("auth.credentials", "auth", "fail"),
            ("updates.status", "updates", "ok"),
            ("network.env", "network", "ok"),
            ("network.websocket_reachability", "websocket", "ok"),
            ("app_server.status", "app-server", "ok"),
            ("network.provider_reachability", "reachability", "ok"),
        ],
    }


def _doctor_output_sample_report_detail_metadata() -> dict[str, dict[str, object]]:
    """Mirror Rust output.rs sample_report detail/remediation metadata."""
    return {
        "system.environment": {
            "details": ["os: macOS 15.0", "os language: en-US"],
            "remediation": None,
        },
        "git.environment": {
            "details": [
                "selected git: /usr/bin/git",
                "git version: git version 2.54.0",
                "repo detected: true",
            ],
            "remediation": None,
        },
        "terminal.title": {
            "details": [
                "terminal title source: default",
                "terminal title items: activity, project-name",
                "terminal title project value: codex",
            ],
            "remediation": None,
        },
        "auth.credentials": {
            "details": ["OPENAI_API_KEY: present"],
            "remediation": "Run `codex login`.",
        },
    }


def _doctor_output_sample_report_status_counts(notes: int = 0) -> dict[str, int]:
    """Mirror Rust output.rs sample_report status counts via StatusCounts::from_report."""
    report = _doctor_output_sample_report_check_metadata()
    statuses = [status for _, _, status in report["checks"]]
    return _doctor_output_status_counts_from_display_statuses(statuses, notes=notes)


def _doctor_output_sample_report_non_ok_notes() -> list[tuple[str, str]]:
    """Mirror Rust output.rs sample_report non-ok notes generation."""
    checks = [
        {"status": "ok", "summary": "OS language en-US"},
        {"status": "ok", "summary": "running local build on darwin-arm64"},
        {"status": "ok", "summary": "installation looks consistent"},
        {"status": "ok", "summary": "search is OK (bundled)"},
        {"status": "ok", "summary": "git version 2.54.0"},
        {"status": "warning", "summary": "narrow terminal"},
        {"status": "ok", "summary": "terminal title default"},
        {"status": "ok", "summary": "state paths inspectable"},
        {"status": "fail", "summary": "token expired", "remediation": "Run `codex login`."},
        {"status": "ok", "summary": "update configuration is locally consistent"},
        {"status": "ok", "summary": "network environment readable"},
        {"status": "ok", "summary": "Responses WebSocket handshake succeeded"},
        {"status": "ok", "summary": "background server is not running"},
        {"status": "ok", "summary": "active provider endpoints are reachable over HTTP"},
    ]
    return _doctor_output_non_ok_notes(checks)


def _doctor_output_sample_report_summary_line(*, ascii_output: bool = False, notes: int = 0) -> str:
    """Mirror Rust output.rs summary_line for sample_report counts."""
    counts = _doctor_output_sample_report_status_counts(notes=notes)
    return _doctor_output_summary_line_text(
        ok=counts["ok"],
        idle=counts["idle"],
        notes=counts["notes"],
        warning=counts["warning"],
        fail=counts["fail"],
        overall_status="fail",
        ascii_output=ascii_output,
    )


def _doctor_output_summary_mode_footer_lines() -> list[str]:
    """Mirror Rust output.rs summary-mode footer advice lines."""
    return [
        "Run codex doctor without --summary for detailed diagnostics.",
        "--all expand truncated lists       --json redacted report",
    ]


def _doctor_output_sample_report_summary_notes_lines() -> list[str]:
    """Mirror Rust output.rs summary output notes block for sample_report."""
    return [
        "Notes",
        "   ⚠ terminal     narrow terminal",
        "   ✗ auth         token expired - Run `codex login`.",
    ]


def _doctor_output_sample_report_summary_section_headings() -> list[str]:
    """Mirror Rust output.rs summary output section heading order for sample_report."""
    return [
        "Environment",
        "Configuration",
        "Updates",
        "Connectivity",
        "Background Server",
    ]


def _doctor_output_sample_report_summary_environment_lines() -> list[str]:
    """Mirror Rust output.rs summary output Environment rows for sample_report."""
    return [
        "  ✓ system       en-US",
        "  ✓ runtime      running local build on darwin-arm64",
        "  ✓ install      consistent",
        "  ✓ search       search is OK (bundled)",
        "  ✓ git          git version 2.54.0",
        "  ⚠ terminal     narrow terminal",
        "  ✓ title        default · project codex",
        "  ✓ state        state paths inspectable",
    ]

def _doctor_output_sample_report_summary_updates_lines() -> list[str]:
    """Mirror Rust output.rs summary output Updates rows for sample_report."""
    return [
        "  ✓ updates      update configuration is locally consistent",
    ]

def _doctor_output_sample_report_summary_connectivity_lines() -> list[str]:
    """Mirror Rust output.rs summary output Connectivity rows for sample_report."""
    return [
        "  ✓ network      network environment readable",
        "  ✓ websocket    Responses WebSocket handshake succeeded",
        "  ✓ reachability active provider endpoints are reachable over HTTP",
    ]

def _doctor_output_sample_report_summary_background_server_lines() -> list[str]:
    """Mirror Rust output.rs summary output Background Server rows for sample_report."""
    return [
        "  ✓ app-server   background server is not running",
    ]

def _doctor_output_sample_report_summary_configuration_lines() -> list[str]:
    """Mirror Rust output.rs summary output Configuration rows for sample_report."""
    return [
        "  ✗ auth         token expired — Run `codex login`.",
    ]

def _doctor_output_sample_report_summary_section_blocks() -> list[tuple[str, list[str]]]:
    """Mirror Rust output.rs summary output section blocks for sample_report."""
    return [
        ("Environment", _doctor_output_sample_report_summary_environment_lines()),
        ("Configuration", _doctor_output_sample_report_summary_configuration_lines()),
        ("Updates", _doctor_output_sample_report_summary_updates_lines()),
        ("Connectivity", _doctor_output_sample_report_summary_connectivity_lines()),
        ("Background Server", _doctor_output_sample_report_summary_background_server_lines()),
    ]

def _doctor_output_sample_report_summary_title_line() -> str:
    """Mirror Rust output.rs summary output title line for sample_report."""
    return "Codex Doctor v0.0.0"

def _doctor_output_sample_report_summary_footer_summary_line() -> str:
    """Mirror Rust output.rs summary output footer summary line for sample_report."""
    return _doctor_output_sample_report_summary_line(notes=2)


def _doctor_output_sample_report_summary_no_color_rendered() -> str:
    """Mirror Rust output.rs render_human_report summary/no-color sample_report snapshot."""
    separator = "─" * 61
    lines: list[str] = [
        _doctor_output_sample_report_summary_title_line(),
        "",
        *_doctor_output_sample_report_summary_notes_lines(),
        separator,
        "",
    ]
    for index, (heading, section_lines) in enumerate(
        _doctor_output_sample_report_summary_section_blocks()
    ):
        if index:
            lines.append("")
        lines.append(heading)
        lines.extend(section_lines)
    lines.extend(
        [
            "",
            separator,
            _doctor_output_sample_report_summary_footer_summary_line(),
            "",
            *_doctor_output_summary_mode_footer_lines(),
        ]
    )
    return "\n".join(lines) + "\n"

def _doctor_output_summary_environment_threads_row() -> str:
    """Mirror Rust output.rs summary row for state.rollout_db_parity in Environment."""
    return "  ⚠ threads      rollout files and state DB thread inventory differ"

def _doctor_output_state_health_summary_with_memories_db_lines() -> list[str]:
    """Mirror Rust output.rs detailed state health summary including memories DB."""
    return [
        "✓ state        databases healthy",
        "memories DB              /tmp/memories.sqlite · integrity ok",
    ]

def _doctor_output_sample_report_summary_ascii_rendered() -> str:
    """Mirror Rust output.rs render_human_report summary/ascii sample_report snapshot."""
    separator = "-" * 61
    return "\n".join(
        [
            "Codex Doctor v0.0.0",
            "",
            "Notes",
            "   [!!] terminal     narrow terminal",
            "   [XX] auth         token expired - Run `codex login`.",
            separator,
            "",
            "Environment",
            "  [ok] system       en-US",
            "  [ok] runtime      running local build on darwin-arm64",
            "  [ok] install      consistent",
            "  [ok] search       search is OK (bundled)",
            "  [ok] git          git version 2.54.0",
            "  [!!] terminal     narrow terminal",
            "  [ok] title        default | project codex",
            "  [ok] state        state paths inspectable",
            "",
            "Configuration",
            "  [XX] auth         token expired - Run `codex login`.",
            "",
            "Updates",
            "  [ok] updates      update configuration is locally consistent",
            "",
            "Connectivity",
            "  [ok] network      network environment readable",
            "  [ok] websocket    Responses WebSocket handshake succeeded",
            "  [ok] reachability active provider endpoints are reachable over HTTP",
            "",
            "Background Server",
            "  [ok] app-server   background server is not running",
            "",
            separator,
            "12 ok | 2 notes | 1 warn | 1 fail failed",
            "",
            "Run codex doctor without --summary for detailed diagnostics.",
            "--all expand truncated lists       --json redacted report",
        ]
    ) + "\n"

def _doctor_output_sample_report_redacted_detail_lines() -> list[str]:
    """Mirror Rust output.rs detailed sample_report redacted credential details."""
    return [
        "      OPENAI_API_KEY           present",
    ]

def _doctor_output_terminal_warning_issue_lines() -> list[str]:
    """Mirror Rust output.rs detailed terminal warning issue rendering."""
    return [
        "⚠ terminal     width 79 cols - output may wrap (recommended >=80)",
        "▸ terminal size            79x26 (expected >= 80 columns)",
        "→ resize the window to at least 80 columns",
    ]


def _doctor_output_terminal_warning_issue_forbidden_summary() -> str:
    """Mirror Rust output.rs terminal warning summary that must not be rendered."""
    return "⚠ terminal     Ghostty 1.3.1"

def _doctor_output_promoted_notes_without_status_change_lines() -> list[str]:
    """Mirror Rust output.rs promoted notes rendering without changing statuses."""
    return [
        "Notes\n   ↑ updates",
        "0.130.0 available (current 0.0.0, dismissed 0.128.0)",
        "⚠ rollouts",
        "⚠ sandbox",
        "⚠ mcp",
        "⚠ auth         mixed auth signals: ChatGPT login plus API key env var; HTTP reachability uses API-key mode",
        "○ app-server   not running (ephemeral mode)",
        "5 ok · 1 idle · 5 notes · 1 warn · 0 fail degraded",
    ]
