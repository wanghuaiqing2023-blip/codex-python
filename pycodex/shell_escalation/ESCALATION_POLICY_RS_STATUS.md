# codex-shell-escalation src/unix/escalation_policy.rs status

Rust coordinate: `codex/codex-rs/shell-escalation/src/unix/escalation_policy.rs`

Python coordinate: `pycodex/shell_escalation/__init__.py`

Status: `complete`

Behavior contract:

- expose an async policy interface named `EscalationPolicy`.
- require implementers to decide an `EscalationDecision` from executable path, argv, and working directory.
- avoid a permissive default decision; Rust defines a trait contract, not a default `Run` implementation.

Evidence:

- `EscalationPolicy.determine_action` is an async interface method that raises until a concrete policy supplies behavior.
- Actual pytest validation is deferred until the crate's remaining functional modules are complete.
