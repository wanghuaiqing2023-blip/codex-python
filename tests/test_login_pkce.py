from __future__ import annotations

import base64
from hashlib import sha256

from pycodex.cli.login import _build_pkce
from pycodex.login.pkce import PkceCodes, code_challenge_for_verifier, generate_pkce


def _base64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_code_challenge_for_verifier_matches_rust_s256_contract():
    # Rust crate: codex-login
    # Rust module: src/pkce.rs
    # Contract: challenge is BASE64URL-ENCODE(SHA256(verifier)) without padding.
    verifier = "verifier-value"
    assert code_challenge_for_verifier(verifier) == _base64url_no_pad(sha256(verifier.encode("ascii")).digest())


def test_generate_pkce_uses_64_random_bytes_and_no_padding(monkeypatch):
    # Rust module: src/pkce.rs
    # Contract: verifier is URL-safe base64 without padding from 64 random bytes.
    monkeypatch.setattr("pycodex.login.pkce.secrets.token_bytes", lambda size: bytes(range(size)))

    pkce = generate_pkce()

    expected_verifier = _base64url_no_pad(bytes(range(64)))
    assert pkce == PkceCodes(
        code_verifier=expected_verifier,
        code_challenge=_base64url_no_pad(sha256(expected_verifier.encode("ascii")).digest()),
    )
    assert "=" not in pkce.code_verifier
    assert "=" not in pkce.code_challenge
    assert len(pkce.code_verifier) == 86


def test_cli_build_pkce_reuses_login_pkce_module(monkeypatch):
    # Rust ownership: src/pkce.rs owns PKCE generation; CLI keeps compatibility.
    monkeypatch.setattr("pycodex.login.pkce.secrets.token_bytes", lambda size: b"x" * size)

    verifier, challenge = _build_pkce()

    assert verifier == _base64url_no_pad(b"x" * 64)
    assert challenge == code_challenge_for_verifier(verifier)
