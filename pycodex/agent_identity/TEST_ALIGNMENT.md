# codex-agent-identity test alignment

Rust crate: `codex-agent-identity`

Python package: `pycodex/agent_identity`

Status: `complete`

Module mapping:

- `codex/codex-rs/agent-identity/src/lib.rs` ->
  `pycodex/agent_identity/__init__.py` (`complete`)

Rust-derived/source-contract coverage implemented:

- `authorization_header_for_agent_task(...)` serializes an AgentAssertion
  envelope and rejects mismatched runtime ids.
- JWT payload decode maps claims and the raw `hc` plan alias.
- JWKS decode verifies trusted kid, issuer, audience, expiration, and RS256
  signatures with standard-library RSA verification.
- JWKS URL helper preserves backend-api and codex-api base URL behavior.
- Key-material helpers generate Ed25519 PKCS#8, derive SSH public keys, and
  sign task registration/assertion payloads.
- Registration response helper accepts direct `task_id` and `taskId` fields.
- Registration response helper decrypts encrypted task id responses through the
  Rust sealed-box pathway.
- Injected async fetch/register helpers preserve URL, timeout, status, and JSON
  error boundaries in a dependency-light form.

Validation:

- Focused validation:
  `python -m pytest tests/test_agent_identity_lib_rs.py -q`
  -> `11 passed`.
- Syntax validation:
  `python -m py_compile pycodex/agent_identity/__init__.py tests/test_agent_identity_lib_rs.py`
