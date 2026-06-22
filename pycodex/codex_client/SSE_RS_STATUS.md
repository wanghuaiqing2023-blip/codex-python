# codex-client/src/sse.rs status

Rust module: `codex/codex-rs/codex-client/src/sse.rs`

Python module: `pycodex/codex_client/sse.py`

Status: `complete`

Ported contract:

- Forward raw SSE `data:` frames as UTF-8 strings.
- Preserve multi-line SSE data by joining lines with `\n`.
- Convert transport errors into `StreamError::Stream`-equivalent results.
- Convert parser/UTF-8 errors into `StreamError::Stream`-equivalent results.
- Report `stream closed before completion` when upstream ends.
- Report `StreamError::Timeout` on idle timeout.

Intentional adaptation:

- Rust `sse_stream` spawns a Tokio task and sends `Result<String, StreamError>` values through an mpsc channel. Python exposes the same result sequence as a synchronous iterator of `SseResult` values to preserve the behavior contract without adding async/runtime dependencies.

Validation:

- `tests/test_codex_client_sse_rs.py`
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`

