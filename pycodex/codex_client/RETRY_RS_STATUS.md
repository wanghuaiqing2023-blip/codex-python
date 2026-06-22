# codex-client/src/retry.rs status

Rust module: `codex/codex-rs/codex-client/src/retry.rs`

Python module: `pycodex/codex_client/retry.py`

Status: `complete`

Ported contract:

- `RetryOn.should_retry` max-attempt boundary.
- HTTP retry policy for 429 and 5xx responses.
- Transport retry policy for timeout and network errors.
- Non-retryable build and retry-limit errors.
- Exponential backoff with Rust's attempt-zero base-delay shortcut and 0.9..1.1 jitter range.
- `run_with_retry` rebuilds a request per attempt, passes attempt index to the operation, sleeps between retryable failures, returns on first success, and returns the terminal non-retryable error at the max-attempt boundary.

Intentional adaptation:

- Rust uses async `tokio::time::sleep` and `Request`; Python exposes a synchronous helper with injectable `sleep` and generic request values so the retry contract can be validated without adding async or HTTP dependencies.

Validation:

- `tests/test_codex_client_error_retry_rs.py`
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`

