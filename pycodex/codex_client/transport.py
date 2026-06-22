"""Transport contracts for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/transport.rs``
"""

from __future__ import annotations

import asyncio
import json
import http.client
import logging
import socket
import ssl
import urllib.parse
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from typing import runtime_checkable

from .error import TransportError
from .custom_ca import EnvSource
from .custom_ca import ProcessEnv
from .custom_ca import configured_ca_bundle
from .request import Request
from .request import RequestBody
from .request import Response


ByteStream = Iterable[bytes | TransportError]
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamResponse:
    status: int
    headers: dict[str, str]
    bytes: ByteStream


@dataclass(frozen=True)
class PreparedTransportRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None
    timeout: float | None


@dataclass(frozen=True)
class TransportHttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes | None
    stream: ByteStream | None = None

    def is_success(self) -> bool:
        return 200 <= self.status <= 299


@runtime_checkable
class HttpTransport(Protocol):
    def execute(self, req: Request) -> Response:
        """Execute a unary request."""

    def stream(self, req: Request) -> StreamResponse:
        """Execute a streaming request."""


class ReqwestTransport:
    """Dependency-light analogue of Rust ``ReqwestTransport``.

    The Rust type wraps ``reqwest::Client``. Python accepts an injected sender
    callable so build/status/error behavior can be ported without adding an
    HTTP dependency.
    """

    def __init__(
        self,
        sender: Callable[[PreparedTransportRequest], TransportHttpResponse] | None = None,
        *,
        stream_sender: Callable[[PreparedTransportRequest], TransportHttpResponse] | None = None,
        env_source: EnvSource | None = None,
        connection_factory: Callable[..., http.client.HTTPConnection] | None = None,
        trace_logger: Callable[[str], None] | None = None,
    ):
        env = env_source or ProcessEnv()
        factory = connection_factory or _default_connection_factory
        self._trace_logger = trace_logger
        self._sender = sender or (
            lambda prepared: _stdlib_execute_sender(prepared, env, factory)
        )
        self._stream_sender = stream_sender or (
            (lambda prepared: _stdlib_stream_sender(prepared, env, factory))
            if sender is None
            else self._sender
        )

    def build(self, req: Request) -> PreparedTransportRequest:
        try:
            prepared = req.prepare_body_for_send()
        except ValueError as exc:
            raise TransportError.build(str(exc)) from exc
        return PreparedTransportRequest(
            method=_normalize_method(req.method),
            url=req.url,
            headers=prepared.headers,
            body=prepared.body,
            timeout=req.timeout,
        )

    @staticmethod
    def map_error(err: BaseException) -> TransportError:
        is_timeout = getattr(err, "is_timeout", None)
        if callable(is_timeout) and is_timeout():
            return TransportError.timeout()
        if bool(getattr(err, "timeout", False)):
            return TransportError.timeout()
        return TransportError.network(str(err))

    def execute(self, req: Request) -> Response:
        url = req.url
        self._trace_request(req)
        try:
            resp = self._sender(self.build(req))
        except TransportError:
            raise
        except BaseException as exc:
            raise self.map_error(exc) from exc

        if not resp.is_success():
            raise TransportError.http(
                resp.status,
                url=url,
                headers=resp.headers,
                body=_decode_utf8_or_none(resp.body),
            )
        return Response(status=resp.status, headers=resp.headers, body=resp.body or b"")

    def stream(self, req: Request) -> StreamResponse:
        url = req.url
        self._trace_request(req)
        try:
            resp = self._stream_sender(self.build(req))
        except TransportError:
            raise
        except BaseException as exc:
            raise self.map_error(exc) from exc

        if not resp.is_success():
            raise TransportError.http(
                resp.status,
                url=url,
                headers=resp.headers,
                body=_decode_text_lossy_or_none(resp.body),
            )
        return StreamResponse(
            status=resp.status,
            headers=resp.headers,
            bytes=resp.stream if resp.stream is not None else _single_body_stream(resp.body),
        )

    async def execute_async(self, req: Request) -> Response:
        """Async facade for Rust ``HttpTransport::execute`` parity.

        Rust's transport trait is async because reqwest performs IO on Tokio.
        The Python port keeps the dependency-light standard-library sender, so
        the async surface delegates the same behavior to a worker thread.
        """

        return await asyncio.to_thread(self.execute, req)

    async def stream_async(self, req: Request) -> StreamResponse:
        """Async facade for Rust ``HttpTransport::stream`` parity."""

        return await asyncio.to_thread(self.stream, req)

    def _trace_request(self, req: Request) -> None:
        message = f"{req.method} to {req.url}: {request_body_for_trace(req)}"
        if self._trace_logger is not None:
            self._trace_logger(message)
        elif _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(message)


def request_body_for_trace(req: Request) -> str:
    if req.body is None:
        return ""
    if req.body.kind == "json":
        return json.dumps(req.body.value, separators=(",", ":"), ensure_ascii=False)
    if req.body.kind == "raw":
        return f"<raw body: {len(req.body.value)} bytes>"
    return ""


def _normalize_method(method: str) -> str:
    candidate = str(method)
    if _is_http_method_token(candidate):
        return candidate
    return "GET"


def _is_http_method_token(method: str) -> bool:
    # Mirrors the http crate's Method::from_bytes token validation closely
    # enough for request-builder parity without depending on an HTTP parser.
    if not method:
        return False
    allowed_symbols = set("!#$%&'*+-.^_`|~")
    return all(
        "A" <= ch <= "Z"
        or "a" <= ch <= "z"
        or "0" <= ch <= "9"
        or ch in allowed_symbols
        for ch in method
    )


def _decode_utf8_or_none(body: bytes | None) -> str | None:
    if body is None:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _decode_text_lossy_or_none(body: bytes | None) -> str | None:
    if body is None:
        return None
    return body.decode("utf-8", errors="replace")


def _single_body_stream(body: bytes | None) -> ByteStream:
    if not body:
        return []
    return [body]


def _stdlib_execute_sender(
    prepared: PreparedTransportRequest,
    env_source: EnvSource,
    connection_factory: Callable[..., http.client.HTTPConnection],
) -> TransportHttpResponse:
    connection, path = _stdlib_connection(prepared, env_source, connection_factory)
    try:
        connection.request(
            prepared.method,
            path,
            body=prepared.body,
            headers=prepared.headers,
        )
        response = connection.getresponse()
        return TransportHttpResponse(
            status=response.status,
            headers=_stdlib_headers(response.getheaders()),
            body=response.read(),
        )
    except (TimeoutError, socket.timeout) as exc:
        setattr(exc, "timeout", True)
        raise
    finally:
        connection.close()


def _stdlib_stream_sender(
    prepared: PreparedTransportRequest,
    env_source: EnvSource,
    connection_factory: Callable[..., http.client.HTTPConnection],
) -> TransportHttpResponse:
    connection, path = _stdlib_connection(prepared, env_source, connection_factory)
    try:
        connection.request(
            prepared.method,
            path,
            body=prepared.body,
            headers=prepared.headers,
        )
        response = connection.getresponse()
    except (TimeoutError, socket.timeout) as exc:
        setattr(exc, "timeout", True)
        connection.close()
        raise
    except BaseException:
        connection.close()
        raise

    headers = _stdlib_headers(response.getheaders())
    if not 200 <= response.status <= 299:
        try:
            body = response.read()
        except BaseException:
            body = None
        connection.close()
        return TransportHttpResponse(
            status=response.status,
            headers=headers,
            body=body,
        )

    return TransportHttpResponse(
        status=response.status,
        headers=headers,
        body=b"",
        stream=_iter_stdlib_response(connection, response),
    )


def _stdlib_connection(
    prepared: PreparedTransportRequest,
    env_source: EnvSource,
    connection_factory: Callable[..., http.client.HTTPConnection],
):
    parsed = urllib.parse.urlsplit(prepared.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"unsupported URL for HTTP transport: {prepared.url}")

    path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    context = _ssl_context_for_url(parsed.scheme, env_source)
    connection = connection_factory(
        parsed.scheme,
        parsed.hostname,
        parsed.port,
        prepared.timeout,
        context,
    )
    return connection, path


def _default_connection_factory(
    scheme: str,
    host: str,
    port: int | None,
    timeout: float | None,
    context: ssl.SSLContext | None,
):
    if scheme == "https":
        return http.client.HTTPSConnection(
            host,
            port,
            timeout=timeout,
            context=context,
        )
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _ssl_context_for_url(scheme: str, env_source: EnvSource) -> ssl.SSLContext | None:
    if scheme != "https":
        return None
    bundle = configured_ca_bundle(env_source)
    if bundle is None:
        return ssl.create_default_context()
    bundle.load_certificates()
    return ssl.create_default_context(cafile=str(bundle.path))


def _stdlib_headers(headers) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers}


def _iter_stdlib_response(connection, response, chunk_size: int = 64 * 1024) -> ByteStream:
    try:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            yield chunk
    except (TimeoutError, socket.timeout) as exc:
        setattr(exc, "timeout", True)
        yield ReqwestTransport.map_error(exc)
    except BaseException as exc:
        yield ReqwestTransport.map_error(exc)
    finally:
        connection.close()
