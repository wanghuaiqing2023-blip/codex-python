# codex-api src/endpoint/responses_websocket.rs status

Rust crate: `codex-api`

Rust module: `src/endpoint/responses_websocket.rs`

Python package/module: `pycodex/codex_api/endpoint/responses_websocket.py`

Status: `complete` for helper, dependency-light stream/send
facade, and standard-library connect/probe projection slices.

Implemented Rust-derived behavior:

- Websocket config projection with permessage-deflate enabled.
- Wrapped websocket error event parsing, including `status` and `status_code`
  status fields, Rust `Option<u16>` invalid-type and range behavior, and
  nested error code/message extraction.
- Wrapped websocket error mapping to `ApiError::Transport(Http)` for
  non-success valid HTTP status values after the same
  `StatusCode::from_u16(...).ok()?` boundary as Rust, preserving original
  payload body and scalar JSON headers.
- Websocket connection-limit error mapping to retryable `ApiError`, including
  the Rust fallback message when the frame omits a message.
- JSON header scalar conversion for strings, numbers, and booleans, with
  arrays/objects ignored and invalid header names/values skipped through the
  same success-only insertion boundary as Rust `HeaderName::from_bytes` and
  `HeaderValue::from_str`.
- Request header merge precedence matching the HTTP path: provider headers are
  the base, extra headers overwrite them, and default headers fill only absent
  names, including Rust `HeaderMap` case-insensitive name matching.
- `send_websocket_request(...)` compact JSON request serialization, send-error
  and send-timeout mapping, explicit idle-timeout send boundary projection,
  concrete stdlib stream socket-timeout wrapping/restoration, and websocket
  request telemetry callback shape.
- `run_websocket_response_stream(...)` dependency-light event loop behavior:
  request send before polling, unsupported/invalid text ignoring, wrapped
  websocket error priority, rate-limit event mapping, server-model de-dupe,
  model-verification emission, regular Responses event processing, completed
  termination, binary/close/EOF/read-error/idle-timeout terminal errors, and
  websocket event telemetry callback shape.
- `ResponsesWebsocketConnection` dependency-light reusable connection behavior
  for server metadata prelude events, `send_response_processed(...)`,
  `stream_request(...)`, closed-connection errors, and closing the injected
  stream after terminal stream errors.
- `ResponsesWebsocketMemoryStream` and message marker classes provide the
  Python-only injection boundary for testing the Rust transport loop without
  adding a websocket dependency.
- `ResponsesWebsocketClient.new/connect/probe_handshake(...)` constructs the
  responses websocket URL, merges provider/extra/default headers, applies auth,
  captures turn-state side effects, projects response metadata, and reports
  immediate close frames from probe handshakes. Probe read timeouts while
  waiting for an immediate close frame are treated as `immediate_close=None`
  rather than stream errors, matching the Rust timeout `.ok().flatten()`
  projection.
- `connect_websocket(...)` provides a dependency-light standard-library
  websocket upgrade for `ws`/`wss`: handshake request construction, HTTP 101
  validation, non-101 HTTP transport-error mapping,
  `Upgrade: websocket`, `Connection: Upgrade`, and
  `Sec-WebSocket-Accept` validation, metadata header extraction, turn-state
  capture, masked text-frame sending, and text/binary/close/ping/pong frame
  reading. Its request-target
  projection preserves path and query while omitting fragments, and Host
  header construction now preserves bracketed IPv6 authorities. Secure `wss`
  connections select a standard-library SSL context through the same
  `codex-client` custom-CA environment precedence, and custom-CA setup
  failures map to the Rust-shaped stream error boundary. Non-101 HTTP error
  bodies use the same strict UTF-8 projection as Rust
  `String::from_utf8(...).ok()`, preserving valid UTF-8 bodies while clearing
  invalid-UTF-8 bodies instead of decoding lossily, and the standard-library
  handshake now drains Content-Length-delimited error bodies that arrive after
  the header read boundary before mapping them to `TransportError::Http`.
  The standard-library stream also mirrors the Rust `WsStream` send/read
  boundary: concrete sends observe the same idle-timeout boundary and restore
  the socket timeout afterward; server Ping frames are answered with masked
  Pong frames and filtered from callers, Pong frames are ignored, and
  text/binary/close/frame messages continue through the read boundary.
  Successful 101 upgrade responses project case-insensitive
  `x-codex-turn-state`, `x-reasoning-included`, `x-models-etag`, and
  `openai-model` headers into the same turn-state and metadata tuple returned
  by the Rust connector.
- `immediate_close_from_message(...)` mirrors the Rust close-frame probe helper
  by preserving close code and reason when the first probe frame is a close.

Completion note:

- Live TLS probe coverage is represented by
  `tests/test_codex_api_endpoint_responses_websocket_live_rs.py`. It requires
  a user-provided non-local `wss://` endpoint via
  `PYCODEX_LIVE_RESPONSES_WS_URL` plus either
  `PYCODEX_LIVE_RESPONSES_WS_HEADERS_JSON` or `OPENAI_API_KEY`; without those
  real credentials it is skipped rather than simulated. This is optional
  smoke coverage only, not a completion gate.
- `codex-cli/src/doctor.rs` consumption is now aligned with Rust: Python
  `doctor_websocket_check` creates a `ResponsesWebsocketClient` and calls
  `probe_handshake(...)`, so real doctor websocket diagnostics exercise this
  module's URL/header/auth/TLS upgrade boundary instead of a separate generic
  websocket path.

Validation:

- `python -m py_compile tests\test_codex_api_endpoint_responses_websocket_live_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_live_rs.py -q --tb=short -rs`
  skipped on 2026-06-21 because `PYCODEX_LIVE_RESPONSES_WS_URL` was not set;
  this is the expected no-credentials behavior for the optional live smoke
  check.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `38 passed, 10 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `72 passed, 17 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `252 passed, 1 skipped, 81 subtests passed`; the
  skipped test is the optional live-only websocket smoke check without
  configured real endpoint credentials.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `250 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_cli_doctor_updates.py -k "doctor_websocket_check or websocket_probe_warning or dns_address_family_details" -q --tb=short`
  passed on 2026-06-21 with `9 passed, 433 deselected`, covering the Rust
  doctor caller dispatch through this module's `ResponsesWebsocketClient`.
- `python -m pytest tests/test_cli_doctor_updates.py -k "websocket_error_detail or doctor_websocket_check or websocket_probe_warning or dns_address_family_details" -q --tb=short`
  passed on 2026-06-21 with `12 passed, 433 deselected`, including endpoint
  query preservation through the codex-api `Provider` boundary.
- `python -m py_compile pycodex/cli/doctor_updates.py tests/test_cli_doctor_updates.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `35 passed, 8 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `69 passed, 15 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `249 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `34 passed, 8 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `68 passed, 15 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `248 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `33 passed, 8 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `67 passed, 15 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `244 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `32 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `63 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `205 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `31 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `62 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `204 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `30 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `61 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `203 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `29 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `200 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `27 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `198 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `26 passed, 5 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `197 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `25 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `196 passed, 45 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `55 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `194 passed, 45 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\responses_websocket.py tests\test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-21 with `22 passed, 5 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-21 with `53 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `189 passed, 42 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py -q --tb=short`
  passed on 2026-06-20 with `21 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/responses_websocket.py pycodex/codex_api/endpoint/__init__.py tests/test_codex_api_endpoint_responses_websocket_rs.py`
  passed on 2026-06-20.
- `python -m pytest tests/test_codex_api_endpoint_responses_websocket_rs.py tests/test_codex_api_sse_responses_rs.py tests/test_codex_api_endpoint_responses_rs.py tests/test_codex_api_common_rs.py -q --tb=short`
  passed on 2026-06-20 with `52 passed, 10 subtests passed`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-20 with
  `185 passed, 42 subtests passed`.
- `python -m py_compile` over PowerShell-expanded `pycodex/codex_api/**/*.py`
  package modules and `tests/test_codex_api_*_rs.py` passed on 2026-06-20.
