"""Responses HTTP endpoint client for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/endpoint/responses.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.codex_client import RequestCompression
from pycodex.codex_client import RequestTelemetry
from pycodex.codex_client import StreamResponse

from ..auth import SharedAuthProvider
from ..common import ResponseStream
from ..common import ResponsesApiRequest
from ..provider import Provider
from ..requests import Compression
from ..requests import SessionSource
from ..requests import attach_item_ids
from ..requests import build_session_headers
from ..requests import insert_header
from ..requests import subagent_header
from ..sse.responses import spawn_response_stream
from ..telemetry import SseTelemetry
from .session import EndpointSession


@dataclass(frozen=True)
class ResponsesOptions:
    session_id: str | None = None
    thread_id: str | None = None
    session_source: SessionSource | None = None
    extra_headers: dict[str, str] | None = None
    compression: Compression = Compression.NONE
    turn_state: Any | None = None


@dataclass(frozen=True)
class ResponsesClient:
    session: EndpointSession
    sse_telemetry: SseTelemetry | None = None

    @classmethod
    def new(
        cls,
        transport: Any,
        provider: Provider,
        auth: SharedAuthProvider,
    ) -> "ResponsesClient":
        return cls(session=EndpointSession.new(transport, provider, auth))

    def with_telemetry(
        self,
        request: RequestTelemetry | None,
        sse: SseTelemetry | None,
    ) -> "ResponsesClient":
        return ResponsesClient(
            session=self.session.with_request_telemetry(request),
            sse_telemetry=sse,
        )

    async def stream_request(
        self,
        request: ResponsesApiRequest,
        options: ResponsesOptions | None = None,
    ) -> ResponseStream:
        opts = options or ResponsesOptions()
        body = _jsonify(request.to_json_dict())
        if request.store and self.session.provider().is_azure_responses_endpoint():
            attach_item_ids(body, request.input or [])

        headers = dict(opts.extra_headers or {})
        if opts.thread_id is not None:
            insert_header(headers, "x-client-request-id", opts.thread_id)
        headers.update(build_session_headers(opts.session_id, opts.thread_id))
        subagent = subagent_header(opts.session_source)
        if subagent is not None:
            insert_header(headers, "x-openai-subagent", subagent)

        return await self.stream(body, headers, opts.compression, opts.turn_state)

    @staticmethod
    def path() -> str:
        return "responses"

    async def stream(
        self,
        body: Any,
        extra_headers: dict[str, str] | None,
        compression: Compression,
        turn_state: Any | None = None,
    ) -> ResponseStream:
        request_compression = (
            RequestCompression.NONE
            if compression == Compression.NONE
            else RequestCompression.ZSTD
        )

        def configure(req) -> None:
            req.headers["accept"] = "text/event-stream"
            object.__setattr__(req, "compression", request_compression)

        stream_response = await self.session.stream_with(
            "POST",
            self.path(),
            dict(extra_headers or {}),
            body,
            configure,
        )
        return spawn_response_stream(
            stream_response,
            self.session.provider().stream_idle_timeout,
            self.sse_telemetry,
            turn_state,
        )


def _jsonify(value: Any) -> Any:
    if hasattr(value, "to_json_dict"):
        return _jsonify(value.to_json_dict())
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonify(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonify(item) for item in value]
    return value


__all__ = [
    "ResponsesClient",
    "ResponsesOptions",
    "spawn_response_stream",
]
