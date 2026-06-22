"""Parity checks for the codex-login auth module aggregation boundary."""

from __future__ import annotations


def test_auth_package_reexports_completed_child_module_contracts() -> None:
    # Source: codex/codex-rs/login/src/auth/mod.rs
    # Rust crate: codex-login
    # Rust module: src/auth/mod.rs
    # Contract: auth module aggregation re-exports completed child modules.
    import pycodex.login.auth as auth

    assert auth.default_client is not None
    assert auth.RefreshTokenFailedError is not None
    assert auth.RefreshTokenFailedReason is not None
    assert auth.try_parse_error_message is not None
    assert auth.AuthDotJson is not None
    assert auth.create_auth_storage is not None
    assert auth.revoke_auth_tokens is not None
    assert auth.should_revoke_auth_tokens is not None
    assert auth.BearerTokenRefresher is not None
    assert auth.AgentIdentityAuth is not None


def test_auth_package_all_matches_completed_public_surface() -> None:
    # Source: codex/codex-rs/login/src/auth/mod.rs
    # Rust crate: codex-login
    # Rust module: src/auth/mod.rs
    # Contract: package-level __all__ lists the aggregation surface.
    import pycodex.login.auth as auth

    expected = {
        "AgentIdentityAuth",
        "AgentIdentityAuthRecord",
        "AuthDotJson",
        "AuthStorageBackend",
        "BearerTokenRefresher",
        "RefreshTokenFailedError",
        "RefreshTokenFailedReason",
        "create_auth_storage",
        "default_client",
        "revoke_auth_tokens",
        "should_revoke_auth_tokens",
        "try_parse_error_message",
    }

    assert expected.issubset(set(auth.__all__))
