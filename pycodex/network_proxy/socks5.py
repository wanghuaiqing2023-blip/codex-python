"""Rust-aligned projection of ``codex-network-proxy::socks5``."""

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
class Socks5TcpRequest:
    host: str
    port: int
    client: str | None = None


@dataclass(frozen=True)
class Socks5UdpRequest:
    host: str
    port: int
    payload: bytes = b""
    client: str | None = None


@dataclass(frozen=True)
class Socks5PolicyResult:
    protocol: str
    host: str
    port: int
    payload: bytes | None = None


class Socks5PolicyError(PermissionError):
    def __init__(self, reason: str, details: PolicyDecisionDetails) -> None:
        self.reason = reason
        self.details = details
        super().__init__(blocked_message_with_policy(reason, details))


async def handle_socks5_tcp_policy(
    request: Socks5TcpRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> Socks5PolicyResult:
    host = normalize_host(_socks_request_host(request))
    port = _socks_request_port(request)
    client = _socks_request_client(request)
    if not host:
        raise ValueError("invalid host")

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", None, details)
        raise policy_denied_error(REASON_PROXY_DISABLED, details)

    mode = await _network_proxy_state_network_mode(state)
    if mode is NetworkMode.LIMITED:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", NetworkMode.LIMITED, details)
        raise policy_denied_error(REASON_METHOD_NOT_ALLOWED, details)

    if await state.host_has_mitm_hooks(host):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_MITM_REQUIRED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", NetworkMode.FULL, details)
        raise policy_denied_error(REASON_MITM_REQUIRED, details)

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.SOCKS5_TCP,
                host=host,
                port=port,
                client_addr=client,
                method=None,
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
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", None, details)
        raise policy_denied_error(decision.reason, details)

    return Socks5PolicyResult(protocol="socks5", host=host, port=port)


async def run_socks5_with_std_listener(
    state: NetworkProxyState,
    listener: socket.socket,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
    enable_socks5_udp: bool = False,
) -> None:
    listener.setblocking(False)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_socks5_tcp_client(
            reader,
            writer,
            state,
            decider,
            enable_socks5_udp,
        ),
        sock=listener,
    )
    async with server:
        await server.serve_forever()


async def run_socks5(
    state: NetworkProxyState,
    addr: tuple[str, int],
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
    enable_socks5_udp: bool = False,
) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(addr)
    listener.listen()
    await run_socks5_with_std_listener(state, listener, decider, enable_socks5_udp)


async def _handle_socks5_tcp_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
    enable_socks5_udp: bool,
) -> None:
    udp_transport: asyncio.DatagramTransport | None = None
    try:
        greeting = await client_reader.readexactly(2)
        version, method_count = greeting[0], greeting[1]
        methods = await client_reader.readexactly(method_count)
        if version != 5 or 0 not in methods:
            client_writer.write(b"\x05\xff")
            await client_writer.drain()
            return
        client_writer.write(b"\x05\x00")
        await client_writer.drain()

        req_head = await client_reader.readexactly(4)
        version, command, _reserved, atyp = req_head
        if version != 5:
            await _write_socks5_reply(client_writer, 7)
            return
        host = await _read_socks5_address(client_reader, atyp)
        port = int.from_bytes(await client_reader.readexactly(2), "big")
        if command == 3:
            if not enable_socks5_udp:
                await _write_socks5_reply(client_writer, 7)
                return
            udp_transport = await _start_socks5_udp_relay(client_writer, state, decider)
            sockname = udp_transport.get_extra_info("sockname")
            if not isinstance(sockname, tuple) or len(sockname) < 2:
                await _write_socks5_reply(client_writer, 1)
                return
            await _write_socks5_reply(client_writer, 0, bound_addr=(str(sockname[0]), int(sockname[1])))
            await client_reader.read()
            return
        if command != 1:
            await _write_socks5_reply(client_writer, 7)
            return
        client = _stream_peer_addr(client_writer)
        try:
            await handle_socks5_tcp_policy(Socks5TcpRequest(host, port, client), state, decider)
        except (Socks5PolicyError, ValueError):
            await _write_socks5_reply(client_writer, 2)
            return

        try:
            target_reader, target_writer = await asyncio.open_connection(host, port)
        except OSError:
            await _write_socks5_reply(client_writer, 5)
            return
        await _write_socks5_reply(client_writer, 0, target_writer)
        await _relay_streams(client_reader, client_writer, target_reader, target_writer)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
        return
    finally:
        if udp_transport is not None:
            udp_transport.close()
        if not client_writer.is_closing():
            await _close_stream_writer(client_writer)


async def _read_socks5_address(reader: asyncio.StreamReader, atyp: int) -> str:
    if atyp == 1:
        return str(ipaddress.IPv4Address(await reader.readexactly(4)))
    if atyp == 3:
        length = (await reader.readexactly(1))[0]
        return (await reader.readexactly(length)).decode("idna")
    if atyp == 4:
        return str(ipaddress.IPv6Address(await reader.readexactly(16)))
    raise ValueError("unsupported SOCKS5 address type")


async def _write_socks5_reply(
    writer: asyncio.StreamWriter,
    code: int,
    target_writer: asyncio.StreamWriter | None = None,
    bound_addr: tuple[str, int] | None = None,
) -> None:
    sockname = target_writer.get_extra_info("sockname") if target_writer is not None else None
    host = "0.0.0.0"
    port = 0
    if bound_addr is not None:
        host, port = bound_addr
    elif isinstance(sockname, tuple) and len(sockname) >= 2:
        host = str(sockname[0])
        port = int(sockname[1])
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = ipaddress.ip_address("0.0.0.0")
    if isinstance(address, ipaddress.IPv6Address):
        payload = b"\x05" + bytes([code]) + b"\x00\x04" + address.packed
    else:
        payload = b"\x05" + bytes([code]) + b"\x00\x01" + address.packed
    payload += int(port).to_bytes(2, "big")
    writer.write(payload)
    await writer.drain()


async def _start_socks5_udp_relay(
    client_writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    peer = client_writer.get_extra_info("peername")
    allowed_client = str(peer[0]) if isinstance(peer, tuple) and len(peer) >= 1 else None
    bind_host = "127.0.0.1"
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Socks5UdpRelayProtocol(state, decider, allowed_client),
        local_addr=(bind_host, 0),
    )
    return transport


class _Socks5UdpRelayProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        state: NetworkProxyState,
        decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
        allowed_client: str | None,
    ) -> None:
        self.state = state
        self.decider = decider
        self.allowed_client = allowed_client
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport if isinstance(transport, asyncio.DatagramTransport) else None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.allowed_client is not None and addr[0] != self.allowed_client:
            return
        asyncio.create_task(self._relay_datagram(data, addr))

    async def _relay_datagram(self, data: bytes, client_addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        try:
            host, port, payload = _parse_socks5_udp_packet(data)
            result = await inspect_socks5_udp_policy(
                Socks5UdpRequest(host, port, payload, f"{client_addr[0]}:{client_addr[1]}"),
                self.state,
                self.decider,
            )
            response = await _udp_round_trip(result.host, result.port, result.payload or b"")
        except (OSError, ValueError, Socks5PolicyError):
            return
        self.transport.sendto(_build_socks5_udp_packet(host, port, response), client_addr)


def _parse_socks5_udp_packet(data: bytes) -> tuple[str, int, bytes]:
    if len(data) < 4 or data[0:2] != b"\x00\x00" or data[2] != 0:
        raise ValueError("unsupported SOCKS5 UDP packet")
    atyp = data[3]
    index = 4
    if atyp == 1:
        if len(data) < index + 4 + 2:
            raise ValueError("truncated SOCKS5 IPv4 UDP packet")
        host = str(ipaddress.IPv4Address(data[index : index + 4]))
        index += 4
    elif atyp == 3:
        if len(data) < index + 1:
            raise ValueError("truncated SOCKS5 domain UDP packet")
        length = data[index]
        index += 1
        if len(data) < index + length + 2:
            raise ValueError("truncated SOCKS5 domain UDP packet")
        host = data[index : index + length].decode("idna")
        index += length
    elif atyp == 4:
        if len(data) < index + 16 + 2:
            raise ValueError("truncated SOCKS5 IPv6 UDP packet")
        host = str(ipaddress.IPv6Address(data[index : index + 16]))
        index += 16
    else:
        raise ValueError("unsupported SOCKS5 UDP address type")
    port = int.from_bytes(data[index : index + 2], "big")
    index += 2
    return host, port, data[index:]


def _build_socks5_udp_packet(host: str, port: int, payload: bytes) -> bytes:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        encoded = host.encode("idna")
        if len(encoded) > 255:
            raise ValueError("SOCKS5 domain address too long")
        return b"\x00\x00\x00\x03" + bytes([len(encoded)]) + encoded + int(port).to_bytes(2, "big") + payload
    if isinstance(address, ipaddress.IPv6Address):
        return b"\x00\x00\x00\x04" + address.packed + int(port).to_bytes(2, "big") + payload
    return b"\x00\x00\x00\x01" + address.packed + int(port).to_bytes(2, "big") + payload


async def _udp_round_trip(host: str, port: int, payload: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        await loop.sock_sendto(sock, payload, (host, port))
        response, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), timeout=5)
        return response
    finally:
        sock.close()


async def _relay_streams(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_reader: asyncio.StreamReader,
    target_writer: asyncio.StreamWriter,
) -> None:
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


async def inspect_socks5_udp_policy(
    request: Socks5UdpRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> Socks5PolicyResult:
    host = normalize_host(_socks_request_host(request))
    port = _socks_request_port(request)
    client = _socks_request_client(request)
    payload = _socks_udp_payload(request)
    if not host:
        raise ValueError("invalid host")

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", None, details)
        raise policy_denied_error(REASON_PROXY_DISABLED, details)

    mode = await _network_proxy_state_network_mode(state)
    if mode is NetworkMode.LIMITED:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", NetworkMode.LIMITED, details)
        raise policy_denied_error(REASON_METHOD_NOT_ALLOWED, details)

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.SOCKS5_UDP,
                host=host,
                port=port,
                client_addr=client,
                method=None,
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
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", None, details)
        raise policy_denied_error(decision.reason, details)

    return Socks5PolicyResult(protocol="socks5-udp", host=host, port=port, payload=payload)


def emit_socks_block_decision_audit_event(
    state: NetworkProxyState,
    source: NetworkDecisionSource | str,
    reason: str,
    protocol: NetworkProtocol | str,
    host: str,
    port: int,
    client_addr: str | None = None,
) -> None:
    emit_block_decision_audit_event(
        state,
        BlockDecisionAuditEventArgs(
            source=NetworkDecisionSource(source),
            reason=reason,
            protocol=NetworkProtocol(protocol),
            server_address=host,
            server_port=port,
            method=None,
            client_addr=client_addr,
        ),
    )


def policy_denied_error(reason: str, details: PolicyDecisionDetails) -> Socks5PolicyError:
    return Socks5PolicyError(reason, details)


async def _record_socks_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    protocol_name: str,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    emit_socks_block_decision_audit_event(
        state,
        details.source,
        details.reason,
        details.protocol,
        host,
        port,
        client,
    )
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method=None,
                mode=mode,
                protocol=protocol_name,
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


def _socks_request_host(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> str:
    if isinstance(request, Mapping):
        return str(request.get("host", ""))
    return str(getattr(request, "host", ""))


def _socks_request_port(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> int:
    if isinstance(request, Mapping):
        port = request.get("port", 0)
    else:
        port = getattr(request, "port", 0)
    return int(port)


def _socks_request_client(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> str | None:
    if isinstance(request, Mapping):
        client = request.get("client")
    else:
        client = getattr(request, "client", None)
    return str(client) if client is not None else None


def _socks_udp_payload(request: Socks5UdpRequest | Mapping[str, object] | object) -> bytes:
    if isinstance(request, Mapping):
        payload = request.get("payload", b"")
    else:
        payload = getattr(request, "payload", b"")
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode()
    return bytes(payload)

from .config import NetworkMode
from .http_proxy import (
    _close_stream_writer,
    _stream_peer_addr,
)
from .network_policy import (
    BlockDecisionAuditEventArgs,
    NetworkDecision,
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkPolicyRequest,
    NetworkPolicyRequestArgs,
    NetworkProtocol,
    emit_block_decision_audit_event,
    evaluate_host_policy,
)
from .policy import normalize_host
from .reasons import (
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_REQUIRED,
    REASON_PROXY_DISABLED,
)
from .responses import (
    PolicyDecisionDetails,
    blocked_message_with_policy,
)
from .runtime import (
    BlockedRequest,
    BlockedRequestArgs,
    NetworkProxyState,
    _network_proxy_state_enabled,
    _network_proxy_state_network_mode,
)

__all__ = [
    "Socks5PolicyError",
    "Socks5PolicyResult",
    "Socks5TcpRequest",
    "Socks5UdpRequest",
    "emit_socks_block_decision_audit_event",
    "handle_socks5_tcp_policy",
    "inspect_socks5_udp_policy",
    "policy_denied_error",
    "run_socks5",
    "run_socks5_with_std_listener",
]
