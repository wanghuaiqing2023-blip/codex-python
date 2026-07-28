"""RMCP Streamable HTTP adapter over the shared executor ``HttpClient``."""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.exec_server.protocol import (
    ByteChunk,
    HttpHeader,
    HttpRequestParams,
)

from .www_authenticate import insufficient_scope_challenge

EVENT_STREAM_MIME_TYPE = "text/event-stream"
JSON_MIME_TYPE = "application/json"
HEADER_SESSION_ID = "Mcp-Session-Id"
NON_JSON_RESPONSE_BODY_PREVIEW_BYTES = 8_192


class StreamableHttpClientAdapterError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        www_authenticate_header: str | None = None,
        required_scope: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.www_authenticate_header = www_authenticate_header
        self.required_scope = required_scope


@dataclass(frozen=True)
class StreamableHttpPostResponse:
    kind: str
    message: Any | None = None
    stream: AsyncIterator[dict[str, str]] | None = None
    session_id: str | None = None


def _header_pairs(value: Any) -> Iterable[tuple[str, str]]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return ((str(name), str(item)) for name, item in value.items())
    return (
        (
            str(item.name if hasattr(item, "name") else item[0]),
            str(item.value if hasattr(item, "value") else item[1]),
        )
        for item in value
    )


def _headers_dict(value: Any) -> dict[str, tuple[str, str]]:
    return {
        name.lower(): (name, item)
        for name, item in _header_pairs(value)
    }


def response_header(headers: Iterable[Any], name: str) -> str | None:
    target = str(name).lower()
    for header_name, value in _header_pairs(headers):
        if header_name.lower() == target:
            return value
    return None


def protocol_headers(headers: Mapping[str, tuple[str, str]]) -> list[HttpHeader]:
    return [HttpHeader(name, value) for name, value in headers.values()]


def status_is_success(status: int) -> bool:
    return 200 <= int(status) < 300


def is_streamable_http_content_type(content_type: str) -> bool:
    return content_type.startswith(EVENT_STREAM_MIME_TYPE) or content_type.startswith(
        JSON_MIME_TYPE
    )


def body_preview(body: str) -> str:
    encoded = body.encode("utf-8")
    if len(encoded) <= NON_JSON_RESPONSE_BODY_PREVIEW_BYTES:
        return body
    prefix = encoded[:NON_JSON_RESPONSE_BODY_PREVIEW_BYTES]
    while prefix:
        try:
            text = prefix.decode("utf-8")
            break
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    else:
        text = ""
    return f"{text}... (truncated {len(encoded) - len(prefix)} bytes)"


async def collect_body(body_stream: Any) -> bytes:
    body = bytearray()
    while True:
        chunk = await body_stream.recv()
        if chunk is None:
            return bytes(body)
        body.extend(chunk)


async def sse_stream_from_body(body_stream: Any) -> AsyncIterator[dict[str, str]]:
    buffer = ""
    event: dict[str, str] = {}
    while True:
        chunk = await body_stream.recv()
        if chunk is None:
            buffer += "\n\n"
            eof = True
        else:
            buffer += bytes(chunk).decode("utf-8")
            eof = False
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                if event:
                    yield event
                    event = {}
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "data" and "data" in event:
                event["data"] += "\n" + value
            elif field in {"event", "data", "id", "retry"}:
                event[field] = value
        if eof:
            return


class StreamableHttpClientAdapter:
    def __init__(
        self,
        http_client: Any,
        default_headers: Any,
        auth_provider: Any | None,
    ) -> None:
        self.http_client = http_client
        self.default_headers = _headers_dict(default_headers)
        self.auth_provider = auth_provider

    def _request_headers(
        self,
        custom_headers: Any,
        *,
        accept: bool = False,
        content_type: bool = False,
        auth_token: str | None = None,
        session_id: str | None = None,
        last_event_id: str | None = None,
    ) -> dict[str, tuple[str, str]]:
        headers = dict(self.default_headers)
        headers.update(_headers_dict(custom_headers))
        if self.auth_provider is not None:
            auth_headers = self.auth_provider.to_auth_headers()
            headers.update(_headers_dict(auth_headers))
        if accept:
            headers["accept"] = (
                "Accept",
                f"{EVENT_STREAM_MIME_TYPE}, {JSON_MIME_TYPE}",
            )
        if content_type:
            headers["content-type"] = ("Content-Type", JSON_MIME_TYPE)
        if auth_token is not None:
            headers["authorization"] = (
                "Authorization",
                f"Bearer {auth_token}",
            )
        if session_id is not None:
            headers["mcp-session-id"] = (HEADER_SESSION_ID, session_id)
        if last_event_id is not None:
            headers["last-event-id"] = ("Last-Event-Id", last_event_id)
        return headers

    async def post_message(
        self,
        uri: str,
        message: Any,
        session_id: str | None,
        auth_token: str | None,
        custom_headers: Any,
    ) -> StreamableHttpPostResponse:
        headers = self._request_headers(
            custom_headers,
            accept=True,
            content_type=True,
            auth_token=auth_token,
            session_id=session_id,
        )
        request = HttpRequestParams(
            method="POST",
            url=str(uri),
            headers=protocol_headers(headers),
            body=ByteChunk(
                json.dumps(
                    message,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ),
            timeout_ms=None,
            request_id="buffered-request",
            stream_response=True,
        )
        response, stream = await self._await(
            self.http_client.http_request_stream(request)
        )
        status = int(response.status)
        if status == 404 and session_id is not None:
            raise StreamableHttpClientAdapterError(
                "session_expired_404",
                "streamable HTTP session expired with 404 Not Found",
            )
        if status == 401:
            header = response_header(response.headers, "WWW-Authenticate")
            if header is not None:
                raise StreamableHttpClientAdapterError(
                    "auth_required",
                    "streamable HTTP authentication required",
                    www_authenticate_header=header,
                )
        if status == 403:
            challenge = insufficient_scope_challenge(response.headers)
            if challenge is not None:
                raise StreamableHttpClientAdapterError(
                    "insufficient_scope",
                    "streamable HTTP OAuth scope is insufficient",
                    www_authenticate_header=challenge.www_authenticate_header,
                    required_scope=challenge.required_scope,
                )
        if status in {202, 204}:
            return StreamableHttpPostResponse("accepted")

        content_type_value = response_header(response.headers, "Content-Type")
        new_session_id = response_header(response.headers, HEADER_SESSION_ID)
        if content_type_value and content_type_value.startswith(EVENT_STREAM_MIME_TYPE):
            return StreamableHttpPostResponse(
                "sse",
                stream=sse_stream_from_body(stream),
                session_id=new_session_id,
            )
        if content_type_value and content_type_value.startswith(JSON_MIME_TYPE):
            body = await collect_body(stream)
            return StreamableHttpPostResponse(
                "json",
                message=json.loads(body),
                session_id=new_session_id,
            )
        body = await collect_body(stream)
        display_type = content_type_value or "missing-content-type"
        raise StreamableHttpClientAdapterError(
            "unexpected_content_type",
            f"{display_type}; body: {body_preview(body.decode('utf-8', errors='replace'))}",
        )

    async def delete_session(
        self,
        uri: str,
        session: str,
        auth_token: str | None,
        custom_headers: Any,
    ) -> None:
        headers = self._request_headers(
            custom_headers,
            auth_token=auth_token,
            session_id=session,
        )
        response = await self._await(
            self.http_client.http_request(
                HttpRequestParams(
                    method="DELETE",
                    url=str(uri),
                    headers=protocol_headers(headers),
                    body=None,
                    timeout_ms=None,
                    request_id="buffered-request",
                    stream_response=False,
                )
            )
        )
        if int(response.status) == 405:
            return
        if not status_is_success(response.status):
            raise StreamableHttpClientAdapterError(
                "unexpected_server_response",
                f"DELETE returned HTTP {response.status}",
            )

    async def get_stream(
        self,
        uri: str,
        session_id: str,
        last_event_id: str | None,
        auth_token: str | None,
        custom_headers: Any,
    ) -> AsyncIterator[dict[str, str]]:
        headers = self._request_headers(
            custom_headers,
            accept=True,
            auth_token=auth_token,
            session_id=session_id,
            last_event_id=last_event_id,
        )
        response, stream = await self._await(
            self.http_client.http_request_stream(
                HttpRequestParams(
                    method="GET",
                    url=str(uri),
                    headers=protocol_headers(headers),
                    body=None,
                    timeout_ms=None,
                    request_id="buffered-request",
                    stream_response=True,
                )
            )
        )
        status = int(response.status)
        if status == 405:
            raise StreamableHttpClientAdapterError(
                "server_does_not_support_sse",
                "server does not support SSE",
            )
        if status == 404:
            raise StreamableHttpClientAdapterError(
                "session_expired_404",
                "streamable HTTP session expired with 404 Not Found",
            )
        if not status_is_success(status):
            raise StreamableHttpClientAdapterError(
                "unexpected_server_response",
                f"GET returned HTTP {status}",
            )
        content_type = response_header(response.headers, "Content-Type")
        if content_type is None or not is_streamable_http_content_type(content_type):
            raise StreamableHttpClientAdapterError(
                "unexpected_content_type",
                str(content_type),
            )
        return sse_stream_from_body(stream)

    @staticmethod
    async def _await(value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value


__all__ = [
    "EVENT_STREAM_MIME_TYPE",
    "HEADER_SESSION_ID",
    "JSON_MIME_TYPE",
    "StreamableHttpClientAdapter",
    "StreamableHttpClientAdapterError",
    "StreamableHttpPostResponse",
    "body_preview",
    "collect_body",
    "is_streamable_http_content_type",
    "protocol_headers",
    "response_header",
    "sse_stream_from_body",
    "status_is_success",
]
