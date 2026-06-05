# pycodex.apply_patch

This package contains the Python counterpart for Rust apply-patch behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-apply-patch
Primary Rust path: codex/codex-rs/apply-patch

Related Rust module: codex-core apply_patch integration
Related Rust path: codex/codex-rs/core/src/apply_patch.rs
```

## Alignment Role

`pycodex.apply_patch` should own patch grammar, patch parsing, patch conversion,
patch safety metadata, and tool-facing apply_patch behavior.

The package may still depend on `pycodex.core` for runtime/tool integration, but
its domain ownership is apply-patch behavior rather than generic core runtime.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
apply_patch.grammar
apply_patch.parse
apply_patch.convert
apply_patch.safety_metadata
apply_patch.tool_handler
```

## Test Source Policy

Prefer Rust tests from the apply-patch crate and Rust core apply_patch tests
before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-apply-patch
# Rust module: tests/suite/scenarios.rs
# Rust test: tests::example_test_name
# Contract: apply_patch.parse
```

## Current Movement Status

The former implementation module `pycodex/core/apply_patch.py` was moved to
`pycodex/apply_patch/__init__.py`.

`pycodex/core/apply_patch.py` has been deleted; use `pycodex.apply_patch` directly.
