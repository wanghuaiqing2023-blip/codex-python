# auth/agent_identity.rs alignment

Rust crate: `codex-login`

Rust module: `codex/codex-rs/login/src/auth/agent_identity.rs`

Python module: `pycodex/login/auth/agent_identity.py`

Status: `complete`

Aligned behavior:

- `agent_identity_authapi_base_url()` prefers
  `CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL`, trims whitespace and trailing slashes,
  ignores empty values, and falls back to the production auth API URL.
- `key()` maps `AgentIdentityAuthRecord.agent_runtime_id` and
  `agent_private_key` into an `AgentIdentityKey`.
- `AgentIdentityAuth.load()` models Rust's async registration flow through an
  injectable registrar, returning an auth object with the record and process
  task id.
- `AgentIdentityAuth` exposes record, process task id, account id, ChatGPT user
  id, email, plan type, and FedRAMP account helpers.

Rust tests and Python parity coverage:

- Rust `agent_identity_authapi_base_url_prefers_env_value` ->
  `tests/test_login_agent_identity.py::test_agent_identity_authapi_base_url_prefers_trimmed_env_value`
- Rust `agent_identity_authapi_base_url_uses_prod_authapi_by_default` ->
  `tests/test_login_agent_identity.py::test_agent_identity_authapi_base_url_uses_prod_by_default`
- Source-contract coverage for key mapping and injectable registration is in
  `tests/test_login_agent_identity.py`.

Validation:

- Not run in this turn; current automation defers actual test execution until the crate functional code is complete.
