"""Rust-derived ownership checks for ``codex-app-server-transport`` modules."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "anchor"),
    [
        ("pycodex.app_server_transport.outgoing_message", "ConnectionId"),
        ("pycodex.app_server_transport.transport.auth", "WebsocketAuthPolicy"),
        (
            "pycodex.app_server_transport.transport.remote_control",
            "RemoteControlStartConfig",
        ),
        (
            "pycodex.app_server_transport.transport.remote_control.client_tracker",
            "ClientTracker",
        ),
        (
            "pycodex.app_server_transport.transport.remote_control.enroll",
            "RemoteControlEnrollment",
        ),
        (
            "pycodex.app_server_transport.transport.remote_control.protocol",
            "ClientEnvelope",
        ),
        (
            "pycodex.app_server_transport.transport.remote_control.segment",
            "ClientSegmentReassembler",
        ),
        (
            "pycodex.app_server_transport.transport.remote_control.websocket",
            "RemoteControlWebsocket",
        ),
        (
            "pycodex.app_server_transport.transport.unix_socket",
            "AppServerStartupLock",
        ),
        (
            "pycodex.app_server_transport.transport.websocket",
            "start_websocket_acceptor",
        ),
    ],
)
def test_rust_module_has_a_dedicated_python_owner(
    module_name: str,
    anchor: str,
) -> None:
    module = importlib.import_module(module_name)

    item = getattr(module, anchor)
    assert item.__module__ == module_name
