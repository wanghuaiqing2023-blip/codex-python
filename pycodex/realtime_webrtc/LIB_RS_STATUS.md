# codex-realtime-webrtc src/lib.rs status

Rust coordinate: `codex/codex-rs/realtime-webrtc/src/lib.rs`

Python coordinate: `pycodex/realtime_webrtc/__init__.py`

Status: `complete`

Behavior contract:

- expose `RealtimeWebrtcError` with message and unsupported-platform variants.
- expose `RealtimeWebrtcEvent` variants for connected, local audio level,
  closed, and failed events.
- expose the started-session data shape with `offer_sdp`, session handle, and
  event receiver/queue.
- expose `RealtimeWebrtcSessionHandle` methods for `apply_answer_sdp`, `close`,
  and `local_audio_peak`.
- expose `RealtimeWebrtcSession.start`.
- on non-native platforms, `apply_answer_sdp` and `start` return/report
  unsupported-platform behavior while `close` is a no-op.

Evidence:

- `pycodex/realtime_webrtc/__init__.py` carries the public API boundary for
  `RealtimeWebrtcError`, `RealtimeWebrtcEvent`, `StartedRealtimeWebrtcSession`,
  `RealtimeWebrtcSessionHandle`, and `RealtimeWebrtcSession`.
- Native macOS worker behavior from `src/native.rs` is intentionally kept as a
  separate module contract and is not certified by this file.

Validation:

- Deferred by project policy until all `codex-realtime-webrtc` functional
  modules are complete. Remaining module: `src/native.rs`.
