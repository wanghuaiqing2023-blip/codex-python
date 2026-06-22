import asyncio

import pytest

import pycodex.network_proxy as network_proxy
from pycodex.network_proxy import (
    ConfigState,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
    StaticNetworkProxyReloader,
)


def state_for_config(
    config: NetworkProxyConfig,
    constraints: NetworkProxyConstraints | None = None,
) -> NetworkProxyState:
    state = ConfigState(config, constraints or NetworkProxyConstraints())
    return NetworkProxyState(state, StaticNetworkProxyReloader(state))


def test_unix_socket_allowlist_is_rejected_when_platform_not_supported(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: unix_socket_allowlist_is_rejected_on_non_macos
    # Contract: unsupported platforms deny unix socket allowlist checks, even with allow-all enabled.
    socket_path = tmp_path / "example.sock"
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets([str(socket_path)])
    config.network.dangerously_allow_all_unix_sockets = True
    state = state_for_config(config)
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: False)

    assert not asyncio.run(state.is_unix_socket_allowed(str(socket_path)))


def test_unix_socket_allowlist_is_respected_when_supported(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: unix_socket_allowlist_is_respected_on_macos
    # Contract: supported unix socket checks allow exact configured absolute paths only.
    socket_path = tmp_path / "example.sock"
    other_path = tmp_path / "not-allowed.sock"
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets([str(socket_path)])
    state = state_for_config(config)
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: True)

    assert asyncio.run(state.is_unix_socket_allowed(str(socket_path)))
    assert not asyncio.run(state.is_unix_socket_allowed(str(other_path)))


def test_unix_socket_allowlist_resolves_symlinks_when_supported(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: unix_socket_allowlist_resolves_symlinks
    # Contract: allowlist comparison falls back to canonical paths when both entries exist.
    real = tmp_path / "real.sock"
    link = tmp_path / "link.sock"
    real.write_bytes(b"not a socket")
    try:
        link.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    config = NetworkProxyConfig()
    config.network.set_allow_unix_sockets([str(real)])
    state = state_for_config(config)
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: True)

    assert asyncio.run(state.is_unix_socket_allowed(str(link)))


def test_unix_socket_allow_all_flag_bypasses_allowlist_when_supported(tmp_path, monkeypatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: unix_socket_allow_all_flag_bypasses_allowlist
    # Contract: allow-all bypasses the allowlist only for absolute paths.
    config = NetworkProxyConfig()
    config.network.dangerously_allow_all_unix_sockets = True
    state = state_for_config(config)
    monkeypatch.setattr(network_proxy, "_unix_socket_permissions_supported", lambda: True)

    assert asyncio.run(state.is_unix_socket_allowed(str(tmp_path / "any.sock")))
    assert not asyncio.run(state.is_unix_socket_allowed("relative.sock"))


def test_runtime_accessors_read_current_network_config() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: NetworkProxyState::{method_allowed,allow_upstream_proxy,allow_local_binding,network_mode}
    # Contract: runtime accessors reload and read the current network config.
    config = NetworkProxyConfig()
    config.network.mode = NetworkMode.LIMITED
    config.network.allow_upstream_proxy = False
    config.network.allow_local_binding = True
    state = state_for_config(config)

    assert asyncio.run(state.network_mode()) is NetworkMode.LIMITED
    assert asyncio.run(state.method_allowed("GET"))
    assert not asyncio.run(state.method_allowed("POST"))
    assert not asyncio.run(state.allow_upstream_proxy())
    assert asyncio.run(state.allow_local_binding())


def test_set_network_mode_updates_mode_when_constraints_allow() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust item: NetworkProxyState::set_network_mode
    # Contract: accepted mode updates replace the validated runtime config state.
    config = NetworkProxyConfig()
    config.network.mode = NetworkMode.FULL
    state = state_for_config(config)

    asyncio.run(state.set_network_mode(NetworkMode.LIMITED))

    assert asyncio.run(state.network_mode()) is NetworkMode.LIMITED
    assert asyncio.run(state.current_cfg()).network.mode is NetworkMode.LIMITED


def test_set_network_mode_rejects_widening_managed_constraint() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust item: NetworkProxyState::set_network_mode
    # Contract: managed mode constraints reject widening updates with the Rust context message.
    config = NetworkProxyConfig()
    config.network.mode = NetworkMode.LIMITED
    state = state_for_config(config, NetworkProxyConstraints(mode=NetworkMode.LIMITED))

    with pytest.raises(ValueError, match="network.mode constrained by managed config"):
        asyncio.run(state.set_network_mode(NetworkMode.FULL))

    assert asyncio.run(state.network_mode()) is NetworkMode.LIMITED
