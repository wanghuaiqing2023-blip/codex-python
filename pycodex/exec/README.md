# pycodex.exec

This package contains Python counterparts for Rust non-interactive exec
entrypoint behavior.

## Rust Counterpart

```text
Primary Rust crate: codex-exec
Primary Rust path: codex/codex-rs/exec
```

## Alignment Role

`pycodex.exec` should own exec-specific CLI orchestration, bootstrap planning,
backend selection, local HTTP/remote fallback integration, event processing,
and final output/exit behavior.

It should not own generic tool dispatch, protocol data models, or shell command
safety behavior. Those belong in `pycodex.core`, `pycodex.protocol`, and
`pycodex.shell_command`.

## Rust Module Areas

Typical Rust module counterparts include:

```text
codex/codex-rs/exec/src/cli.rs
codex/codex-rs/exec/src/main.rs
codex/codex-rs/exec/src/lib.rs
codex/codex-rs/exec/tests/
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
exec.cli_args
exec.bootstrap_plan
exec.backend_selection
exec.session_start_resume
exec.event_processing
exec.output_and_exit
```

## Test Source Policy

Prefer Rust exec integration tests under `codex/codex-rs/exec/tests/` before
Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-exec
# Rust module: tests/suite/prompt_stdin.rs
# Rust test: tests::example_test_name
# Contract: exec.cli_args
```

## Current Movement Status

No code movement is required for the first structural pass. `pycodex.exec`
should remain an entrypoint/orchestration package, not a dumping ground for
runtime or protocol behavior.
