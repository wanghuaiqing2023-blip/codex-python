# codex-api/src/error.rs status

Rust module: `codex/codex-rs/codex-api/src/error.rs`

Python module: `pycodex/codex_api/error.py`

Status: `complete`

Ported contract:

- `ApiError` variants and user-facing display strings:
  `Transport`, `Api`, `Stream`, `ContextWindowExceeded`, `QuotaExceeded`,
  `UsageNotIncluded`, `Retryable`, `RateLimit`, `InvalidRequest`,
  `CyberPolicy`, and `ServerOverloaded`.
- `Retryable` retains the optional delay field while matching Rust display,
  which only includes the retryable message.
- `Transport` is transparent over multiple `TransportError` displays.
- `From<RateLimitError> for ApiError` is represented by
  `ApiError.from_rate_limit_error(...)`, preserving the source error's display
  text inside the `RateLimit` variant.

Intentional adaptation:

- Rust stores `http::StatusCode` and `std::time::Duration`. Python uses an
  integer/string status and optional float delay while formatting common HTTP
  statuses with standard-library `HTTPStatus` names.

Validation:

- `tests/test_codex_api_error_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_error_rs.py -q --tb=short`
  (`5 passed, 12 subtests passed`)
- Syntax validation:
  `python -m py_compile pycodex\codex_api\error.py tests\test_codex_api_error_rs.py`
- Codex API focused validation:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`209 passed, 47 subtests passed`)
