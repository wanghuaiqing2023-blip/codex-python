# codex-api/src/endpoint/realtime_websocket methods status

Rust modules:

- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/protocol.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/methods_common.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/methods_v1.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/methods_v2.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/methods.rs`

Python modules:

- `pycodex/codex_api/endpoint/realtime_websocket/protocol.py`
- `pycodex/codex_api/endpoint/realtime_websocket/methods_common.py`
- `pycodex/codex_api/endpoint/realtime_websocket/methods_v1.py`
- `pycodex/codex_api/endpoint/realtime_websocket/methods_v2.py`
- `pycodex/codex_api/endpoint/realtime_websocket/methods.py`

Status: `complete` for the pure outbound-message/session helper slice.

Status: `complete` for the websocket
URL/config, active-transcript helper, dependency-light read/write facade, and
standard-library connect/session-update projection slices, including the
dependency-light custom-CA SSL context selection/error projection for `wss`
and local `ws://` mock-server handshake/frame exchange validation.

Implemented behavior:

- `RealtimeEventParser`, `RealtimeSessionMode`, and `RealtimeSessionConfig`
  mirror the Rust public helper surface needed by realtime websocket and
  realtime call session setup.
- `normalized_session_mode(...)` preserves Rust V1 behavior by forcing
  conversational mode while Realtime V2 preserves the requested mode.
- `conversation_item_create_message(...)` emits V1/V2 user text
  `conversation.item.create` JSON.
- `conversation_function_call_output_message(...)` emits V1
  `conversation.handoff.append` with the Rust final-message prefix and V2
  `function_call_output` item JSON.
- `session_update_session_json(...)` emits V1 quicksilver, V2 realtime, and V2
  transcription session JSON with Rust audio format, transcription, tools,
  output modality, voice, id, and model behavior, including Rust
  `skip_serializing_if = Option::is_none` omission for absent `id` and
  `model`.
- `websocket_intent(...)` emits V1 `quicksilver` and V2 `None`.
- `websocket_url_from_api_url(...)` mirrors Rust scheme conversion, realtime
  path normalization, intent/model append order, and extra query filtering.
- `websocket_url_from_api_url_for_call(...)` appends sideband `call_id` after
  base realtime URL construction.
- `websocket_config()` is a dependency-light placeholder for Rust
  `WebSocketConfig::default()`; concrete websocket runtime remains deferred.
- `RealtimeActiveTranscript.update_active_transcript(...)` mirrors Rust
  active transcript mutation for transcript deltas/done events, handoff
  injection, response-created output boundaries, and speech-started input
  boundaries.
- `append_transcript_delta(...)`, `apply_transcript_done(...)`,
  `append_handoff_input(...)`, and `contains_transcript_entry(...)` mirror the
  Rust low-level transcript helpers.
- `RealtimeWebsocketWriter`, `RealtimeWebsocketEvents`, and
  `RealtimeWebsocketConnection` mirror the Rust send/close/next-event behavior
  at an injectable stream/message boundary: outbound JSON helpers, idempotent
  close and closed-send errors, send/close/read error mapping, ignored
  ping/pong/frame/unsupported text events, binary frame error events, close
  frame termination, and active-transcript updates while parsing events.
- `RealtimeWebsocketClient` mirrors the Rust connect URL/header/session setup:
  provider base/query/model URL construction, provider/extra/default
  case-insensitive header precedence, `x-session-id` insertion with
  case-insensitive replacement and Rust `HeaderValue::from_str`-style value
  validation, connector error mapping, WebRTC sideband `call_id` joins with
  retry attempts, websocket stream adaptation, dependency-light custom-CA SSL
  context selection/error projection for secure websocket connections, and
  immediate `session.update` send after a successful connection.
- `connect_realtime_websocket_url(...)` reuses the dependency-light
  standard-library websocket upgrade path for `ws`/`wss`, while preserving
  realtime-specific `ApiError::Stream` error shaping. The concrete `ws://`
  path is covered by a local standard-library mock websocket server that
  validates handshake headers, masked client text frames, server text frames,
  V1 event parsing, active-transcript handoff projection, and graceful close.
- `RealtimeTextMessage`, `RealtimeBinaryMessage`, `RealtimeCloseMessage`,
  `RealtimePingMessage`, `RealtimePongMessage`, `RealtimeFrameMessage`, and
  `RealtimeWebsocketMemoryStream` are Python-only test/injection helpers for
  the Rust websocket transport boundary.

Evidence:

- Rust source:
  `src/endpoint/realtime_websocket/{protocol,methods_common,methods_v1,methods_v2,methods}.rs`
- Rust tests/source contracts:
  `src/endpoint/realtime_websocket/methods.rs`
  `e2e_connect_and_exchange_events_against_mock_ws_server`,
  `realtime_v2_session_update_includes_background_agent_tool_and_handoff_output_item`,
  `transcription_mode_session_update_omits_output_audio_and_instructions`,
  and websocket URL tests.
- Active transcript behavior from
  `e2e_connect_and_exchange_events_against_mock_ws_server` and the helper
  functions in `methods.rs`.
- Python tests:
  `tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py`
  `tests/test_codex_api_endpoint_realtime_websocket_url_rs.py`
  `tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py`
  `tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`

Validation:

- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `20 passed, 3 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `56 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `247 passed, 79 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `40 passed, 3 subtests passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `55 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `244 passed, 79 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\realtime_websocket\methods.py tests\test_codex_api_endpoint_realtime_websocket_methods_rs.py tests\test_codex_api_endpoint_realtime_websocket_url_rs.py tests\test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests\test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `55 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused pytest over `tests/test_codex_api_*_rs.py`
  passed on 2026-06-21 with `243 passed, 76 subtests passed`.
- `python -m py_compile pycodex\codex_api\endpoint\realtime_websocket\methods_common.py pycodex\codex_api\endpoint\realtime_websocket\methods_v1.py pycodex\codex_api\endpoint\realtime_websocket\methods_v2.py pycodex\codex_api\endpoint\realtime_websocket\protocol.py tests\test_codex_api_endpoint_realtime_websocket_methods_rs.py`
  passed on 2026-06-21.
- `python -m py_compile pycodex\codex_api\endpoint\realtime_websocket\methods.py tests\test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `52 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `202 passed, 45 subtests passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_methods_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `13 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `16 passed, 3 subtests passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `49 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `192 passed, 45 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/methods.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_methods_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `13 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-21 with `48 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-21 with
  `191 passed, 42 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/methods.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py`
  passed on 2026-06-21.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_methods_rs tests.test_codex_api_endpoint_realtime_call_rs -v`
  passed on 2026-06-20 with `13 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `15 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `33 tests`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `35 tests`.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-20 with `13 passed`.
- `python -m unittest tests.test_codex_api_endpoint_realtime_websocket_runtime_rs tests.test_codex_api_endpoint_realtime_websocket_active_transcript_rs tests.test_codex_api_endpoint_realtime_websocket_protocol_rs tests.test_codex_api_endpoint_realtime_websocket_url_rs tests.test_codex_api_endpoint_realtime_websocket_methods_rs -v`
  passed on 2026-06-20 with `46 tests`.
- `python -m pytest @tests -q --tb=short` where `@tests` is PowerShell-expanded
  from `tests/test_codex_api_*_rs.py` passed on 2026-06-20 with
  `188 passed, 42 subtests passed`.
- `python -m py_compile` over PowerShell-expanded `pycodex/codex_api/**/*.py`
  package modules and `tests/test_codex_api_*_rs.py` passed on 2026-06-20.

Non-blocking runtime notes:

- Completion is based on the Rust-derived module contract and focused local
  validation. Exact native rustls connector registration, exact
  tokio/tungstenite async timing, and live TLS websocket probes are not module
  or crate completion inputs for the dependency-light Python port.
