import asyncio
import socket

import pytest

from pycodex.network_proxy import (
    ConfigState,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyNetworkConfig,
    NetworkProxyState,
    StaticNetworkProxyReloader,
    TargetCheckedTcpConnector,
    TargetRejectedError,
)


def state_for_allow_local_binding(allow_local_binding: bool) -> NetworkProxyState:
    config = NetworkProxyConfig(
        network=NetworkProxyNetworkConfig(allow_local_binding=allow_local_binding)
    )
    state = ConfigState(config=config, constraints=NetworkProxyConstraints())
    return NetworkProxyState(state=state, reloader=StaticNetworkProxyReloader(state))


def test_direct_connector_rejects_non_public_target_when_local_binding_disabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/connect_policy.rs
    # Rust test: direct_connector_rejects_non_public_target_when_local_binding_disabled
    # Contract: direct TCP targets are rejected before connect when allow_local_binding is false and the target IP is non-public.
    connector = TargetCheckedTcpConnector.new(state_for_allow_local_binding(False))

    with pytest.raises(TargetRejectedError, match="network target rejected by policy"):
        asyncio.run(connector.check_target("127.0.0.1", 9))


def test_direct_connector_allows_non_public_target_when_local_binding_enabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/connect_policy.rs
    # Rust test: direct_connector_allows_non_public_target_when_local_binding_enabled
    # Contract: enabling allow_local_binding permits a real direct localhost TCP connect.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(2)
    host, port = listener.getsockname()
    connector = TargetCheckedTcpConnector.new(state_for_allow_local_binding(True))

    client = asyncio.run(connector.connect(host, port, timeout=2))
    try:
        accepted, _addr = listener.accept()
        accepted.close()
    finally:
        client.close()
        listener.close()


def test_proxy_address_bypasses_direct_target_policy_projection() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/connect_policy.rs
    # Rust item: TargetCheckedTcpConnector::serve
    # Contract: Rama inputs carrying ProxyAddress use the plain TcpConnector path and do not apply the direct target check.
    connector = TargetCheckedTcpConnector.from_allow_local_binding(False)

    asyncio.run(connector.check_target("127.0.0.1", 9, proxy_address=object()))
