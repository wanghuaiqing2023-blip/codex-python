# codex-agent-identity src/lib.rs status

Rust source:

- `codex/codex-rs/agent-identity/src/lib.rs`

Python target:

- `pycodex/agent_identity/__init__.py`

Status: complete.

Implemented:

- Agent identity key, task target, bill of materials, generated key material,
  and JWT claim shapes.
- AgentAssertion authorization header construction with Ed25519 signatures.
- JWT payload decode and JWKS-backed RS256 verification with issuer/audience
  checks.
- Task registration payload signatures and direct task id response extraction.
- Key generation/public-key/verifying-key/Curve25519 scalar helpers.
- Encrypted task id response sealed-box decryption.
- Agent registration, task registration, biscuit, JWKS, request-id, and ABOM
  helpers.
- Injected async JWKS fetch and task registration request boundaries.

Validation:

- Focused validation:
  `python -m pytest tests/test_agent_identity_lib_rs.py -q`
  -> `11 passed`.
- Syntax validation:
  `python -m py_compile pycodex/agent_identity/__init__.py tests/test_agent_identity_lib_rs.py`
