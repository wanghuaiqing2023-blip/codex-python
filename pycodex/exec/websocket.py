"""Small standard-library WebSocket helpers for remote app-server transport.

Codex's Rust remote app-server client uses tungstenite for WebSocket handshakes
and text frames.  Python does not ship a WebSocket client, so this module keeps
the protocol pieces needed by the future transport loop dependency-free.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from pathlib import Path
import secrets
import socket
import ssl
import struct
from urllib.parse import urlparse

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WEBSOCKET_VERSION = "13"
DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE = 128 << 20

OPCODE_CONTINUATION = 0x0
OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA


class WebSocketProtocolError(ValueError):
    """Raised when bytes do not satisfy the WebSocket protocol shape."""


@dataclass(frozen=True)
class WebSocketHandshakeResponse:
    status_code: int
    reason: str
    headers: dict[str, str]

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())

    def to_mapping(self) -> dict[str, object]:
        return {
            "statusCode": self.status_code,
            "reason": self.reason,
            "headers": dict(self.headers),
        }


@dataclass(frozen=True)
class WebSocketFrame:
    fin: bool
    opcode: int
    payload: bytes
    masked: bool = False

    def text(self) -> str:
        if self.opcode != OPCODE_TEXT:
            raise WebSocketProtocolError(f"expected text frame, got opcode {self.opcode}")
        return self.payload.decode("utf-8")

    def to_mapping(self) -> dict[str, object]:
        return {
            "fin": self.fin,
            "opcode": self.opcode,
            "masked": self.masked,
            "payloadLength": len(self.payload),
        }


@dataclass(frozen=True)
class WebSocketFrameEvent:
    kind: str
    text: str | None = None
    close_code: int | None = None
    close_reason: str | None = None
    ignored_opcode: int | None = None

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {"kind": self.kind}
        if self.text is not None:
            data["text"] = self.text
        if self.close_code is not None:
            data["closeCode"] = self.close_code
        if self.close_reason is not None:
            data["closeReason"] = self.close_reason
        if self.ignored_opcode is not None:
            data["ignoredOpcode"] = self.ignored_opcode
        return data


def generate_websocket_key(random_bytes: bytes | None = None) -> str:
    data = secrets.token_bytes(16) if random_bytes is None else bytes(random_bytes)
    if len(data) != 16:
        raise ValueError("websocket key material must be exactly 16 bytes")
    return base64.b64encode(data).decode("ascii")


def websocket_accept_key(key: str) -> str:
    digest = hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def websocket_authorization_header(auth_token: str) -> str:
    return f"Bearer {auth_token}"


def _parsed_websocket_url(websocket_url: str):
    parsed = urlparse(str(websocket_url))
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError(f"invalid websocket URL `{websocket_url}`: unsupported scheme `{parsed.scheme}`")
    if parsed.hostname is None:
        raise ValueError(f"invalid websocket URL `{websocket_url}`: missing host")
    return parsed


def _host_header(parsed) -> str:
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "wss" else 80
    if parsed.port is not None and parsed.port != default_port:
        return f"{host}:{parsed.port}"
    return host


def _request_target(parsed) -> str:
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    return target


def build_websocket_handshake_request(
    websocket_url: str,
    key: str,
    *,
    auth_token: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    parsed = _parsed_websocket_url(websocket_url)
    headers = [
        f"GET {_request_target(parsed)} HTTP/1.1",
        f"Host: {_host_header(parsed)}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        f"Sec-WebSocket-Version: {WEBSOCKET_VERSION}",
    ]
    if auth_token is not None:
        headers.append(f"Authorization: {websocket_authorization_header(auth_token)}")
    for name, value in (extra_headers or {}).items():
        headers.append(f"{name}: {value}")
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


def parse_websocket_handshake_response(response: bytes | str) -> WebSocketHandshakeResponse:
    text = response.decode("iso-8859-1") if isinstance(response, bytes) else str(response)
    head = text.split("\r\n\r\n", 1)[0]
    lines = head.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/"):
        raise WebSocketProtocolError("websocket upgrade response is missing HTTP status line")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2 or not parts[1].isdigit():
        raise WebSocketProtocolError("websocket upgrade response has invalid HTTP status line")
    reason = parts[2] if len(parts) > 2 else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise WebSocketProtocolError(f"websocket upgrade response has invalid header `{line}`")
        name, value = line.split(":", 1)
        key = name.strip().lower()
        item = value.strip()
        headers[key] = f"{headers[key]}, {item}" if key in headers else item
    return WebSocketHandshakeResponse(int(parts[1]), reason, headers)


def _has_header_token(value: str | None, token: str) -> bool:
    if value is None:
        return False
    expected = token.lower()
    return any(part.strip().lower() == expected for part in value.split(","))


def validate_websocket_handshake_response(
    response: bytes | str,
    key: str,
) -> WebSocketHandshakeResponse:
    parsed = parse_websocket_handshake_response(response)
    if parsed.status_code != 101:
        raise WebSocketProtocolError(
            f"websocket upgrade failed with status {parsed.status_code} {parsed.reason}".rstrip()
        )
    if not _has_header_token(parsed.header("upgrade"), "websocket"):
        raise WebSocketProtocolError("websocket upgrade response is missing `Upgrade: websocket`")
    if not _has_header_token(parsed.header("connection"), "upgrade"):
        raise WebSocketProtocolError("websocket upgrade response is missing `Connection: Upgrade`")
    expected_accept = websocket_accept_key(key)
    if parsed.header("sec-websocket-accept") != expected_accept:
        raise WebSocketProtocolError("websocket upgrade response has invalid Sec-WebSocket-Accept")
    return parsed


def _mask_payload(payload: bytes, mask_key: bytes) -> bytes:
    return bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))


def encode_websocket_frame(
    payload: str | bytes,
    *,
    opcode: int = OPCODE_TEXT,
    fin: bool = True,
    mask: bool = True,
    mask_key: bytes | None = None,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> bytes:
    data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if len(data) > max_message_size:
        raise WebSocketProtocolError("websocket message exceeds configured max message size")
    if opcode >= 0x8 and (not fin or len(data) > 125):
        raise WebSocketProtocolError("websocket control frames must be final and at most 125 bytes")
    first = (0x80 if fin else 0) | (opcode & 0x0F)
    length = len(data)
    if length < 126:
        length_bytes = bytes([length])
    elif length <= 0xFFFF:
        length_bytes = bytes([126]) + struct.pack("!H", length)
    else:
        length_bytes = bytes([127]) + struct.pack("!Q", length)

    if not mask:
        return bytes([first]) + length_bytes + data
    key = secrets.token_bytes(4) if mask_key is None else bytes(mask_key)
    if len(key) != 4:
        raise ValueError("websocket mask key must be exactly 4 bytes")
    return bytes([first, length_bytes[0] | 0x80]) + length_bytes[1:] + key + _mask_payload(data, key)


def decode_websocket_frame(
    data: bytes,
    *,
    expect_masked: bool | None = None,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> tuple[WebSocketFrame, bytes]:
    if len(data) < 2:
        raise EOFError("incomplete websocket frame header")
    first, second = data[0], data[1]
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    if expect_masked is not None and masked != expect_masked:
        expected = "masked" if expect_masked else "unmasked"
        raise WebSocketProtocolError(f"expected {expected} websocket frame")

    length = second & 0x7F
    offset = 2
    if length == 126:
        if len(data) < offset + 2:
            raise EOFError("incomplete websocket frame extended length")
        length = struct.unpack("!H", data[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        if len(data) < offset + 8:
            raise EOFError("incomplete websocket frame extended length")
        length = struct.unpack("!Q", data[offset : offset + 8])[0]
        offset += 8

    if length > max_message_size:
        raise WebSocketProtocolError("websocket message exceeds configured max message size")
    if opcode >= 0x8 and (not fin or length > 125):
        raise WebSocketProtocolError("websocket control frames must be final and at most 125 bytes")

    mask_key = b""
    if masked:
        if len(data) < offset + 4:
            raise EOFError("incomplete websocket frame mask")
        mask_key = data[offset : offset + 4]
        offset += 4

    end = offset + length
    if len(data) < end:
        raise EOFError("incomplete websocket frame payload")
    payload = data[offset:end]
    if masked:
        payload = _mask_payload(payload, mask_key)
    return WebSocketFrame(fin=fin, opcode=opcode, payload=payload, masked=masked), data[end:]


def encode_websocket_text_message(
    text: str,
    *,
    mask: bool = True,
    mask_key: bytes | None = None,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> bytes:
    return encode_websocket_frame(
        text,
        opcode=OPCODE_TEXT,
        mask=mask,
        mask_key=mask_key,
        max_message_size=max_message_size,
    )


def encode_websocket_close_frame(
    *,
    code: int | None = None,
    reason: str = "",
    mask: bool = True,
    mask_key: bytes | None = None,
) -> bytes:
    if code is None:
        if reason:
            raise ValueError("websocket close reason requires a close code")
        payload = b""
    else:
        if not 0 <= code <= 0xFFFF:
            raise ValueError("websocket close code must fit in 16 bits")
        payload = struct.pack("!H", code) + reason.encode("utf-8")
    return encode_websocket_frame(payload, opcode=OPCODE_CLOSE, mask=mask, mask_key=mask_key)


def decode_websocket_text_message(
    data: bytes,
    *,
    expect_masked: bool | None = False,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> tuple[str, bytes]:
    frame, remaining = decode_websocket_frame(
        data,
        expect_masked=expect_masked,
        max_message_size=max_message_size,
    )
    return frame.text(), remaining


def websocket_close_code_and_reason(frame: WebSocketFrame) -> tuple[int | None, str]:
    if frame.opcode != OPCODE_CLOSE:
        raise WebSocketProtocolError(f"expected close frame, got opcode {frame.opcode}")
    if not frame.payload:
        return None, ""
    if len(frame.payload) == 1:
        raise WebSocketProtocolError("websocket close payload must be empty or include a two-byte status code")
    code = struct.unpack("!H", frame.payload[:2])[0]
    return code, frame.payload[2:].decode("utf-8")


def websocket_close_reason(frame: WebSocketFrame, *, default: str = "connection closed") -> str:
    _code, reason = websocket_close_code_and_reason(frame)
    return reason or default


def websocket_frame_event(
    frame: WebSocketFrame,
    *,
    close_default: str = "connection closed",
) -> WebSocketFrameEvent:
    if frame.opcode == OPCODE_TEXT:
        return WebSocketFrameEvent(kind="text", text=frame.text())
    if frame.opcode == OPCODE_CLOSE:
        code, reason = websocket_close_code_and_reason(frame)
        return WebSocketFrameEvent(
            kind="close",
            close_code=code,
            close_reason=reason or close_default,
        )
    if frame.opcode in {OPCODE_CONTINUATION, OPCODE_BINARY, OPCODE_PING, OPCODE_PONG}:
        return WebSocketFrameEvent(kind="ignored", ignored_opcode=frame.opcode)
    raise WebSocketProtocolError(f"unsupported websocket opcode {frame.opcode}")


def _read_exact(sock: socket.socket, byte_count: int) -> bytes:
    data = bytearray()
    while len(data) < byte_count:
        chunk = sock.recv(byte_count - len(data))
        if not chunk:
            raise EOFError("websocket stream closed while reading frame")
        data.extend(chunk)
    return bytes(data)


def read_websocket_frame(
    sock: socket.socket,
    *,
    expect_masked: bool | None = False,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> WebSocketFrame:
    data = bytearray(_read_exact(sock, 2))
    length = data[1] & 0x7F
    if length == 126:
        data.extend(_read_exact(sock, 2))
        length = struct.unpack("!H", data[2:4])[0]
    elif length == 127:
        data.extend(_read_exact(sock, 8))
        length = struct.unpack("!Q", data[2:10])[0]

    if length > max_message_size:
        raise WebSocketProtocolError("websocket message exceeds configured max message size")
    if data[1] & 0x80:
        data.extend(_read_exact(sock, 4))
    data.extend(_read_exact(sock, length))
    frame, remaining = decode_websocket_frame(
        bytes(data),
        expect_masked=expect_masked,
        max_message_size=max_message_size,
    )
    if remaining:
        raise WebSocketProtocolError("unexpected trailing bytes after websocket frame")
    return frame


def read_websocket_text_message(
    sock: socket.socket,
    *,
    expect_masked: bool | None = False,
    max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
) -> str:
    return read_websocket_frame(
        sock,
        expect_masked=expect_masked,
        max_message_size=max_message_size,
    ).text()


def read_http_headers(sock: socket.socket, *, max_header_bytes: int = 65536) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise EOFError("websocket upgrade response closed before headers completed")
        data.extend(chunk)
        if len(data) > max_header_bytes:
            raise WebSocketProtocolError("websocket upgrade response headers are too large")
    return bytes(data)


class StdlibWebSocket:
    """Minimal blocking WebSocket connection used by the future remote client."""

    def __init__(self, sock: socket.socket, *, max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE) -> None:
        self._sock = sock
        self._max_message_size = max_message_size

    @classmethod
    def connect(
        cls,
        websocket_url: str,
        *,
        auth_token: str | None = None,
        timeout: float = 10.0,
        max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
    ) -> "StdlibWebSocket":
        parsed = _parsed_websocket_url(websocket_url)
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        raw = socket.create_connection((parsed.hostname, port), timeout=timeout)
        sock = raw
        try:
            if parsed.scheme == "wss":
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            return cls.connect_socket(
                sock,
                websocket_url,
                auth_token=auth_token,
                max_message_size=max_message_size,
            )
        except Exception:
            sock.close()
            raise

    @classmethod
    def connect_socket(
        cls,
        sock: socket.socket,
        websocket_url: str,
        *,
        auth_token: str | None = None,
        max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
    ) -> "StdlibWebSocket":
        try:
            key = generate_websocket_key()
            sock.sendall(build_websocket_handshake_request(websocket_url, key, auth_token=auth_token))
            validate_websocket_handshake_response(read_http_headers(sock), key)
            return cls(sock, max_message_size=max_message_size)
        except Exception:
            sock.close()
            raise

    @classmethod
    def connect_unix_socket(
        cls,
        socket_path: Path | str,
        *,
        websocket_url: str = "ws://localhost/rpc",
        timeout: float = 10.0,
        max_message_size: int = DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE,
    ) -> "StdlibWebSocket":
        family = getattr(socket, "AF_UNIX", None)
        if family is None:
            raise OSError("Unix domain sockets are not supported on this platform")
        raw = socket.socket(family, socket.SOCK_STREAM)
        raw.settimeout(timeout)
        try:
            raw.connect(str(socket_path))
            return cls.connect_socket(raw, websocket_url, max_message_size=max_message_size)
        except Exception:
            raw.close()
            raise

    def send_text(self, text: str) -> None:
        self._sock.sendall(
            encode_websocket_text_message(text, max_message_size=self._max_message_size)
        )

    def recv_frame(self, *, expect_masked: bool | None = False) -> WebSocketFrame:
        return read_websocket_frame(
            self._sock,
            expect_masked=expect_masked,
            max_message_size=self._max_message_size,
        )

    def recv_text(self, *, expect_masked: bool | None = False) -> str:
        return read_websocket_text_message(
            self._sock,
            expect_masked=expect_masked,
            max_message_size=self._max_message_size,
        )

    def close(self) -> None:
        try:
            self._sock.sendall(encode_websocket_close_frame())
        finally:
            self._sock.close()


__all__ = [
    "DEFAULT_MAX_WEBSOCKET_MESSAGE_SIZE",
    "OPCODE_BINARY",
    "OPCODE_CLOSE",
    "OPCODE_CONTINUATION",
    "OPCODE_PING",
    "OPCODE_PONG",
    "OPCODE_TEXT",
    "StdlibWebSocket",
    "WEBSOCKET_GUID",
    "WEBSOCKET_VERSION",
    "WebSocketFrame",
    "WebSocketFrameEvent",
    "WebSocketHandshakeResponse",
    "WebSocketProtocolError",
    "build_websocket_handshake_request",
    "decode_websocket_frame",
    "decode_websocket_text_message",
    "encode_websocket_close_frame",
    "encode_websocket_frame",
    "encode_websocket_text_message",
    "generate_websocket_key",
    "parse_websocket_handshake_response",
    "read_http_headers",
    "read_websocket_frame",
    "read_websocket_text_message",
    "validate_websocket_handshake_response",
    "websocket_close_code_and_reason",
    "websocket_close_reason",
    "websocket_frame_event",
    "websocket_accept_key",
    "websocket_authorization_header",
]
