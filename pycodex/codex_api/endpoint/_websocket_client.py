"""Vendored WebSocket transport for codex-api endpoint modules.

Rust source:
- ``codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs``

Rust uses ``tokio-tungstenite`` for RFC 6455/RFC 7692 protocol handling. This
module keeps that lower transport concern behind a small Python boundary so
``responses_websocket`` can keep its Rust-aligned public API.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from pycodex.codex_client import TransportError
from pycodex.vendor import import_vendored

from ..error import ApiError


DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE = 128 << 20


@dataclass(frozen=True)
class VendoredWebsocketMessage:
    kind: str
    text: str | None = None
    data: bytes | None = None
    close_code: str | None = None
    close_reason: str | None = None


class VendoredResponsesWebsocketStream:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def send(self, payload: str) -> None:
        _timing_trace("vendored_websocket_send_start", bytes=len(payload.encode("utf-8", errors="replace")))
        self._connection.send(payload)
        _timing_trace("vendored_websocket_send_done")

    def send_with_timeout(self, payload: str, timeout: float | None) -> None:
        # The vendored sync client owns the socket from a background receive
        # thread. Changing the socket timeout here also affects that thread and
        # can close long-running turns before the first model event arrives.
        del timeout
        self.send(payload)

    def next(self) -> VendoredWebsocketMessage | None:
        return self.next_with_timeout(None)

    def next_with_timeout(self, timeout: float | None) -> VendoredWebsocketMessage | None:
        exceptions = import_vendored("websockets.exceptions")
        try:
            _timing_trace("vendored_websocket_recv_start", timeout=timeout)
            message = self._connection.recv(timeout=timeout)
        except TimeoutError as err:
            _timing_trace("vendored_websocket_recv_timeout", timeout=timeout)
            from .responses_websocket import ResponsesWebsocketIdleTimeout

            raise ResponsesWebsocketIdleTimeout("probe") from err
        except exceptions.ConnectionClosed as err:
            _timing_trace("vendored_websocket_recv_closed", error=str(err))
            return _connection_closed_message(err)
        _timing_trace("vendored_websocket_recv_done", kind=type(message).__name__)
        if isinstance(message, str):
            return VendoredWebsocketMessage("text", text=message)
        if isinstance(message, bytes):
            return VendoredWebsocketMessage("binary", data=message)
        return VendoredWebsocketMessage("frame", data=message)

    def close(self) -> None:
        self._connection.close()


def connect_vendored_websocket(
    url: str,
    headers: dict[str, str],
    *,
    ssl_context: Any | None = None,
    timeout: float | None = None,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
    connect_impl: Any | None = None,
) -> tuple[VendoredResponsesWebsocketStream, int, dict[str, str]]:
    client = import_vendored("websockets.sync.client")
    exceptions = import_vendored("websockets.exceptions")
    connect = connect_impl or client.connect
    try:
        _timing_trace("vendored_websocket_connect_start", url=_redact_url(url), timeout=timeout)
        connection = connect(
            url,
            additional_headers=list(headers.items()),
            ssl_context=ssl_context,
            open_timeout=timeout,
            close_timeout=timeout,
            max_size=max_message_size,
            compression="deflate",
            user_agent_header=None,
        )
    except exceptions.InvalidStatus as err:
        response = err.response
        _timing_trace(
            "vendored_websocket_connect_http_status",
            url=_redact_url(url),
            status=getattr(response, "status_code", None),
        )
        raise ApiError.transport_error(
            TransportError.http(
                response.status_code,
                url=url,
                headers=_headers_to_dict(response.headers),
                body=_decode_body(response.body),
            )
        ) from err
    except exceptions.ConnectionClosed as err:
        _timing_trace("vendored_websocket_connect_closed", url=_redact_url(url), error=str(err))
        raise ApiError.stream(_connection_closed_reason(err)) from err
    except OSError as err:
        _timing_trace("vendored_websocket_connect_os_error", url=_redact_url(url), error=str(err))
        raise ApiError.transport_error(TransportError.network(str(err))) from err
    except ApiError:
        raise
    except Exception as err:
        _timing_trace("vendored_websocket_connect_error", url=_redact_url(url), error=str(err))
        raise ApiError.transport_error(TransportError.network(str(err))) from err

    _restore_nagle_default(connection)
    response = getattr(connection, "response", None)
    status = int(getattr(response, "status_code", 101))
    response_headers = _headers_to_dict(getattr(response, "headers", {}))
    _timing_trace("vendored_websocket_connect_done", url=_redact_url(url), status=status)
    return VendoredResponsesWebsocketStream(connection), status, response_headers


def _timing_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        return


def _redact_url(url: str) -> str:
    if "?" not in url:
        return url
    return url.split("?", 1)[0] + "?..."


def _headers_to_dict(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    raw_items = getattr(headers, "raw_items", None)
    if raw_items is not None:
        items = raw_items()
    elif hasattr(headers, "items"):
        items = headers.items()
    else:
        return {}
    mapped: dict[str, str] = {}
    for name, value in items:
        key = str(name).lower()
        item = str(value)
        mapped[key] = f"{mapped[key]}, {item}" if key in mapped else item
    return mapped


def _decode_body(body: Any) -> str | None:
    if body is None:
        return None
    if isinstance(body, str):
        return body
    if isinstance(body, bytes):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return str(body)


def _connection_closed_message(err: Any) -> VendoredWebsocketMessage | None:
    received = getattr(err, "rcvd", None)
    if received is None:
        return None
    code = getattr(received, "code", None)
    reason = getattr(received, "reason", None)
    return VendoredWebsocketMessage(
        "close",
        close_code=str(code) if code is not None else None,
        close_reason=str(reason) if reason else None,
    )


def _connection_closed_reason(err: Any) -> str:
    message = _connection_closed_message(err)
    if message is None:
        return "websocket closed"
    if message.close_reason:
        return message.close_reason
    if message.close_code:
        return f"websocket closed with code {message.close_code}"
    return "websocket closed"


def _restore_nagle_default(connection: Any) -> None:
    # Rust passes `false` to `connect_async_tls_with_config`'s
    # `disable_nagle` parameter. The vendored sync client disables Nagle by
    # default, so restore the ordinary TCP setting when the socket is exposed.
    sock = getattr(connection, "socket", None)
    if sock is None:
        return
    try:
        import socket

        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 0)
    except OSError:
        pass


__all__ = [
    "DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE",
    "VendoredResponsesWebsocketStream",
    "VendoredWebsocketMessage",
    "connect_vendored_websocket",
]
