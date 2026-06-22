# codex-realtime-webrtc

Rust crate: `codex-realtime-webrtc`

Rust anchor: `codex/codex-rs/realtime-webrtc`

Current certified modules:

- `realtime-webrtc/src/lib.rs`
- `realtime-webrtc/src/native.rs`

The crate root API is represented in `pycodex/realtime_webrtc/__init__.py`:
error types, event shapes, started-session data, session handle methods, and
the non-native unsupported-platform behavior.

The native macOS worker module is represented as a dependency-light
compatibility boundary: Python does not bind Rust `libwebrtc`, but preserves the
unsupported public behavior plus stable helper contracts such as native message
wrapping and audio-level peak conversion.

Remaining Rust modules: none.
