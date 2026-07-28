from __future__ import annotations

import pytest

from pycodex.app_server_transport.transport.remote_control.protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    PongStatus,
    RemoteControlTarget,
    ServerEnvelope,
    ServerEvent,
    StreamId,
    normalize_remote_control_url,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "https://chatgpt.com/backend-api",
            RemoteControlTarget(
                websocket_url="wss://chatgpt.com/backend-api/wham/remote/control/server",
                enroll_url="https://chatgpt.com/backend-api/wham/remote/control/server/enroll",
            ),
        ),
        (
            "https://api.chatgpt-staging.com/backend-api",
            RemoteControlTarget(
                websocket_url=(
                    "wss://api.chatgpt-staging.com/backend-api/"
                    "wham/remote/control/server"
                ),
                enroll_url=(
                    "https://api.chatgpt-staging.com/backend-api/"
                    "wham/remote/control/server/enroll"
                ),
            ),
        ),
        (
            "http://localhost:8080/backend-api",
            RemoteControlTarget(
                websocket_url="ws://localhost:8080/backend-api/wham/remote/control/server",
                enroll_url=(
                    "http://localhost:8080/backend-api/"
                    "wham/remote/control/server/enroll"
                ),
            ),
        ),
    ],
)
def test_normalize_remote_control_url_accepts_rust_supported_targets(
    source: str,
    expected: RemoteControlTarget,
) -> None:
    assert normalize_remote_control_url(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "http://chatgpt.com/backend-api",
        "https://example.com/backend-api",
        "https://chat.openai.com/backend-api",
        "https://chatgpt.com.evil.com/backend-api",
        "https://foo.localhost/backend-api",
    ],
)
def test_normalize_remote_control_url_rejects_unsupported_targets(source: str) -> None:
    with pytest.raises(ValueError, match="expected HTTPS URL"):
        normalize_remote_control_url(source)


def test_client_and_server_envelopes_use_rust_wire_shape() -> None:
    client = ClientEnvelope(
        event=ClientEvent.client_message({"method": "initialized"}),
        client_id=ClientId("client-1"),
        stream_id=StreamId("stream-1"),
        seq_id=7,
    )
    assert client.to_mapping() == {
        "type": "client_message",
        "message": {"method": "initialized"},
        "client_id": "client-1",
        "stream_id": "stream-1",
        "seq_id": 7,
    }
    assert ClientEnvelope.from_mapping(client.to_mapping()) == client

    server = ServerEnvelope(
        event=ServerEvent.pong(PongStatus.ACTIVE),
        client_id=ClientId("client-1"),
        stream_id=StreamId("stream-1"),
        seq_id=9,
    )
    assert server.to_mapping() == {
        "type": "pong",
        "status": "active",
        "client_id": "client-1",
        "stream_id": "stream-1",
        "seq_id": 9,
    }

