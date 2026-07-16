# pycodex.core

This package contains Python counterparts for Rust core runtime behavior.

## Rust Counterpart

```text
Primary Rust crate: codex-core
Primary Rust path: codex/codex-rs/core
```

## Alignment Role

`pycodex.core` is the Python runtime aggregation package. It should coordinate
agent turns, model requests, tool registration, tool dispatch, event mapping,
context assembly, rollout/session behavior, and runtime safety boundaries.

Because Rust `codex-core` is a large crate, this package must not be treated as
a single acceptance unit.

## Rust Module Areas

Typical Rust module counterparts include:

```text
codex/codex-rs/core/src/client.rs
codex/codex-rs/core/src/codex_thread.rs
codex/codex-rs/core/src/event_mapping.rs
codex/codex-rs/core/src/agents_md.rs
codex/codex-rs/core/src/exec.rs
codex/codex-rs/core/src/safety.rs
codex/codex-rs/core/src/rollout.rs
codex/codex-rs/core/src/tools/
```

Context fragments are intentionally implemented in `pycodex.core.context` to
share their common Python base class. Rust-coordinate modules such as
`context/fragment.py` and `context/goal_context.py` re-export those classes;
they must not grow independent duplicate implementations.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract, not the whole
`codex-core` crate.

Initial contract areas:

```text
core.turn_runtime
core.model_client
core.tools.registry
core.tools.router
core.tools.spec_plan
core.event_mapping
core.agents_md
core.exec_command
core.safety
core.rollout
```

## Transitional Shims

No legacy `pycodex.core` compatibility shim files remain for crates that already have canonical Python packages. New crate-level migrations should move implementation to the canonical package, update imports, validate the touched slice, then delete the old coordinate.

## Cross-Package Rust Module Mappings

Some Rust `codex-core` modules intentionally live outside `pycodex.core` when
Python has a clearer domain package:

```text
codex/codex-rs/core/src/apply_patch.rs
  -> pycodex.apply_patch
```

`pycodex.apply_patch` also carries the adjacent Rust `codex-apply-patch` crate
surface plus the core apply-patch handler helpers. Do not recreate a duplicate
`pycodex.core.apply_patch` shim unless a compatibility break requires it.

## Test Source Policy

Prefer Rust `codex-core` unit tests, `src/*_tests.rs`, and `core/tests/common`
fixtures before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-core
# Rust module: src/event_mapping.rs
# Rust test: tests::example_test_name
# Contract: core.event_mapping
```

## Current Movement Status

No code movement is required for the first structural pass. Future core work
must be split by module-scoped behavior contract to avoid treating `core` as a
single oversized module.
