import asyncio

import pytest

from pycodex.network_proxy import (
    ConfigState,
    HostBlockDecision,
    HostBlockReason,
    NetworkMode,
    NetworkProxy,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    StaticNetworkProxyReloader,
)


async def public_dns_lookup(_host: str, port: int):
    return [("8.8.8.8", port)]


def network_settings(allowed_domains: list[str], denied_domains: list[str]) -> NetworkProxyConfig:
    config = NetworkProxyConfig()
    config.network.mode = NetworkMode.FULL
    config.network.set_allowed_domains(allowed_domains)
    config.network.set_denied_domains(denied_domains)
    return config


def network_proxy_state_for_config(
    config: NetworkProxyConfig,
    constraints: NetworkProxyConstraints | None = None,
) -> NetworkProxyState:
    state = ConfigState(config, constraints or NetworkProxyConstraints())
    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=public_dns_lookup,
        dns_lookup_timeout=0.01,
    )


def test_add_allowed_domain_removes_matching_deny_entry() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_allowed_domain_removes_matching_deny_entry
    # Contract: adding an allow entry normalizes host casing and removes a matching deny entry.
    state = network_proxy_state_for_config(network_settings([], ["example.com"]))

    asyncio.run(state.add_allowed_domain("ExAmPlE.CoM"))

    allowed, denied = asyncio.run(state.current_patterns())
    assert allowed == ["example.com"]
    assert denied == []
    assert asyncio.run(state.host_blocked("example.com", 80)) == HostBlockDecision.allow()


def test_add_denied_domain_removes_matching_allow_entry() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_denied_domain_removes_matching_allow_entry
    # Contract: adding a deny entry normalizes host casing and removes a matching allow entry.
    state = network_proxy_state_for_config(network_settings(["example.com"], []))

    asyncio.run(state.add_denied_domain("EXAMPLE.COM"))

    allowed, denied = asyncio.run(state.current_patterns())
    assert allowed == []
    assert denied == ["example.com"]
    assert asyncio.run(state.host_blocked("example.com", 80)) == HostBlockDecision.blocked(HostBlockReason.DENIED)


def test_add_denied_domain_forces_block_with_global_wildcard_allowlist() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_denied_domain_forces_block_with_global_wildcard_allowlist
    # Contract: an explicit deny entry wins even when the allowlist contains the global wildcard.
    state = network_proxy_state_for_config(network_settings(["*"], []))

    assert asyncio.run(state.host_blocked("8.8.8.8", 80)) == HostBlockDecision.allow()

    asyncio.run(state.add_denied_domain("8.8.8.8"))

    allowed, denied = asyncio.run(state.current_patterns())
    assert allowed == ["*"]
    assert denied == ["8.8.8.8"]
    assert asyncio.run(state.host_blocked("8.8.8.8", 80)) == HostBlockDecision.blocked(HostBlockReason.DENIED)


def test_add_allowed_domain_succeeds_when_managed_baseline_allows_expansion() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_allowed_domain_succeeds_when_managed_baseline_allows_expansion
    # Contract: managed allowlist constraints may opt into user expansion while preserving baseline entries.
    config = network_settings(["managed.example.com"], [])
    config.network.enabled = True
    constraints = NetworkProxyConstraints(
        allowed_domains=["managed.example.com"],
        allowlist_expansion_enabled=True,
    )
    state = network_proxy_state_for_config(config, constraints)

    asyncio.run(state.add_allowed_domain("user.example.com"))

    allowed, denied = asyncio.run(state.current_patterns())
    assert allowed == ["managed.example.com", "user.example.com"]
    assert denied == []


def test_add_allowed_domain_rejects_expansion_when_managed_baseline_is_fixed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_allowed_domain_rejects_expansion_when_managed_baseline_is_fixed
    # Contract: fixed managed allowlist constraints reject widening additions.
    config = network_settings(["managed.example.com"], [])
    config.network.enabled = True
    constraints = NetworkProxyConstraints(
        allowed_domains=["managed.example.com"],
        allowlist_expansion_enabled=False,
    )
    state = network_proxy_state_for_config(config, constraints)

    with pytest.raises(ValueError, match="network.allowed_domains constrained by managed config"):
        asyncio.run(state.add_allowed_domain("user.example.com"))


def test_add_denied_domain_rejects_expansion_when_managed_baseline_is_fixed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: add_denied_domain_rejects_expansion_when_managed_baseline_is_fixed
    # Contract: fixed managed denylist constraints reject widening additions.
    config = network_settings([], ["managed.example.com"])
    config.network.enabled = True
    constraints = NetworkProxyConstraints(
        denied_domains=["managed.example.com"],
        denylist_expansion_enabled=False,
    )
    state = network_proxy_state_for_config(config, constraints)

    with pytest.raises(ValueError, match="network.denied_domains constrained by managed config"):
        asyncio.run(state.add_denied_domain("user.example.com"))


def test_network_proxy_add_allowed_domain_forwards_to_state() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust modules: src/proxy.rs, src/runtime.rs
    # Rust items: NetworkProxy::add_allowed_domain, NetworkProxyState::add_allowed_domain
    # Contract: the public proxy facade forwards domain mutations to its runtime state.
    config = network_settings([], ["example.com"])
    state = network_proxy_state_for_config(config)
    proxy = asyncio.run(NetworkProxy.builder().state(state).managed_by_codex(False).build())

    asyncio.run(proxy.add_allowed_domain("EXAMPLE.com"))

    assert asyncio.run(proxy.current_cfg()).network.allowed_domains() == ["example.com"]
    assert asyncio.run(proxy.current_cfg()).network.denied_domains() is None
