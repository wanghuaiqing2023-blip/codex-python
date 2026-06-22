# codex-client test alignment

Rust crate: `codex-client`

Python package: `pycodex/codex_client`

Status: `complete`

Module mapping:

- `codex/codex-rs/codex-client/src/chatgpt_cloudflare_cookies.rs` ->
  `pycodex/codex_client/chatgpt_cloudflare_cookies.py` (`complete`)
- `codex/codex-rs/codex-client/src/custom_ca.rs` ->
  `pycodex/codex_client/custom_ca.py` (`complete`; real reqwest/rustls TLS
  registration and local TLS handshake probes remain runtime debt)
- `codex/codex-rs/codex-client/src/chatgpt_hosts.rs` ->
  `pycodex/codex_client/chatgpt_hosts.py` (`complete`)
- `codex/codex-rs/codex-client/src/error.rs` ->
  `pycodex/codex_client/error.py` (`complete`)
- `codex/codex-rs/codex-client/src/retry.rs` ->
  `pycodex/codex_client/retry.py` (`complete`)
- `codex/codex-rs/codex-client/src/request.rs` ->
  `pycodex/codex_client/request.py` (`complete`; Python intentionally emits a
  valid dependency-light Zstandard raw-block frame rather than byte-identical
  native zstd level-3 output)
- `codex/codex-rs/codex-client/src/telemetry.rs` ->
  `pycodex/codex_client/telemetry.py` (`complete`)
- `codex/codex-rs/codex-client/src/sse.rs` ->
  `pycodex/codex_client/sse.py` (`complete`)
- `codex/codex-rs/codex-client/src/transport.rs` ->
  `pycodex/codex_client/transport.py` (`complete`; dependency-light async
  facade and standard-library real HTTP projection covered; native
  reqwest/Tokio error-text identity and generated TLS probes remain runtime
  debt)
- `codex/codex-rs/codex-client/src/default_client.rs` ->
  `pycodex/codex_client/default_client.py` (`complete`; dependency-light
  traceparent span-context projection, real local HTTP send, async send facade,
  and debug side effects covered; full native reqwest/OpenTelemetry integration
  remains runtime debt)
- `codex/codex-rs/codex-client/src/lib.rs` ->
  `pycodex/codex_client/__init__.py` (`complete`)

Rust behavior covered in `tests/test_codex_client_chatgpt_hosts_rs.py`:

- `recognizes_chatgpt_hosts_without_suffix_tricks`

Rust behavior covered in `tests/test_codex_client_chatgpt_cloudflare_cookies_rs.py`:

- `stores_and_returns_cloudflare_cookies_for_chatgpt_hosts`
- `ignores_non_chatgpt_cookies`
- `ignores_non_cloudflare_cookies_for_chatgpt_hosts`
- `ignores_mixed_non_cloudflare_cookies_for_chatgpt_hosts`
- `does_not_return_chatgpt_cloudflare_cookies_for_other_hosts`
- `rejects_plain_http_chatgpt_cookie_urls`
- `only_allows_https_urls`
- `allows_only_known_cloudflare_cookie_names`
- Public builder hook behavior for `with_chatgpt_cloudflare_cookie_store`.

Rust-derived behavior covered in `tests/test_codex_client_custom_ca_rs.py`:

- Rust unit tests `ca_path_prefers_codex_env`,
  `ca_path_falls_back_to_ssl_cert_file`, `ca_path_ignores_empty_values`,
  `rustls_config_uses_custom_ca_bundle_when_configured`, and
  `rustls_config_reports_invalid_ca_file`.
- Integration-test contracts from `tests/ca_env.rs` for multi-certificate
  bundles, OpenSSL `TRUSTED CERTIFICATE` acceptance, CRL ignoring, malformed
  PEM hints, and subprocess-test `no_proxy()` behavior.
- `BuildCustomCaTransportError` user-facing variant messages, DER first-item
  trimming, and dependency-light reqwest/rustls registration boundaries from
  `src/custom_ca.rs`.

Rust-derived behavior covered in `tests/test_codex_client_error_retry_rs.py`:

- `TransportError` and `StreamError` variant display strings from `src/error.rs`.
- `RetryOn.should_retry` HTTP 429, HTTP 5xx, timeout/network, non-retryable, and max-attempt branches from `src/retry.rs`.
- `backoff` attempt-zero and jittered exponential behavior from `src/retry.rs`.
- `run_with_retry` request rebuilding, attempt indexing, success, non-retryable error, and max-attempt terminal error behavior from `src/retry.rs`.

Rust-derived behavior covered in `tests/test_codex_client_request_rs.py`:

- Rust test `prepare_body_for_send_serializes_json_and_sets_content_type`.
- Rust test `prepare_body_for_send_rejects_existing_content_encoding_when_compressing`.
- Raw body preparation, raw compression rejection, non-mutating header/body preparation, `PreparedRequestBody.body_bytes`, and `Response` public field shape from `src/request.rs`.
- Zstd request compression byte production, `content-encoding: zstd`, and
  larger JSON payload block splitting through a dependency-light raw-block
  Zstandard frame.

Rust-derived behavior covered in `tests/test_codex_client_telemetry_rs.py`:

- `RequestTelemetry::on_request` argument contract from `src/telemetry.rs`.
- Structural implementor acceptance, matching Rust's trait-object role.
- Optional status/error values.

Rust-derived behavior covered in `tests/test_codex_client_sse_rs.py`:

- Raw SSE `data:` frame forwarding from `src/sse.rs`.
- Chunk-boundary handling, multi-line data joining, transport/parser error mapping,
  closed-before-completion error, and idle-timeout error branches.

Rust-derived behavior covered in `tests/test_codex_client_transport_rs.py`:

- `request_body_for_trace` JSON/raw/empty branches.
- `ReqwestTransport::build` request preparation and build-error mapping.
- `ReqwestTransport::build` method conversion via
  `Method::from_bytes(...).unwrap_or(Method::GET)`, including valid extension
  methods, original valid-token case preservation, and invalid-token fallback.
- Timeout/network error mapping.
- Send-stage timeout/network failures before response headers are available
  map through `builder.send().await.map_err(Self::map_error)?`.
- Unary success and non-success HTTP response handling.
- Unary successful-status body-read failures are mapped through
  `Self::map_error` before a `Response` is returned, so non-timeout read errors
  become `TransportError::Network`.
- Unary non-success response body-read timeout ordering from
  `execute()`: `resp.bytes().await.map_err(Self::map_error)?` happens before
  status inspection, so a read timeout returns `TransportError::Timeout`
  rather than `TransportError::Http`.
- Unary non-success response body-read non-timeout failures follow the same
  read-body-before-status ordering and return `TransportError::Network`
  rather than `TransportError::Http`.
- Unary non-success response body decoding uses
  `String::from_utf8(bytes.to_vec()).ok()`, so invalid UTF-8 clears the
  optional HTTP error body while preserving status, URL, and headers.
- Streaming success and non-success HTTP response handling.
- Streaming non-success response body decoding follows
  `resp.text().await.ok()`; reqwest text decoding replaces malformed UTF-8
  rather than clearing the body.
- Streaming success fallback body projection preserves the Rust `ByteStream`
  item shape by yielding only non-empty bytes or `TransportError`, never empty
  chunks or `None`.
- Streaming non-success HTTP response body-read failures preserve the HTTP
  error classification with `body=None`, matching the Rust
  `resp.text().await.ok()` projection.
- Streaming non-success HTTP response body-read timeouts preserve the HTTP
  error classification with `body=None`, matching the same
  `resp.text().await.ok()` projection instead of returning
  `TransportError::Timeout`.
- `StreamResponse` and `HttpTransport` public shapes.
- Dependency-light real HTTP dispatch via the standard-library sender for
  localhost request/status/header validation and streaming byte iteration.
- Real unary body reading through the standard-library sender.
- HTTPS custom-CA context selection from `CODEX_CA_CERTIFICATE` /
  `SSL_CERT_FILE` before connection construction.
- Dependency-light standard-library request-target projection preserves path
  and query, defaults an empty path to `/`, and excludes URL fragments.
- Execute/stream trace emission before send using Rust's `METHOD to URL: BODY`
  message shape.
- Dependency-light async `execute_async()` and `stream_async()` facades preserve
  Rust's async `HttpTransport::execute`/`stream` contract while reusing the same
  trace/build/send/status/error behavior.
- Streaming response-body read timeout mapping through
  `bytes_stream().map(Self::map_error)` semantics.
- Streaming response-body non-timeout read errors map to
  `TransportError::Network` stream items through the same
  `bytes_stream().map(Self::map_error)` boundary.

Rust-derived behavior covered in `tests/test_codex_client_default_client_rs.py`:

- `CodexHttpClient::get`, `post`, and `request` builder creation.
- `CodexHttpClient::request` preserves the supplied method token while
  `get()` and `post()` use the uppercase Rust method constants.
- Builder method chaining for headers, single header, bearer auth, timeout,
  JSON body, and raw body.
- `bearer_auth<T: Display>` formatting as `Authorization: Bearer {token}`,
  case-insensitive Authorization replacement, and invalid Display output
  preserved as a send-time builder error.
- HeaderMap-style case-insensitive replacement for user-provided headers
  through both `header()` and `headers()`.
- Reqwest-style `json()` content-type behavior: insert `content-type:
  application/json` when absent, respect existing content-type
  case-insensitively, and preserve the JSON content-type header when a later
  `body()` call replaces only the request body.
- Builder override ordering for later `json()` replacing a previously
  configured raw body, and repeated `timeout()` using the last configured
  value.
- User-supplied invalid header names/values are retained as builder errors
  until `send`, which fails before invoking the sender.
- Send-time trace header injection.
- Send-time trace-header duplicate-key precedence over existing request
  headers, matching `send()` calling `builder.headers(trace_headers())` and
  reqwest `replace_headers()` replacement semantics, including differently
  cased prior header spellings.
- Send-time invalid trace-header filtering through the `HeaderMapInjector::set`
  success-only insertion contract, including invalid token characters, control
  bytes, and non-ASCII value rejection.
- Dependency-light `trace_headers` projection from valid span-context
  `trace_id`/`span_id` fields to the W3C `traceparent` header shape used by
  OpenTelemetry TraceContext propagation.
- `send()` success and failure debug side effects, including method, URL,
  status, response headers/version, error text, reqwest-style success
  `response.status()`/`headers()`/`version()` projection, and reqwest-style
  failure `error.status()` projection.
- Default `send()` path through the dependency-light standard-library HTTP
  transport, including real local request body/header forwarding.
- Dependency-light `send_async()` facade preserves Rust's async
  `CodexRequestBuilder::send` contract while reusing the same send-time trace
  header injection, debug side effect, result, and exception path.
- Rust test `inject_trace_headers_uses_current_span_context` adapted to the
  dependency-light trace-header boundary.

Rust-derived behavior covered in `tests/test_codex_client_lib_rs.py`:

- Crate-root `pub use` facade from `src/lib.rs`.
- Re-export identity checks ensuring package-root names point at canonical
  sibling module implementations.

Validation:

- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `26 passed`.
- `python -m pytest tests/test_codex_client_transport_rs.py tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `58 passed, 4 subtests passed`.
- Crate-focused Rust-derived pytest over the codex-client test set passed on
  2026-06-21 with `107 passed, 14 subtests passed`.
- `python -m pytest tests/test_codex_client_transport_rs.py tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `58 passed, 4 subtests passed`.
- `python -m py_compile pycodex\codex_client\transport.py pycodex\codex_client\default_client.py tests\test_codex_client_transport_rs.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `107 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `25 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `104 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `30 passed, 2 subtests passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `102 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `23 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `100 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `28 passed, 2 subtests passed`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `19 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `95 tests`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `93 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `17 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `92 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `26 passed, 2 subtests passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `90 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `25 passed, 2 subtests passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `89 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `87 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `13 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `85 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `23 passed, 2 subtests passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `84 tests`.
- `python -m pytest tests/test_codex_client_request_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `12 passed`.
- `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `81 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `12 passed`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `20 passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `81 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `19 passed`.
- `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `80 tests`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `79 tests`.
- `python -m pytest tests/test_codex_client_request_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `18 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `77 tests`.
- `python -m pytest tests/test_codex_client_request_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `72 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `73 tests`.
- `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `17 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `75 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 with `10 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 with `76 tests`.
- `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  passed on 2026-06-21 after stricter header validation with `10 passed`.
- `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-21 after stricter header validation with `76 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `62 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `64 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `65 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `67 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `71 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_default_client_rs -v`
  passed on 2026-06-20 with `9 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `69 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs -v`
  passed on 2026-06-20 with `14 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs -v`
  passed on 2026-06-20 with `12 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_default_client_rs -v`
  passed on 2026-06-20 with `7 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs -v`
  passed on 2026-06-20 with `10 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs -v`
  passed on 2026-06-20 with `2 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `45 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `60 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_custom_ca_rs -v`
  passed on 2026-06-20 with `15 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `36 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `30 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `22 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `16 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `14 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `7 tests`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_chatgpt_hosts_rs -v`
  passed on 2026-06-20 with `1 test`.
- `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m py_compile pycodex/codex_client/__init__.py pycodex/codex_client/chatgpt_hosts.py pycodex/codex_client/chatgpt_cloudflare_cookies.py pycodex/codex_client/custom_ca.py pycodex/codex_client/default_client.py pycodex/codex_client/error.py pycodex/codex_client/retry.py pycodex/codex_client/request.py pycodex/codex_client/telemetry.py pycodex/codex_client/sse.py pycodex/codex_client/transport.py tests/test_codex_client_lib_rs.py tests/test_codex_client_chatgpt_hosts_rs.py tests/test_codex_client_chatgpt_cloudflare_cookies_rs.py tests/test_codex_client_custom_ca_rs.py tests/test_codex_client_default_client_rs.py tests/test_codex_client_error_retry_rs.py tests/test_codex_client_request_rs.py tests/test_codex_client_telemetry_rs.py tests/test_codex_client_sse_rs.py tests/test_codex_client_transport_rs.py`
  passed on 2026-06-20.

Deferred:

- Latest `src/transport.rs` trace-before-build-error validation:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `31 passed, 4 subtests passed`;
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`
  passed; crate-focused unittest passed with `105 tests`.
- Real custom-CA reqwest/rustls TLS registration and local TLS handshake probes
  remain runtime validation debt.
- Rust `zstd::stream::encode_all(..., 3)` byte identity remains an accepted
  dependency-light adaptation in complete `src/request.rs` coverage.
- Complete `src/transport.rs` real HTTP client integration and async stream
  adapter after the dependency/runtime boundary is chosen.
- Full native reqwest/OpenTelemetry send integration remains runtime debt
  outside the dependency-light `src/default_client.rs` module contract.
