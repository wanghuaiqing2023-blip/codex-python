# codex-client/src/default_client.rs status

Rust module: `codex/codex-rs/codex-client/src/default_client.rs`

Python module: `pycodex/codex_client/default_client.py`

Status: `complete`

Ported contract:

- `CodexHttpClient::get`, `post`, and `request` builder creation, including
  preserving the caller-supplied `request(...)` method token while `get()` and
  `post()` use the uppercase Rust method constants.
- `CodexRequestBuilder` chain methods for `headers`, `header`, `bearer_auth`, `timeout`, `json`, and `body`.
- Builder operations preserve prior builder values by returning a new builder.
- `bearer_auth<T: Display>` formats `Authorization: Bearer {token}`, replaces
  prior Authorization headers case-insensitively through HeaderMap semantics,
  and stores invalid header-value errors until `send` without dispatching.
- User-provided headers replace prior same-name entries case-insensitively,
  matching `http::HeaderMap`/reqwest `RequestBuilder` insertion semantics.
- `json()` mirrors reqwest content-type behavior: it inserts
  `content-type: application/json` when absent, respects existing content-type
  headers case-insensitively, and leaves that header in place when a later
  `body()` call replaces only the request body. A later `json()` call likewise
  replaces a previously configured raw body with the JSON body.
- Repeated `timeout()` calls preserve the last configured timeout value,
  matching the wrapped reqwest builder override semantics.
- Invalid user-supplied header names/values poison the builder until `send`,
  preserving the Rust `reqwest::RequestBuilder` stored-error behavior without
  invoking the sender.
- `send` injects trace headers at send time before delegating to the injected sender.
- Send-time trace headers replace same-name existing request headers, matching
  `send()` applying `builder.headers(trace_headers())` and reqwest
  `replace_headers()` immediately before dispatch, including differently
  cased prior header spellings.
- `send` emits Rust-shaped debug side-effect events after successful sends and
  before re-raising failed sends, covering method, URL, status, headers/version,
  and error text where applicable, including success field projection from
  reqwest-style `response.status()`, `response.headers()`, and
  `response.version()` methods, plus failure status projection from a
  reqwest-style `error.status()` method.
- Default `send` now delegates to the dependency-light standard-library HTTP
  sender through `ReqwestTransport`, preserving request body/header/timeout
  preparation and trace-header injection.
- `send_async()` provides a dependency-light async facade for Rust's async
  `CodexRequestBuilder::send` while preserving the same send-time trace-header
  injection, debug side effects, return value, and exception propagation.
- `trace_headers` accepts current span context/propagator-style input,
  projects valid `trace_id`/`span_id` fields into a W3C `traceparent` header,
  and filters invalid header names/values through an HTTP token/value
  validator.
- Send-time trace header injection filters invalid header names/values before
  merging them into the outgoing snapshot, matching `HeaderMapInjector::set`.

Intentional adaptation:

- Rust wraps `reqwest::RequestBuilder`, OpenTelemetry global propagators, and
  async `send`. Python exposes a dependency-light builder snapshot plus
  injected sender/trace-header provider/debug logger and uses the package's
  standard-library HTTP transport as the default sender. This keeps real local
  HTTP sending and deterministic debug-event verification available without
  adding an HTTP dependency or OpenTelemetry dependency.

Runtime debt:

- Full native reqwest-equivalent request builder/send runtime and full
  OpenTelemetry global propagator integration remain runtime debt. The
  module-local behavior contract is complete under the dependency-light porting
  policy: builder state, send-time trace header injection, HeaderMapInjector
  filtering, debug side effects, default real local HTTP send, and async facade
  behavior are covered.

Validation:

- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`26 passed`).
- Related transport/default-client regression passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`58 passed, 4 subtests passed`).
- Crate-focused Rust-derived pytest passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_chatgpt_cloudflare_cookies_rs.py tests/test_codex_client_chatgpt_hosts_rs.py tests/test_codex_client_custom_ca_rs.py tests/test_codex_client_default_client_rs.py tests/test_codex_client_error_retry_rs.py tests/test_codex_client_lib_rs.py tests/test_codex_client_request_rs.py tests/test_codex_client_sse_rs.py tests/test_codex_client_telemetry_rs.py tests/test_codex_client_transport_rs.py -q --tb=short`
  (`107 passed, 14 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_transport_rs.py tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`58 passed, 4 subtests passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\transport.py pycodex\codex_client\default_client.py tests\test_codex_client_transport_rs.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`107 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`25 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`104 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`23 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`100 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`19 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`95 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`17 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`92 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`15 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`87 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`13 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`85 tests`).
- `tests/test_codex_client_default_client_rs.py`
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`12 passed`).
- Syntax validation passed on 2026-06-21:
  `python -m py_compile pycodex\codex_client\default_client.py tests\test_codex_client_default_client_rs.py`.
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`81 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`12 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`79 tests`).
- Focused command passed on 2026-06-21:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`10 passed`).
- Crate-focused command passed on 2026-06-21:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`76 tests`).
- Focused command passed on 2026-06-21 after stricter header validation:
  `python -m pytest tests/test_codex_client_default_client_rs.py -q --tb=short`
  (`10 passed`).
- Crate-focused command passed on 2026-06-21 after stricter header validation:
  `python -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`76 tests`).
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_default_client_rs -v`
  (`9 tests`).
- Crate-focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_lib_rs tests.test_codex_client_custom_ca_rs tests.test_codex_client_chatgpt_cloudflare_cookies_rs tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
  (`71 tests`).
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_default_client_rs tests.test_codex_client_transport_rs tests.test_codex_client_sse_rs tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`
