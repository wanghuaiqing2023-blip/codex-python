# pycodex.execpolicy

This package contains the Python counterpart for Rust execution policy behavior.

## Rust Counterparts

```text
Primary Rust crate: codex-execpolicy
Primary Rust path: codex/codex-rs/execpolicy

Related Rust module: codex-core exec_policy integration
Related Rust path: codex/codex-rs/core/src/exec_policy.rs
```

## Alignment Role

`pycodex.execpolicy` should own command policy decisions, allow/prompt/forbid
classification, prefix-rule matching, and approval requirement rendering that is
not specific to a single runtime entrypoint.

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
execpolicy.decision
execpolicy.prefix_rules
execpolicy.command_parsing_for_policy
execpolicy.approval_requirement
execpolicy.unmatched_command_rendering
```

## Test Source Policy

Prefer Rust tests from `codex-execpolicy` and Rust `core/src/exec_policy*`
tests before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-execpolicy
# Rust module: src/policy.rs
# Rust test: tests::example_test_name
# Contract: execpolicy.decision
```

## Current Movement Status

The former implementation module `pycodex/core/exec_policy.py` was moved to
`pycodex/execpolicy/__init__.py`.

`pycodex/core/exec_policy.py` has been deleted; use `pycodex.execpolicy` directly.
