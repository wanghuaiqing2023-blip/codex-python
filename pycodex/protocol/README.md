# pycodex.protocol

This package contains Python counterparts for Rust protocol and shared data
contract crates.

## Rust Counterparts

```text
Primary Rust crate: codex-protocol
Primary Rust path: codex/codex-rs/protocol

Related Rust crate: codex-app-server-protocol
Related Rust path: codex/codex-rs/app-server-protocol
```

## Alignment Role

`pycodex.protocol` should own data contracts that are shared across runtime,
tools, CLI/app-server shims, and tests.

Typical Rust module counterparts include:

```text
codex/codex-rs/protocol/src/items.rs
codex/codex-rs/protocol/src/protocol.rs
codex/codex-rs/protocol/src/exec_output.rs
codex/codex-rs/protocol/src/tool_name.rs
codex/codex-rs/protocol/src/permissions.rs
codex/codex-rs/protocol/src/request_user_input.rs
codex/codex-rs/protocol/src/request_permissions.rs
codex/codex-rs/protocol/src/plan_tool.rs
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
protocol.items
protocol.events
protocol.exec_output
protocol.tool_name
protocol.permissions
protocol.request_user_input
protocol.request_permissions
protocol.plan_tool
```

## Test Source Policy

Prefer Rust protocol tests and fixtures before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-protocol
# Rust module: src/exec_output.rs
# Rust test: tests::example_test_name
# Contract: protocol.exec_output
```

## Current Movement Status

`codex-protocol` is `complete` as of 2026-06-17. All current Rust protocol
modules are recorded in `TEST_ALIGNMENT.md`, including `src/lib.rs` in
`LIB_RS_STATUS.md`: the Python package root exports Rust's crate-root
identifier/path types and maps every public Rust module to a Python sibling
module, with `permissions.rs` intentionally merged into `models.py`.

Focused protocol validation passed after functional module completion:
`$files = Get-ChildItem tests -Filter 'test_protocol_*.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q`
-> `369 passed, 118 subtests passed`.
