"""Parity tests for codex-rs/tui/src/status/remote_connection.rs."""

from dataclasses import dataclass
from pathlib import Path

from pycodex.tui.status.remote_connection import (
    RemoteConnectionStatus,
    remote_connection_status_value,
    remote_connection_status_value_formats_display_value,
    sanitized_websocket_display_address,
)


@dataclass
class Endpoint:
    kind: str
    websocket_url: str | None = None
    socket_path: Path | None = None


@dataclass
class Target:
    kind: str
    endpoint: Endpoint | None = None


def test_remote_connection_status_value_formats_display_value_like_rust_test():
    assert remote_connection_status_value({"kind": "Embedded"}, "1.2.3") is None

    websocket_target = {
        "kind": "Remote",
        "endpoint": {
            "kind": "WebSocket",
            "websocket_url": "ws://user:secret@127.0.0.1:4500/?token=abc#frag",
            "auth_token": "abc",
        },
    }
    assert remote_connection_status_value(websocket_target, "1.2.3") == RemoteConnectionStatus(
        address="ws://127.0.0.1:4500/",
        version="v1.2.3",
    )

    daemon_target = {
        "kind": "LocalDaemon",
        "endpoint": {"kind": "UnixSocket", "socket_path": Path("codex.sock")},
    }
    assert remote_connection_status_value(daemon_target, None) == RemoteConnectionStatus(
        address="unix://codex.sock",
        version="unknown",
    )


def test_remote_connection_status_value_accepts_object_shaped_targets():
    target = Target("Remote", Endpoint("WebSocket", websocket_url="wss://user:pw@example.com/socket?x=1"))

    assert remote_connection_status_value(target, "2") == RemoteConnectionStatus(
        address="wss://example.com/socket",
        version="v2",
    )


def test_sanitized_websocket_display_address_removes_credentials_query_and_fragment():
    assert sanitized_websocket_display_address("ws://u:p@host.test:123/path?q=1#frag") == "ws://host.test:123/path"
    assert sanitized_websocket_display_address("not a url") is None


def test_invalid_websocket_url_uses_rust_invalid_placeholder():
    target = {"kind": "Remote", "endpoint": {"kind": "WebSocket", "websocket_url": "not a url"}}

    assert remote_connection_status_value(target, "1") == RemoteConnectionStatus(
        address="<invalid websocket URL>",
        version="v1",
    )


def test_rust_shaped_helper_returns_documented_examples():
    embedded, websocket, socket = remote_connection_status_value_formats_display_value()

    assert embedded is None
    assert websocket == RemoteConnectionStatus("ws://127.0.0.1:4500/", "v1.2.3")
    assert socket == RemoteConnectionStatus("unix://codex.sock", "unknown")
