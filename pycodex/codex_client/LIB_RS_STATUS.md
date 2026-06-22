# codex-client src/lib.rs

Rust source: `codex/codex-rs/codex-client/src/lib.rs`

Python target: `pycodex/codex_client/__init__.py`

Status: `complete`

Implemented behavior:

- Crate-root facade re-exports all Rust `pub use` symbols:
  `with_chatgpt_cloudflare_cookie_store`, `is_allowed_chatgpt_host`,
  `BuildCustomCaTransportError`, `build_reqwest_client_for_subprocess_tests`,
  `build_reqwest_client_with_custom_ca`,
  `maybe_build_rustls_client_config_with_custom_ca`, `CodexHttpClient`,
  `CodexRequestBuilder`, `StreamError`, `TransportError`,
  `PreparedRequestBody`, `Request`, `RequestBody`, `RequestCompression`,
  `Response`, `RetryOn`, `RetryPolicy`, `backoff`, `run_with_retry`,
  `sse_stream`, `RequestTelemetry`, `ByteStream`, `HttpTransport`,
  `ReqwestTransport`, and `StreamResponse`.
- Facade exports point at canonical sibling modules rather than package-local
  compatibility copies.

Intentional adaptation:

- Python exposes a few additional testing/helper names from sibling modules.
  The Rust parity contract here is that every Rust crate-root public export is
  present and canonical; extra Python helpers remain package-local convenience
  surface and do not change the Rust facade evidence.

Validation:

- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs -v`
  passed on 2026-06-20 with `2 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `62 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile`
  over all `pycodex/codex_client` modules and Rust-derived codex-client tests
  passed on 2026-06-20.
