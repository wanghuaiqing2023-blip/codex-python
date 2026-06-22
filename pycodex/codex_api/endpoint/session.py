"""Shared endpoint session helper for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/endpoint/session.rs``
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any
from typing import Callable

from pycodex.codex_client import Request
from pycodex.codex_client import RequestBody
from pycodex.codex_client import RequestTelemetry
from pycodex.codex_client import Response
from pycodex.codex_client import StreamResponse
from pycodex.codex_client import TransportError

from ..auth import AuthError
from ..auth import SharedAuthProvider
from ..error import ApiError
from ..provider import Provider
from ..telemetry import run_with_request_telemetry


RequestConfigure = Callable[[Request], None]


@dataclass(frozen=True)
class EndpointSession:
    transport: Any
    provider_value: Provider
    auth: SharedAuthProvider
    request_telemetry: RequestTelemetry | None = None

    @classmethod
    def new(
        cls,
        transport: Any,
        provider: Provider,
        auth: SharedAuthProvider,
    ) -> "EndpointSession":
        return cls(transport=transport, provider_value=provider, auth=auth)

    def with_request_telemetry(
        self,
        request: RequestTelemetry | None,
    ) -> "EndpointSession":
        return EndpointSession(
            transport=self.transport,
            provider_value=self.provider_value,
            auth=self.auth,
            request_telemetry=request,
        )

    def provider(self) -> Provider:
        return self.provider_value

    def make_request(
        self,
        method: str,
        path: str,
        extra_headers: dict[str, str] | None,
        body: Any | None,
    ) -> Request:
        request = self.provider_value.build_request(method, path)
        headers = dict(request.headers or {})
        headers.update(dict(extra_headers or {}))
        request = request.with_headers(headers)
        if body is not None:
            request = Request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                body=RequestBody.json(body),
                compression=request.compression,
                timeout=request.timeout,
            )
        return request

    async def execute(
        self,
        method: str,
        path: str,
        extra_headers: dict[str, str] | None,
        body: Any | None,
    ) -> Response:
        return await self.execute_with(method, path, extra_headers, body, lambda _req: None)

    async def execute_with(
        self,
        method: str,
        path: str,
        extra_headers: dict[str, str] | None,
        body: Any | None,
        configure: RequestConfigure,
    ) -> Response:
        def make_request() -> Request:
            request = self.make_request(method, path, extra_headers, body)
            configure(request)
            return request

        async def send(request: Request) -> Response:
            authenticated = await self._apply_auth(request)
            return await _maybe_await(self.transport.execute(authenticated))

        try:
            return await run_with_request_telemetry(
                self.provider_value.retry.to_policy(),
                self.request_telemetry,
                make_request,
                send,
            )
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

    async def stream_with(
        self,
        method: str,
        path: str,
        extra_headers: dict[str, str] | None,
        body: Any | None,
        configure: RequestConfigure,
    ) -> StreamResponse:
        def make_request() -> Request:
            request = self.make_request(method, path, extra_headers, body)
            configure(request)
            return request

        async def send(request: Request) -> StreamResponse:
            authenticated = await self._apply_auth(request)
            return await _maybe_await(self.transport.stream(authenticated))

        try:
            return await run_with_request_telemetry(
                self.provider_value.retry.to_policy(),
                self.request_telemetry,
                make_request,
                send,
            )
        except TransportError as exc:
            raise ApiError.transport_error(exc) from exc

    async def _apply_auth(self, request: Request) -> Request:
        try:
            return await _maybe_await(self.auth.apply_auth(request))
        except AuthError as exc:
            raise exc.to_transport_error() from exc


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = ["EndpointSession"]
