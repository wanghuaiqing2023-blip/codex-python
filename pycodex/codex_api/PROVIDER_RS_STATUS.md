# codex-api/src/provider.rs status

Rust module: `codex/codex-rs/codex-api/src/provider.rs`

Python module: `pycodex/codex_api/provider.py`

Status: `complete`

Ported contract:

- `RetryConfig::to_policy` conversion to the `codex-client` retry policy
  shape.
- `Provider::url_for_path` base/path slash normalization and direct query-param
  joining.
- `Provider::build_request` construction of a `codex-client` `Request` with
  cloned headers, no body, no timeout, and no compression.
- `Provider::is_azure_responses_endpoint` delegation.
- `Provider::websocket_url_for_path` scheme conversion: `http -> ws`,
  `https -> wss`, while `ws`, `wss`, and other schemes remain unchanged.
- `is_azure_responses_provider` and Azure marker matching, including the Rust
  unit-test positive and negative cases.

Intentional adaptation:

- Rust uses `http::Method`, `HeaderMap`, `Duration`, and `url::Url`. Python uses
  strings, dictionaries, float seconds, and standard-library `urllib.parse`
  while preserving the module-scoped behavior contract.

Validation:

- Focused validation passed on 2026-06-21:
  `python -m pytest tests/test_codex_api_provider_rs.py -q --tb=short`
  (`6 passed, 9 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_api\provider.py tests\test_codex_api_provider_rs.py`.
- Codex API focused validation passed on 2026-06-21:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`205 passed, 45 subtests passed`).
