# pycodex.responses_api_proxy

Python porting target for Rust `codex-responses-api-proxy`.

Rust coordinate:

- Crate: `codex-responses-api-proxy`
- Rust path: `codex/codex-rs/responses-api-proxy`
- Python package: `pycodex/responses_api_proxy`

Status: `complete`

Implemented module contracts:

- `src/read_api_key.rs` API-key stdin reader and header validation helpers.
- `src/dump.rs` request/response JSON dump helpers, including header redaction
  and response body tee behavior.
- `src/lib.rs` non-blocking proxy configuration and request/response projection
  helpers used by the existing CLI runtime.
- `src/main.rs` package entrypoint handoff through `run_main(...)` and
  `python -m pycodex.responses_api_proxy`, delegating to the existing CLI
  runtime path.

Native/runtime boundary:

- `src/main.rs` native pre-main hardening side effect remains a Rust binary
  boundary.

The existing CLI path delegates to this package-owned runtime.
