# codex-api/src/endpoint/realtime_websocket protocol parser status

Rust modules:

- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/protocol.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/protocol_common.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/protocol_v1.rs`
- `codex/codex-rs/codex-api/src/endpoint/realtime_websocket/protocol_v2.rs`

Python modules:

- `pycodex/codex_api/endpoint/realtime_websocket/protocol.py`
- `pycodex/codex_api/endpoint/realtime_websocket/protocol_common.py`
- `pycodex/codex_api/endpoint/realtime_websocket/protocol_v1.py`
- `pycodex/codex_api/endpoint/realtime_websocket/protocol_v2.py`

Status: `complete` for the pure realtime websocket event parser slice.

Implemented behavior:

- `parse_realtime_event(...)` dispatches by `RealtimeEventParser` to V1 or V2
  parser behavior.
- Shared parser helpers mirror Rust JSON parsing, required `type` handling,
  `session.updated`, transcript delta/done extraction, and error message
  fallback behavior.
- V1 parser covers session updates, explicit audio deltas, item added/done,
  handoff requested, input/output transcript aliases, and unsupported/invalid
  payload fallthrough to `None`. Audio numeric fields mirror Rust
  `Value::as_u64` plus `u32`/`u16` conversion boundaries.
- V2 parser covers session updates, defaulted audio deltas, item added/created,
  normal item done, background-agent handoff tool calls, remain-silent noop tool
  calls, transcript aliases, speech started, response lifecycle events, and
  unsupported/invalid payload fallthrough to `None`. Invalid audio numeric
  fields fall back to Rust defaults where the Rust parser uses `unwrap_or`.

Evidence:

- Rust source:
  `src/endpoint/realtime_websocket/{protocol,protocol_common,protocol_v1,protocol_v2}.rs`
- Rust tests/source contracts:
  parser tests in `src/endpoint/realtime_websocket/methods.rs` from
  `parse_session_updated_event` through realtime V2 lifecycle tests.
- Python tests:
  `tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py`

Validation:

- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py -q --tb=short`
  passed on 2026-06-21 with `15 passed, 5 subtests passed`.
- `python -m py_compile pycodex/codex_api/endpoint/realtime_websocket/protocol.py pycodex/codex_api/endpoint/realtime_websocket/protocol_common.py pycodex/codex_api/endpoint/realtime_websocket/protocol_v1.py pycodex/codex_api/endpoint/realtime_websocket/protocol_v2.py tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py`
  passed on 2026-06-21.
- `python -m pytest tests/test_codex_api_endpoint_realtime_websocket_protocol_rs.py tests/test_codex_api_endpoint_realtime_websocket_methods_rs.py tests/test_codex_api_endpoint_realtime_websocket_url_rs.py tests/test_codex_api_endpoint_realtime_websocket_active_transcript_rs.py tests/test_codex_api_endpoint_realtime_websocket_runtime_rs.py -q --tb=short`
  passed on 2026-06-21 with `54 passed, 8 subtests passed`.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api_*_rs.py -q --tb=short` passed on
  2026-06-21 with `242 passed, 76 subtests passed`.

Deferred:

- Async websocket connection/probe/runtime behavior and active-transcript
  mutation in `src/endpoint/realtime_websocket/methods.rs` remain separate
  module contracts.
