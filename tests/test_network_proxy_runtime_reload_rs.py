import asyncio

import pytest

from pycodex.network_proxy import (
    BlockedRequest,
    BlockedRequestArgs,
    ConfigState,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
)


def config_with(*, enabled: bool = False, mode: NetworkMode = NetworkMode.FULL) -> NetworkProxyConfig:
    config = NetworkProxyConfig()
    config.network.enabled = enabled
    config.network.mode = mode
    return config


def blocked_request(host: str = "example.com") -> BlockedRequest:
    return BlockedRequest.new(
        BlockedRequestArgs(
            host=host,
            reason="not_allowed",
            method="GET",
            protocol="http",
            port=80,
        )
    )


class SequenceReloader:
    def __init__(self, maybe_states=(), reload_state=None, reload_error: Exception | None = None) -> None:
        self.maybe_states = list(maybe_states)
        self.reload_state = reload_state
        self.reload_error = reload_error
        self.maybe_calls = 0
        self.reload_calls = 0

    def source_label(self) -> str:
        return "SequenceReloader"

    async def maybe_reload(self):
        self.maybe_calls += 1
        if not self.maybe_states:
            return None
        return self.maybe_states.pop(0)

    async def reload_now(self):
        self.reload_calls += 1
        if self.reload_error is not None:
            raise self.reload_error
        if self.reload_state is None:
            raise RuntimeError("missing reload state")
        return self.reload_state


def test_current_cfg_reloads_on_demand_and_preserves_blocked_buffer() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: ConfigReloader::maybe_reload, NetworkProxyState::current_cfg, reload_if_needed
    # Contract: on-demand reload replaces config state while preserving blocked requests and total.
    initial_state = ConfigState(config_with(enabled=False), NetworkProxyConstraints())
    reloaded_state = ConfigState(config_with(enabled=True), NetworkProxyConstraints())
    reloader = SequenceReloader(maybe_states=[None, reloaded_state])
    state = NetworkProxyState(initial_state, reloader)
    asyncio.run(state.record_blocked(blocked_request("blocked.example")))

    cfg = asyncio.run(state.current_cfg())

    assert cfg.network.enabled is True
    assert reloader.maybe_calls >= 2
    snapshot = asyncio.run(state.blocked_snapshot())
    assert [entry.host for entry in snapshot] == ["blocked.example"]
    assert state.state.blocked_total == 1


def test_enabled_uses_reloaded_config_state() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: NetworkProxyState::enabled, reload_if_needed
    # Contract: enabled() is a live policy view and reloads before reading.
    initial_state = ConfigState(config_with(enabled=False), NetworkProxyConstraints())
    reloader = SequenceReloader(maybe_states=[ConfigState(config_with(enabled=True), NetworkProxyConstraints())])
    state = NetworkProxyState(initial_state, reloader)

    assert asyncio.run(state.enabled()) is True


def test_force_reload_replaces_state_and_preserves_blocked_buffer() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: ConfigReloader::reload_now, NetworkProxyState::force_reload
    # Contract: forced reload replaces config state while preserving blocked requests and total.
    initial_state = ConfigState(config_with(mode=NetworkMode.FULL), NetworkProxyConstraints())
    reloader = SequenceReloader(reload_state=ConfigState(config_with(mode=NetworkMode.LIMITED), NetworkProxyConstraints()))
    state = NetworkProxyState(initial_state, reloader)
    asyncio.run(state.record_blocked(blocked_request("blocked.example")))

    asyncio.run(state.force_reload())

    assert reloader.reload_calls == 1
    assert asyncio.run(state.network_mode()) is NetworkMode.LIMITED
    assert [entry.host for entry in asyncio.run(state.blocked_snapshot())] == ["blocked.example"]
    assert state.state.blocked_total == 1


def test_force_reload_error_keeps_previous_config_state() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust items: NetworkProxyState::force_reload error branch
    # Contract: failed force reload propagates the error and keeps the previous config.
    initial_state = ConfigState(config_with(mode=NetworkMode.FULL), NetworkProxyConstraints())
    state = NetworkProxyState(initial_state, SequenceReloader(reload_error=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(state.force_reload())

    assert asyncio.run(state.network_mode()) is NetworkMode.FULL
