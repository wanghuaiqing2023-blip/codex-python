import asyncio

from pycodex.network_proxy import (
    ConfigState,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyNetworkConfig,
    NetworkProxyState,
    ProxyAddress,
    ProxyConfig,
    StaticNetworkProxyReloader,
    UpstreamClient,
    proxy_for_connect,
    read_proxy_env,
)


def state_for_allow_local_binding(allow_local_binding: bool = False) -> NetworkProxyState:
    config = NetworkProxyConfig(
        network=NetworkProxyNetworkConfig(allow_local_binding=allow_local_binding)
    )
    state = ConfigState(config=config, constraints=NetworkProxyConstraints())
    return NetworkProxyState(state=state, reloader=StaticNetworkProxyReloader(state))


def test_read_proxy_env_uses_first_non_empty_valid_http_proxy() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: read_proxy_env
    # Contract: proxy env lookup walks keys in order, trims values, skips empties and invalid entries, and returns the first HTTP proxy.
    env = {
        "HTTP_PROXY": "   ",
        "http_proxy": " http://proxy.local:8080 ",
        "ALL_PROXY": "http://fallback.local:8080",
    }

    proxy = read_proxy_env(("HTTP_PROXY", "http_proxy"), env)

    assert proxy == ProxyAddress(
        address="http://proxy.local:8080",
        protocol="http",
        host="proxy.local",
        port=8080,
    )


def test_read_proxy_env_ignores_non_http_and_invalid_proxy_values() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: read_proxy_env
    # Contract: non-http protocols and unparsable proxy addresses are ignored instead of selected.
    env = {
        "HTTPS_PROXY": "socks5://proxy.local:1080",
        "https_proxy": "http://secure-proxy.local:8080",
        "ALL_PROXY": "://bad",
    }

    assert read_proxy_env(("ALL_PROXY",), env) is None
    assert read_proxy_env(("HTTPS_PROXY", "https_proxy"), env) == ProxyAddress(
        address="http://secure-proxy.local:8080",
        protocol="http",
        host="secure-proxy.local",
        port=8080,
    )


def test_proxy_config_protocol_selection_matches_rust_priority() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: ProxyConfig::proxy_for_protocol
    # Contract: secure requests prefer HTTPS, then HTTP, then ALL; insecure requests prefer HTTP, then ALL and never use HTTPS alone.
    http = ProxyAddress.try_from("http://http-proxy:8080")
    https = ProxyAddress.try_from("http://https-proxy:8080")
    all_proxy = ProxyAddress.try_from("http://all-proxy:8080")

    config = ProxyConfig(http=http, https=https, all=all_proxy)

    assert config.proxy_for_protocol(True) is https
    assert config.proxy_for_protocol(False) is http
    assert ProxyConfig(https=https, all=all_proxy).proxy_for_protocol(True) is https
    assert ProxyConfig(https=https, all=all_proxy).proxy_for_protocol(False) is all_proxy
    assert ProxyConfig(http=http, all=all_proxy).proxy_for_protocol(True) is http
    assert ProxyConfig(all=all_proxy).proxy_for_protocol(True) is all_proxy


def test_proxy_for_connect_uses_secure_proxy_selection_from_env() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: proxy_for_connect
    # Contract: CONNECT proxy selection uses secure protocol priority.
    env = {
        "HTTP_PROXY": "http://http-proxy:8080",
        "HTTPS_PROXY": "http://https-proxy:8080",
        "ALL_PROXY": "http://all-proxy:8080",
    }

    assert proxy_for_connect(env) == ProxyAddress.try_from("http://https-proxy:8080")


def test_upstream_client_constructors_capture_proxy_config_and_target_policy() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust items: UpstreamClient::{direct,from_env_proxy,direct_with_allow_local_binding,from_env_proxy_with_allow_local_binding}
    # Contract: direct constructors use empty proxy config; env constructors use ProxyConfig::from_env; allow-local-binding constructors carry config policy into the target checked transport.
    state = state_for_allow_local_binding(True)
    env = {"HTTP_PROXY": "http://http-proxy:8080"}

    direct = UpstreamClient.direct(state)
    from_env = UpstreamClient.from_env_proxy(state, env)
    direct_config = UpstreamClient.direct_with_allow_local_binding(True)
    env_config = UpstreamClient.from_env_proxy_with_allow_local_binding(False, env)

    assert direct.proxy_config == ProxyConfig()
    assert from_env.proxy_config.http == ProxyAddress.try_from("http://http-proxy:8080")
    assert asyncio.run(direct.transport.allow_local_binding()) is True  # type: ignore[union-attr]
    assert asyncio.run(direct_config.transport.allow_local_binding()) is True  # type: ignore[union-attr]
    assert asyncio.run(env_config.transport.allow_local_binding()) is False  # type: ignore[union-attr]


def test_upstream_client_select_route_projects_rust_proxy_insertion_decision() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: UpstreamClient::serve
    # Contract: before serving, secure requests select a proxy with ProxyConfig priority and direct requests keep route=direct.
    env_client = UpstreamClient.from_env_proxy_with_allow_local_binding(
        True,
        {
            "HTTP_PROXY": "http://http-proxy:8080",
            "HTTPS_PROXY": "http://https-proxy:8080",
        },
    )
    direct_client = UpstreamClient.direct_with_allow_local_binding(True)

    secure_route = env_client.select_route("https://example.com/v1")
    insecure_route = env_client.select_route("http://example.com/v1")
    direct_route = direct_client.select_route("https://example.com/v1")

    assert secure_route.authority == "example.com"
    assert secure_route.route == "upstream_proxy"
    assert secure_route.proxy == ProxyAddress.try_from("http://https-proxy:8080")
    assert insecure_route.proxy == ProxyAddress.try_from("http://http-proxy:8080")
    assert direct_route.route == "direct"
    assert direct_route.proxy is None


def test_upstream_client_unix_socket_constructor_uses_direct_proxy_config() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/upstream.rs
    # Rust item: UpstreamClient::unix_socket
    # Contract: macOS unix-socket upstream clients use a fixed unix connector and no env proxy config.
    client = UpstreamClient.unix_socket("/tmp/proxy.sock")

    assert client.unix_socket_path == "/tmp/proxy.sock"
    assert client.proxy_config == ProxyConfig()
    assert client.transport is None
