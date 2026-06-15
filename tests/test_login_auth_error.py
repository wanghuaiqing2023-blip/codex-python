"""Parity tests for Rust ``codex-login::auth::error``.

Rust source:
- ``codex/codex-rs/login/src/auth/error.rs``
"""

from __future__ import annotations

import pycodex.login as login
import pycodex.login.auth as login_auth
from pycodex.login.auth import error as login_auth_error
from pycodex.protocol.auth import RefreshTokenFailedError, RefreshTokenFailedReason


def test_login_auth_error_reexports_protocol_refresh_failure_types() -> None:
    assert login_auth_error.RefreshTokenFailedError is RefreshTokenFailedError
    assert login_auth_error.RefreshTokenFailedReason is RefreshTokenFailedReason
    assert login_auth.RefreshTokenFailedError is RefreshTokenFailedError
    assert login_auth.RefreshTokenFailedReason is RefreshTokenFailedReason
    assert login.RefreshTokenFailedError is RefreshTokenFailedError
    assert login.RefreshTokenFailedReason is RefreshTokenFailedReason


def test_login_auth_error_preserves_protocol_error_behavior() -> None:
    error = login_auth_error.RefreshTokenFailedError(
        login_auth_error.RefreshTokenFailedReason.EXPIRED,
        "refresh token expired",
    )

    assert str(error) == "refresh token expired"
    assert error.reason is RefreshTokenFailedReason.EXPIRED
    assert error.message == "refresh token expired"
