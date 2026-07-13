"""Managed proxy routing helpers for the Linux sandbox.

Port of the pure planning/serialization helpers from
``codex/codex-rs/linux-sandbox/src/proxy_routing.rs``.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "FTP_PROXY",
    "YARN_HTTP_PROXY",
    "YARN_HTTPS_PROXY",
    "NPM_CONFIG_HTTP_PROXY",
    "NPM_CONFIG_HTTPS_PROXY",
    "NPM_CONFIG_PROXY",
    "BUNDLE_HTTP_PROXY",
    "BUNDLE_HTTPS_PROXY",
    "PIP_PROXY",
    "DOCKER_HTTP_PROXY",
    "DOCKER_HTTPS_PROXY",
)
PROXY_SOCKET_DIR_PREFIX = "codex-linux-sandbox-proxy-"


@dataclass(frozen=True, order=True)
class SocketAddr:
    host: str
    port: int

    @classmethod
    def parse(cls, value: str) -> "SocketAddr":
        host, sep, port = value.rpartition(":")
        if not sep:
            raise ValueError("socket address missing port")
        return cls(host, int(port))

    def __str__(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class ProxyRouteEntry:
    env_key: str
    uds_path: Path

    def to_mapping(self) -> dict[str, str]:
        return {"env_key": self.env_key, "uds_path": self.uds_path.as_posix()}

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> "ProxyRouteEntry":
        return cls(str(value["env_key"]), Path(str(value["uds_path"])))


@dataclass(frozen=True)
class ProxyRouteSpec:
    routes: tuple[ProxyRouteEntry, ...]

    def to_json(self) -> str:
        return json.dumps({"routes": [route.to_mapping() for route in self.routes]}, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "ProxyRouteSpec":
        data = json.loads(value)
        return cls(tuple(ProxyRouteEntry.from_mapping(item) for item in data.get("routes", ())))


@dataclass(frozen=True)
class PlannedProxyRoute:
    env_key: str
    endpoint: SocketAddr


@dataclass(frozen=True)
class ProxyRoutePlan:
    routes: tuple[PlannedProxyRoute, ...]
    has_proxy_config: bool


def plan_proxy_routes(env: dict[str, str]) -> ProxyRoutePlan:
    routes: list[PlannedProxyRoute] = []
    has_proxy_config = False
    for key, value in env.items():
        if not is_proxy_env_key(key):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        has_proxy_config = True
        endpoint = parse_loopback_proxy_endpoint(trimmed)
        if endpoint is None:
            continue
        routes.append(PlannedProxyRoute(key, endpoint))
    routes.sort(key=lambda route: route.env_key)
    return ProxyRoutePlan(tuple(routes), has_proxy_config)


def is_proxy_env_key(key: str) -> bool:
    return key.upper() in PROXY_ENV_KEYS


def parse_loopback_proxy_endpoint(proxy_url: str) -> SocketAddr | None:
    candidate = proxy_url if "://" in proxy_url else f"http://{proxy_url}"
    parsed = urlparse(candidate)
    host = parsed.hostname
    if host is None or not is_loopback_host(host):
        return None
    port = parsed.port or default_proxy_port(parsed.scheme.lower())
    if port == 0:
        return None
    ip = "127.0.0.1" if host.lower() == "localhost" else host
    try:
        parsed_ip = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not parsed_ip.is_loopback:
        return None
    return SocketAddr(str(parsed_ip), port)


def is_loopback_host(host: str) -> bool:
    return host.lower() == "localhost" or host in {"127.0.0.1", "::1"}


def default_proxy_port(scheme: str) -> int:
    if scheme == "https":
        return 443
    if scheme in {"socks5", "socks5h", "socks4", "socks4a"}:
        return 1080
    return 80


def rewrite_proxy_env_value(proxy_url: str, local_port: int) -> str | None:
    had_scheme = "://" in proxy_url
    candidate = proxy_url if had_scheme else f"http://{proxy_url}"
    parsed = urlparse(candidate)
    if not parsed.scheme or parsed.hostname is None:
        return None
    username = parsed.username or ""
    password = f":{parsed.password}" if parsed.password is not None else ""
    auth = f"{username}{password}@" if parsed.username is not None else ""
    netloc = f"{auth}127.0.0.1:{local_port}"
    rewritten = urlunparse((parsed.scheme, netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment))
    if not had_scheme and rewritten.startswith("http://"):
        rewritten = rewritten[len("http://") :]
    if (
        not proxy_url.endswith("/")
        and "?" not in proxy_url
        and "#" not in proxy_url
        and rewritten.endswith("/")
    ):
        rewritten = rewritten[:-1]
    return rewritten


def parse_proxy_socket_dir_owner_pid(file_name: str) -> int | None:
    if not file_name.startswith(PROXY_SOCKET_DIR_PREFIX):
        return None
    suffix = file_name[len(PROXY_SOCKET_DIR_PREFIX) :]
    pid_raw, sep, _ = suffix.partition("-")
    if not sep:
        return None
    try:
        pid = int(pid_raw)
    except ValueError:
        return None
    return pid if pid != 0 else None


def cleanup_proxy_socket_dir(socket_dir: Path | str) -> None:
    path = Path(socket_dir)
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return


def cleanup_stale_proxy_socket_dirs_in(temp_dir: Path | str) -> None:
    root = Path(temp_dir)
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        owner_pid = parse_proxy_socket_dir_owner_pid(entry.name)
        if owner_pid is None or is_pid_alive(owner_pid):
            continue
        cleanup_proxy_socket_dir(entry)


def is_pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        return _is_windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except OverflowError:
        return False
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_windows_pid_alive(pid: int) -> bool:
    """Use process handles instead of the incompatible Windows ``kill(pid, 0)``."""

    if pid <= 0 or pid > 0xFFFFFFFF:
        return False

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ctypes.get_last_error() == access_denied
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def prepare_host_proxy_route_spec() -> str:
    plan = plan_proxy_routes(dict(os.environ))
    if not plan.routes:
        if plan.has_proxy_config:
            message = "managed proxy mode requires parseable loopback proxy endpoints"
        else:
            message = "managed proxy mode requires proxy environment variables"
        raise ValueError(message)
    raise NotImplementedError("proxy bridge process creation is a runtime boundary in the Python port")


def activate_proxy_routes_in_netns(serialized_spec: str) -> None:
    spec = ProxyRouteSpec.from_json(serialized_spec)
    if not spec.routes:
        raise ValueError("proxy routing spec contained no routes")
    raise NotImplementedError("proxy bridge activation is a runtime boundary in the Python port")


__all__ = [
    "PROXY_ENV_KEYS",
    "PROXY_SOCKET_DIR_PREFIX",
    "PlannedProxyRoute",
    "ProxyRouteEntry",
    "ProxyRoutePlan",
    "ProxyRouteSpec",
    "SocketAddr",
    "activate_proxy_routes_in_netns",
    "cleanup_proxy_socket_dir",
    "cleanup_stale_proxy_socket_dirs_in",
    "default_proxy_port",
    "is_pid_alive",
    "is_loopback_host",
    "is_proxy_env_key",
    "parse_loopback_proxy_endpoint",
    "parse_proxy_socket_dir_owner_pid",
    "plan_proxy_routes",
    "prepare_host_proxy_route_spec",
    "rewrite_proxy_env_value",
]
