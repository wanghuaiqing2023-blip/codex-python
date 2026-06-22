"""Default client builder contracts for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/default_client.rs``
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .request import Request
from .request import RequestBody


Sender = Callable[["CodexRequestSnapshot"], Any]
TraceHeaderProvider = Callable[[], dict[str, str]]
DebugLogger = Callable[[dict[str, Any]], None]


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexRequestSnapshot:
    method: str
    url: str
    headers: dict[str, str]
    timeout: float | None = None
    body: bytes | None = None
    json_value: Any | None = None


class CodexHttpClient:
    def __init__(
        self,
        sender: Sender | None = None,
        *,
        trace_header_provider: TraceHeaderProvider | None = None,
        debug_logger: DebugLogger | None = None,
    ) -> None:
        self._sender = sender or _default_sender
        self._trace_header_provider = trace_header_provider or trace_headers
        self._debug_logger = debug_logger

    def get(self, url: str) -> "CodexRequestBuilder":
        return self.request("GET", url)

    def post(self, url: str) -> "CodexRequestBuilder":
        return self.request("POST", url)

    def request(self, method: str, url: str) -> "CodexRequestBuilder":
        return CodexRequestBuilder(
            sender=self._sender,
            trace_header_provider=self._trace_header_provider,
            debug_logger=self._debug_logger,
            method=str(method),
            url=str(url),
        )


@dataclass(frozen=True)
class CodexRequestBuilder:
    sender: Sender
    trace_header_provider: TraceHeaderProvider
    debug_logger: DebugLogger | None
    method: str
    url: str
    headers_map: dict[str, str] | None = None
    timeout_value: float | None = None
    body_value: bytes | None = None
    json_body: Any | None = None
    builder_error: Exception | None = None

    def _replace(self, **changes: Any) -> "CodexRequestBuilder":
        values = {
            "sender": self.sender,
            "trace_header_provider": self.trace_header_provider,
            "debug_logger": self.debug_logger,
            "method": self.method,
            "url": self.url,
            "headers_map": dict(self.headers_map or {}),
            "timeout_value": self.timeout_value,
            "body_value": self.body_value,
            "json_body": self.json_body,
            "builder_error": self.builder_error,
        }
        values.update(changes)
        return CodexRequestBuilder(**values)

    def headers(self, headers: dict[str, str]) -> "CodexRequestBuilder":
        merged = dict(self.headers_map or {})
        error = self.builder_error
        for key, value in headers.items():
            key_str = str(key)
            value_str = str(value)
            if _valid_header(key_str, value_str):
                _set_header(merged, key_str, value_str)
            elif error is None:
                error = ValueError(f"invalid HTTP header: {key_str!r}")
        return self._replace(headers_map=merged, builder_error=error)

    def header(self, key: str, value: str) -> "CodexRequestBuilder":
        merged = dict(self.headers_map or {})
        key_str = str(key)
        value_str = str(value)
        if not _valid_header(key_str, value_str):
            return self._replace(
                headers_map=merged,
                builder_error=self.builder_error
                or ValueError(f"invalid HTTP header: {key_str!r}"),
            )
        _set_header(merged, key_str, value_str)
        return self._replace(headers_map=merged)

    def bearer_auth(self, token: object) -> "CodexRequestBuilder":
        return self.header("authorization", f"Bearer {token}")

    def timeout(self, timeout: float) -> "CodexRequestBuilder":
        return self._replace(timeout_value=timeout)

    def json(self, value: Any) -> "CodexRequestBuilder":
        headers = dict(self.headers_map or {})
        if not _has_header(headers, "content-type"):
            _set_header(headers, "content-type", "application/json")
        return self._replace(headers_map=headers, json_body=value, body_value=None)

    def body(self, body: bytes | bytearray | memoryview | str) -> "CodexRequestBuilder":
        if isinstance(body, str):
            data = body.encode()
        else:
            data = bytes(body)
        return self._replace(body_value=data, json_body=None)

    def snapshot(self, *, include_trace_headers: bool = False) -> CodexRequestSnapshot:
        headers = dict(self.headers_map or {})
        if include_trace_headers:
            for key, value in _filtered_headers(self.trace_header_provider()).items():
                _set_header(headers, key, value)
        body = self.body_value
        if self.json_body is not None:
            body = json.dumps(
                self.json_body,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
            if not _has_header(headers, "content-type"):
                _set_header(headers, "content-type", "application/json")
        return CodexRequestSnapshot(
            method=self.method,
            url=self.url,
            headers=headers,
            timeout=self.timeout_value,
            body=body,
            json_value=self.json_body,
        )

    def send(self) -> Any:
        snapshot = self.snapshot(include_trace_headers=True)
        if self.builder_error is not None:
            self._debug_request_failed(snapshot, self.builder_error)
            raise self.builder_error
        try:
            response = self.sender(snapshot)
        except Exception as error:
            self._debug_request_failed(snapshot, error)
            raise
        self._debug_request_completed(snapshot, response)
        return response

    async def send_async(self) -> Any:
        """Async facade for Rust ``CodexRequestBuilder::send`` parity."""

        return await asyncio.to_thread(self.send)

    def _debug_request_completed(
        self,
        snapshot: CodexRequestSnapshot,
        response: Any,
    ) -> None:
        self._debug(
            {
                "message": "Request completed",
                "method": snapshot.method,
                "url": snapshot.url,
                "status": _response_value(response, "status"),
                "headers": _response_value(response, "headers"),
                "version": _response_value(response, "version"),
            }
        )

    def _debug_request_failed(
        self,
        snapshot: CodexRequestSnapshot,
        error: Exception,
    ) -> None:
        self._debug(
            {
                "message": "Request failed",
                "method": snapshot.method,
                "url": snapshot.url,
                "status": _response_value(error, "status"),
                "error": str(error),
            }
        )

    def _debug(self, event: dict[str, Any]) -> None:
        if self.debug_logger is not None:
            self.debug_logger(event)
            return
        _LOG.debug(event["message"], extra={"codex_client": event})


def trace_headers(
    span_context: dict[str, str] | None = None,
    propagator: Callable[[dict[str, str]], dict[str, str]] | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if propagator is not None:
        for key, value in propagator(span_context or {}).items():
            if _valid_header(key, value):
                headers[str(key)] = str(value)
    elif span_context:
        traceparent = span_context.get("traceparent")
        if traceparent and _valid_header("traceparent", traceparent):
            headers["traceparent"] = traceparent
        else:
            traceparent = _traceparent_from_span_context(span_context)
            if traceparent is not None:
                headers["traceparent"] = traceparent
    return headers


def _traceparent_from_span_context(span_context: dict[str, str]) -> str | None:
    trace_id = str(span_context.get("trace_id", "")).lower()
    span_id = str(span_context.get("span_id", "")).lower()
    if not _valid_lower_hex(trace_id, 32) or trace_id == "0" * 32:
        return None
    if not _valid_lower_hex(span_id, 16) or span_id == "0" * 16:
        return None

    flags = span_context.get("trace_flags", span_context.get("flags", "01"))
    if isinstance(flags, int):
        flags_hex = f"{flags & 0xFF:02x}"
    else:
        flags_hex = str(flags).lower()
        if flags_hex.startswith("0x"):
            flags_hex = flags_hex[2:]
        flags_hex = flags_hex.zfill(2)
    if not _valid_lower_hex(flags_hex, 2):
        flags_hex = "01"
    return f"00-{trace_id}-{span_id}-{flags_hex}"


def _valid_lower_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    return all("0" <= ch <= "9" or "a" <= ch <= "f" for ch in value)


def _filtered_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in headers.items()
        if _valid_header(key, value)
    }


def _has_header(headers: dict[str, str], name: str) -> bool:
    wanted = name.lower()
    return any(key.lower() == wanted for key in headers)


def _set_header(headers: dict[str, str], key: str, value: str) -> None:
    wanted = key.lower()
    for existing in list(headers):
        if existing.lower() == wanted:
            del headers[existing]
    headers[key] = value


def _valid_header(key: object, value: object) -> bool:
    if not isinstance(key, str) or not isinstance(value, str):
        return False
    return _valid_header_name(key) and _valid_header_value(value)


def _valid_header_name(key: str) -> bool:
    if not key:
        return False
    allowed_symbols = set("!#$%&'*+-.^_`|~")
    return all(
        "A" <= ch <= "Z"
        or "a" <= ch <= "z"
        or "0" <= ch <= "9"
        or ch in allowed_symbols
        for ch in key
    )


def _valid_header_value(value: str) -> bool:
    return all(ch == "\t" or " " <= ch <= "~" for ch in value)


def _response_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        result = value.get(name)
    else:
        result = getattr(value, name, None)
    if callable(result):
        return result()
    return result


def _default_sender(snapshot: CodexRequestSnapshot):
    from .transport import ReqwestTransport

    body = RequestBody.raw(snapshot.body) if snapshot.body is not None else None
    request = Request(
        method=snapshot.method,
        url=snapshot.url,
        headers=snapshot.headers,
        body=body,
        timeout=snapshot.timeout,
    )
    return ReqwestTransport().execute(request)
