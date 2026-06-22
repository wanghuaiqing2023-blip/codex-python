from __future__ import annotations

import asyncio
import socket

import pytest

from pycodex.network_proxy import (
    AUDIT_TARGET,
    DEFAULT_CLIENT_ADDRESS,
    DEFAULT_METHOD,
    ConfigState,
    MitmHookConfig,
    MitmHookMatchConfig,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    POLICY_DECISION_EVENT_NAME,
    POLICY_SCOPE_NON_DOMAIN,
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_REQUIRED,
    REASON_PROXY_DISABLED,
    Socks5PolicyError,
    Socks5TcpRequest,
    Socks5UdpRequest,
    StaticNetworkProxyReloader,
    handle_socks5_tcp_policy,
    inspect_socks5_udp_policy,
    run_socks5_with_std_listener,
)


def network_proxy_state_for_policy(config: NetworkProxyConfig) -> NetworkProxyState:
    state = ConfigState(config, NetworkProxyConstraints())
    proxy_state = NetworkProxyState(state, StaticNetworkProxyReloader(state))
    object.__setattr__(proxy_state, "audit_events", [])
    return proxy_state


def policy_event(state: NetworkProxyState) -> dict[str, str]:
    events = getattr(state, "audit_events")
    matches = [event for event in events if event.get("event.name") == POLICY_DECISION_EVENT_NAME]
    assert len(matches) == 1
    return matches[0]


def test_handle_socks5_tcp_emits_block_decision_for_proxy_disabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/socks5.rs
    # Rust test: handle_socks5_tcp_emits_block_decision_for_proxy_disabled
    # Contract: disabled proxy denies SOCKS5 TCP before host policy and emits non-domain proxy_state audit fields.
    config = NetworkProxyConfig()
    config.network.enabled = False
    config.network.mode = NetworkMode.FULL
    state = network_proxy_state_for_policy(config)

    with pytest.raises(Socks5PolicyError) as exc_info:
        asyncio.run(handle_socks5_tcp_policy(Socks5TcpRequest("example.com", 443), state))

    assert exc_info.value.reason == REASON_PROXY_DISABLED
    blocked = asyncio.run(state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_PROXY_DISABLED
    assert blocked[0].host == "example.com"
    assert blocked[0].port == 443
    assert blocked[0].protocol == "socks5"
    assert blocked[0].decision == "deny"
    assert blocked[0].source == "proxy_state"

    event = policy_event(state)
    assert event["target"] == AUDIT_TARGET
    assert event["network.policy.scope"] == POLICY_SCOPE_NON_DOMAIN
    assert event["network.policy.decision"] == "deny"
    assert event["network.policy.source"] == "proxy_state"
    assert event["network.policy.reason"] == REASON_PROXY_DISABLED
    assert event["network.transport.protocol"] == "socks5_tcp"
    assert event["server.address"] == "example.com"
    assert event["server.port"] == "443"
    assert event["http.request.method"] == DEFAULT_METHOD
    assert event["client.address"] == DEFAULT_CLIENT_ADDRESS


def test_handle_socks5_tcp_blocks_hooked_host_in_full_mode() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/socks5.rs
    # Rust test: handle_socks5_tcp_blocks_hooked_host_in_full_mode
    # Contract: SOCKS5 TCP to a host with configured MITM hooks is blocked in full mode because SOCKS cannot enforce HTTPS hook policy.
    config = NetworkProxyConfig()
    config.network.enabled = True
    config.network.mode = NetworkMode.FULL
    config.network.mitm = True
    config.network.mitm_hooks = [
        MitmHookConfig(
            host="api.github.com",
            matcher=MitmHookMatchConfig(methods=["GET"], path_prefixes=["/"]),
        )
    ]
    config.network.set_allowed_domains(["api.github.com"])
    state = network_proxy_state_for_policy(config)

    with pytest.raises(Socks5PolicyError) as exc_info:
        asyncio.run(handle_socks5_tcp_policy(Socks5TcpRequest("api.github.com", 443), state))

    assert exc_info.value.reason == REASON_MITM_REQUIRED
    blocked = asyncio.run(state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_MITM_REQUIRED
    assert blocked[0].host == "api.github.com"
    assert blocked[0].port == 443
    assert blocked[0].protocol == "socks5"
    assert blocked[0].decision == "deny"
    assert blocked[0].source == "mode_guard"

    event = policy_event(state)
    assert event["network.policy.scope"] == POLICY_SCOPE_NON_DOMAIN
    assert event["network.policy.decision"] == "deny"
    assert event["network.policy.source"] == "mode_guard"
    assert event["network.policy.reason"] == REASON_MITM_REQUIRED
    assert event["network.transport.protocol"] == "socks5_tcp"
    assert event["server.address"] == "api.github.com"
    assert event["server.port"] == "443"
    assert event["http.request.method"] == DEFAULT_METHOD
    assert event["client.address"] == DEFAULT_CLIENT_ADDRESS


def test_inspect_socks5_udp_emits_block_decision_for_mode_guard_deny() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/socks5.rs
    # Rust test: inspect_socks5_udp_emits_block_decision_for_mode_guard_deny
    # Contract: limited mode denies SOCKS5 UDP before host policy and emits non-domain mode_guard audit fields.
    config = NetworkProxyConfig()
    config.network.enabled = True
    config.network.mode = NetworkMode.LIMITED
    state = network_proxy_state_for_policy(config)

    with pytest.raises(Socks5PolicyError) as exc_info:
        asyncio.run(inspect_socks5_udp_policy(Socks5UdpRequest("93.184.216.34", 53), state))

    assert exc_info.value.reason == REASON_METHOD_NOT_ALLOWED
    blocked = asyncio.run(state.drain_blocked())
    assert len(blocked) == 1
    assert blocked[0].reason == REASON_METHOD_NOT_ALLOWED
    assert blocked[0].host == "93.184.216.34"
    assert blocked[0].port == 53
    assert blocked[0].protocol == "socks5-udp"
    assert blocked[0].decision == "deny"
    assert blocked[0].source == "mode_guard"

    event = policy_event(state)
    assert event["network.policy.scope"] == POLICY_SCOPE_NON_DOMAIN
    assert event["network.policy.decision"] == "deny"
    assert event["network.policy.source"] == "mode_guard"
    assert event["network.policy.reason"] == REASON_METHOD_NOT_ALLOWED
    assert event["network.transport.protocol"] == "socks5_udp"
    assert event["server.address"] == "93.184.216.34"
    assert event["server.port"] == "53"
    assert event["http.request.method"] == DEFAULT_METHOD
    assert event["client.address"] == DEFAULT_CLIENT_ADDRESS


def test_run_socks5_with_std_listener_relays_allowed_tcp_connect() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/socks5.rs
    # Rust items: run_socks5_with_std_listener, handle_socks5_tcp, TargetCheckedTcpConnector
    # Contract: the live SOCKS5 listener accepts no-auth TCP CONNECT, applies the same TCP policy, connects the allowed target, and relays bytes.
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        target_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_listener.bind(("127.0.0.1", 0))
        target_listener.listen()
        target_listener.setblocking(False)
        target_host, target_port = target_listener.getsockname()

        socks_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socks_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socks_listener.bind(("127.0.0.1", 0))
        socks_listener.listen()
        socks_addr = socks_listener.getsockname()

        async def target_accept() -> None:
            conn, _ = await loop.sock_accept(target_listener)
            try:
                payload = await asyncio.wait_for(loop.sock_recv(conn, 1), timeout=2)
                assert payload == b"z"
                await loop.sock_sendall(conn, b"q")
            finally:
                conn.close()

        config = NetworkProxyConfig()
        config.network.enabled = True
        config.network.mode = NetworkMode.FULL
        config.network.allow_local_binding = True
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_policy(config)
        socks_task = asyncio.create_task(run_socks5_with_std_listener(state, socks_listener))
        target_task = asyncio.create_task(target_accept())
        try:
            reader, writer = await asyncio.open_connection(*socks_addr)
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(2), timeout=2) == b"\x05\x00"

            writer.write(
                b"\x05\x01\x00\x01"
                + socket.inet_aton(target_host)
                + int(target_port).to_bytes(2, "big")
            )
            await writer.drain()
            reply = await asyncio.wait_for(reader.readexactly(10), timeout=2)
            assert reply[:2] == b"\x05\x00"

            writer.write(b"z")
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(1), timeout=2) == b"q"
            await asyncio.wait_for(target_task, timeout=2)

            writer.close()
            await writer.wait_closed()
        finally:
            socks_task.cancel()
            try:
                await socks_task
            except asyncio.CancelledError:
                pass
            if not target_task.done():
                target_task.cancel()
            target_listener.close()

        assert await state.blocked_snapshot() == []

    asyncio.run(scenario())


def test_run_socks5_with_std_listener_relays_allowed_udp_associate() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/socks5.rs
    # Rust items: run_socks5_with_std_listener, DefaultUdpRelay, inspect_socks5_udp
    # Contract: when SOCKS5 UDP is enabled, UDP ASSOCIATE starts a relay, applies the same UDP inspection policy, forwards an allowed datagram, and returns the target payload in SOCKS5 UDP framing.
    def udp_packet(host: str, port: int, payload: bytes) -> bytes:
        return b"\x00\x00\x00\x01" + socket.inet_aton(host) + int(port).to_bytes(2, "big") + payload

    async def scenario() -> None:
        loop = asyncio.get_running_loop()

        target_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        target_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_sock.bind(("127.0.0.1", 0))
        target_sock.setblocking(False)
        target_host, target_port = target_sock.getsockname()

        socks_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socks_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        socks_listener.bind(("127.0.0.1", 0))
        socks_listener.listen()
        socks_addr = socks_listener.getsockname()

        async def target_echo() -> None:
            payload, addr = await asyncio.wait_for(loop.sock_recvfrom(target_sock, 1024), timeout=2)
            assert payload == b"u"
            await loop.sock_sendto(target_sock, b"v", addr)

        config = NetworkProxyConfig()
        config.network.enabled = True
        config.network.mode = NetworkMode.FULL
        config.network.allow_local_binding = True
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_policy(config)
        socks_task = asyncio.create_task(
            run_socks5_with_std_listener(state, socks_listener, enable_socks5_udp=True)
        )
        target_task = asyncio.create_task(target_echo())
        udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_client.bind(("127.0.0.1", 0))
        udp_client.setblocking(False)
        try:
            reader, writer = await asyncio.open_connection(*socks_addr)
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(2), timeout=2) == b"\x05\x00"

            writer.write(b"\x05\x03\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
            await writer.drain()
            reply = await asyncio.wait_for(reader.readexactly(10), timeout=2)
            assert reply[:4] == b"\x05\x00\x00\x01"
            relay_host = socket.inet_ntoa(reply[4:8])
            relay_port = int.from_bytes(reply[8:10], "big")

            await loop.sock_sendto(
                udp_client,
                udp_packet(target_host, target_port, b"u"),
                (relay_host, relay_port),
            )
            response, _ = await asyncio.wait_for(loop.sock_recvfrom(udp_client, 1024), timeout=2)
            assert response == udp_packet(target_host, target_port, b"v")
            await asyncio.wait_for(target_task, timeout=2)

            writer.close()
            await writer.wait_closed()
        finally:
            udp_client.close()
            target_sock.close()
            socks_task.cancel()
            try:
                await socks_task
            except asyncio.CancelledError:
                pass
            if not target_task.done():
                target_task.cancel()

        assert await state.blocked_snapshot() == []

    asyncio.run(scenario())
