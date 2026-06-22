# codex-client/src/transport.rs status

Rust module: `codex/codex-rs/codex-client/src/transport.rs`

Python module: `pycodex/codex_client/transport.py`

Status: `complete`

Ported contract:

- `ByteStream` public alias role.
- `StreamResponse` public field shape.
- `HttpTransport` structural interface with unary `execute` and streaming `stream`.
- `request_body_for_trace` branches for JSON, raw bodies, and absent bodies.
- `ReqwestTransport` request build behavior using `Request.prepare_body_for_send`.
- Build-time HTTP method normalization that preserves valid extension method
  tokens, including their original case, and falls back to GET only for invalid
  method tokens, matching `Method::from_bytes(...).unwrap_or(Method::GET)`.
- Build-error mapping to `TransportError::Build`.
- Timeout/network error mapping.
- Execute/stream send failures before any response is available map through
  `ReqwestTransport::map_error`, so timeouts become `TransportError::Timeout`
  and non-timeout failures become `TransportError::Network`.
- Unary success response shape.
- Unary successful-status body-read failures map through
  `ReqwestTransport::map_error` before returning a `Response`, so non-timeout
  read errors become `TransportError::Network`.
- Unary and streaming non-success HTTP error mapping with URL, headers, status, and body.
- Unary non-success responses preserve Rust's read-body-before-status ordering:
  a response body read timeout maps to `TransportError::Timeout` before an
  HTTP status error can be constructed.
- Unary non-success body-read non-timeout failures follow the same ordering and
  map to `TransportError::Network` before an HTTP status error can be
  constructed.
- Unary non-success response bodies use Rust's strict
  `String::from_utf8(...).ok()` projection, so invalid UTF-8 clears the
  optional HTTP error body without replacing the HTTP status error.
- Streaming non-success response bodies use Rust reqwest `Response::text`
  semantics, preserving malformed UTF-8 with replacement characters when body
  reading succeeds.
- Streaming non-success HTTP responses preserve HTTP error classification even
  when reading the error body fails, matching Rust's `resp.text().await.ok()`
  body projection.
- Streaming non-success HTTP responses also preserve HTTP error classification
  when reading the error body times out, clearing only the optional body rather
  than returning `TransportError::Timeout`.
- Streaming success response shape with byte stream handoff.
- Streaming success fallback body projection never yields empty chunks or
  non-byte `None` items, preserving Rust's
  `ByteStream = Result<Bytes, TransportError>` item shape for
  dependency-light injected senders.
- Streaming response-body read errors are mapped through the same
  `ReqwestTransport::map_error` boundary, including timeout and non-timeout
  errors that occur after response headers are received.
- Standard-library real HTTP unary body reading and streaming response-body
  iteration for localhost validation.
- HTTPS connection construction honors the selected custom CA bundle by loading
  an `ssl` context from `CODEX_CA_CERTIFICATE` / `SSL_CERT_FILE`.
- Dependency-light standard-library request-target projection preserves path
  and query, defaults an empty path to `/`, and excludes URL fragments,
  matching the request target shape produced by reqwest for the supplied URL.
- Execute/stream trace emission before sending, using the Rust message shape
  `METHOD to URL: BODY`.
- Execute/stream trace emission happens before request building, so body trace
  formatting is still observable when `Request.prepare_body_for_send` fails.
- `execute_async()` and `stream_async()` provide a dependency-light async
  facade for Rust's async `HttpTransport::execute` and `HttpTransport::stream`
  trait methods while preserving the same trace/build/send/status/error path.

Intentional adaptation:

- Rust wraps `reqwest::Client` and performs real async HTTP. Python keeps the
  injected sender callable for deterministic unit coverage and now also
  provides a standard-library HTTP sender built on `http.client` for real
  localhost HTTP request/stream validation without adding a dependency.

Runtime debt:

- Rust uses `reqwest::Client` on Tokio. Python intentionally keeps the
  dependency-light standard-library transport and injected sender boundary.
  Native reqwest/Tokio error text identity and generated local TLS handshake
  probes are integration/runtime debt, not remaining module-local
  `transport.rs` behavior gaps; the standard-library sender covers real HTTP
  request dispatch/status/header/body handling, real streaming response body
  iteration, HTTPS custom-CA context selection, and trace message emission.

Validation:

- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`58 passed, 4 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py pycodex\codex_client\default_client.py tests\test_codex_client_transport_rs.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`107 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`31 passed, 4 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`105 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`30 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`102 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`28 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`98 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`26 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`90 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`25 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`89 tests`).
- `tests/test_codex_client_transport_rs.py`
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`23 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`84 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`21 passed, 2 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex/codex_client/transport.py tests/test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`82 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`21 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex/codex_client/transport.py tests/test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`82 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`20 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`81 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`19 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py tests\test_codex_client_transport_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`80 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`18 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`77 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`17 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`75 tests`).
- Earlier focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py -q --tb=short`
  (`15 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`73 tests`).
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs -v`
  (`14 tests`).
- Crate-focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`69 tests`).
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
