# codex-shell-escalation src/unix/stopwatch.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/stopwatch.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- construct limited and unlimited stopwatches.
- return a cancellation token that fires once non-paused elapsed time reaches the limit.
- pause elapsed-time accounting while an awaitable is pending.
- keep overlapping pauses reference-counted so the clock resumes only after every pause completes.

Evidence:

- `Stopwatch.new`, `Stopwatch.unlimited`, `Stopwatch.cancellation_token`, and `Stopwatch.pause_for` mirror the Rust public methods.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
