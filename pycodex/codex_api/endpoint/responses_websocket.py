"""Responses WebSocket endpoint helpers for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs``
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import inspect
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from pycodex.codex_client import TransportError
from pycodex.codex_client.custom_ca import ProcessEnv
from pycodex.codex_client.custom_ca import configured_ca_bundle

from ._websocket_client import DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE
from ._websocket_client import VendoredWebsocketMessage
from ._websocket_client import connect_vendored_websocket
from ..auth import SharedAuthProvider
from ..common import ResponseEvent
from ..common import ResponseProcessedWsRequest
from ..common import ResponseStream
from ..common import ResponsesWsRequest
from ..error import ApiError
from ..provider import Provider
from ..rate_limits import parse_rate_limit_event
from ..sse.responses import ResponsesEventError
from ..sse.responses import ResponsesStreamEvent
from ..sse.responses import process_responses_event


X_CODEX_TURN_STATE_HEADER = "x-codex-turn-state"
X_MODELS_ETAG_HEADER = "x-models-etag"
X_REASONING_INCLUDED_HEADER = "x-reasoning-included"
OPENAI_MODEL_HEADER = "openai-model"
WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE = "websocket_connection_limit_reached"
WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE = (
    "Responses websocket connection limit reached (60 minutes). Create a new "
    "websocket connection to continue."
)


@dataclass(frozen=True)
class WebSocketConfigProjection:
    permessage_deflate: bool = True


@dataclass(frozen=True)
class WrappedWebsocketError:
    code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class WrappedWebsocketErrorEvent:
    kind: str
    status: int | None = None
    error: WrappedWebsocketError | None = None
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class ResponsesWebsocketClose:
    code: str
    reason: str


@dataclass(frozen=True)
class ResponsesWebsocketProbe:
    url: str
    status: int
    reasoning_included: bool
    models_etag_present: bool
    server_model_present: bool
    immediate_close: ResponsesWebsocketClose | None = None


@dataclass(frozen=True)
class ResponsesWebsocketTextMessage:
    text: str


@dataclass(frozen=True)
class ResponsesWebsocketBinaryMessage:
    data: bytes


@dataclass(frozen=True)
class ResponsesWebsocketCloseMessage:
    code: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ResponsesWebsocketPingMessage:
    data: bytes = b""


@dataclass(frozen=True)
class ResponsesWebsocketPongMessage:
    data: bytes = b""


@dataclass(frozen=True)
class ResponsesWebsocketFrameMessage:
    data: Any = None


class ResponsesWebsocketIdleTimeout(Exception):
    def __init__(self, operation: str) -> None:
        super().__init__(operation)
        self.operation = operation


class ResponsesWebsocketConnectionClosed(Exception):
    pass


class ResponsesWebsocketAlreadyClosed(Exception):
    pass


class ResponsesWebsocketMemoryStream:
    def __init__(
        self,
        messages: Iterable[Any] = (),
        *,
        send_error: Exception | None = None,
    ) -> None:
        self.sent_payloads: list[str] = []
        self._messages = iter(messages)
        self.send_error = send_error

    def send(self, payload: str) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent_payloads.append(payload)

    def send_with_timeout(self, payload: str, timeout: float | None) -> None:
        del timeout
        self.send(payload)

    def next(self) -> Any | None:
        try:
            return next(self._messages)
        except StopIteration:
            return None


class _StdlibResponsesWebsocketStream:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def send(self, payload: str) -> None:
        self._send_frame(0x1, payload.encode("utf-8"))

    def send_with_timeout(self, payload: str, timeout: float | None) -> None:
        original_timeout = self._sock.gettimeout()
        self._sock.settimeout(timeout)
        try:
            self.send(payload)
        except socket.timeout as err:
            raise ResponsesWebsocketIdleTimeout("send") from err
        finally:
            self._sock.settimeout(original_timeout)

    def next(self) -> Any | None:
        while True:
            header = self._recv_exact(2)
            if not header:
                return None
            first, second = header
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            payload = self._recv_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x1:
                return ResponsesWebsocketTextMessage(payload.decode("utf-8"))
            if opcode == 0x2:
                return ResponsesWebsocketBinaryMessage(payload)
            if opcode == 0x8:
                code = reason = None
                if len(payload) >= 2:
                    code = str(struct.unpack("!H", payload[:2])[0])
                    reason = payload[2:].decode("utf-8", errors="replace")
                return ResponsesWebsocketCloseMessage(code, reason)
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            return ResponsesWebsocketFrameMessage(payload)

    def next_with_timeout(self, timeout: float | None) -> Any | None:
        original_timeout = self._sock.gettimeout()
        self._sock.settimeout(timeout)
        try:
            return self.next()
        except socket.timeout as err:
            raise ResponsesWebsocketIdleTimeout("probe") from err
        finally:
            self._sock.settimeout(original_timeout)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        first = 0x80 | opcode
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes([first, 0x80 | length])
        elif length <= 0xFFFF:
            header = bytes([first, 0x80 | 126]) + struct.pack("!H", length)
        else:
            header = bytes([first, 0x80 | 127]) + struct.pack("!Q", length)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(header + mask + masked)

    def _recv_exact(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = self._sock.recv(remaining)
            if not chunk:
                if chunks:
                    raise ConnectionError("websocket stream ended mid-frame")
                return b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


@dataclass
class ResponsesWebsocketConnection:
    stream: ResponsesWebsocketMemoryStream | None
    idle_timeout: float | None = None
    server_reasoning_included: bool = False
    models_etag: str | None = None
    server_model: str | None = None
    telemetry: Any | None = None

    def is_closed(self) -> bool:
        return self.stream is None

    def send_response_processed(self, response_id: str) -> None:
        request = ResponsesWsRequest.response_processed(
            ResponseProcessedWsRequest(response_id)
        )
        stream = self.stream
        if stream is None:
            raise ApiError.stream("websocket connection is closed")
        send_websocket_request(
            stream,
            request.to_json_dict(),
            self.idle_timeout,
            self.telemetry,
            connection_reused=True,
        )

    def stream_request(
        self,
        request: ResponsesWsRequest,
        connection_reused: bool,
    ) -> Any:
        events: list[ResponseEvent | ApiError] = []
        if self.server_model is not None:
            events.append(ResponseEvent("server_model", self.server_model))
        if self.models_etag is not None:
            events.append(ResponseEvent("models_etag", self.models_etag))
        if self.server_reasoning_included:
            events.append(ResponseEvent("server_reasoning_included", True))

        stream = self.stream
        if stream is None:
            events.append(ApiError.stream("websocket connection is closed"))
            return ResponseStream.from_iterable(events)

        def iter_events() -> Iterator[ResponseEvent | ApiError]:
            yield from events
            try:
                yield from iter_websocket_response_stream(
                    stream,
                    request.to_json_dict(),
                    self.idle_timeout,
                    self.telemetry,
                    connection_reused,
                )
            except ApiError as err:
                self.stream = None
                yield err

        return _IteratorResponseStream(iter_events())


@dataclass
class _IteratorResponseStream:
    iterator: Iterator[Any]
    upstream_request_id: str | None = None

    def __iter__(self) -> "_IteratorResponseStream":
        return self

    def __next__(self) -> Any:
        return next(self.iterator)


class ResponsesWebsocketClient:
    def __init__(
        self,
        provider: Provider,
        auth: SharedAuthProvider,
        connector: Callable[..., tuple[Any, int, bool, str | None, str | None]] | None = None,
    ) -> None:
        self.provider = provider
        self.auth = auth
        self.connector = connector or connect_websocket

    @classmethod
    def new(
        cls,
        provider: Provider,
        auth: SharedAuthProvider,
        connector: Callable[..., tuple[Any, int, bool, str | None, str | None]] | None = None,
    ) -> "ResponsesWebsocketClient":
        return cls(provider, auth, connector)

    def connect(
        self,
        extra_headers: dict[str, str] | None = None,
        default_headers: dict[str, str] | None = None,
        turn_state: Any | None = None,
        telemetry: Any | None = None,
        timeout: float | None = None,
    ) -> ResponsesWebsocketConnection:
        ws_url = self.provider.websocket_url_for_path("responses")
        headers = merge_request_headers(
            dict(self.provider.headers),
            dict(extra_headers or {}),
            dict(default_headers or {}),
        )
        self.auth.add_auth_headers(headers)
        stream, _status, reasoning_included, models_etag, server_model = _call_connector(
            self.connector,
            ws_url,
            headers,
            turn_state,
            timeout=timeout,
        )
        return ResponsesWebsocketConnection(
            stream,
            self.provider.stream_idle_timeout,
            reasoning_included,
            models_etag,
            server_model,
            telemetry,
        )

    def probe_handshake(
        self,
        extra_headers: dict[str, str] | None = None,
        default_headers: dict[str, str] | None = None,
        immediate_close_timeout: float | None = None,
    ) -> ResponsesWebsocketProbe:
        ws_url = self.provider.websocket_url_for_path("responses")
        headers = merge_request_headers(
            dict(self.provider.headers),
            dict(extra_headers or {}),
            dict(default_headers or {}),
        )
        self.auth.add_auth_headers(headers)
        stream, status, reasoning_included, models_etag, server_model = _call_connector(
            self.connector,
            ws_url,
            headers,
            None,
        )
        try:
            message = _next_probe_message(stream, immediate_close_timeout)
        except Exception as err:
            raise ApiError.stream(f"failed to read websocket probe event: {err}") from err
        return ResponsesWebsocketProbe(
            url=ws_url,
            status=status,
            reasoning_included=reasoning_included,
            models_etag_present=models_etag is not None,
            server_model_present=server_model is not None,
            immediate_close=immediate_close_from_message(message),
        )


def _call_connector(
    connector: Callable[..., tuple[Any, int, bool, str | None, str | None]],
    url: str,
    headers: dict[str, str],
    turn_state: Any | None,
    *,
    timeout: float | None = None,
) -> tuple[Any, int, bool, str | None, str | None]:
    if timeout is not None and _callable_accepts_timeout(connector):
        return connector(url, headers, turn_state, timeout=timeout)
    return connector(url, headers, turn_state)


def _callable_accepts_timeout(value: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == "timeout":
            return True
    return False


def websocket_config() -> WebSocketConfigProjection:
    return WebSocketConfigProjection(permessage_deflate=True)


def connect_websocket(
    url: str,
    headers: dict[str, str],
    turn_state: Any | None = None,
    *,
    timeout: float | None = None,
) -> tuple[Any, int, bool, str | None, str | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname:
        raise ApiError.stream(f"failed to build websocket request: unsupported URL: {url}")
    try:
        tls_context = None
        if parsed.scheme == "wss":
            try:
                tls_context = _ssl_context_for_websocket()
            except Exception as err:
                raise ApiError.stream(f"failed to configure websocket TLS: {err}") from err
        stream, status, response_headers = connect_vendored_websocket(
            url,
            headers,
            ssl_context=tls_context,
            timeout=timeout,
            max_message_size=DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
        )
    except ApiError:
        raise
    except Exception as err:
        raise ApiError.transport_error(TransportError.network(str(err))) from err
    if turn_state is not None:
        turn_state_value = _header_lookup(response_headers, X_CODEX_TURN_STATE_HEADER)
        if turn_state_value is not None:
            _set_turn_state(turn_state, turn_state_value)
    return (
        stream,
        status,
        _header_lookup(response_headers, X_REASONING_INCLUDED_HEADER) is not None,
        _header_lookup(response_headers, X_MODELS_ETAG_HEADER),
        _header_lookup(response_headers, OPENAI_MODEL_HEADER),
    )


def _connect_websocket_stdlib(
    url: str,
    headers: dict[str, str],
    turn_state: Any | None = None,
    *,
    timeout: float | None = None,
) -> tuple[_StdlibResponsesWebsocketStream, int, bool, str | None, str | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("ws", "wss") or not parsed.hostname:
        raise ApiError.stream(f"failed to build websocket request: unsupported URL: {url}")
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request_headers = {
        "Host": _host_header(parsed.hostname, parsed.port, parsed.scheme),
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Key": key,
        "Sec-WebSocket-Version": "13",
    }
    request_headers.update(headers)

    try:
        tls_context = None
        if parsed.scheme == "wss":
            try:
                tls_context = _ssl_context_for_websocket()
            except Exception as err:
                raise ApiError.stream(f"failed to configure websocket TLS: {err}") from err
        raw_sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        if tls_context is not None:
            raw_sock = tls_context.wrap_socket(
                raw_sock,
                server_hostname=parsed.hostname,
            )
        request = _websocket_handshake_request(path, request_headers)
        raw_sock.sendall(request)
        header_bytes, body = _read_http_response(raw_sock)
    except ApiError:
        raise
    except Exception as err:
        raise ApiError.transport_error(TransportError.network(str(err))) from err

    status, response_headers = _parse_http_response_headers(header_bytes)
    if status != 101:
        body = _read_remaining_http_body(raw_sock, response_headers, body)
        raise ApiError.transport_error(
            TransportError.http(
                status,
                url=url,
                headers=response_headers,
                body=_decode_utf8_or_none(body),
            )
        )
    _validate_websocket_accept(key, response_headers)
    if turn_state is not None:
        turn_state_value = _header_lookup(response_headers, X_CODEX_TURN_STATE_HEADER)
        if turn_state_value is not None:
            _set_turn_state(turn_state, turn_state_value)
    return (
        _StdlibResponsesWebsocketStream(raw_sock),
        status,
        _header_lookup(response_headers, X_REASONING_INCLUDED_HEADER) is not None,
        _header_lookup(response_headers, X_MODELS_ETAG_HEADER),
        _header_lookup(response_headers, OPENAI_MODEL_HEADER),
    )


def _ssl_context_for_websocket() -> ssl.SSLContext:
    bundle = configured_ca_bundle(ProcessEnv())
    if bundle is None:
        return ssl.create_default_context()
    bundle.load_certificates()
    return ssl.create_default_context(cafile=str(bundle.path))


def parse_wrapped_websocket_error_event(
    payload: str,
) -> WrappedWebsocketErrorEvent | None:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or value.get("type") != "error":
        return None

    has_status = "status" in value or "status_code" in value
    raw_status = value.get("status", value.get("status_code"))
    if raw_status is None:
        status = None
    elif isinstance(raw_status, int) and not isinstance(raw_status, bool):
        if not 0 <= raw_status <= 0xFFFF:
            return None
        status = raw_status
    elif has_status:
        return None
    else:
        status = None

    raw_error = value.get("error")
    error = None
    if isinstance(raw_error, dict):
        error = WrappedWebsocketError(
            code=raw_error.get("code") if isinstance(raw_error.get("code"), str) else None,
            message=(
                raw_error.get("message")
                if isinstance(raw_error.get("message"), str)
                else None
            ),
        )

    raw_headers = value.get("headers")
    headers = json_headers_to_http_headers(raw_headers) if isinstance(raw_headers, dict) else None
    return WrappedWebsocketErrorEvent(
        kind="error",
        status=status,
        error=error,
        headers=headers,
    )


def map_wrapped_websocket_error_event(
    event: WrappedWebsocketErrorEvent,
    original_payload: str,
) -> ApiError | None:
    if (
        event.error is not None
        and event.error.code == WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE
    ):
        return ApiError.retryable(
            event.error.message or WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE,
            delay=None,
        )

    if event.status is None or not 100 <= event.status <= 999 or 200 <= event.status <= 299:
        return None

    return ApiError.transport_error(
        TransportError.http(
            event.status,
            url=None,
            headers=event.headers,
            body=original_payload,
        )
    )


def json_headers_to_http_headers(headers: dict[str, Any]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for name, value in headers.items():
        header_name = str(name)
        if not _valid_header_name(header_name):
            continue
        header_value = json_header_value(value)
        if header_value is None:
            continue
        mapped[header_name] = header_value
    return mapped


def json_header_value(value: Any) -> str | None:
    if isinstance(value, str):
        header_value = value
    elif isinstance(value, bool):
        header_value = "true" if value else "false"
    elif isinstance(value, int | float):
        header_value = str(value)
    else:
        return None
    return header_value if _valid_header_value(header_value) else None


def immediate_close_from_message(message: Any) -> ResponsesWebsocketClose | None:
    if not isinstance(message, ResponsesWebsocketCloseMessage):
        return None
    if message.code is None:
        return None
    return ResponsesWebsocketClose(message.code, message.reason or "")


def send_websocket_request(
    ws_stream: Any,
    request_body: Any,
    idle_timeout: float | None = None,
    telemetry: Any | None = None,
    connection_reused: bool = False,
) -> None:
    try:
        request_text = json.dumps(request_body, separators=(",", ":"))
    except Exception as err:
        raise ApiError.stream(f"failed to encode websocket request: {err}") from err

    try:
        timeout_sender = getattr(ws_stream, "send_with_timeout", None)
        if timeout_sender is not None:
            timeout_sender(request_text, idle_timeout)
        else:
            sender = getattr(ws_stream, "send_text", None) or getattr(ws_stream, "send")
            sender(request_text)
        error = None
    except ResponsesWebsocketIdleTimeout as err:
        error = ApiError.stream("idle timeout sending websocket request")
        _telemetry_ws_request(telemetry, error, connection_reused)
        raise error from err
    except Exception as err:
        error = ApiError.stream(f"failed to send websocket request: {err}")
        _telemetry_ws_request(telemetry, error, connection_reused)
        raise error from err
    _telemetry_ws_request(telemetry, error, connection_reused)


def run_websocket_response_stream(
    ws_stream: Any,
    request_body: Any,
    idle_timeout: float | None = None,
    telemetry: Any | None = None,
    connection_reused: bool = False,
) -> list[ResponseEvent]:
    return list(
        iter_websocket_response_stream(
            ws_stream,
            request_body,
            idle_timeout,
            telemetry,
            connection_reused,
        )
    )


def iter_websocket_response_stream(
    ws_stream: Any,
    request_body: Any,
    idle_timeout: float | None = None,
    telemetry: Any | None = None,
    connection_reused: bool = False,
) -> Iterator[ResponseEvent]:
    last_server_model: str | None = None
    send_websocket_request(
        ws_stream,
        request_body,
        idle_timeout,
        telemetry,
        connection_reused,
    )

    while True:
        try:
            message = _next_message(ws_stream, idle_timeout)
            event_error = None
        except ResponsesWebsocketIdleTimeout as err:
            event_error = ApiError.stream("idle timeout waiting for websocket")
            _telemetry_ws_event(telemetry, event_error)
            raise event_error from err
        except Exception as err:
            event_error = ApiError.stream(str(err))
            _telemetry_ws_event(telemetry, event_error)
            raise event_error from err
        _telemetry_ws_event(telemetry, event_error)

        if message is None:
            raise ApiError.stream("stream closed before response.completed")
        if isinstance(message, ResponsesWebsocketIdleTimeout):
            raise ApiError.stream("idle timeout waiting for websocket")
        if isinstance(message, Exception):
            raise ApiError.stream(str(message))
        if isinstance(message, str):
            message = ResponsesWebsocketTextMessage(message)
        elif isinstance(message, bytes):
            message = ResponsesWebsocketBinaryMessage(message)

        if isinstance(message, ResponsesWebsocketTextMessage):
            text = message.text
            wrapped_error = parse_wrapped_websocket_error_event(text)
            if wrapped_error is not None:
                mapped_error = map_wrapped_websocket_error_event(wrapped_error, text)
                if mapped_error is not None:
                    raise mapped_error

            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue
            stream_event = ResponsesStreamEvent.from_json_dict(value)
            if stream_event.kind == "codex.rate_limits":
                snapshot = parse_rate_limit_event(text)
                if snapshot is not None:
                    yield ResponseEvent("rate_limits", snapshot)
                continue
            model = stream_event.response_model()
            if model is not None and model != last_server_model:
                yield ResponseEvent("server_model", model)
                last_server_model = model
            verifications = stream_event.model_verifications()
            if verifications is not None:
                yield ResponseEvent("model_verifications", verifications)
            try:
                mapped = process_responses_event(stream_event)
            except ResponsesEventError as err:
                raise err.into_api_error() from err
            if mapped is None:
                continue
            yield mapped
            if mapped.kind == "completed":
                return
            continue

        if isinstance(message, ResponsesWebsocketBinaryMessage):
            raise ApiError.stream("unexpected binary websocket event")
        if isinstance(message, ResponsesWebsocketCloseMessage):
            raise ApiError.stream("websocket closed by server before response.completed")
        if isinstance(
            message,
            (
                ResponsesWebsocketFrameMessage,
                ResponsesWebsocketPingMessage,
                ResponsesWebsocketPongMessage,
            ),
        ):
            continue


def _next_message(ws_stream: Any, idle_timeout: float | None = None) -> Any | None:
    timeout_receiver = getattr(ws_stream, "next_with_timeout", None)
    if timeout_receiver is not None:
        return _coerce_vendored_message(timeout_receiver(idle_timeout))
    receiver = getattr(ws_stream, "next", None) or getattr(ws_stream, "recv", None)
    if receiver is None:
        raise TypeError("websocket stream must provide next() or recv()")
    return _coerce_vendored_message(receiver())


def _coerce_vendored_message(message: Any) -> Any:
    if not isinstance(message, VendoredWebsocketMessage):
        return message
    if message.kind == "text":
        return ResponsesWebsocketTextMessage(message.text or "")
    if message.kind == "binary":
        return ResponsesWebsocketBinaryMessage(message.data or b"")
    if message.kind == "close":
        return ResponsesWebsocketCloseMessage(
            message.close_code,
            message.close_reason,
        )
    if message.kind == "ping":
        return ResponsesWebsocketPingMessage(message.data or b"")
    if message.kind == "pong":
        return ResponsesWebsocketPongMessage(message.data or b"")
    return ResponsesWebsocketFrameMessage(message.data)


def _next_probe_message(stream: Any, timeout: float | None) -> Any | None:
    receiver = getattr(stream, "next_with_timeout", None)
    if receiver is not None:
        try:
            message = receiver(timeout)
        except ResponsesWebsocketIdleTimeout:
            return None
    else:
        message = _next_message(stream)
    message = _coerce_vendored_message(message)
    if isinstance(message, Exception):
        raise message
    return message


def _host_header(hostname: str, port: int | None, scheme: str) -> str:
    default_port = 443 if scheme == "wss" else 80
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port is None or port == default_port:
        return host
    return f"{host}:{port}"


def _websocket_handshake_request(path: str, headers: dict[str, str]) -> bytes:
    lines = [f"GET {path} HTTP/1.1"]
    lines.extend(f"{name}: {value}" for name, value in headers.items())
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def _read_http_response(sock: socket.socket) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > 1024 * 1024:
            raise ApiError.stream("failed to build websocket request: response headers too large")
    header, _, body = bytes(data).partition(b"\r\n\r\n")
    return header, body


def _parse_http_response_headers(header_bytes: bytes) -> tuple[int, dict[str, str]]:
    text = header_bytes.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/"):
        raise ApiError.stream("failed to build websocket request: invalid HTTP response")
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError) as err:
        raise ApiError.stream("failed to build websocket request: invalid HTTP status") from err
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    return status, headers


def _read_remaining_http_body(
    sock: socket.socket,
    headers: dict[str, str],
    body: bytes,
) -> bytes:
    content_length = _header_lookup(headers, "content-length")
    if content_length is None:
        return body
    try:
        expected_len = int(content_length)
    except ValueError:
        return body
    if expected_len <= len(body):
        return body[:expected_len]
    chunks = [body]
    remaining = expected_len - len(body)
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)[:expected_len]


def _decode_utf8_or_none(body: bytes) -> str | None:
    if not body:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _validate_websocket_accept(key: str, headers: dict[str, str]) -> None:
    if not _header_has_token(headers, "upgrade", "websocket"):
        raise ApiError.stream("failed to build websocket request: invalid websocket upgrade header")
    if not _header_has_token(headers, "connection", "upgrade"):
        raise ApiError.stream("failed to build websocket request: invalid websocket connection header")
    expected = base64.b64encode(
        hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()
    ).decode("ascii")
    actual = _header_lookup(headers, "sec-websocket-accept")
    if actual != expected:
        raise ApiError.stream("failed to build websocket request: invalid websocket accept header")


def _header_has_token(headers: dict[str, str], name: str, token: str) -> bool:
    value = _header_lookup(headers, name)
    if value is None:
        return False
    wanted = token.lower()
    return any(part.strip().lower() == wanted for part in value.split(","))


def _header_lookup(headers: dict[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _set_turn_state(turn_state: Any, value: str) -> None:
    setter = getattr(turn_state, "set", None)
    if setter is not None:
        setter(value)
        return
    if isinstance(turn_state, dict):
        turn_state.setdefault("value", value)
        return
    try:
        setattr(turn_state, "value", value)
    except Exception:
        pass


def _telemetry_ws_request(
    telemetry: Any | None,
    error: ApiError | None,
    connection_reused: bool,
) -> None:
    if telemetry is None:
        return
    callback = getattr(telemetry, "on_ws_request", None)
    if callback is not None:
        callback(0.0, error, connection_reused)


def _telemetry_ws_event(telemetry: Any | None, error: ApiError | None) -> None:
    if telemetry is None:
        return
    callback = getattr(telemetry, "on_ws_event", None)
    if callback is not None:
        callback(error, 0.0)


def merge_request_headers(
    provider_headers: dict[str, str],
    extra_headers: dict[str, str],
    default_headers: dict[str, str],
) -> dict[str, str]:
    headers = dict(provider_headers)
    _extend_case_insensitive(headers, extra_headers, overwrite=True)
    _extend_case_insensitive(headers, default_headers, overwrite=False)
    return headers


def _extend_case_insensitive(
    target: dict[str, str],
    source: dict[str, str],
    *,
    overwrite: bool,
) -> None:
    for name, value in source.items():
        existing = _find_header_key(target, name)
        if existing is not None:
            if overwrite:
                del target[existing]
                target[name] = value
            continue
        target[name] = value


def _find_header_key(headers: dict[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key in headers:
        if key.lower() == wanted:
            return key
    return None


def _valid_header_name(name: str) -> bool:
    if not name:
        return False
    separators = set('()<>@,;:\\"/[]?={} \t')
    return all(31 < ord(ch) < 127 and ch not in separators for ch in name)


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or " " <= ch <= "~" for ch in value)


__all__ = [
    "OPENAI_MODEL_HEADER",
    "ResponsesWebsocketAlreadyClosed",
    "ResponsesWebsocketBinaryMessage",
    "ResponsesWebsocketClose",
    "ResponsesWebsocketCloseMessage",
    "ResponsesWebsocketConnection",
    "ResponsesWebsocketConnectionClosed",
    "ResponsesWebsocketFrameMessage",
    "ResponsesWebsocketIdleTimeout",
    "ResponsesWebsocketMemoryStream",
    "ResponsesWebsocketPingMessage",
    "ResponsesWebsocketPongMessage",
    "ResponsesWebsocketProbe",
    "ResponsesWebsocketTextMessage",
    "ResponsesWebsocketClient",
    "WEBSOCKET_CONNECTION_LIMIT_REACHED_CODE",
    "WEBSOCKET_CONNECTION_LIMIT_REACHED_MESSAGE",
    "WrappedWebsocketError",
    "WrappedWebsocketErrorEvent",
    "X_CODEX_TURN_STATE_HEADER",
    "X_MODELS_ETAG_HEADER",
    "X_REASONING_INCLUDED_HEADER",
    "json_header_value",
    "json_headers_to_http_headers",
    "connect_websocket",
    "immediate_close_from_message",
    "map_wrapped_websocket_error_event",
    "merge_request_headers",
    "parse_wrapped_websocket_error_event",
    "run_websocket_response_stream",
    "send_websocket_request",
    "websocket_config",
]
