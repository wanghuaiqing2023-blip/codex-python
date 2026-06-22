import pytest

from pycodex.network_proxy import (
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyNetworkConfig,
    host_and_port_from_network_addr,
    resolve_runtime,
)


def test_network_proxy_settings_default_matches_local_use_baseline() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: network_proxy_settings_default_matches_local_use_baseline
    # Contract: NetworkProxySettings::default local proxy baseline.
    settings = NetworkProxyNetworkConfig()

    assert settings.enabled is False
    assert settings.proxy_url == "http://127.0.0.1:3128"
    assert settings.enable_socks5 is True
    assert settings.socks_url == "http://127.0.0.1:8081"
    assert settings.enable_socks5_udp is True
    assert settings.allow_upstream_proxy is True
    assert settings.dangerously_allow_non_loopback_proxy is False
    assert settings.dangerously_allow_all_unix_sockets is False
    assert settings.mode is NetworkMode.FULL
    assert settings.allowed_domains() is None
    assert settings.denied_domains() is None
    assert settings.allow_unix_sockets_effective() == []
    assert settings.allow_local_binding is False
    assert settings.mitm is False
    assert settings.mitm_hooks == []


def test_partial_network_config_uses_struct_defaults_for_missing_fields() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: partial_network_config_uses_struct_defaults_for_missing_fields
    # Contract: serde defaults fill missing NetworkProxySettings fields.
    config = NetworkProxyConfig.from_mapping({"network": {"enabled": True}})

    assert config.network.enabled is True
    assert config.network.proxy_url == "http://127.0.0.1:3128"
    assert config.network.enable_socks5 is True
    assert config.network.socks_url == "http://127.0.0.1:8081"
    assert config.network.enable_socks5_udp is True
    assert config.network.allow_upstream_proxy is True
    assert config.network.mode is NetworkMode.FULL


def test_set_allowed_domains_preserves_existing_deny_for_same_pattern() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: set_allowed_domains_preserves_existing_deny_for_same_pattern
    # Contract: effective permission precedence is None < Allow < Deny.
    settings = NetworkProxyNetworkConfig()
    settings.set_denied_domains(["example.com"])

    settings.set_allowed_domains(["example.com"])

    assert settings.allowed_domains() is None
    assert settings.denied_domains() == ["example.com"]


def test_network_domain_permissions_serialize_to_effective_map_shape() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: network_domain_permissions_serialize_to_effective_map_shape
    # Contract: duplicate allow/deny entries serialize as one effective deny map entry.
    settings = NetworkProxyNetworkConfig()
    settings.set_denied_domains(["example.com"])
    settings.set_allowed_domains(["example.com"])
    config = NetworkProxyConfig(settings)

    assert config.to_mapping() == {
        "network": {
            "enabled": False,
            "proxy_url": "http://127.0.0.1:3128",
            "enable_socks5": True,
            "socks_url": "http://127.0.0.1:8081",
            "enable_socks5_udp": True,
            "allow_upstream_proxy": True,
            "dangerously_allow_non_loopback_proxy": False,
            "dangerously_allow_all_unix_sockets": False,
            "mode": "full",
            "domains": {"example.com": "deny"},
            "unix_sockets": None,
            "allow_local_binding": False,
            "mitm": False,
            "mitm_hooks": [],
        }
    }


@pytest.mark.parametrize(
    ("value", "default_port", "expected"),
    [
        ("", 1234, "<missing>"),
        ("127.0.0.1:8080", 3128, "127.0.0.1:8080"),
        ("http://example.com:8080/some/path", 3128, "example.com:8080"),
        ("http://user:pass@host.example:5555", 3128, "host.example:5555"),
        ("http://[::1]:8080", 3128, "[::1]:8080"),
        ("2001:db8::1", 3128, "[2001:db8::1]:3128"),
        ("example.com:notaport", 3128, "example.com:3128"),
    ],
)
def test_host_and_port_from_network_addr_matches_rust_parse_cases(
    value: str,
    default_port: int,
    expected: str,
) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust tests: parse_host_port_* and host_and_port_from_network_addr_*
    # Contract: network proxy address display accepts loose URL/host inputs.
    assert host_and_port_from_network_addr(value, default_port) == expected


def test_resolve_runtime_clamps_non_loopback_unless_dangerously_allowed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust tests: clamp_bind_addrs_allows_non_loopback_when_enabled and resolve_addr_*.
    # Contract: runtime bind addresses map hostnames to loopback and clamp non-loopback IPs by default.
    config = NetworkProxyConfig()
    config.network.proxy_url = "0.0.0.0:3128"
    config.network.socks_url = "http://example.com:5555"

    runtime = resolve_runtime(config)

    assert runtime.http_addr == "127.0.0.1:3128"
    assert runtime.socks_addr == "127.0.0.1:5555"

    config.network.dangerously_allow_non_loopback_proxy = True
    runtime = resolve_runtime(config)
    assert runtime.http_addr == "0.0.0.0:3128"


def test_resolve_runtime_forces_loopback_when_unix_sockets_enabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust tests: clamp_bind_addrs_forces_loopback_when_unix_sockets_enabled,
    # clamp_bind_addrs_forces_loopback_when_all_unix_sockets_enabled.
    # Contract: unix socket proxying makes externally reachable bind addresses local-only.
    config = NetworkProxyConfig()
    config.network.proxy_url = "0.0.0.0:3128"
    config.network.socks_url = "0.0.0.0:8081"
    config.network.dangerously_allow_non_loopback_proxy = True
    config.network.set_allow_unix_sockets(["/tmp/docker.sock"])

    runtime = resolve_runtime(config)

    assert runtime.http_addr == "127.0.0.1:3128"
    assert runtime.socks_addr == "127.0.0.1:8081"


def test_resolve_runtime_rejects_relative_allow_unix_sockets_entries() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: resolve_runtime_rejects_relative_allow_unix_sockets_entries
    # Contract: allow_unix_sockets entries must be absolute paths.
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets(["relative.sock"])

    with pytest.raises(ValueError, match=r"network\.allow_unix_sockets\[0\]"):
        resolve_runtime(config)


def test_resolve_runtime_accepts_unix_style_absolute_allow_unix_sockets_entries() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust test: resolve_runtime_accepts_unix_style_absolute_allow_unix_sockets_entries
    # Contract: Unix-style absolute paths are accepted even on non-Unix hosts.
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets(["/private/tmp/example.sock"])

    resolve_runtime(config)


def test_upsert_domain_permission_removes_normalized_opposite_entries() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/config.rs
    # Rust item: NetworkProxySettings::upsert_domain_permission
    # Contract: upsert normalizes comparison and keeps the newly selected permission.
    settings = NetworkProxyNetworkConfig()
    settings.upsert_domain_permission("EXAMPLE.com.", NetworkDomainPermission.DENY)
    settings.upsert_domain_permission("example.com", NetworkDomainPermission.ALLOW)

    assert settings.allowed_domains() == ["example.com"]
    assert settings.denied_domains() is None
