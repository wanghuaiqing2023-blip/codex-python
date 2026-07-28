"""API-key input handling owned by ``read_api_key.rs``."""

from __future__ import annotations

from collections.abc import Callable

from . import ResponsesApiProxyError

BUFFER_SIZE = 1024
AUTH_HEADER_PREFIX = b"Bearer "


def validate_auth_header_bytes(key_bytes: bytes) -> None:
    if all(
        byte in b"-_"
        or 48 <= byte <= 57
        or 65 <= byte <= 90
        or 97 <= byte <= 122
        for byte in key_bytes
    ):
        return
    raise ResponsesApiProxyError(
        "API key may only contain ASCII letters, numbers, '-' or '_'"
    )


def read_auth_header_with(read_fn: Callable[[bytearray], int]) -> str:
    buf = bytearray(BUFFER_SIZE)
    buf[: len(AUTH_HEADER_PREFIX)] = AUTH_HEADER_PREFIX
    prefix_len = len(AUTH_HEADER_PREFIX)
    capacity = len(buf) - prefix_len
    total_read = 0
    saw_newline = False
    saw_eof = False

    while total_read < capacity:
        scratch = bytearray(capacity - total_read)
        try:
            read = read_fn(scratch)
        except OSError:
            _zeroize(buf)
            raise

        if read < 0:
            _zeroize(buf)
            raise ResponsesApiProxyError(
                "read function returned a negative byte count"
            )
        if read > len(scratch):
            _zeroize(buf)
            raise ResponsesApiProxyError(
                "read function returned more bytes than the supplied buffer"
            )
        if read == 0:
            saw_eof = True
            break

        newly_written = bytes(scratch[:read])
        newline_pos = newly_written.find(b"\n")
        if newline_pos >= 0:
            copy_len = newline_pos + 1
            start = prefix_len + total_read
            buf[start : start + copy_len] = newly_written[:copy_len]
            total_read += copy_len
            saw_newline = True
            break

        start = prefix_len + total_read
        buf[start : start + read] = newly_written
        total_read += read

    if total_read == capacity and not saw_newline and not saw_eof:
        _zeroize(buf)
        raise ResponsesApiProxyError(
            f"API key is too large to fit in the {BUFFER_SIZE}-byte buffer"
        )

    total = prefix_len + total_read
    while total > prefix_len and buf[total - 1] in (ord("\n"), ord("\r")):
        total -= 1

    if total == prefix_len:
        _zeroize(buf)
        raise ResponsesApiProxyError(
            "API key must be provided via stdin "
            "(e.g. printenv OPENAI_API_KEY | codex responses-api-proxy)"
        )

    key = bytes(buf[prefix_len:total])
    try:
        validate_auth_header_bytes(key)
        header = bytes(buf[:total]).decode("utf-8")
    except UnicodeDecodeError as exc:
        _zeroize(buf)
        raise ResponsesApiProxyError(
            "reading Authorization header from stdin as UTF-8"
        ) from exc
    except ResponsesApiProxyError:
        _zeroize(buf)
        raise

    _zeroize(buf)
    return header


def read_auth_header_from_text(text: str | bytes | None) -> str:
    if text is None:
        data = b""
    elif isinstance(text, bytes):
        data = text
    else:
        data = text.encode("utf-8")
    sent = False

    def read_once(buffer: bytearray) -> int:
        nonlocal sent
        if sent:
            return 0
        sent = True
        count = min(len(buffer), len(data))
        buffer[:count] = data[:count]
        return count

    return read_auth_header_with(read_once)


def _zeroize(buf: bytearray) -> None:
    for index in range(len(buf)):
        buf[index] = 0


__all__ = [
    "AUTH_HEADER_PREFIX",
    "BUFFER_SIZE",
    "read_auth_header_from_text",
    "read_auth_header_with",
    "validate_auth_header_bytes",
]
