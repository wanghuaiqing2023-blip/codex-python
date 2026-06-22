# pycodex.utils.readiness

Python alignment target for Rust crate `codex-utils-readiness`.

Rust coordinate:

- `codex/codex-rs/utils/readiness/src/lib.rs`

Python mapping:

- `pycodex/utils/readiness/__init__.py`

The module preserves Rust's readiness flag contract:

- `ReadinessFlag` starts not-ready.
- `subscribe` returns an authorization `Token`.
- `mark_ready` succeeds only once for a subscribed non-zero token.
- `wait_ready` unblocks when readiness is marked.
- `is_ready` auto-marks ready when there are no subscribers.
- contended token lock acquisition raises `TokenLockFailed`.

