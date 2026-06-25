from __future__ import annotations

from pathlib import Path

from pycodex.vendor import import_vendored
from pycodex.vendor import vendor_packages_path
from pycodex.codex_api.endpoint._websocket_client import VendoredResponsesWebsocketStream


def _assert_under_vendor(module) -> None:
    origin = Path(module.__file__).resolve()
    origin.relative_to(vendor_packages_path().resolve())


def test_import_vendored_loads_websockets_sync_client_from_vendor_tree() -> None:
    # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
    # Contract: Python's tungstenite-equivalent transport must resolve through
    # the audited vendored websocket implementation, not a global site package.
    websockets = import_vendored("websockets")
    sync_client = import_vendored("websockets.sync.client")
    compression = import_vendored("websockets.extensions.permessage_deflate")

    _assert_under_vendor(websockets)
    _assert_under_vendor(sync_client)
    _assert_under_vendor(compression)
    assert websockets.__version__ == "11.0.3"
    assert callable(sync_client.connect)
    assert hasattr(compression, "enable_client_permessage_deflate")


def test_vendored_stream_send_timeout_does_not_mutate_socket_timeout() -> None:
    # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
    # Contract: the send timeout wraps the send operation; it must not corrupt
    # the concurrently-running websocket receive loop. The vendored sync client
    # owns a background receiver, so Python must not change socket timeouts here.
    class FakeSocket:
        def __init__(self) -> None:
            self.timeout = None
            self.set_timeout_calls: list[float | None] = []

        def gettimeout(self):
            return self.timeout

        def settimeout(self, value):
            self.set_timeout_calls.append(value)
            self.timeout = value

    class FakeConnection:
        def __init__(self) -> None:
            self.socket = FakeSocket()
            self.sent: list[str] = []

        def send(self, payload: str) -> None:
            self.sent.append(payload)

    connection = FakeConnection()
    stream = VendoredResponsesWebsocketStream(connection)

    stream.send_with_timeout("{}", 1.5)

    assert connection.sent == ["{}"]
    assert connection.socket.set_timeout_calls == []


def test_vendored_stream_writes_timing_trace_without_headers(monkeypatch, tmp_path) -> None:
    # Rust crate/module: codex-api/src/endpoint/responses_websocket.rs
    # Contract: websocket transport diagnosis is tied to the transport boundary.
    # Trace records must expose phase/status, not auth headers or payloads.
    path = tmp_path / "timing.jsonl"
    monkeypatch.setenv("PYCODEX_TUI_TIMING_LOG", str(path))

    class FakeConnection:
        def __init__(self) -> None:
            self.sent: list[str] = []
            self.messages = iter(["hello"])

        def send(self, payload: str) -> None:
            self.sent.append(payload)

        def recv(self, timeout=None):
            del timeout
            return next(self.messages)

    stream = VendoredResponsesWebsocketStream(FakeConnection())
    stream.send('{"secret":"not-written"}')
    message = stream.next_with_timeout(0.25)

    assert message.text == "hello"
    trace = path.read_text(encoding="utf-8")
    assert "vendored_websocket_send_start" in trace
    assert "vendored_websocket_recv_done" in trace
    assert "not-written" not in trace
    assert "Authorization" not in trace
