import pytest

from pycodex.network_proxy import (
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraintError,
    NetworkProxyConstraints,
    build_config_state,
    validate_policy_against_constraints,
)


def _config(
    *,
    allowed_domains=(),
    denied_domains=(),
    enabled=True,
    mode=NetworkMode.FULL,
) -> NetworkProxyConfig:
    config = NetworkProxyConfig()
    config.network.enabled = enabled
    config.network.mode = mode
    config.network.set_allowed_domains(list(allowed_domains))
    config.network.set_denied_domains(list(denied_domains))
    return config


def _raises_field(config: NetworkProxyConfig, constraints: NetworkProxyConstraints, field: str) -> NetworkProxyConstraintError:
    with pytest.raises(NetworkProxyConstraintError) as exc_info:
        validate_policy_against_constraints(config, constraints)
    assert exc_info.value.field_name == field
    assert str(exc_info.value).startswith(f"invalid value for {field}: ")
    return exc_info.value


def test_validate_policy_against_constraints_disallows_widening_allowed_domains() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_disallows_widening_allowed_domains
    # Contract: unmanaged allowlist candidate must be subset of managed allowed_domains.
    constraints = NetworkProxyConstraints(allowed_domains=["example.com"])
    config = _config(allowed_domains=["example.com", "evil.com"])

    err = _raises_field(config, constraints, "network.allowed_domains")

    assert err.candidate == '["evil.com"]'
    assert err.allowed == "subset of managed allowed_domains"


def test_validate_policy_against_constraints_allows_expanding_allowed_domains_when_enabled() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_allows_expanding_allowed_domains_when_enabled
    # Contract: allowlist expansion mode only requires managed entries to remain present.
    constraints = NetworkProxyConstraints(
        allowed_domains=["example.com"],
        allowlist_expansion_enabled=True,
    )
    config = _config(allowed_domains=["example.com", "api.openai.com"])

    validate_policy_against_constraints(config, constraints)


def test_validate_policy_against_constraints_disallows_widening_mode() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_disallows_widening_mode
    # Contract: Full is wider than managed Limited mode.
    constraints = NetworkProxyConstraints(mode=NetworkMode.LIMITED)
    config = _config(mode=NetworkMode.FULL)

    err = _raises_field(config, constraints, "network.mode")

    assert err.candidate == "Full"
    assert err.allowed == "Limited or more restrictive"


def test_validate_policy_against_constraints_allows_narrowing_wildcard_allowlist() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_allows_narrowing_wildcard_allowlist
    # Contract: exact subdomain is a subset of managed `*.example.com`.
    constraints = NetworkProxyConstraints(allowed_domains=["*.example.com"])
    config = _config(allowed_domains=["api.example.com"])

    validate_policy_against_constraints(config, constraints)


def test_validate_policy_against_constraints_rejects_widening_wildcard_allowlist() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_rejects_widening_wildcard_allowlist
    # Contract: `**.example.com` is wider than managed `*.example.com`.
    constraints = NetworkProxyConstraints(allowed_domains=["*.example.com"])
    config = _config(allowed_domains=["**.example.com"])

    _raises_field(config, constraints, "network.allowed_domains")


@pytest.mark.parametrize("pattern", ["*", "[*]", "**.[*]"])
def test_validate_policy_against_constraints_rejects_global_wildcard_in_managed_allowlist(pattern: str) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust tests: validate_policy_against_constraints_rejects_*global_wildcard*_managed_allowlist
    # Contract: managed allowlist constraints cannot use global wildcard patterns.
    constraints = NetworkProxyConstraints(allowed_domains=[pattern])
    config = _config(allowed_domains=["api.example.com"])

    err = _raises_field(config, constraints, "network.allowed_domains")

    assert err.candidate == pattern
    assert "scoped wildcards" in err.allowed


def test_validate_policy_against_constraints_requires_managed_denied_domains_entries() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_requires_managed_denied_domains_entries
    # Contract: managed deny entries must remain present unless no deny constraints exist.
    constraints = NetworkProxyConstraints(denied_domains=["evil.com"])
    config = _config()

    err = _raises_field(config, constraints, "network.denied_domains")

    assert err.candidate == "missing managed denied_domains entries"
    assert err.allowed == '["evil.com"]'


def test_validate_policy_against_constraints_disallows_expanding_denied_domains_when_fixed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_disallows_expanding_denied_domains_when_fixed
    # Contract: fixed managed denylist must match exactly.
    constraints = NetworkProxyConstraints(
        denied_domains=["evil.com"],
        denylist_expansion_enabled=False,
    )
    config = _config(denied_domains=["evil.com", "more-evil.com"])

    err = _raises_field(config, constraints, "network.denied_domains")

    assert err.candidate == '["evil.com", "more-evil.com"]'
    assert err.allowed == "must match managed denied_domains"


def test_validate_policy_against_constraints_disallows_boolean_widening() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust tests: disallows_enabling_when_managed_disabled, disallows_allow_local_binding_when_managed_disabled,
    # disallows_allow_all_unix_sockets_without_managed_opt_in.
    config = _config()
    config.network.allow_local_binding = True
    config.network.dangerously_allow_all_unix_sockets = True

    _raises_field(config, NetworkProxyConstraints(enabled=False), "network.enabled")
    _raises_field(config, NetworkProxyConstraints(allow_local_binding=False), "network.allow_local_binding")
    _raises_field(
        config,
        NetworkProxyConstraints(dangerously_allow_all_unix_sockets=False),
        "network.dangerously_allow_all_unix_sockets",
    )


def test_validate_policy_against_constraints_disallows_allow_all_unix_sockets_when_allowlist_is_managed() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_disallows_allow_all_unix_sockets_when_allowlist_is_managed
    # Contract: managed unix-socket allowlist disables the all-unix-sockets escape hatch.
    config = _config()
    config.network.dangerously_allow_all_unix_sockets = True

    _raises_field(
        config,
        NetworkProxyConstraints(allow_unix_sockets=["/tmp/allowed.sock"]),
        "network.dangerously_allow_all_unix_sockets",
    )


def test_validate_policy_against_constraints_allows_allow_all_unix_sockets_with_managed_opt_in() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs via src/runtime.rs::tests
    # Rust test: validate_policy_against_constraints_allows_allow_all_unix_sockets_with_managed_opt_in
    # Contract: explicit managed opt-in allows the all-unix-sockets flag.
    config = _config()
    config.network.dangerously_allow_all_unix_sockets = True

    validate_policy_against_constraints(
        config,
        NetworkProxyConstraints(dangerously_allow_all_unix_sockets=True),
    )


def test_validate_policy_against_constraints_rejects_unmanaged_unix_socket_paths() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs
    # Rust item: validate_policy_against_constraints allow_unix_sockets branch
    # Contract: configured unix socket paths must be subset of managed allow_unix_sockets.
    config = _config()
    config.network.set_allow_unix_sockets(["/tmp/allowed.sock", "/tmp/other.sock"])

    err = _raises_field(
        config,
        NetworkProxyConstraints(allow_unix_sockets=["/tmp/allowed.sock"]),
        "network.allow_unix_sockets",
    )

    assert err.candidate == '["/tmp/other.sock"]'
    assert err.allowed == "subset of managed allow_unix_sockets"


def test_build_config_state_validates_relative_unix_socket_and_denied_global_wildcard() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/state.rs
    # Rust item: build_config_state
    # Contract: build_config_state applies config.rs unix socket validation and rejects global deny wildcards.
    relative = _config()
    relative.network.set_allow_unix_sockets(["relative.sock"])
    with pytest.raises(ValueError, match=r"network\.allow_unix_sockets\[0\]"):
        build_config_state(relative, NetworkProxyConstraints())

    wildcard = _config(denied_domains=["*"])
    with pytest.raises(NetworkProxyConstraintError, match="network.denied_domains"):
        build_config_state(wildcard, NetworkProxyConstraints())


def test_build_config_state_allows_global_wildcard_allowed_domains() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: build_config_state_allows_global_wildcard_allowed_domains
    # Contract: global wildcard allowlist entries are accepted when building runtime config state.
    config = _config(allowed_domains=["*"])

    build_config_state(config, NetworkProxyConstraints())


def test_build_config_state_allows_bracketed_global_wildcard_allowed_domains() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust test: build_config_state_allows_bracketed_global_wildcard_allowed_domains
    # Contract: bracket-normalized global wildcard allowlist entries are accepted.
    config = _config(allowed_domains=["[*]"])

    build_config_state(config, NetworkProxyConstraints())


@pytest.mark.parametrize("pattern", ["*", "[*]"])
def test_build_config_state_rejects_global_wildcard_denied_domains(pattern: str) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-network-proxy
    # Rust module: src/runtime.rs
    # Rust tests: build_config_state_rejects_global_wildcard_denied_domains,
    # build_config_state_rejects_bracketed_global_wildcard_denied_domains
    # Contract: global wildcard denylist entries are rejected while building runtime config state.
    config = _config(allowed_domains=["example.com"], denied_domains=[pattern])

    with pytest.raises(NetworkProxyConstraintError, match="network.denied_domains"):
        build_config_state(config, NetworkProxyConstraints())
