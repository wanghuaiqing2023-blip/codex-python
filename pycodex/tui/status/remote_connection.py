"""Semantic port of codex-rs/tui/src/status/remote_connection.rs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status::remote_connection",
    source="codex/codex-rs/tui/src/status/remote_connection.rs",
)


@dataclass(frozen=True)
class RemoteConnectionStatus:
    address: str
    version: str


def remote_connection_status_value(
    app_server_target: Any,
    server_version: str | None = None,
) -> RemoteConnectionStatus | None:
    target_kind = _kind(app_server_target)
    if target_kind == "Embedded":
        return None
    endpoint = _get(app_server_target, "endpoint")
    if endpoint is None:
        return None

    endpoint_kind = _kind(endpoint)
    if endpoint_kind == "WebSocket":
        raw = _get(endpoint, "websocket_url", "")
        address = sanitized_websocket_display_address(str(raw)) or "<invalid websocket URL>"
    elif endpoint_kind == "UnixSocket":
        socket_path = _get(endpoint, "socket_path", "")
        address = f"unix://{Path(socket_path)}"
    else:
        return None

    version = f"v{server_version}" if server_version is not None else "unknown"
    return RemoteConnectionStatus(address=address, version=version)


def sanitized_websocket_display_address(raw: str) -> str | None:
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    host = parsed.hostname
    if host is None:
        return None
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))


def _kind(value: Any) -> str:
    raw = _get(value, "kind", _get(value, "type", value if isinstance(value, str) else ""))
    enum_value = getattr(raw, "value", raw)
    text = str(enum_value).split(".")[-1]
    aliases = {
        "embedded": "Embedded",
        "localdaemon": "LocalDaemon",
        "local_daemon": "LocalDaemon",
        "remote": "Remote",
        "websocket": "WebSocket",
        "web_socket": "WebSocket",
        "unixsocket": "UnixSocket",
        "unix_socket": "UnixSocket",
    }
    return aliases.get(text.replace("-", "_").lower(), text)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def remote_connection_status_value_formats_display_value() -> tuple[RemoteConnectionStatus | None, RemoteConnectionStatus, RemoteConnectionStatus]:
    """Rust-test-shaped helper returning the three documented examples."""

    embedded = remote_connection_status_value({"kind": "Embedded"}, "1.2.3")
    websocket = remote_connection_status_value(
        {
            "kind": "Remote",
            "endpoint": {
                "kind": "WebSocket",
                "websocket_url": "ws://user:secret@127.0.0.1:4500/?token=abc#frag",
                "auth_token": "abc",
            },
        },
        "1.2.3",
    )
    socket = remote_connection_status_value(
        {
            "kind": "LocalDaemon",
            "endpoint": {"kind": "UnixSocket", "socket_path": "codex.sock"},
        },
        None,
    )
    assert websocket is not None
    assert socket is not None
    return embedded, websocket, socket


__all__ = [
    "RUST_MODULE",
    "RemoteConnectionStatus",
    "remote_connection_status_value",
    "remote_connection_status_value_formats_display_value",
    "sanitized_websocket_display_address",
]
