"""Port of Rust ``codex-login::pkce``.

Rust source:
- ``codex/codex-rs/login/src/pkce.rs``
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class PkceCodes:
    code_verifier: str
    code_challenge: str


def generate_pkce() -> PkceCodes:
    code_verifier = _base64url_bytes(secrets.token_bytes(64))
    return PkceCodes(
        code_verifier=code_verifier,
        code_challenge=code_challenge_for_verifier(code_verifier),
    )


def code_challenge_for_verifier(code_verifier: str) -> str:
    digest = sha256(code_verifier.encode("ascii")).digest()
    return _base64url_bytes(digest)


def _base64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


__all__ = [
    "PkceCodes",
    "code_challenge_for_verifier",
    "generate_pkce",
]
