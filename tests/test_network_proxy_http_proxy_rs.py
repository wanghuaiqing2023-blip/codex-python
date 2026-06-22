import asyncio
import json
import socket

import pycodex.network_proxy as network_proxy
from pycodex.network_proxy import (
    ConfigState,
    HttpConnectRejected,
    HttpConnectRequest,
    HttpPlainRequest,
    MitmHookConfig,
    MitmHookMatchConfig,
    NetworkDecisionSource,
    NetworkMode,
    NetworkPolicyDecision,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    NetworkProtocol,
    PolicyDecisionDetails,
    REASON_DENIED,
    REASON_PROXY_DISABLED,
    StaticNetworkProxyReloader,
    http_connect_accept,
    http_plain_proxy,
    json_blocked,
    remove_hop_by_hop_request_headers,
    run_http_proxy_with_std_listener,
    validate_absolute_form_host_header,
)


async def public_dns_lookup(_host: str, _port: int):
    return [("8.8.8.8", 443)]


def network_proxy_state_for_policy(config: NetworkProxyConfig) -> NetworkProxyState:
    config.network.enabled = True
    state = ConfigState(config, NetworkProxyConstraints())
    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=public_dns_lookup,
        dns_lookup_timeout=0.01,
    )


def connect_request(host: str, port: int = 443) -> HttpConnectRequest:
    return HttpConnectRequest(
        uri=f"https://{host}:{port}",
        headers={"host": f"{host}:{port}"},
    )


def unix_socket_request(method: str = "GET", path: str = "/tmp/test.sock") -> HttpPlainRequest:
    return HttpPlainRequest(
        method=method,
        uri="http://example.com",
        headers={"x-unix-socket": path},
    )


def plain_request(
    method: str = "GET",
    uri: str = "http://example.com/",
    host: str | None = "example.com",
) -> HttpPlainRequest:
    headers = {"host": host} if host is not None else {}
    return HttpPlainRequest(method=method, uri=uri, headers=headers)


def disabled_network_proxy_state(config: NetworkProxyConfig) -> NetworkProxyState:
    config.network.enabled = False
    state = ConfigState(config, NetworkProxyConstraints())
    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=public_dns_lookup,
        dns_lookup_timeout=0.01,
    )


def test_http_plain_proxy_rejects_absolute_uri_host_header_mismatch() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_plain_proxy_rejects_absolute_uri_host_header_mismatch
    # Contract: plain HTTP absolute-form requests reject mismatched Host headers before policy checks.
    state = network_proxy_state_for_policy(NetworkProxyConfig())

    response = asyncio.run(
        http_plain_proxy(
            plain_request(
                uri="http://raw.githubusercontent.com/openai/codex/main/README.md",
                host="api.github.com",
            ),
            state,
        )
    )

    assert response.status == 400
    assert response.body == "Host header does not match request target"


def test_http_plain_proxy_disabled_records_blocked_request() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: http_plain_proxy -> proxy_disabled_response
    # Contract: disabled plain HTTP proxy returns 503 text and records a proxy_state deny event.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    state = disabled_network_proxy_state(config)

    response = asyncio.run(http_plain_proxy(plain_request(), state))

    assert response.status == 503
    assert response.body == "network proxy is disabled"
    blocked = asyncio.run(state.blocked_snapshot())
    assert [(entry.host, entry.reason, entry.method, entry.protocol, entry.port) for entry in blocked] == [
        ("example.com", REASON_PROXY_DISABLED, "GET", "http", 80)
    ]


def test_http_plain_proxy_denies_denylisted_host_with_json_blocked() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: http_plain_proxy host policy deny branch
    # Contract: host policy deny records a blocked HTTP request and returns JSON blocked with the policy header.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["**.openai.com"])
    config.network.set_denied_domains(["api.openai.com"])
    state = network_proxy_state_for_policy(config)

    response = asyncio.run(http_plain_proxy(plain_request(uri="http://api.openai.com/", host="api.openai.com"), state))

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-denylist"
    assert '"host":"api.openai.com"' in response.body
    assert '"protocol":"http"' in response.body
    blocked = asyncio.run(state.blocked_snapshot())
    assert [(entry.host, entry.reason, entry.method, entry.protocol, entry.port) for entry in blocked] == [
        ("api.openai.com", "denied", "GET", "http", 80)
    ]


def test_json_blocked_omits_policy_fields_when_details_absent() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: json_blocked + BlockedResponse skip_serializing_if fields
    # Contract: absent PolicyDecisionDetails omits optional policy fields instead of serializing nulls.
    response = json_blocked("unix-socket", "not_allowed", None)

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-allowlist"
    assert json.loads(response.body) == {
        "status": "blocked",
        "host": "unix-socket",
        "reason": "not_allowed",
    }


def test_json_blocked_includes_policy_fields_when_details_present() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: json_blocked + BlockedResponse optional policy fields
    # Contract: present PolicyDecisionDetails serializes decision/source/protocol/port/message.
    details = PolicyDecisionDetails(
        decision=NetworkPolicyDecision.DENY,
        reason=REASON_DENIED,
        source=NetworkDecisionSource.BASELINE_POLICY,
        protocol=NetworkProtocol.HTTP,
        host="api.openai.com",
        port=80,
    )

    response = json_blocked("api.openai.com", REASON_DENIED, details)

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-denylist"
    assert json.loads(response.body) == {
        "status": "blocked",
        "host": "api.openai.com",
        "reason": "denied",
        "decision": "deny",
        "source": "baseline_policy",
        "protocol": "http",
        "port": 80,
        "message": "Domain denied by the sandbox policy.",
    }


def test_http_plain_proxy_blocks_disallowed_method_after_host_policy_allows() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: http_plain_proxy method policy branch
    # Contract: limited-mode method policy is enforced after host allowlist evaluation for plain HTTP requests.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    state = network_proxy_state_for_policy(config)
    asyncio.run(state.set_network_mode(NetworkMode.LIMITED))

    response = asyncio.run(http_plain_proxy(plain_request(method="POST"), state))

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-method-policy"
    blocked = asyncio.run(state.blocked_snapshot())
    assert [(entry.host, entry.reason, entry.method, entry.mode, entry.protocol, entry.port) for entry in blocked] == [
        ("example.com", "method_not_allowed", "POST", NetworkMode.LIMITED, "http", 80)
    ]


def test_http_plain_proxy_allowed_request_maps_upstream_failure_to_bad_gateway(monkeypatch) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: http_plain_proxy upstream failure branch
    # Contract: once plain HTTP preflight allows a request, upstream service failure maps to 502 text.
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    closed.bind(("127.0.0.1", 0))
    _, port = closed.getsockname()
    closed.close()

    config = NetworkProxyConfig()
    config.network.allow_local_binding = True
    config.network.allow_upstream_proxy = False
    config.network.set_allowed_domains(["127.0.0.1"])
    state = network_proxy_state_for_policy(config)

    response = asyncio.run(
        http_plain_proxy(
            plain_request(uri=f"http://127.0.0.1:{port}/", host=f"127.0.0.1:{port}"),
            state,
        )
    )

    assert response.status == 502
    assert response.body == "upstream failure"
    assert asyncio.run(state.blocked_snapshot()) == []


def test_http_plain_proxy_forwards_allowed_direct_http_request(monkeypatch) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust items: http_plain_proxy, remove_hop_by_hop_request_headers, UpstreamClient::direct
    # Contract: after policy allows a plain HTTP request, hop-by-hop headers are stripped and the request is served through the direct upstream client.
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        target_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_listener.bind(("127.0.0.1", 0))
        target_listener.listen()
        target_listener.setblocking(False)
        target_host, target_port = target_listener.getsockname()

        async def target_accept() -> None:
            conn, _ = await loop.sock_accept(target_listener)
            try:
                request = await asyncio.wait_for(loop.sock_recv(conn, 4096), timeout=2)
                assert request.startswith(b"GET /alpha?x=1 HTTP/1.1\r\n"), request
                assert b"Host: 127.0.0.1:" in request
                assert b"Connection:" not in request
                assert b"Proxy-Authorization:" not in request
                assert b"X-Hop:" not in request
                assert b"X-Forwarded-For: 127.0.0.1\r\n" in request
                await loop.sock_sendall(
                    conn,
                    b"HTTP/1.1 201 Created\r\nContent-Type: text/plain\r\nContent-Length: 4\r\n\r\npong",
                )
            finally:
                conn.close()

        config = NetworkProxyConfig()
        config.network.allow_local_binding = True
        config.network.allow_upstream_proxy = False
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_policy(config)
        target_task = asyncio.create_task(target_accept())
        try:
            request = HttpPlainRequest(
                method="GET",
                uri=f"http://{target_host}:{target_port}/alpha?x=1",
                headers={
                    "Host": f"{target_host}:{target_port}",
                    "Connection": "X-Hop, keep-alive",
                    "X-Hop": "1",
                    "Proxy-Authorization": "Basic abc",
                    "X-Forwarded-For": "127.0.0.1",
                },
            )
            response = await http_plain_proxy(request, state)
            await asyncio.wait_for(target_task, timeout=2)
        finally:
            if not target_task.done():
                target_task.cancel()
            target_listener.close()

        assert response.status == 201
        assert response.headers["content-type"] == "text/plain"
        assert response.body == "pong"
        assert await state.blocked_snapshot() == []

    asyncio.run(scenario())


def test_http_plain_proxy_routes_allowed_request_via_upstream_proxy(monkeypatch) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs + src/upstream.rs
    # Rust items: http_plain_proxy, UpstreamClient::from_env_proxy, ProxyConfig::proxy_for_protocol
    # Contract: allowed insecure HTTP requests use HTTP_PROXY/ALL_PROXY when allow_upstream_proxy is true, preserving absolute-form request targets for the upstream proxy.
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        upstream_listener.bind(("127.0.0.1", 0))
        upstream_listener.listen()
        upstream_listener.setblocking(False)
        upstream_host, upstream_port = upstream_listener.getsockname()
        monkeypatch.setenv("HTTP_PROXY", f"http://{upstream_host}:{upstream_port}")

        async def upstream_accept() -> None:
            conn, _ = await loop.sock_accept(upstream_listener)
            try:
                request = await asyncio.wait_for(loop.sock_recv(conn, 4096), timeout=2)
                assert request.startswith(b"GET http://example.com/proxy-path HTTP/1.1\r\n"), request
                assert b"host: example.com\r\n" in request.lower()
                await loop.sock_sendall(
                    conn,
                    b"HTTP/1.1 202 Accepted\r\nContent-Length: 7\r\nX-Upstream: proxy\r\n\r\nproxied",
                )
            finally:
                conn.close()

        config = NetworkProxyConfig()
        config.network.allow_upstream_proxy = True
        config.network.set_allowed_domains(["example.com"])
        state = network_proxy_state_for_policy(config)
        upstream_task = asyncio.create_task(upstream_accept())
        try:
            response = await http_plain_proxy(
                plain_request(uri="http://example.com/proxy-path", host="example.com"),
                state,
            )
            await asyncio.wait_for(upstream_task, timeout=2)
        finally:
            if not upstream_task.done():
                upstream_task.cancel()
            upstream_listener.close()

        assert response.status == 202
        assert response.headers["x-upstream"] == "proxy"
        assert response.body == "proxied"
        assert await state.blocked_snapshot() == []

    asyncio.run(scenario())


def test_http_plain_proxy_blocks_unix_socket_when_method_not_allowed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_plain_proxy_blocks_unix_socket_when_method_not_allowed
    # Contract: limited-mode method policy blocks unsafe unix-socket HTTP methods before platform checks.
    state = network_proxy_state_for_policy(NetworkProxyConfig())
    asyncio.run(state.set_network_mode(NetworkMode.LIMITED))

    response = asyncio.run(http_plain_proxy(unix_socket_request("POST"), state))

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-method-policy"


def test_http_plain_proxy_rejects_unix_socket_when_not_allowlisted_on_supported_platform(monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_plain_proxy_rejects_unix_socket_when_not_allowlisted
    # Contract: on unix-socket-capable platforms, unallowlisted socket paths are blocked by allowlist policy.
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: True)
    state = network_proxy_state_for_policy(NetworkProxyConfig())

    response = asyncio.run(http_plain_proxy(unix_socket_request(), state))

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-allowlist"


def test_http_plain_proxy_rejects_unix_socket_when_platform_unsupported(monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_plain_proxy_rejects_unix_socket_when_not_allowlisted
    # Contract: non-macOS platforms reject unix-socket proxying before allowlist inspection with NOT_IMPLEMENTED.
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: False)
    state = network_proxy_state_for_policy(NetworkProxyConfig())

    response = asyncio.run(http_plain_proxy(unix_socket_request(), state))

    assert response.status == 501
    assert response.body == "unix sockets unsupported"


def test_http_plain_proxy_attempts_allowed_unix_socket_proxy(monkeypatch, tmp_path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_plain_proxy_attempts_allowed_unix_socket_proxy
    # Contract: supported and allowlisted unix-socket requests pass policy and map failed upstream proxying to BAD_GATEWAY.
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: True)
    socket_path = str(tmp_path / "test.sock")
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets([socket_path])
    state = network_proxy_state_for_policy(config)

    response = asyncio.run(http_plain_proxy(unix_socket_request(path=socket_path), state))

    assert response.status == 502
    assert response.body == "unix socket proxy failed"


def test_http_connect_accept_blocks_in_limited_mode() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_connect_accept_blocks_in_limited_mode
    # Contract: limited mode requires MITM for CONNECT and blocks when MITM state is absent.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["example.com"])
    state = network_proxy_state_for_policy(config)
    asyncio.run(state.set_network_mode(NetworkMode.LIMITED))

    try:
        asyncio.run(http_connect_accept(connect_request("example.com"), state))
    except HttpConnectRejected as exc:
        response = exc.response
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("CONNECT should be rejected")

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-mitm-required"
    blocked = asyncio.run(state.blocked_snapshot())
    assert [(entry.host, entry.reason, entry.method, entry.protocol, entry.mode) for entry in blocked] == [
        ("example.com", "mitm_required", "CONNECT", "http-connect", NetworkMode.LIMITED)
    ]


def test_http_connect_accept_allows_allowlisted_host_in_full_mode() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_connect_accept_allows_allowlisted_host_in_full_mode
    # Contract: allowlisted CONNECT hosts are accepted in full mode when MITM is not required.
    config = NetworkProxyConfig()
    config.network.allow_local_binding = True
    config.network.set_allowed_domains(["example.com"])
    state = network_proxy_state_for_policy(config)

    result = asyncio.run(http_connect_accept(connect_request("example.com"), state))

    assert result.response.status == 200
    assert result.accepted.host == "example.com"
    assert result.accepted.port == 443
    assert result.accepted.mitm_enabled is False
    assert asyncio.run(state.blocked_snapshot()) == []


def test_http_connect_accept_blocks_hooked_host_in_full_mode_without_mitm_state() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_connect_accept_blocks_hooked_host_in_full_mode_without_mitm_state
    # Contract: host-specific MITM hooks make CONNECT require MITM even in full mode.
    config = NetworkProxyConfig()
    config.network.mitm = True
    config.network.mitm_hooks = [
        MitmHookConfig(
            host="api.github.com",
            matcher=MitmHookMatchConfig(
                methods=["POST"],
                path_prefixes=["/repos/openai/"],
            ),
        )
    ]
    config.network.set_allowed_domains(["api.github.com"])
    state = network_proxy_state_for_policy(config)

    try:
        asyncio.run(http_connect_accept(connect_request("api.github.com"), state))
    except HttpConnectRejected as exc:
        response = exc.response
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("CONNECT should be rejected")

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-mitm-required"


def test_http_connect_accept_denies_denylisted_host() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_connect_accept_denies_denylisted_host
    # Contract: denylist wins over wildcard allowlist and returns the denylist blocked header.
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["**.openai.com"])
    config.network.set_denied_domains(["api.openai.com"])
    state = network_proxy_state_for_policy(config)

    try:
        asyncio.run(http_connect_accept(connect_request("api.openai.com"), state))
    except HttpConnectRejected as exc:
        response = exc.response
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("CONNECT should be rejected")

    assert response.status == 403
    assert response.headers["x-proxy-error"] == "blocked-by-denylist"


def test_http_proxy_listener_accepts_plain_http1_connect_requests(monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: http_proxy_listener_accepts_plain_http1_connect_requests
    # Contract: the live HTTP/1 proxy listener accepts a raw CONNECT request,
    # returns HTTP/1.1 200 OK after the same CONNECT accept policy, then forwards
    # client bytes to the target TCP stream like forward_connect_tunnel.
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        target_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        target_listener.bind(("127.0.0.1", 0))
        target_listener.listen()
        target_listener.setblocking(False)
        target_host, target_port = target_listener.getsockname()
        target_accept = asyncio.create_task(loop.sock_accept(target_listener))

        proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_listener.bind(("127.0.0.1", 0))
        proxy_listener.listen()
        proxy_addr = proxy_listener.getsockname()

        config = NetworkProxyConfig()
        config.network.allow_local_binding = True
        config.network.allow_upstream_proxy = False
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_policy(config)
        proxy_task = asyncio.create_task(run_http_proxy_with_std_listener(state, proxy_listener))
        try:
            reader, writer = await asyncio.open_connection(*proxy_addr)
            request = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n"
                "\r\n"
            )
            writer.write(request.encode("ascii"))
            await writer.drain()

            response = await asyncio.wait_for(reader.read(256), timeout=2)
            assert response.startswith(b"HTTP/1.1 200 OK\r\n"), response

            writer.write(b"x")
            await writer.drain()
            target_conn, _ = await asyncio.wait_for(target_accept, timeout=2)
            try:
                payload = await asyncio.wait_for(loop.sock_recv(target_conn, 1), timeout=2)
                assert payload == b"x"
            finally:
                target_conn.close()

            writer.close()
            await writer.wait_closed()
        finally:
            target_accept.cancel()
            proxy_task.cancel()
            try:
                await proxy_task
            except asyncio.CancelledError:
                pass
            target_listener.close()

    asyncio.run(scenario())


def test_http_proxy_listener_routes_connect_via_upstream_proxy_env(monkeypatch) -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs + src/upstream.rs
    # Rust items: http_connect_proxy, forward_connect_tunnel, proxy_for_connect
    # Contract: when allow_upstream_proxy is true and proxy_for_connect selects an
    # HTTP env proxy, CONNECT is routed through that upstream proxy before stream
    # forwarding begins.
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        upstream_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        upstream_listener.bind(("127.0.0.1", 0))
        upstream_listener.listen()
        upstream_listener.setblocking(False)
        upstream_host, upstream_port = upstream_listener.getsockname()
        monkeypatch.setenv("HTTPS_PROXY", f"http://{upstream_host}:{upstream_port}")

        proxy_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        proxy_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy_listener.bind(("127.0.0.1", 0))
        proxy_listener.listen()
        proxy_addr = proxy_listener.getsockname()

        target_host = "127.0.0.1"
        target_port = 443

        async def upstream_accept() -> None:
            upstream_conn, _ = await loop.sock_accept(upstream_listener)
            try:
                request = await asyncio.wait_for(loop.sock_recv(upstream_conn, 4096), timeout=2)
                authority = f"{target_host}:{target_port}".encode("ascii")
                assert request.startswith(b"CONNECT " + authority + b" HTTP/1.1\r\n"), request
                assert b"Host: " + authority + b"\r\n" in request
                await loop.sock_sendall(upstream_conn, b"HTTP/1.1 200 OK\r\n\r\n")
                payload = await asyncio.wait_for(loop.sock_recv(upstream_conn, 1), timeout=2)
                assert payload == b"y"
            finally:
                upstream_conn.close()

        config = NetworkProxyConfig()
        config.network.allow_local_binding = True
        config.network.allow_upstream_proxy = True
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_policy(config)
        proxy_task = asyncio.create_task(run_http_proxy_with_std_listener(state, proxy_listener))
        upstream_task = asyncio.create_task(upstream_accept())
        try:
            reader, writer = await asyncio.open_connection(*proxy_addr)
            request = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n"
                "\r\n"
            )
            writer.write(request.encode("ascii"))
            await writer.drain()

            response = await asyncio.wait_for(reader.read(256), timeout=2)
            assert response.startswith(b"HTTP/1.1 200 OK\r\n"), response

            writer.write(b"y")
            await writer.drain()
            await asyncio.wait_for(upstream_task, timeout=2)

            writer.close()
            await writer.wait_closed()
        finally:
            proxy_task.cancel()
            try:
                await proxy_task
            except asyncio.CancelledError:
                pass
            if not upstream_task.done():
                upstream_task.cancel()
            upstream_listener.close()

    asyncio.run(scenario())


def test_validate_absolute_form_host_header_allows_matching_default_port() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: validate_absolute_form_host_header_allows_matching_default_port
    # Contract: absolute-form HTTP requests may omit the default port from Host.
    assert validate_absolute_form_host_header(
        "http://example.com/",
        {"host": "example.com"},
    ) is None


def test_validate_absolute_form_host_header_rejects_mismatched_host() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: validate_absolute_form_host_header_rejects_mismatched_host
    # Contract: absolute-form request target host must match Host header.
    assert validate_absolute_form_host_header(
        "http://raw.githubusercontent.com/",
        {"host": "api.github.com"},
    ) == "Host header does not match request target"


def test_validate_absolute_form_host_header_rejects_missing_non_default_port() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: validate_absolute_form_host_header_rejects_missing_non_default_port
    # Contract: non-default target ports must be present and equal in Host.
    assert validate_absolute_form_host_header(
        "http://example.com:8080/",
        {"host": "example.com"},
    ) == "Host header does not match request target"


def test_validate_absolute_form_host_header_allows_origin_form_or_missing_host() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: validate_absolute_form_host_header
    # Contract: origin-form requests and absolute-form requests without Host are accepted.
    assert validate_absolute_form_host_header("/v1/models", {"host": "api.openai.com"}) is None
    assert validate_absolute_form_host_header("http://example.com/", {}) is None


def test_validate_absolute_form_host_header_reports_invalid_host_header() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: validate_absolute_form_host_header
    # Contract: invalid typed Host parsing maps to the stable invalid Host header reason.
    assert validate_absolute_form_host_header(
        "http://example.com/",
        {"host": "example.com:not-a-port"},
    ) == "invalid Host header"


def test_remove_hop_by_hop_request_headers_keeps_forwarding_headers() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust test: remove_hop_by_hop_request_headers_keeps_forwarding_headers
    # Contract: Connection-listed and standard hop-by-hop headers are removed, forwarding headers remain.
    headers: dict[str, object] = {
        "connection": "x-hop, keep-alive",
        "x-hop": "1",
        "proxy-authorization": "Basic abc",
        "x-forwarded-for": "127.0.0.1",
        "host": "example.com",
    }

    remove_hop_by_hop_request_headers(headers)

    assert "connection" not in headers
    assert "x-hop" not in headers
    assert "proxy-authorization" not in headers
    assert headers["x-forwarded-for"] == "127.0.0.1"
    assert headers["host"] == "example.com"


def test_remove_hop_by_hop_request_headers_removes_te_and_connection_tokens_case_insensitively() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/http_proxy.rs
    # Rust item: remove_hop_by_hop_request_headers
    # Contract: header names from Connection and the explicit TE hop-by-hop header are removed case-insensitively.
    headers: dict[str, object] = {
        "Connection": "X-Hop",
        "X-Hop": "1",
        "TE": "trailers",
        "Host": "example.com",
    }

    remove_hop_by_hop_request_headers(headers)

    assert headers == {"Host": "example.com"}
