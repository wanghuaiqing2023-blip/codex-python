# app-server-protocol `protocol/v2/realtime.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/realtime.rs`

Python target: `pycodex/app_server_protocol/realtime.py`

Status: implemented module contract.

## Covered Rust items

- `ThreadRealtimeAudioChunk`
- `ThreadRealtimeStartParams`
- `ThreadRealtimeStartTransport`
- `ThreadRealtimeStartResponse`
- `ThreadRealtimeAppendAudioParams`
- `ThreadRealtimeAppendAudioResponse`
- `ThreadRealtimeAppendTextParams`
- `ThreadRealtimeAppendTextResponse`
- `ThreadRealtimeStopParams`
- `ThreadRealtimeStopResponse`
- `ThreadRealtimeListVoicesParams`
- `ThreadRealtimeListVoicesResponse`
- `ThreadRealtimeStartedNotification`
- `ThreadRealtimeItemAddedNotification`
- `ThreadRealtimeTranscriptDeltaNotification`
- `ThreadRealtimeTranscriptDoneNotification`
- `ThreadRealtimeOutputAudioDeltaNotification`
- `ThreadRealtimeSdpNotification`
- `ThreadRealtimeErrorNotification`
- `ThreadRealtimeClosedNotification`

## Notes

- The module reuses `pycodex.protocol` realtime enums and voice-list types,
  matching the Rust dependency on core protocol realtime types.
- `ThreadRealtimeStartParams.prompt` preserves Rust `Option<Option<String>>`
  serde behavior with a module-local `UNSET` sentinel for omitted fields,
  `None` for explicit JSON `null`, and strings for prompt text.
- `ThreadRealtimeStartTransport` mirrors Rust's tagged websocket/webrtc shape.
- Payloads accept Rust serde camelCase keys and emit Rust wire names through
  `to_camel_mapping()`.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/realtime.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed audio chunks, start params prompt states, websocket and
  WebRTC transport, append audio/text, stop, voices, started/item/transcript/
  output-audio/SDP/error/closed notifications.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
