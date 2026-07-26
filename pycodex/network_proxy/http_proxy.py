"""Rust-aligned projection of ``codex-network-proxy::http_proxy``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

@dataclass(frozen=True)
class HttpConnectRequest:
    uri: str
    headers: Mapping[str, object] = field(default_factory=dict)
    client: str | None = None


@dataclass(frozen=True)
class HttpConnectAccepted:
    host: str
    port: int
    mitm_enabled: bool
    mode: NetworkMode
    mitm_state: object | None = None


@dataclass(frozen=True)
class HttpConnectAcceptResult:
    response: NetworkProxyResponse
    request: HttpConnectRequest
    accepted: HttpConnectAccepted


@dataclass(frozen=True)
class HttpPlainRequest:
    method: str
    uri: str
    headers: Mapping[str, object] = field(default_factory=dict)
    client: str | None = None


def validate_absolute_form_host_header(url: str, headers: Mapping[str, object]) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    target_host = parsed.hostname
    if not target_host:
        return None
    host_header = _header_value(headers, "host")
    if host_header is None:
        return None
    try:
        header_host, header_port = _parse_host_header(str(host_header))
    except ValueError:
        return "invalid Host header"
    if normalize_host(header_host) != normalize_host(target_host):
        return "Host header does not match request target"
    target_port = parsed.port
    if header_port is not None:
        if header_port != target_port:
            return "Host header does not match request target"
        return None
    if target_port is not None and target_port != _default_port_for_scheme(parsed.scheme):
        return "Host header does not match request target"
    return None


async def http_connect_accept(
    request: HttpConnectRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> HttpConnectAcceptResult:
    http_request = _http_connect_request(request)
    authority = _http_connect_authority(http_request)
    if authority is None:
        raise HttpConnectRejected(text_response(400, "missing authority"))

    host = normalize_host(authority[0])
    port = authority[1]
    if not host:
        raise HttpConnectRejected(text_response(400, "invalid host"))

    client = http_request.client
    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        await _record_http_connect_blocked(state, host, port, client, None, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(REASON_PROXY_DISABLED, details))

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.HTTPS_CONNECT,
                host=host,
                port=port,
                client_addr=client,
                method="CONNECT",
                command=None,
                exec_policy_hint=None,
            )
        ),
    )
    if not decision.is_allow:
        if decision.reason is None or decision.source is None or decision.decision is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        details = PolicyDecisionDetails(
            decision=decision.decision,
            reason=decision.reason,
            source=decision.source,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        await _record_http_connect_blocked(state, host, port, client, None, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(decision.reason, details))

    mode = await _network_proxy_state_network_mode(state)
    mitm_state = await _network_proxy_state_mitm_state(state)
    host_has_hooks = await state.host_has_mitm_hooks(host)
    connect_needs_mitm = mode is NetworkMode.LIMITED or host_has_hooks

    if connect_needs_mitm and mitm_state is None:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_MITM_REQUIRED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.MODE_GUARD,
                reason=REASON_MITM_REQUIRED,
                protocol=NetworkProtocol.HTTPS_CONNECT,
                server_address=host,
                server_port=port,
                method="CONNECT",
                client_addr=client,
            ),
        )
        await _record_http_connect_blocked(state, host, port, client, mode, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(REASON_MITM_REQUIRED, details))

    return HttpConnectAcceptResult(
        response=NetworkProxyResponse(status=200, body="", headers={}),
        request=http_request,
        accepted=HttpConnectAccepted(
            host=host,
            port=port,
            mitm_enabled=connect_needs_mitm,
            mode=mode,
            mitm_state=mitm_state if connect_needs_mitm else None,
        ),
    )


class HttpConnectRejected(PermissionError):
    def __init__(self, response: NetworkProxyResponse) -> None:
        self.response = response
        super().__init__(response.body)


async def run_http_proxy(
    state: NetworkProxyState,
    addr: tuple[str, int] | str,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> None:
    """Run the dependency-light HTTP/1 proxy listener.

    Rust source: codex-network-proxy/src/http_proxy.rs `run_http_proxy`.
    Contract: bind an HTTP proxy listener and serve HTTP/1 CONNECT/plain
    requests through the same policy helpers as the direct Python facades.
    """

    host, port = _parse_socket_addr(addr)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_http_proxy_client(reader, writer, state, decider),
        host=host,
        port=port,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        server.close()
        await server.wait_closed()


async def run_http_proxy_with_std_listener(
    state: NetworkProxyState,
    listener: socket.socket,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> None:
    """Serve HTTP proxy traffic from an existing stdlib listener socket."""

    listener.setblocking(False)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_http_proxy_client(reader, writer, state, decider),
        sock=listener,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        server.close()
        await server.wait_closed()


async def http_plain_proxy(
    request: HttpPlainRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> NetworkProxyResponse:
    http_request = _http_plain_request(request)
    method = http_request.method.upper()
    method_allowed = await state.method_allowed(method)
    socket_path = _header_value(http_request.headers, "x-unix-socket")
    if socket_path is None:
        authority = _http_plain_authority(http_request)
        if authority is None:
            return text_response(400, "missing host")
        host = normalize_host(authority[0])
        port = authority[1]
        mismatch_reason = validate_absolute_form_host_header(http_request.uri, http_request.headers)
        if mismatch_reason is not None:
            return text_response(400, mismatch_reason)

        if not await _network_proxy_state_enabled(state):
            details = PolicyDecisionDetails(
                decision=NetworkPolicyDecision.DENY,
                reason=REASON_PROXY_DISABLED,
                source=NetworkDecisionSource.PROXY_STATE,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            emit_block_decision_audit_event(
                state,
                BlockDecisionAuditEventArgs(
                    source=NetworkDecisionSource.PROXY_STATE,
                    reason=REASON_PROXY_DISABLED,
                    protocol=NetworkProtocol.HTTP,
                    server_address=host,
                    server_port=port,
                    method=method,
                    client_addr=http_request.client,
                ),
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, None, details)
            return text_response(503, blocked_message_with_policy(REASON_PROXY_DISABLED, details))

        policy_request = NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
                client_addr=http_request.client,
                method=method,
                command=None,
                exec_policy_hint=None,
            )
        )
        decision = await evaluate_host_policy(state, decider, policy_request)
        if not decision.is_allow:
            if decision.reason is None or decision.source is None or decision.decision is None:
                raise ValueError("deny network decision must carry decision, source, and reason")
            details = PolicyDecisionDetails(
                decision=decision.decision,
                reason=decision.reason,
                source=decision.source,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, None, details)
            return json_blocked(host, decision.reason, details)

        if not method_allowed:
            details = PolicyDecisionDetails(
                decision=NetworkPolicyDecision.DENY,
                reason=REASON_METHOD_NOT_ALLOWED,
                source=NetworkDecisionSource.MODE_GUARD,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            emit_block_decision_audit_event(
                state,
                BlockDecisionAuditEventArgs(
                    source=NetworkDecisionSource.MODE_GUARD,
                    reason=REASON_METHOD_NOT_ALLOWED,
                    protocol=NetworkProtocol.HTTP,
                    server_address=host,
                    server_port=port,
                    method=method,
                    client_addr=http_request.client,
                ),
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, NetworkMode.LIMITED, details)
            return json_blocked(host, REASON_METHOD_NOT_ALLOWED, details)

        try:
            allow_upstream_proxy = await state.allow_upstream_proxy()
        except Exception:
            allow_upstream_proxy = False
        upstream_proxy = ProxyConfig.from_env().proxy_for_protocol(False) if allow_upstream_proxy else None
        try:
            return await _serve_plain_http_upstream(http_request, host, port, upstream_proxy)
        except OSError:
            return text_response(502, "upstream failure")
    socket_path = str(socket_path)

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.HTTP,
            host=socket_path,
            port=0,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason=REASON_PROXY_DISABLED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        await _record_plain_http_blocked(state, socket_path, 0, http_request.client, method, None, details)
        return text_response(503, blocked_message_with_policy(REASON_PROXY_DISABLED, details))

    if not method_allowed:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.HTTP,
            host="unix-socket",
            port=0,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.MODE_GUARD,
                reason=REASON_METHOD_NOT_ALLOWED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return json_blocked("unix-socket", REASON_METHOD_NOT_ALLOWED, None)

    if not _unix_socket_permissions_supported():
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason=REASON_UNIX_SOCKET_UNSUPPORTED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return text_response(501, "unix sockets unsupported")

    if await state.is_unix_socket_allowed(socket_path):
        emit_allow_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason="allow",
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return text_response(502, "unix socket proxy failed")

    emit_block_decision_audit_event(
        state,
        BlockDecisionAuditEventArgs(
            source=NetworkDecisionSource.PROXY_STATE,
            reason=REASON_NOT_ALLOWED,
            protocol=NetworkProtocol.HTTP,
            server_address="unix-socket",
            server_port=0,
            method=method,
            client_addr=http_request.client,
        ),
    )
    return json_blocked("unix-socket", REASON_NOT_ALLOWED, None)


def remove_hop_by_hop_request_headers(headers: MutableMapping[str, object]) -> None:
    while True:
        connection_key = _header_key(headers, "connection")
        if connection_key is None:
            break
        raw_connection = headers.pop(connection_key)
        for token in _connection_header_tokens(raw_connection):
            key = _header_key(headers, token)
            if key is not None:
                headers.pop(key, None)
    for name in (
        "keep-alive",
        "proxy-connection",
        "proxy-authorization",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "te",
    ):
        key = _header_key(headers, name)
        if key is not None:
            headers.pop(key, None)


async def _serve_plain_http_upstream(
    request: HttpPlainRequest,
    host: str,
    port: int,
    proxy: ProxyAddress | None,
) -> NetworkProxyResponse:
    connect_host = proxy.host if proxy is not None else host
    if not connect_host:
        raise OSError("missing upstream host")
    if proxy is not None:
        connect_port = proxy.port or 80
    else:
        connect_port = port

    reader, writer = await asyncio.open_connection(connect_host, connect_port)
    try:
        headers: dict[str, object] = dict(request.headers)
        remove_hop_by_hop_request_headers(headers)
        if _header_key(headers, "host") is None:
            headers["host"] = _authority_header_for_host_port(host, port)

        target = _plain_http_request_target(request.uri, host, port, proxy is not None)
        lines = [f"{request.method.upper()} {target} HTTP/1.1"]
        for key, value in headers.items():
            if value is None:
                continue
            lines.append(f"{key}: {value}")
        lines.append("")
        lines.append("")
        writer.write("\r\n".join(lines).encode("iso-8859-1", "replace"))
        await writer.drain()

        response_head = await reader.readuntil(b"\r\n\r\n")
        status, response_headers, content_length = _parse_plain_http_response_head(response_head)
        if content_length is None:
            body = await reader.read()
        else:
            body = await reader.readexactly(content_length)
        return NetworkProxyResponse(
            status=status,
            body=body.decode("utf-8", "replace"),
            headers=response_headers,
        )
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError) as exc:
        raise OSError("upstream failure") from exc
    finally:
        await _close_stream_writer(writer)


def _plain_http_request_target(uri: str, host: str, port: int, via_proxy: bool) -> str:
    parsed = urlparse(uri)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if via_proxy:
        if parsed.scheme and parsed.netloc:
            return uri
        return f"http://{_authority_header_for_host_port(host, port)}{path}"
    return path


def _authority_header_for_host_port(host: str, port: int) -> str:
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = f"[{host}]"
    return host if port == 80 else f"{host}:{port}"


def _parse_plain_http_response_head(head: bytes) -> tuple[int, dict[str, str], int | None]:
    text = head.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/"):
        raise ValueError("invalid HTTP response")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2:
        raise ValueError("missing HTTP status")
    status = int(parts[1])
    headers: dict[str, str] = {}
    content_length: int | None = None
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        lower_name = name.strip().lower()
        stripped = value.strip()
        headers[lower_name] = stripped
        if lower_name == "content-length":
            content_length = int(stripped)
    return status, headers, content_length


def json_blocked(
    host: str,
    reason: str,
    details: PolicyDecisionDetails | None = None,
) -> NetworkProxyResponse:
    payload: dict[str, JsonValue] = {
        "status": "blocked",
        "host": host,
        "reason": reason,
    }
    if details is not None:
        payload["decision"] = details.decision.as_str()
        payload["source"] = details.source.as_str()
        payload["protocol"] = details.protocol.as_policy_protocol()
        payload["port"] = details.port
        payload["message"] = blocked_message_with_policy(reason, details)
    response = json_response(payload)
    return NetworkProxyResponse(
        status=403,
        body=response.body,
        headers={**dict(response.headers), "x-proxy-error": blocked_header_value(reason)},
    )


def _extract_request_host(request: Any) -> str | None:
    return extract_request_host(request)


def _http_connect_request(request: HttpConnectRequest | Mapping[str, object] | object) -> HttpConnectRequest:
    if isinstance(request, HttpConnectRequest):
        return request
    return HttpConnectRequest(
        uri=_request_uri(request),
        headers=dict(_request_headers(request)),
        client=_request_client(request),
    )


def _http_plain_request(request: HttpPlainRequest | Mapping[str, object] | object) -> HttpPlainRequest:
    if isinstance(request, HttpPlainRequest):
        return request
    return HttpPlainRequest(
        method=_request_method(request),
        uri=_request_uri(request),
        headers=dict(_request_headers(request)),
        client=_request_client(request),
    )


def _http_connect_authority(request: HttpConnectRequest) -> tuple[str, int] | None:
    candidates: list[str] = []
    parsed = urlparse(request.uri)
    if parsed.netloc:
        candidates.append(parsed.netloc)
    elif request.uri:
        candidates.append(request.uri)
    host_header = _header_value(request.headers, "host")
    if host_header is not None:
        candidates.append(str(host_header))

    for candidate in candidates:
        try:
            host, port = _parse_host_header(candidate)
        except ValueError:
            continue
        if port is None:
            scheme = parsed.scheme.lower()
            port = _default_port_for_scheme(scheme) if scheme else 443
        if port is None:
            continue
        return host, port
    return None


def _http_plain_authority(request: HttpPlainRequest) -> tuple[str, int] | None:
    parsed = urlparse(request.uri)
    if parsed.hostname:
        port = parsed.port or _default_port_for_scheme(parsed.scheme) or 80
        return parsed.hostname, port
    host_header = _header_value(request.headers, "host")
    if host_header is None:
        return None
    try:
        host, port = _parse_host_header(str(host_header))
    except ValueError:
        return None
    return host, port or 80


async def _handle_http_proxy_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
) -> None:
    try:
        raw_head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        _write_http_proxy_response(writer, text_response(400, "bad request"))
        await _close_stream_writer(writer)
        return

    try:
        method, target, headers = _parse_http1_proxy_request_head(raw_head)
    except ValueError:
        _write_http_proxy_response(writer, text_response(400, "bad request"))
        await _close_stream_writer(writer)
        return

    client = _stream_peer_addr(writer)
    if method == "CONNECT":
        try:
            result = await http_connect_accept(
                HttpConnectRequest(uri=target, headers=headers, client=client),
                state,
                decider,
            )
        except HttpConnectRejected as exc:
            _write_http_proxy_response(writer, exc.response)
            await _close_stream_writer(writer)
            return
        _write_http_proxy_response(writer, result.response)
        await writer.drain()
        await _forward_connect_tunnel(reader, writer, result.accepted, state)
        return

    response = await http_plain_proxy(
        HttpPlainRequest(method=method, uri=target, headers=headers, client=client),
        state,
        decider,
    )
    _write_http_proxy_response(writer, response)
    await _close_stream_writer(writer)


def _parse_http1_proxy_request_head(raw_head: bytes) -> tuple[str, str, dict[str, str]]:
    text = raw_head.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines or not lines[0]:
        raise ValueError("missing request line")
    parts = lines[0].split()
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        raise ValueError("invalid request line")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    return parts[0].upper(), parts[1], headers


def _write_http_proxy_response(writer: asyncio.StreamWriter, response: NetworkProxyResponse) -> None:
    body = response.body.encode("utf-8")
    headers: dict[str, str] = {
        "content-length": str(len(body)),
        "connection": "close",
    }
    headers.update({str(key): str(value) for key, value in response.headers.items()})
    lines = [f"HTTP/1.1 {response.status} {_http_reason_phrase(response.status)}"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1") + body)


def _http_reason_phrase(status: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }.get(status, "OK")


def _stream_peer_addr(writer: asyncio.StreamWriter) -> str | None:
    peer = writer.get_extra_info("peername")
    if isinstance(peer, tuple) and len(peer) >= 2:
        return f"{peer[0]}:{peer[1]}"
    return None


async def _close_stream_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, RuntimeError):
        pass


async def _forward_connect_tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    accepted: HttpConnectAccepted,
    state: NetworkProxyState,
) -> None:
    if accepted.mitm_enabled:
        # MITM tunnel handling remains a separate runtime boundary.
        await _close_stream_writer(client_writer)
        return

    try:
        allow_upstream_proxy = await state.allow_upstream_proxy()
    except Exception:
        allow_upstream_proxy = False
    upstream_proxy = proxy_for_connect() if allow_upstream_proxy else None

    try:
        if upstream_proxy is not None:
            target_reader, target_writer = await _open_upstream_connect_tunnel(
                accepted,
                upstream_proxy,
            )
        else:
            target_reader, target_writer = await asyncio.open_connection(
                accepted.host,
                accepted.port,
            )
    except (OSError, ValueError):
        await _close_stream_writer(client_writer)
        return

    async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            await _close_stream_writer(writer)

    await asyncio.gather(
        pipe(client_reader, target_writer),
        pipe(target_reader, client_writer),
        return_exceptions=True,
    )


async def _open_upstream_connect_tunnel(
    accepted: HttpConnectAccepted,
    proxy: ProxyAddress,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    if not proxy.host:
        raise ValueError("missing proxy host")
    proxy_port = proxy.port or 80
    reader, writer = await asyncio.open_connection(proxy.host, proxy_port)
    authority = f"{accepted.host}:{accepted.port}"
    request = (
        f"CONNECT {authority} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        "\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()

    try:
        response = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        await _close_stream_writer(writer)
        raise OSError("upstream CONNECT failed") from exc
    status_line = response.split(b"\r\n", 1)[0]
    if not (
        status_line.startswith(b"HTTP/1.1 200 ")
        or status_line == b"HTTP/1.1 200"
        or status_line.startswith(b"HTTP/1.0 200 ")
        or status_line == b"HTTP/1.0 200"
    ):
        await _close_stream_writer(writer)
        raise OSError("upstream CONNECT failed")
    return reader, writer


async def _record_http_connect_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method="CONNECT",
                mode=mode,
                protocol="http-connect",
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


async def _record_plain_http_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    method: str | None,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method=method,
                mode=mode,
                protocol=NetworkProtocol.HTTP.as_policy_protocol(),
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


def _remove_header_case_insensitive(headers: MutableMapping[str, Any], header_name: str) -> None:
    lowered = header_name.lower()
    for key in list(headers.keys()):
        if str(key).lower() == lowered:
            del headers[key]


def _header_key(headers: Mapping[str, object], name: str) -> str | None:
    lowered = name.lower()
    for key in headers:
        if str(key).lower() == lowered:
            return str(key)
    return None


def _header_value(headers: Mapping[str, object], name: str) -> object | None:
    key = _header_key(headers, name)
    if key is None:
        return None
    return headers[key]


def _connection_header_tokens(raw_connection: object) -> list[str]:
    if isinstance(raw_connection, bytes):
        try:
            raw_connection = raw_connection.decode("ascii")
        except UnicodeDecodeError:
            return []
    if isinstance(raw_connection, Sequence) and not isinstance(raw_connection, str):
        values = raw_connection
    else:
        values = (raw_connection,)
    tokens: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        tokens.extend(token.strip() for token in value.split(",") if token.strip())
    return tokens


def _parse_host_header(value: str) -> tuple[str, int | None]:
    text = value.strip()
    if not text:
        raise ValueError("empty Host header")
    parsed = urlparse(f"//{text}")
    host = parsed.hostname
    if not host:
        raise ValueError("invalid Host header")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Host header") from exc
    return host, port


def _default_port_for_scheme(scheme: str) -> int | None:
    normalized = scheme.lower()
    if normalized == "http":
        return 80
    if normalized == "https":
        return 443
    return None

from .config import NetworkMode
from .mitm import (
    _request_client,
    _request_headers,
    _request_method,
    _request_uri,
    extract_request_host,
)
from .network_policy import (
    BlockDecisionAuditEventArgs,
    NetworkDecision,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyRequest,
    NetworkPolicyRequestArgs,
    NetworkProtocol,
    emit_allow_decision_audit_event,
    emit_block_decision_audit_event,
    evaluate_host_policy,
)
from .policy import normalize_host
from .proxy import _parse_socket_addr
from .reasons import (
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_REQUIRED,
    REASON_NOT_ALLOWED,
    REASON_PROXY_DISABLED,
    REASON_UNIX_SOCKET_UNSUPPORTED,
)
from .responses import (
    NetworkProxyResponse,
    PolicyDecisionDetails,
    blocked_header_value,
    blocked_message_with_policy,
    blocked_text_response_with_policy,
    json_response,
    text_response,
)
from .runtime import (
    BlockedRequest,
    BlockedRequestArgs,
    NetworkProxyState,
    _network_proxy_state_enabled,
    _network_proxy_state_mitm_state,
    _network_proxy_state_network_mode,
    _unix_socket_permissions_supported,
)
from .upstream import (
    ProxyAddress,
    ProxyConfig,
    proxy_for_connect,
)

__all__ = [
    "HttpConnectAcceptResult",
    "HttpConnectAccepted",
    "HttpConnectRejected",
    "HttpConnectRequest",
    "HttpPlainRequest",
    "http_connect_accept",
    "http_plain_proxy",
    "json_blocked",
    "remove_hop_by_hop_request_headers",
    "run_http_proxy",
    "run_http_proxy_with_std_listener",
    "validate_absolute_form_host_header",
]
