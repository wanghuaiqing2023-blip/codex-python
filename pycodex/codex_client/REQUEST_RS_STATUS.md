# codex-client/src/request.rs status

Rust module: `codex/codex-rs/codex-client/src/request.rs`

Python module: `pycodex/codex_client/request.py`

Status: `complete`

Ported contract:

- `RequestCompression` public enum shape for `None` and `Zstd`.
- `RequestBody::Json` and `RequestBody::Raw`, including `json()`-style access through `json_value`.
- `PreparedRequestBody` with `body_bytes()` returning empty bytes when body is absent.
- `Request::new`, `with_json`, `with_raw_body`, `with_compression`, and non-mutating `prepare_body_for_send`.
- JSON serialization with compact separators and default `content-type: application/json`.
- Rejection of compression on raw bodies.
- Rejection of compression when `content-encoding` is already present.
- `RequestCompression::Zstd` produces a valid Zstandard frame and sets
  `content-encoding: zstd`.
- Multi-block Zstandard raw-frame production for larger JSON byte payloads.
- `Response` public field shape.

Intentional adaptation:

- Rust `RequestCompression::Zstd` uses `zstd::stream::encode_all(..., 3)`.
  Python keeps the port dependency-light by emitting a standards-compliant
  Zstandard frame with raw blocks rather than byte-identical level-3 zstd
  output. HTTP peers still receive an actual `Content-Encoding: zstd` payload.

This adaptation is accepted for the module-scoped behavior contract because
the Rust tests do not assert native byte identity and the Python Rust-derived
tests prove the observable request contract: compact JSON serialization,
`content-encoding: zstd`, `content-type: application/json`, non-mutating
request preparation, and a decodable Zstandard payload containing the original
JSON bytes.

Validation:

- `tests/test_codex_client_request_rs.py`
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_request_rs.py -q --tb=short`
  (`8 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`72 tests`).
- Earlier focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
