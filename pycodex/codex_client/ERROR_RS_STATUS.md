# codex-client/src/error.rs status

Rust module: `codex/codex-rs/codex-client/src/error.rs`

Python module: `pycodex/codex_client/error.py`

Status: `complete`

Ported contract:

- `TransportError::Http` with status, optional URL, optional headers, and optional body.
- `TransportError::RetryLimit`, `Timeout`, `Network`, and `Build`.
- `StreamError::Stream` and `Timeout`.
- Rust `thiserror` display strings are mirrored by Python `__str__`.

Validation:

- `tests/test_codex_client_error_retry_rs.py`
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`

