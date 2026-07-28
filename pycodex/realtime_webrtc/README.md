# codex-realtime-webrtc

Rust crate: `codex-realtime-webrtc`

Rust anchor: `codex/codex-rs/realtime-webrtc`

Current certified modules:

- `realtime-webrtc/src/lib.rs`
- `realtime-webrtc/src/native.rs`

The crate root API is represented in `pycodex/realtime_webrtc/__init__.py`:
error types, event shapes, started-session data, session handle methods, and
the non-native unsupported-platform behavior.

The native macOS worker module maps to `native.py`. Python does not bind Rust
`libwebrtc`; this is an intentional platform adaptation. The module preserves
the host-independent native contracts (error wrapping and exact audio-peak
conversion), while the crate root preserves Rust's unsupported-platform
behavior on non-macOS hosts. It does not fabricate a successful WebRTC session.

Remaining Rust modules: none.
