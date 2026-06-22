# pycodex.agent_identity

Python alignment target for Rust crate `codex-agent-identity`.

Rust coordinates:

- `codex/codex-rs/agent-identity/src/lib.rs`

Python mapping:

- `pycodex/agent_identity/__init__.py`

Current status: complete.

Implemented module contract:

- Agent identity/task dataclasses and constants.
- Agent task assertion header serialization with Ed25519 signatures from
  Ed25519 PKCS#8 key material.
- Agent task registration signing and direct task id response extraction.
- Agent identity JWT payload decoding, raw plan alias mapping, JWKS kid lookup,
  issuer/audience/expiration validation, and pure-stdlib RS256 verification.
- Agent registration/JWKS/biscuit URL helpers and request id generation.
- Agent key material generation, SSH Ed25519 public-key encoding, verifying-key
  extraction, and Curve25519 scalar derivation.
- Encrypted task id sealed-box decryption using standard-library X25519,
  XSalsa20-Poly1305, and Poly1305 helpers.
- Injected async boundaries for JWKS fetch and task registration.
- ABOM helper projection.

Validation:

- Focused validation:
  `python -m pytest tests/test_agent_identity_lib_rs.py -q`
  -> `11 passed`.
- Syntax validation:
  `python -m py_compile pycodex/agent_identity/__init__.py tests/test_agent_identity_lib_rs.py`
