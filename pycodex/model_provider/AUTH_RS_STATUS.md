# `codex-model-provider/src/auth.rs` alignment status

Rust crate: `codex-model-provider`

Rust module: `src/auth.rs`

Python module: `pycodex/model_provider/auth.py`

Status: `complete`

Covered behavior:

- `UnauthenticatedAuthProvider` and `unauthenticated_auth_provider()` add no
  request headers.
- `auth_manager_for_provider()` keeps the caller auth manager unless the
  provider supplies command-backed auth, in which case it returns an external
  bearer-only manager.
- `resolve_provider_auth()` prefers provider-scoped API-key or experimental
  bearer-token auth before falling back to caller-supplied Codex auth.
- `bearer_auth_for_provider()` checks `provider.api_key()` before
  `experimental_bearer_token`.
- `auth_provider_from_auth()` maps bearer-like first-party auth snapshots to
  `BearerAuthProvider`.
- `AgentIdentityAuthProvider.add_auth_headers()` builds an AgentAssertion
  authorization header through `pycodex.agent_identity`, inserts valid
  account/FedRAMP routing headers, and skips invalid header values or signing
  failures like Rust's `HeaderValue::from_str(...).ok()` path.

Evidence:

- Rust source: `codex/codex-rs/model-provider/src/auth.rs`.
- Rust test: `unauthenticated_auth_provider_adds_no_headers`.
- Python tests: `tests/test_model_provider_auth_rs.py`.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_model_provider_auth_rs -v`
  passed on 2026-06-20 with `9 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/model_provider/auth.py tests/test_model_provider_auth_rs.py`
  passed on 2026-06-20.
