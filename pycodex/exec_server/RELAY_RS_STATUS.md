# codex-exec-server src/relay.rs and src/relay_proto.rs Status

Rust sources:

- `codex/codex-rs/exec-server/src/relay.rs`
- `codex/codex-rs/exec-server/src/relay_proto.rs`
- `codex/codex-rs/exec-server/src/proto/codex.exec_server.relay.v1.proto`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This slice maps the pure relay frame protocol helpers:

- `RelayData`, `RelayResume`, `RelayReset`, `RelayAck`,
  `RelayHeartbeat`, and `RelayMessageFrame`.
- `RelayMessageFrame.data(...)`, `RelayMessageFrame.resume(...)`, and the
  Python test/runtime constructor for reset frames.
- `RelayMessageFrame.validate(...)`, `into_jsonrpc_message(...)`, and
  `into_reset_reason(...)`.
- `encode_relay_message_frame(...)` and `decode_relay_message_frame(...)`
  with the Rust prost field numbers.
- `jsonrpc_payload(...)` compact JSON payload encoding.
- `harness_connection_from_websocket(...)` on the harness/client side:
  initial resume frame emission, outbound JSON-RPC to relay data frames,
  inbound relay data to JSON-RPC connection events, text/malformed frame
  reporting, close/reset disconnect reporting, and single-loop send
  backpressure ordering.
- `run_multiplexed_environment(...)` on the environment/server side:
  physical websocket data-frame decode, per-stream virtual connection
  creation, processor handoff, outbound JSON-RPC response framing, reset
  disconnect delivery, physical close disconnect fan-out, and malformed or
  non-data frame dropping.
- `_spawn_virtual_stream(...)` writer behavior: outbound virtual JSON-RPC
  messages become relay data frames with per-stream wrapping sequence numbers
  and are sent over the shared physical outgoing channel.

## Evidence

- Rust source:
  - `src/relay.rs`
  - `src/relay_proto.rs`
  - `src/proto/codex.exec_server.relay.v1.proto`
- Rust tests:
  - `src/relay.rs::tests::harness_connection_receives_relay_data`
  - `src/relay.rs::tests::harness_connection_reports_text_frames_as_malformed`
  - `src/relay.rs::tests::harness_connection_reports_server_close`
  - `src/relay.rs::tests::harness_connection_keeps_outbound_frame_while_send_is_backpressured`
- Rust source-derived contracts:
  - `src/relay.rs::run_multiplexed_environment`
  - `src/relay.rs::spawn_virtual_stream`
  - `src/relay.rs::VirtualStream::disconnect`
- Python tests:
  - `tests/test_exec_server_relay_rs.py`

## Validation

```powershell
python -m pytest tests/test_exec_server_relay_rs.py -q --tb=short
python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_relay_rs.py
```

Result on 2026-06-21:

- `python -m pytest tests/test_exec_server_relay_rs.py -q --tb=short`
  passed with `18 passed`.
- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py -q --tb=short`
  passed with `31 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_relay_rs.py`
  passed.

Concrete websocket relay transport and full live `ConnectionProcessor`
integration through the remote environment runtime remain crate-level runtime
boundaries tracked in `TEST_ALIGNMENT.md`; they are outside this module's
dependency-light relay frame and virtual-stream behavior contract.
