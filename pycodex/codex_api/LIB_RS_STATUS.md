# codex-api/src/lib.rs

Status: `complete`

Rust source:

- `codex/codex-rs/codex-api/src/lib.rs`

Python target:

- `pycodex/codex_api/__init__.py`

Behavior contract:

- The crate root declares the private module tree for `codex-api` and publicly
  re-exports the module APIs consumed by core runtime callers.
- Python mirrors this as a package-root facade over the already mapped module
  contracts, including endpoint clients, shared request/response data, search
  shapes, telemetry traits, auth/provider/error helpers, and the upstream
  `codex-client` transport/telemetry aliases.
- Rust also re-exports `codex_protocol::protocol::{RealtimeAudioFrame,
  RealtimeEvent}`. Python maps `RealtimeAudioFrame` to `pycodex.protocol` and
  maps `RealtimeEvent` to the dependency-light realtime websocket event result
  carried by `pycodex.codex_api.endpoint.realtime_websocket`, because the
  generated protocol package currently exposes the wrapper
  `RealtimeConversationRealtimeEvent` but not a standalone `RealtimeEvent`
  enum facade.

Rust tests/fixtures:

- `src/lib.rs` has no local Rust tests; the behavior boundary is the source
  `pub use` surface.
- Sibling module behavior remains covered by the module-specific Rust-derived
  tests listed in `TEST_ALIGNMENT.md`.

Python tests:

- `tests/test_codex_api_lib_rs.py`

Validation:

- `python -m pytest tests/test_codex_api_lib_rs.py -q --tb=short`
  passed with `2 passed`.
- `python -m py_compile pycodex\codex_api\__init__.py pycodex\codex_api\endpoint\__init__.py pycodex\codex_api\endpoint\realtime_websocket\__init__.py tests\test_codex_api_lib_rs.py`
  passed.
- PowerShell-expanded codex-api focused validation
  `python -m pytest tests/test_codex_api*_rs.py -q --tb=short`
  passed with `246 passed, 79 subtests passed`.

Crate-level status note:

- `codex-api` is complete for the dependency-light Python port. Completion is
  based on Rust-derived module contracts and focused local validation; live
  websocket probes remain optional smoke coverage only.
