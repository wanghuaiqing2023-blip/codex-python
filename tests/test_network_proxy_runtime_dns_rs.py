import asyncio

from pycodex.network_proxy import (
    ConfigState,
    HostBlockDecision,
    HostBlockReason,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    StaticNetworkProxyReloader,
    host_resolves_to_non_public_ip,
)


def state_with_dns_lookup(lookup) -> NetworkProxyState:
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(["does-not-resolve.invalid", "public.example"])
    state = ConfigState(config, NetworkProxyConstraints())
    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=lookup,
        dns_lookup_timeout=0.01,
    )


def state_for_policy(
    allowed_domains=(),
    denied_domains=(),
    *,
    allow_local_binding: bool = False,
    lookup=None,
) -> NetworkProxyState:
    config = NetworkProxyConfig()
    config.network.set_allowed_domains(list(allowed_domains))
    config.network.set_denied_domains(list(denied_domains))
    config.network.allow_local_binding = allow_local_binding
    state = ConfigState(config, NetworkProxyConstraints())
    return NetworkProxyState(
        state,
        StaticNetworkProxyReloader(state),
        dns_lookup=lookup or public_lookup,
        dns_lookup_timeout=0.01,
    )


async def public_lookup(_host: str, _port: int):
    return [("8.8.8.8", 80)]


def test_host_blocked_denied_wins_over_allowed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_denied_wins_over_allowed
    # Contract: denylist entries are evaluated before allowlist entries for the same normalized host.
    state = state_for_policy(["example.com"], ["example.com"])

    assert asyncio.run(state.host_blocked("example.com", 80)) == HostBlockDecision.blocked(HostBlockReason.DENIED)


def test_host_blocked_requires_allowlist_match() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_requires_allowlist_match
    # Contract: allowed domains admit exact matches and reject unmatched public IP literals as not_allowed.
    state = state_for_policy(["example.com"])

    assert asyncio.run(state.host_blocked("example.com", 80)) == HostBlockDecision.allow()
    assert asyncio.run(state.host_blocked("8.8.8.8", 80)) == HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED)


def test_host_blocked_subdomain_wildcards_exclude_apex() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_subdomain_wildcards_exclude_apex
    # Contract: "*.openai.com" allowlists subdomains but not the apex host.
    state = state_for_policy(["*.openai.com"])

    assert asyncio.run(state.host_blocked("api.openai.com", 80)) == HostBlockDecision.allow()
    assert asyncio.run(state.host_blocked("openai.com", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED
    )


def test_host_blocked_global_wildcard_allowlist_allows_public_hosts_except_denylist() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_global_wildcard_allowlist_allows_public_hosts_except_denylist
    # Contract: "*" allowlists public hosts while denylist entries still win first.
    state = state_for_policy(["*"], ["evil.example"])

    assert asyncio.run(state.host_blocked("example.com", 80)) == HostBlockDecision.allow()
    assert asyncio.run(state.host_blocked("api.openai.com", 443)) == HostBlockDecision.allow()
    assert asyncio.run(state.host_blocked("evil.example", 80)) == HostBlockDecision.blocked(HostBlockReason.DENIED)


def test_host_blocked_rejects_loopback_when_local_binding_disabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_rejects_loopback_when_local_binding_disabled
    # Contract: loopback names/literals are blocked as local-risk unless explicitly allowlisted.
    state = state_for_policy(["example.com"])

    assert asyncio.run(state.host_blocked("127.0.0.1", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )
    assert asyncio.run(state.host_blocked("localhost", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )


def test_host_blocked_allows_loopback_when_explicitly_allowlisted_and_local_binding_disabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_allows_loopback_when_explicitly_allowlisted_and_local_binding_disabled
    # Contract: an exact local allowlist entry bypasses the local-binding guard for that host.
    state = state_for_policy(["localhost"])

    assert asyncio.run(state.host_blocked("localhost", 80)) == HostBlockDecision.allow()


def test_host_blocked_allows_private_ip_literal_when_explicitly_allowlisted() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_allows_private_ip_literal_when_explicitly_allowlisted
    # Contract: exact private IP allowlist entries bypass the local-binding guard for that literal.
    state = state_for_policy(["10.0.0.1"])

    assert asyncio.run(state.host_blocked("10.0.0.1", 80)) == HostBlockDecision.allow()


def test_host_blocked_scoped_ipv6_allowlist_and_denylist_are_exact() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust tests: host_blocked_requires_exact_scoped_ipv6_allowlist_match,
    # host_blocked_requires_exact_scoped_ipv6_denylist_match
    # Contract: scoped IPv6 allow/deny entries match only the exact normalized scope.
    allow_state = state_for_policy(["fe80::1%eth0"], allow_local_binding=True)
    deny_state = state_for_policy(["*"], ["fd00::1%eth0"], allow_local_binding=True)

    assert asyncio.run(allow_state.host_blocked("fe80::1%eth0", 80)) == HostBlockDecision.allow()
    assert asyncio.run(allow_state.host_blocked("fe80::1%eth1", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED
    )
    assert asyncio.run(deny_state.host_blocked("fd00::1%eth0", 80)) == HostBlockDecision.blocked(
        HostBlockReason.DENIED
    )
    assert asyncio.run(deny_state.host_blocked("fd00::1%eth1", 80)) == HostBlockDecision.allow()


def test_host_blocked_denies_unscoped_scoped_ipv6_before_local_binding() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_denies_scoped_ipv6_literal_before_local_binding
    # Contract: unscoped denylist literals block scoped IPv6 spellings before local-binding checks.
    state = state_for_policy(["*"], ["fd00::1"], allow_local_binding=True)

    for host in ("fd00::1%eth0", "[fd00::1%eth0]", "[fd00::1%25eth0]"):
        assert asyncio.run(state.host_blocked(host, 80)) == HostBlockDecision.blocked(HostBlockReason.DENIED)


def test_host_blocked_rejects_private_and_loopback_literals_when_not_allowlisted() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust tests: host_blocked_rejects_scoped_ipv6_literal_when_not_allowlisted,
    # host_blocked_rejects_private_ip_literals_when_local_binding_disabled,
    # host_blocked_rejects_loopback_when_allowlist_empty
    # Contract: local/private literals fail closed before ordinary allowlist matching.
    state = state_for_policy(["example.com"])
    empty_state = state_for_policy([])

    assert asyncio.run(state.host_blocked("fe80::1%lo0", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )
    assert asyncio.run(state.host_blocked("10.0.0.1", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )
    assert asyncio.run(empty_state.host_blocked("127.0.0.1", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )


def test_host_blocked_rejects_allowlisted_hostname_when_dns_lookup_fails() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_blocked_rejects_allowlisted_hostname_when_dns_lookup_fails
    # Contract: allowlisted hostnames are still blocked as local-risk when the DNS safety lookup fails.
    def lookup(_host: str, _port: int):
        raise OSError("forced failure")

    state = state_with_dns_lookup(lookup)

    assert asyncio.run(state.host_blocked("does-not-resolve.invalid", 80)) == HostBlockDecision.blocked(
        HostBlockReason.NOT_ALLOWED_LOCAL
    )


def test_host_resolves_to_non_public_ip_blocks_on_dns_lookup_timeout() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_resolves_to_non_public_ip_blocks_on_dns_lookup_timeout
    # Contract: DNS timeout during private-address safety lookup blocks fail-closed.
    async def lookup(_host: str, _port: int):
        await asyncio.sleep(1)
        return [("8.8.8.8", 80)]

    assert asyncio.run(host_resolves_to_non_public_ip("slow.example", 80, 0.001, lookup))


def test_host_resolves_to_non_public_ip_blocks_on_dns_lookup_error() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_resolves_to_non_public_ip_blocks_on_dns_lookup_error
    # Contract: DNS error during private-address safety lookup blocks fail-closed.
    async def lookup(_host: str, _port: int):
        raise TimeoutError("forced failure")

    assert asyncio.run(host_resolves_to_non_public_ip("error.example", 80, 0.01, lookup))


def test_host_resolves_to_non_public_ip_blocks_private_resolution() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_resolves_to_non_public_ip_blocks_private_resolution
    # Contract: any resolved private/local address blocks the host.
    async def lookup(_host: str, _port: int):
        return [("127.0.0.1", 80)]

    assert asyncio.run(host_resolves_to_non_public_ip("local.example", 80, 0.01, lookup))


def test_host_resolves_to_non_public_ip_allows_public_resolution() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: host_resolves_to_non_public_ip_allows_public_resolution
    # Contract: all-public DNS resolutions do not trigger the local/private-address block.
    async def lookup(_host: str, _port: int):
        return [("8.8.8.8", 80)]

    assert not asyncio.run(host_resolves_to_non_public_ip("public.example", 80, 0.01, lookup))


def test_host_blocked_allows_allowlisted_hostname_with_public_dns_resolution() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: NetworkProxyState::host_blocked, host_resolves_to_non_public_ip
    # Contract: an allowlisted hostname with only public DNS answers reaches the final allow branch.
    async def lookup(_host: str, _port: int):
        return [("8.8.8.8", 80)]

    state = state_with_dns_lookup(lookup)

    assert asyncio.run(state.host_blocked("public.example", 80)) == HostBlockDecision.allow()
