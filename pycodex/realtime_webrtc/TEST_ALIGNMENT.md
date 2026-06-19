# codex-realtime-webrtc test alignment

Rust crate: `codex-realtime-webrtc`

Python package: `pycodex/realtime_webrtc`

Status: `complete`

Certified modules:

- `codex/codex-rs/realtime-webrtc/src/lib.rs` -> `pycodex/realtime_webrtc/__init__.py`
- `codex/codex-rs/realtime-webrtc/src/native.rs` -> `pycodex/realtime_webrtc/__init__.py`

Remaining Rust modules: none.

Rust tests and fixtures:

- No standalone Rust test functions are registered for this crate; source
  contract is derived from `src/lib.rs` and `src/native.rs`.

Validation:

- `python -m pytest tests/test_realtime_webrtc_crate.py -q` (`4 passed`)
- `python -m py_compile pycodex/realtime_webrtc/__init__.py tests/test_realtime_webrtc_crate.py` (passed)
