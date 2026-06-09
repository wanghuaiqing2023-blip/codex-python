"""Port of Rust ``codex-login::auth::error``.

Rust source:
- ``codex/codex-rs/login/src/auth/error.rs``

This Rust module is a pure re-export of protocol auth error types.
"""

from __future__ import annotations

from pycodex.protocol.auth import RefreshTokenFailedError, RefreshTokenFailedReason


__all__ = [
    "RefreshTokenFailedError",
    "RefreshTokenFailedReason",
]
