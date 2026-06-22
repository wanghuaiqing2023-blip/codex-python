"""Parity checks for the codex-login crate-root export surface."""

from __future__ import annotations


def test_login_root_reexports_completed_child_modules() -> None:
    # Source: codex/codex-rs/login/src/lib.rs
    # Rust crate: codex-login
    # Rust module: src/lib.rs
    # Contract: crate root re-exports completed child-module surfaces.
    import pycodex.login as login

    assert login.auth is not None
    assert login.default_client is not None
    assert login.AuthEnvTelemetry is not None
    assert login.collect_auth_env_telemetry is not None
    assert login.TokenData is not None
    assert login.DeviceCode is not None
    assert login.ServerOptions is not None
    assert login.request_device_code is not None
    assert login.complete_device_code_login is not None
    assert login.run_device_code_login is not None


def test_login_root_all_contains_completed_crate_root_exports() -> None:
    # Source: codex/codex-rs/login/src/lib.rs
    # Rust crate: codex-login
    # Rust module: src/lib.rs
    # Contract: root __all__ includes completed public re-export names.
    import pycodex.login as login

    expected = {
        "auth",
        "BuildLoginHttpClientError",
        "AuthEnvTelemetry",
        "TokenData",
        "DeviceCode",
        "ServerOptions",
        "request_device_code",
        "complete_device_code_login",
        "run_device_code_login",
        "RefreshTokenFailedError",
        "RefreshTokenFailedReason",
        "ExternalAuthTokens",
        "revoke_auth_tokens",
        "should_revoke_auth_tokens",
    }

    assert expected.issubset(set(login.__all__))
