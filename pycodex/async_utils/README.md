# pycodex.async_utils

Python alignment target for Rust crate `codex-async-utils`.

Rust coordinate:

- `codex/codex-rs/async-utils/src/lib.rs`

Python mapping:

- `pycodex/async_utils/__init__.py`

The Rust crate exposes an `OrCancelExt` trait for futures. Python maps the same
module-scoped behavior to:

- `CancelErr`
- `CancellationToken`
- `CancelledError`
- `or_cancel(awaitable, token)`

This preserves the Rust behavior contract: return the awaitable result when it
completes first, raise cancellation when the token wins, and raise immediately
for an already-cancelled token.

