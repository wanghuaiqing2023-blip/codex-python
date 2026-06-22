# codex-api/src/auth.rs status

Rust module: `codex/codex-rs/codex-api/src/auth.rs`

Python module: `pycodex/codex_api/auth.py`

Status: `complete`

Ported contract:

- `AuthError::Build` and `AuthError::Transient` display strings.
- `From<AuthError> for TransportError` mapping: build errors become transport
  build errors, transient auth errors become transport network errors.
- `AuthProvider::to_auth_headers` builds a fresh header map through
  `add_auth_headers`, preserving Rust `HeaderMap` case-insensitive replacement
  semantics.
- Default `AuthProvider::apply_auth` adds header-only auth to the outbound
  request, replaces equivalent header names regardless of casing, and returns
  the new request as authoritative.
- `AuthHeaderTelemetry` and `auth_header_telemetry` report whether an
  authorization header is attached.

Intentional adaptation:

- Rust uses `async_trait`, `http::HeaderMap`, and `Arc<dyn AuthProvider>`.
  Python uses an async protocol method over standard dictionaries and the
  existing `pycodex.codex_client.Request` value object. `SharedAuthProvider`
  is a type alias because Python references already provide shared handles.

Validation:

- `tests/test_codex_api_auth_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_auth_rs.py -q --tb=short`
  (`5 passed`)
- Syntax validation:
  `python -m py_compile pycodex\codex_api\auth.py tests\test_codex_api_auth_rs.py`
- Codex API focused validation:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`208 passed, 45 subtests passed`)
