"""Python port entry point for Codex TUI.

Upstream Rust implementation for the terminal UI is in ``codex-rs/tui``.
This package mirrors the Rust ``codex-tui`` module boundaries so behavior can be
ported module-by-module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse

from ._porting import RustTuiModule
from .app.runtime import ActiveThreadRuntime
from pycodex.exec.session import RemoteAppServerEndpoint, app_server_control_socket_path

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="lib",
    source="codex/codex-rs/tui/src/lib.rs",
    status="complete",
)

_TOGGLE_RAW_OUTPUT_KEY_ACTION = "/__pycodex_toggle_raw_output"


class TUIUnavailableError(RuntimeError):
    """Backward-compatible exception class for callers that still import it."""


class ExitReason(Enum):
    """Python boundary for Rust ``codex_tui::ExitReason``."""

    UNKNOWN = "unknown"
    USER_REQUESTED = "UserRequested"
    FATAL = "Fatal"

    @classmethod
    def user_requested(cls) -> "ExitReason":
        return cls.USER_REQUESTED

    @classmethod
    def fatal(cls, message: str) -> "ExitReasonPayload":
        return ExitReasonPayload(cls.FATAL, message)


@dataclass(frozen=True)
class ExitReasonPayload:
    reason: ExitReason
    message: str | None = None


@dataclass(frozen=True)
class AppExitInfo:
    """Python boundary for Rust ``codex_tui::AppExitInfo``."""

    exit_reason: ExitReason | ExitReasonPayload = ExitReason.USER_REQUESTED
    token_usage: Any = None
    thread_id: str | None = None
    thread_name: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def reason(self) -> ExitReason | ExitReasonPayload:
        return self.exit_reason


@dataclass(frozen=True)
class AppServerTarget:
    kind: str
    endpoint: RemoteAppServerEndpoint | None = None

    @classmethod
    def embedded(cls) -> "AppServerTarget":
        return cls("Embedded")

    @classmethod
    def local_daemon(cls, endpoint: RemoteAppServerEndpoint) -> "AppServerTarget":
        return cls("LocalDaemon", endpoint=endpoint)

    @classmethod
    def remote(cls, endpoint: RemoteAppServerEndpoint) -> "AppServerTarget":
        return cls("Remote", endpoint=endpoint)

    def uses_remote_workspace(self) -> bool:
        return self.kind == "Remote"

    def thread_params_mode(self) -> str:
        return "Remote" if self.uses_remote_workspace() else "Embedded"


@dataclass(frozen=True)
class Cli:
    """Python boundary for Rust ``codex_tui::Cli``.

    The concrete argparse mapping will be filled in from ``tui/src/cli.rs``.
    """

    raw_args: tuple[str, ...] = ()


TUI_LOG_FILE_NAME = "codex-tui.log"


def remote_addr_parse_error_message(addr: str) -> str:
    return (
        f"invalid remote address `{addr}`; expected `ws://host:port`, "
        "`wss://host:port`, `unix://`, or `unix://PATH`"
    )


def remote_addr_has_explicit_port(addr: str, parsed: Any | None = None) -> bool:
    parsed = urlparse(addr) if parsed is None else parsed
    if parsed.hostname is None:
        return False
    if parsed.port is not None:
        return True
    if "://" not in addr:
        return False
    rest = addr.split("://", 1)[1]
    authority = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host_and_port = authority.rsplit("@", 1)[-1]
    default = {"ws": 80, "wss": 443}.get(parsed.scheme)
    if default is None:
        return False
    expected_host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return host_and_port == f"{expected_host}:{default}"


def websocket_url_supports_auth_token(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme == "wss" and parsed.hostname:
        return True
    if parsed.scheme != "ws" or not parsed.hostname:
        return False
    host = parsed.hostname
    if host.lower() == "localhost":
        return True
    try:
        import ipaddress

        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_remote_addr(
    addr: str,
    *,
    codex_home: Path | str | None = None,
    cwd: Path | str | None = None,
) -> RemoteAppServerEndpoint:
    if addr.startswith("unix://"):
        socket_path = addr.removeprefix("unix://")
        if socket_path == "":
            if codex_home is None:
                from pycodex.utils.home_dir import find_codex_home

                codex_home = find_codex_home()
            return RemoteAppServerEndpoint.unix_socket(app_server_control_socket_path(codex_home))
        path = Path(socket_path)
        if not path.is_absolute():
            path = (Path.cwd() if cwd is None else Path(cwd)) / path
        return RemoteAppServerEndpoint.unix_socket(path)

    parsed = urlparse(addr)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(remote_addr_parse_error_message(addr)) from exc
    if (
        parsed.scheme in {"ws", "wss"}
        and parsed.hostname is not None
        and remote_addr_has_explicit_port(addr, parsed)
        and (parsed.path or "/") == "/"
        and parsed.query == ""
        and parsed.fragment == ""
        and port is not None
    ):
        return RemoteAppServerEndpoint.websocket(parsed.geturl())
    raise ValueError(remote_addr_parse_error_message(addr))


def remote_addr_supports_auth_token(endpoint: RemoteAppServerEndpoint) -> bool:
    if endpoint.kind != "websocket":
        return False
    return websocket_url_supports_auth_token(str(endpoint.websocket_url))


def app_server_target_for_launch(
    explicit_remote_endpoint: RemoteAppServerEndpoint | None,
    default_daemon_socket: Path | str | None,
    can_reuse_implicit_local_daemon: bool,
) -> AppServerTarget:
    if explicit_remote_endpoint is not None:
        return AppServerTarget.remote(explicit_remote_endpoint)
    if can_reuse_implicit_local_daemon and default_daemon_socket is not None:
        return AppServerTarget.local_daemon(RemoteAppServerEndpoint.unix_socket(default_daemon_socket))
    return AppServerTarget.embedded()


def latest_session_cwd_filter(
    uses_remote_workspace: bool,
    remote_cwd_override: Path | str | None,
    config: Any,
    show_all: bool,
) -> Path | None:
    if show_all:
        return None
    if uses_remote_workspace:
        return None if remote_cwd_override is None else Path(remote_cwd_override)
    cwd = getattr(config, "cwd", None)
    if cwd is None and isinstance(config, dict):
        cwd = config.get("cwd")
    return None if cwd is None else Path(cwd)


def config_cwd_for_app_server_target(
    cwd: Path | str | None,
    app_server_target: AppServerTarget,
    environment_manager: Any | None = None,
) -> Path | None:
    if app_server_target.uses_remote_workspace() or _environment_manager_is_remote(environment_manager):
        return None
    target = Path.cwd() if cwd is None else Path(cwd)
    return target.resolve(strict=True)


def _environment_manager_is_remote(environment_manager: Any | None) -> bool:
    if environment_manager is None:
        return False
    default_environment = getattr(environment_manager, "default_environment", None)
    environment = default_environment() if callable(default_environment) else getattr(environment_manager, "environment", None)
    is_remote = getattr(environment, "is_remote", None)
    return bool(is_remote() if callable(is_remote) else is_remote)


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


ENTER_ALT_SCREEN = "\x1b[?1049h"
LEAVE_ALT_SCREEN = "\x1b[?1049l"
ENABLE_ALT_SCROLL = "\x1b[?1007h"
DISABLE_ALT_SCROLL = "\x1b[?1007l"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
CLEAR_SCREEN = "\x1b[2J"
CURSOR_HOME = "\x1b[H"
RESET_STYLE = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"
SAVE_CURSOR = "\x1b[s"
RESTORE_CURSOR = "\x1b[u"
def run_terminal_tui(
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: object | None,
    active_thread_runtime: ActiveThreadRuntime | None = None,
    use_alt_screen: bool = True,
) -> int:
    """Legacy terminal projection compatibility trap.

    Product TTY sessions enter ``textual_runtime.run_textual_tui`` directly
    from the CLI/app boundary.  The old dependency-light renderer is retained
    only as a migration symbol so tests can patch/assert it is not used.
    """

    raise TUIUnavailableError("legacy terminal TUI renderer has been removed; use textual_runtime.run_textual_tui")


def run_tui(*_args: object, stderr: object | None = None, **_kwargs: object) -> int:
    """Start the interactive TUI.

    Product interactive sessions are owned by ``textual_runtime``.  This
    compatibility boundary no longer starts the legacy terminal projection.
    """

    if stderr is None:
        import sys

        stderr = sys.stderr
    active_thread_runtime = _kwargs.get("active_thread_runtime")
    if active_thread_runtime is not None:
        from .textual_runtime import run_textual_tui

        return run_textual_tui(active_thread_runtime=active_thread_runtime)
    write = getattr(stderr, "write", None)
    if callable(write):
        if _enabled(os.environ.get("PYCODEX_TUI_FALLBACK")):
            write("pycodex: interactive TUI is disabled in this Python port.\n")
            return 0
        write("pycodex: interactive TUI requires an active thread runtime.\n")
    return 64


async def run_main(*_args: object, **kwargs: object) -> AppExitInfo:
    """Python boundary for Rust ``codex_tui::run_main``.

    The Rust root wires config/app-server setup and then enters the terminal
    app.  Python's product path already constructs the exec-backed prompt
    runner in ``pycodex.cli.parser``; this boundary accepts that runner as an
    injection point and executes the same terminal runtime.
    """

    import sys

    active_thread_runtime = kwargs.get("active_thread_runtime")
    if active_thread_runtime is None:
        stderr = kwargs.get("stderr", sys.stderr)
        write = getattr(stderr, "write", None)
        if callable(write):
            write("pycodex: codex_tui::run_main requires an active thread runtime in this Python port.\n")
        return AppExitInfo(exit_reason=ExitReasonPayload(ExitReason.FATAL, "missing active thread runtime"))

    from .textual_runtime import run_textual_tui

    code = run_textual_tui(active_thread_runtime=active_thread_runtime)
    if code == 0:
        return AppExitInfo(exit_reason=ExitReason.USER_REQUESTED)
    return AppExitInfo(exit_reason=ExitReasonPayload(ExitReason.FATAL, f"TUI exited with status {code}"))


__all__ = [
    "AppServerTarget",
    "AppExitInfo",
    "Cli",
    "ExitReason",
    "ExitReasonPayload",
    "RemoteAppServerEndpoint",
    "RUST_MODULE",
    "TUI_LOG_FILE_NAME",
    "app_server_target_for_launch",
    "config_cwd_for_app_server_target",
    "latest_session_cwd_filter",
    "remote_addr_has_explicit_port",
    "remote_addr_parse_error_message",
    "remote_addr_supports_auth_token",
    "resolve_remote_addr",
    "TUIUnavailableError",
    "websocket_url_supports_auth_token",
    "run_main",
    "run_tui",
]

