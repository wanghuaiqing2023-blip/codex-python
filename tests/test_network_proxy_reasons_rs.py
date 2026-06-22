from pycodex.network_proxy import (
    HostBlockReason,
    REASON_DENIED,
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_HOOK_DENIED,
    REASON_MITM_REQUIRED,
    REASON_NOT_ALLOWED,
    REASON_NOT_ALLOWED_LOCAL,
    REASON_POLICY_DENIED,
    REASON_PROXY_DISABLED,
    REASON_UNIX_SOCKET_UNSUPPORTED,
)


def test_reason_constants_match_rust_reasons_rs() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust module: src/reasons.rs
    # Rust items: REASON_* constants
    # Contract: stable reason strings are shared by runtime.rs, network_policy.rs,
    # responses.rs, http_proxy.rs, socks5.rs, and mitm.rs.
    assert REASON_DENIED == "denied"
    assert REASON_METHOD_NOT_ALLOWED == "method_not_allowed"
    assert REASON_MITM_HOOK_DENIED == "mitm_hook_denied"
    assert REASON_MITM_REQUIRED == "mitm_required"
    assert REASON_NOT_ALLOWED == "not_allowed"
    assert REASON_NOT_ALLOWED_LOCAL == "not_allowed_local"
    assert REASON_POLICY_DENIED == "policy_denied"
    assert REASON_PROXY_DISABLED == "proxy_disabled"
    assert REASON_UNIX_SOCKET_UNSUPPORTED == "unix_socket_unsupported"


def test_host_block_reason_as_str_uses_reasons_rs_constants() -> None:
    # Source: rust_contract_inferred
    # Rust crate: codex-network-proxy
    # Rust modules: src/runtime.rs, src/reasons.rs
    # Rust items: HostBlockReason::as_str, REASON_DENIED, REASON_NOT_ALLOWED,
    # REASON_NOT_ALLOWED_LOCAL
    # Contract: HostBlockReason display/policy/audit strings are exactly the
    # reason constants from reasons.rs.
    assert HostBlockReason.DENIED.as_str() == REASON_DENIED
    assert HostBlockReason.NOT_ALLOWED.as_str() == REASON_NOT_ALLOWED
    assert HostBlockReason.NOT_ALLOWED_LOCAL.as_str() == REASON_NOT_ALLOWED_LOCAL
