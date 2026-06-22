import asyncio
import socket

import pytest
import pycodex.network_proxy as network_proxy

from pycodex.network_proxy import (
    ALLOW_LOCAL_BINDING_ENV_KEY,
    PROXY_GIT_SSH_COMMAND_ENV_KEY,
    ConfigState,
    DEFAULT_NO_PROXY_VALUE,
    ELECTRON_GET_USE_PROXY_ENV_KEY,
    NODE_USE_ENV_PROXY_ENV_KEY,
    PROXY_ACTIVE_ENV_KEY,
    PROXY_ENV_KEYS,
    NetworkMode,
    NetworkProxy,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyHandle,
    NetworkProxyState,
    NetworkProxyTask,
    StaticNetworkProxyReloader,
    apply_proxy_env_overrides,
    has_proxy_url_env_vars,
    proxy_url_env_value,
    reserve_windows_managed_listeners,
    windows_managed_loopback_addr,
)


def network_proxy_state_for_config(config: NetworkProxyConfig) -> NetworkProxyState:
    state = ConfigState(config, NetworkProxyConstraints())
    return NetworkProxyState(state, StaticNetworkProxyReloader(state))


def test_managed_proxy_builder_uses_loopback_ports() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: managed_proxy_builder_uses_loopback_ports
    # Contract: managed builders reserve loopback listeners and replace requested ports with concrete loopback ports.
    config = NetworkProxyConfig()
    config.network.proxy_url = "http://127.0.0.1:43128"
    config.network.socks_url = "http://127.0.0.1:48081"
    state = network_proxy_state_for_config(config)

    proxy = asyncio.run(NetworkProxy.builder().state(state).build())

    assert proxy.http_addr()[0] == "127.0.0.1"
    assert proxy.socks_addr()[0] == "127.0.0.1"
    assert proxy.http_addr()[1] != 0
    assert proxy.socks_addr()[1] != 0
    assert proxy.reserved_listeners is not None
    proxy.reserved_listeners.close()


def test_non_codex_managed_proxy_builder_uses_configured_ports() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: non_codex_managed_proxy_builder_uses_configured_ports
    # Contract: non-managed builder uses runtime config addresses instead of reserving ephemeral listeners.
    config = NetworkProxyConfig()
    config.network.proxy_url = "http://127.0.0.1:43128"
    config.network.socks_url = "http://127.0.0.1:48081"
    state = network_proxy_state_for_config(config)

    proxy = asyncio.run(NetworkProxy.builder().state(state).managed_by_codex(False).build())

    assert proxy.http_addr() == ("127.0.0.1", 43128)
    assert proxy.socks_addr() == ("127.0.0.1", 48081)
    assert proxy.reserved_listeners is None


def test_network_proxy_handle_wait_awaits_socks_task_before_http_error() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust items: NetworkProxyHandle::wait
    # Contract: wait joins the HTTP task and the optional SOCKS task before propagating task errors.
    async def scenario() -> None:
        socks_finished = asyncio.Event()

        async def socks_task() -> None:
            await asyncio.sleep(0)
            socks_finished.set()

        handle = NetworkProxyHandle(
            http_task=NetworkProxyTask("http", result=RuntimeError("http failed")),
            socks_task=NetworkProxyTask.pending("socks", asyncio.create_task(socks_task())),
        )

        with pytest.raises(RuntimeError, match="http failed"):
            await handle.wait()

        assert socks_finished.is_set()
        assert handle.completed is True
        assert handle.http_task is None
        assert handle.socks_task is None

    asyncio.run(scenario())


def test_network_proxy_handle_drop_cancels_unfinished_tasks() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust items: Drop for NetworkProxyHandle, abort_tasks
    # Contract: dropping an incomplete handle aborts any unfinished proxy tasks.
    async def scenario() -> None:
        cancelled = asyncio.Event()

        async def never_finishes() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(never_finishes())
        proxy_task = NetworkProxyTask.pending("http", task)
        handle = NetworkProxyHandle(http_task=proxy_task)

        await asyncio.sleep(0)
        handle.__del__()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert proxy_task.aborted is True
        assert cancelled.is_set()
        assert task.cancelled()
        assert handle.completed is True
        assert handle.http_task is None
        assert handle.socks_task is None

    asyncio.run(scenario())


def test_managed_proxy_builder_does_not_reserve_socks_listener_when_disabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: managed_proxy_builder_does_not_reserve_socks_listener_when_disabled
    # Contract: managed builder skips SOCKS listener reservation when network.enable_socks5 is false.
    config = NetworkProxyConfig()
    config.network.enable_socks5 = False
    config.network.proxy_url = "http://127.0.0.1:43128"
    config.network.socks_url = "http://127.0.0.1:43129"
    state = network_proxy_state_for_config(config)

    proxy = asyncio.run(NetworkProxy.builder().state(state).build())

    assert proxy.http_addr()[0] == "127.0.0.1"
    assert proxy.http_addr()[1] != 0
    assert proxy.socks_addr() == ("127.0.0.1", 43129)
    assert proxy.reserved_listeners is not None
    assert proxy.reserved_listeners.socks_listener is None
    proxy.reserved_listeners.close()


def test_network_proxy_replace_config_state_rejects_runtime_endpoint_changes() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust item: NetworkProxy::replace_config_state
    # Contract: running proxy replacement rejects listener/runtime endpoint fields that Rust treats as immutable.
    config = NetworkProxyConfig()
    config.network.enabled = True
    config.network.proxy_url = "http://127.0.0.1:43128"
    config.network.socks_url = "http://127.0.0.1:48081"
    state = network_proxy_state_for_config(config)
    proxy = asyncio.run(NetworkProxy.builder().state(state).managed_by_codex(False).build())

    for field_name, mutate in (
        ("network.enabled", lambda cfg: setattr(cfg.network, "enabled", False)),
        ("network.proxy_url", lambda cfg: setattr(cfg.network, "proxy_url", "http://127.0.0.1:43129")),
        ("network.socks_url", lambda cfg: setattr(cfg.network, "socks_url", "http://127.0.0.1:48082")),
        ("network.enable_socks5", lambda cfg: setattr(cfg.network, "enable_socks5", False)),
        ("network.enable_socks5_udp", lambda cfg: setattr(cfg.network, "enable_socks5_udp", False)),
    ):
        next_config = NetworkProxyConfig.from_mapping(config.to_mapping())
        mutate(next_config)
        with pytest.raises(ValueError, match=f"cannot update {field_name}"):
            asyncio.run(proxy.replace_config_state(ConfigState(next_config, NetworkProxyConstraints())))


def test_network_proxy_replace_config_state_refreshes_runtime_settings() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust item: NetworkProxy::replace_config_state
    # Contract: accepted replacement updates both shared state and runtime settings snapshot.
    config = NetworkProxyConfig()
    config.network.enabled = True
    config.network.proxy_url = "http://127.0.0.1:43128"
    config.network.socks_url = "http://127.0.0.1:48081"
    state = network_proxy_state_for_config(config)
    proxy = asyncio.run(NetworkProxy.builder().state(state).managed_by_codex(False).build())

    next_config = NetworkProxyConfig.from_mapping(config.to_mapping())
    next_config.network.allow_local_binding = True
    next_config.network.dangerously_allow_all_unix_sockets = True
    next_config.network.set_allow_unix_sockets(["/tmp/codex.sock"])

    asyncio.run(proxy.replace_config_state(ConfigState(next_config, NetworkProxyConstraints())))

    assert proxy.allow_local_binding() is True
    assert proxy.dangerously_allow_all_unix_sockets() is True
    assert proxy.allow_unix_sockets() == ("/tmp/codex.sock",)


def test_network_proxy_run_starts_http_and_socks_tasks_and_shutdown_aborts_them() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust items: NetworkProxy::run, NetworkProxyHandle::shutdown, run_http_proxy_with_std_listener, run_socks5_with_std_listener
    # Contract: running an enabled proxy consumes reserved listeners, starts HTTP plus optional SOCKS tasks, and shutdown aborts both listener tasks.
    async def can_connect(addr: tuple[str, int]) -> bool:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*addr), timeout=1)
        except OSError:
            return False
        writer.close()
        await writer.wait_closed()
        del reader
        return True

    async def scenario() -> None:
        config = NetworkProxyConfig()
        config.network.enabled = True
        config.network.mode = NetworkMode.FULL
        config.network.enable_socks5 = True
        config.network.enable_socks5_udp = True
        config.network.allow_local_binding = True
        config.network.set_allowed_domains(["127.0.0.1"])
        state = network_proxy_state_for_config(config)
        proxy = await NetworkProxy.builder().state(state).build()
        http_addr = proxy.http_addr()
        socks_addr = proxy.socks_addr()

        handle = await proxy.run()
        assert handle.http_task is not None
        assert handle.socks_task is not None
        assert proxy.reserved_listeners is not None
        assert proxy.reserved_listeners.http_listener is None
        assert proxy.reserved_listeners.socks_listener is None
        try:
            assert await can_connect(http_addr) is True

            reader, writer = await asyncio.wait_for(asyncio.open_connection(*socks_addr), timeout=1)
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(2), timeout=1) == b"\x05\x00"
            writer.close()
            await writer.wait_closed()
        finally:
            await handle.shutdown()

        assert handle.completed is True
        assert handle.http_task is None
        assert handle.socks_task is None
        assert await can_connect(http_addr) is False
        assert await can_connect(socks_addr) is False

    asyncio.run(scenario())


def test_proxy_url_env_value_resolves_lowercase_aliases() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: proxy_url_env_value_resolves_lowercase_aliases
    # Contract: canonical proxy env lookup falls back to lowercase aliases.
    env = {"http_proxy": "http://127.0.0.1:3128"}

    assert proxy_url_env_value(env, "HTTP_PROXY") == "http://127.0.0.1:3128"


def test_has_proxy_url_env_vars_detects_lowercase_aliases() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: has_proxy_url_env_vars_detects_lowercase_aliases
    # Contract: proxy env detection considers lowercase aliases and ignores empty values.
    assert has_proxy_url_env_vars({"HTTP_PROXY": "   "}) is False
    assert has_proxy_url_env_vars({"all_proxy": "socks5h://127.0.0.1:8081"}) is True


def test_has_proxy_url_env_vars_detects_websocket_proxy_keys() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: has_proxy_url_env_vars_detects_websocket_proxy_keys
    # Contract: websocket proxy variables are part of managed proxy detection.
    assert has_proxy_url_env_vars({"wss_proxy": "http://127.0.0.1:3128"}) is True


def test_apply_proxy_env_overrides_sets_common_tool_vars() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_sets_common_tool_vars
    # Contract: managed env injection sets HTTP, websocket, SOCKS, no-proxy, and runtime marker keys.
    env: dict[str, str] = {}

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 8081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert env["HTTP_PROXY"] == "http://127.0.0.1:3128"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:3128"
    assert env["WS_PROXY"] == "http://127.0.0.1:3128"
    assert env["WSS_PROXY"] == "http://127.0.0.1:3128"
    assert env["npm_config_proxy"] == "http://127.0.0.1:3128"
    assert env["ALL_PROXY"] == "socks5h://127.0.0.1:8081"
    assert env["FTP_PROXY"] == "socks5h://127.0.0.1:8081"
    assert env["NO_PROXY"] == DEFAULT_NO_PROXY_VALUE
    assert "10.0.0.0/8" in env["NO_PROXY"]
    assert "172.16.0.0/12" in env["NO_PROXY"]
    assert "192.168.0.0/16" in env["NO_PROXY"]
    assert "169.254.0.0/16" not in env["NO_PROXY"]
    assert env[PROXY_ACTIVE_ENV_KEY] == "1"
    assert env[ALLOW_LOCAL_BINDING_ENV_KEY] == "0"
    assert env[ELECTRON_GET_USE_PROXY_ENV_KEY] == "true"
    assert env[NODE_USE_ENV_PROXY_ENV_KEY] == "1"


def test_apply_proxy_env_overrides_sets_only_expected_env_keys() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_sets_only_expected_env_keys
    # Contract: proxy env writer only creates the Rust-listed managed proxy env keys.
    env: dict[str, str] = {}

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 8081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert set(env).issubset(set(PROXY_ENV_KEYS))


def test_apply_proxy_env_overrides_uses_http_for_all_proxy_without_socks() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_uses_http_for_all_proxy_without_socks
    # Contract: when SOCKS is disabled, ALL_PROXY/FTP_PROXY use the HTTP proxy endpoint.
    env: dict[str, str] = {}

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 8081),
        socks_enabled=False,
        allow_local_binding=True,
    )

    assert env["ALL_PROXY"] == "http://127.0.0.1:3128"
    assert env["FTP_PROXY"] == "http://127.0.0.1:3128"
    assert env[ALLOW_LOCAL_BINDING_ENV_KEY] == "1"


def test_apply_proxy_env_overrides_uses_plain_http_proxy_url() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_uses_plain_http_proxy_url
    # Contract: HTTP_PROXY/HTTPS_PROXY/WS_PROXY/WSS_PROXY stay plain HTTP even when SOCKS is enabled.
    env: dict[str, str] = {}

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 8081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert env["HTTP_PROXY"] == "http://127.0.0.1:3128"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:3128"
    assert env["WS_PROXY"] == "http://127.0.0.1:3128"
    assert env["WSS_PROXY"] == "http://127.0.0.1:3128"
    assert env["ALL_PROXY"] == "socks5h://127.0.0.1:8081"


def test_apply_proxy_env_overrides_preserves_existing_git_ssh_command(monkeypatch: pytest.MonkeyPatch) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_preserves_existing_git_ssh_command
    # Contract: macOS managed proxy injection preserves existing non-Codex SSH wrappers.
    monkeypatch.setattr(network_proxy.sys, "platform", "darwin")
    env = {
        PROXY_GIT_SSH_COMMAND_ENV_KEY: "ssh -o ProxyCommand='tsh proxy ssh --cluster=dev %r@%h:%p'"
    }

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 8081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert (
        env[PROXY_GIT_SSH_COMMAND_ENV_KEY]
        == "ssh -o ProxyCommand='tsh proxy ssh --cluster=dev %r@%h:%p'"
    )


def test_apply_proxy_env_overrides_preserves_unmarked_git_ssh_command_with_proxy_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_preserves_unmarked_git_ssh_command_with_proxy_shape
    # Contract: Rust only refreshes commands with the Codex marker, not user-provided commands with the same ProxyCommand shape.
    monkeypatch.setattr(network_proxy.sys, "platform", "darwin")
    env = {
        PROXY_GIT_SSH_COMMAND_ENV_KEY: "ssh -o ProxyCommand='nc -X 5 -x 127.0.0.1:8081 %h %p'"
    }

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 3128),
        ("127.0.0.1", 48081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert (
        env[PROXY_GIT_SSH_COMMAND_ENV_KEY]
        == "ssh -o ProxyCommand='nc -X 5 -x 127.0.0.1:8081 %h %p'"
    )


def test_apply_proxy_env_overrides_refreshes_previous_codex_proxy_git_ssh_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: apply_proxy_env_overrides_refreshes_previous_codex_proxy_git_ssh_command
    # Contract: macOS managed proxy injection replaces stale Codex-marked SSH ProxyCommand values.
    monkeypatch.setattr(network_proxy.sys, "platform", "darwin")
    env = {
        PROXY_GIT_SSH_COMMAND_ENV_KEY: network_proxy.codex_proxy_git_ssh_command(
            ("127.0.0.1", 8081)
        )
    }

    apply_proxy_env_overrides(
        env,
        ("127.0.0.1", 43128),
        ("127.0.0.1", 48081),
        socks_enabled=True,
        allow_local_binding=False,
    )

    assert env[PROXY_GIT_SSH_COMMAND_ENV_KEY] == network_proxy.codex_proxy_git_ssh_command(
        ("127.0.0.1", 48081)
    )


def test_windows_managed_loopback_addr_clamps_non_loopback_inputs() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: windows_managed_loopback_addr_clamps_non_loopback_inputs
    # Contract: managed Windows proxy bind addresses are forced onto IPv4 loopback while preserving the port.
    assert windows_managed_loopback_addr("0.0.0.0:3128") == ("127.0.0.1", 3128)
    assert windows_managed_loopback_addr("[::]:8081") == ("127.0.0.1", 8081)


def test_reserve_windows_managed_listeners_falls_back_when_http_port_is_busy() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/proxy.rs
    # Rust test: reserve_windows_managed_listeners_falls_back_when_http_port_is_busy
    # Contract: an occupied managed HTTP port falls back to loopback ephemeral listeners and skips SOCKS reservation when disabled.
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        busy_port = occupied.getsockname()[1]

        with reserve_windows_managed_listeners(
            ("127.0.0.1", busy_port),
            ("127.0.0.1", 48081),
            reserve_socks_listener=False,
        ) as reserved:
            assert reserved.socks_listener is None
            host, port = reserved.http_addr()
            assert host == "127.0.0.1"
            assert port != busy_port
    finally:
        occupied.close()
