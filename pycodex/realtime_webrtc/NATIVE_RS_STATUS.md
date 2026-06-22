# codex-realtime-webrtc src/native.rs status

Rust coordinate: `codex/codex-rs/realtime-webrtc/src/native.rs`

Python coordinate: `pycodex/realtime_webrtc/__init__.py`

Status: `complete`

Behavior contract:

- on macOS, Rust starts a `codex-realtime-webrtc` worker thread, creates a
  peer connection and offer, accepts answer SDP commands, emits connected and
  closed events, and polls local audio level.
- worker-stopped and native WebRTC failures are converted to
  `RealtimeWebrtcError::Message` with focused context.
- `message_error(prefix, err)` formats native errors as `{prefix}: {err}`.
- `audio_level_to_peak(audio_level)` clamps the floating-point WebRTC audio
  level into `[0.0, 1.0]`, multiplies by `i16::MAX`, rounds, and returns `u16`.

Python adaptation:

- The Python port intentionally does not vendor or bind Rust `libwebrtc`.
- The public session start/apply-answer behavior remains an unsupported
  compatibility boundary outside native macOS Rust.
- Stable helper behavior from `native.rs` is mirrored by `message_error` and
  `audio_level_to_peak` for parity tests and downstream compatibility.

Evidence:

- `pycodex/realtime_webrtc/__init__.py` exposes the unsupported native boundary
  and deterministic helper behavior.
- `tests/test_realtime_webrtc_crate.py` covers public crate-root behavior plus
  native helper contracts.

Validation:

- `tests/test_realtime_webrtc_crate.py`
