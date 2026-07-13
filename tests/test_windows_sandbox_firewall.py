from __future__ import annotations

from pycodex.windows_sandbox.firewall import (
    OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME,
    OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME,
    blocked_loopback_tcp_remote_ports,
    offline_rule_specs,
    wfp_defense_rule_specs,
)


def test_blocked_port_complement_matches_fixed_rust_helper() -> None:
    # Rust owner: setup_main::win::firewall::blocked_loopback_tcp_remote_ports.
    assert blocked_loopback_tcp_remote_ports([]) == "1-65535"
    assert blocked_loopback_tcp_remote_ports([1, 8080, 65535]) == "2-8079,8081-65534"
    assert blocked_loopback_tcp_remote_ports([8080, 8080, 0, 70000]) == "1-8079,8081-65535"


def test_local_binding_removes_loopback_blocks() -> None:
    names = {spec.name for spec in offline_rule_specs([8080], True)}
    assert OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME not in names
    assert OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME not in names


def test_proxy_only_mode_blocks_udp_and_tcp_complement() -> None:
    specs = {spec.name: spec for spec in offline_rule_specs([8080], False)}
    assert OFFLINE_BLOCK_LOOPBACK_UDP_RULE_NAME in specs
    assert specs[OFFLINE_BLOCK_LOOPBACK_TCP_RULE_NAME].remote_ports == "1-8079,8081-65535"


def test_wfp_defense_projection_covers_fixed_rust_protocols() -> None:
    # Rust owner: windows-sandbox-rs/src/wfp/filter_specs.rs.
    specs = wfp_defense_rule_specs()
    assert {(spec.protocol, spec.remote_ports) for spec in specs} >= {
        (1, None),
        (58, None),
        (6, "53"),
        (17, "53"),
        (6, "853"),
        (6, "445"),
        (6, "139"),
    }
