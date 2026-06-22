import os
from pathlib import Path

import pytest

from pycodex.linux_sandbox import proxy_routing


def test_recognizes_proxy_env_keys_case_insensitively() -> None:
    # Rust source: linux-sandbox/src/proxy_routing.rs
    # recognizes_proxy_env_keys_case_insensitively.
    assert proxy_routing.is_proxy_env_key("HTTP_PROXY") is True
    assert proxy_routing.is_proxy_env_key("http_proxy") is True
    assert proxy_routing.is_proxy_env_key("PATH") is False


def test_parses_loopback_proxy_endpoint() -> None:
    # Rust source: parses_loopback_proxy_endpoint.
    assert proxy_routing.parse_loopback_proxy_endpoint("http://127.0.0.1:43128") == proxy_routing.SocketAddr(
        "127.0.0.1",
        43128,
    )


def test_ignores_non_loopback_proxy_endpoint() -> None:
    # Rust source: ignores_non_loopback_proxy_endpoint.
    assert proxy_routing.parse_loopback_proxy_endpoint("http://example.com:3128") is None


def test_plan_proxy_routes_only_includes_valid_loopback_endpoints() -> None:
    # Rust source: plan_proxy_routes_only_includes_valid_loopback_endpoints.
    env = {
        "HTTP_PROXY": "http://127.0.0.1:43128",
        "HTTPS_PROXY": "http://example.com:3128",
        "PATH": "/usr/bin",
    }

    plan = proxy_routing.plan_proxy_routes(env)

    assert plan.has_proxy_config is True
    assert len(plan.routes) == 1
    assert plan.routes[0].env_key == "HTTP_PROXY"
    assert plan.routes[0].endpoint == proxy_routing.SocketAddr("127.0.0.1", 43128)


def test_rewrites_proxy_url_to_local_loopback_port() -> None:
    # Rust source: rewrites_proxy_url_to_local_loopback_port.
    assert (
        proxy_routing.rewrite_proxy_env_value("socks5h://127.0.0.1:8081", 43210)
        == "socks5h://127.0.0.1:43210"
    )


def test_default_proxy_ports_match_expected_schemes() -> None:
    # Rust source: default_proxy_ports_match_expected_schemes.
    assert proxy_routing.default_proxy_port("http") == 80
    assert proxy_routing.default_proxy_port("https") == 443
    assert proxy_routing.default_proxy_port("socks5h") == 1080


def test_cleanup_proxy_socket_dir_removes_bridge_artifacts(tmp_path: Path) -> None:
    # Rust source: cleanup_proxy_socket_dir_removes_bridge_artifacts.
    socket_dir = tmp_path / "codex-linux-sandbox-proxy-test"
    socket_dir.mkdir()
    (socket_dir / "bridge.sock").write_bytes(b"test")

    proxy_routing.cleanup_proxy_socket_dir(socket_dir)

    assert socket_dir.exists() is False


def test_proxy_route_spec_serialization_omits_proxy_urls() -> None:
    # Rust source: proxy_route_spec_serialization_omits_proxy_urls.
    spec = proxy_routing.ProxyRouteSpec(
        (
            proxy_routing.ProxyRouteEntry(
                env_key="HTTP_PROXY",
                uds_path=Path("/tmp/proxy-route-0.sock"),
            ),
        )
    )

    assert spec.to_json() == '{"routes":[{"env_key":"HTTP_PROXY","uds_path":"/tmp/proxy-route-0.sock"}]}'


def test_parse_proxy_socket_dir_owner_pid_reads_owner_pid() -> None:
    # Rust source: parse_proxy_socket_dir_owner_pid_reads_owner_pid.
    assert proxy_routing.parse_proxy_socket_dir_owner_pid("codex-linux-sandbox-proxy-1234-0") == 1234
    assert proxy_routing.parse_proxy_socket_dir_owner_pid("codex-linux-sandbox-proxy-x") is None
    assert proxy_routing.parse_proxy_socket_dir_owner_pid("not-a-proxy-dir") is None


def test_cleanup_stale_proxy_socket_dirs_removes_dead_pid_directories(tmp_path: Path) -> None:
    # Rust source: cleanup_stale_proxy_socket_dirs_removes_dead_pid_directories.
    dead_dir = tmp_path / f"{proxy_routing.PROXY_SOCKET_DIR_PREFIX}{2 ** 32 - 1}-0"
    dead_dir.mkdir()
    alive_dir = tmp_path / f"{proxy_routing.PROXY_SOCKET_DIR_PREFIX}{os.getpid()}-1"
    alive_dir.mkdir()
    unrelated_dir = tmp_path / "unrelated-proxy-dir"
    unrelated_dir.mkdir()

    proxy_routing.cleanup_stale_proxy_socket_dirs_in(tmp_path)

    assert dead_dir.exists() is False
    assert alive_dir.exists() is True
    assert unrelated_dir.exists() is True


def test_prepare_host_proxy_route_spec_fails_closed_without_proxy_env(monkeypatch) -> None:
    # Rust integration source: linux-sandbox/tests/suite/managed_proxy.rs
    # managed_proxy_mode_fails_closed_without_proxy_env.
    for key in proxy_routing.PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)

    with pytest.raises(ValueError, match="managed proxy mode requires proxy environment variables"):
        proxy_routing.prepare_host_proxy_route_spec()


def test_prepare_host_proxy_route_spec_fails_closed_without_loopback_proxy(monkeypatch) -> None:
    # Rust source: proxy_routing.rs prepare_host_proxy_route_spec plan error.
    for key in proxy_routing.PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://example.com:3128")

    with pytest.raises(ValueError, match="managed proxy mode requires parseable loopback proxy endpoints"):
        proxy_routing.prepare_host_proxy_route_spec()


def test_prepare_host_proxy_route_spec_reaches_bridge_runtime_boundary_with_loopback_proxy(monkeypatch) -> None:
    # Rust source: proxy_routing.rs prepare_host_proxy_route_spec proceeds to
    # bridge creation after valid loopback planning.
    for key in proxy_routing.PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:43128")

    with pytest.raises(NotImplementedError, match="proxy bridge process creation is a runtime boundary"):
        proxy_routing.prepare_host_proxy_route_spec()
