# pycodex.sandboxing

This package contains the Python public import surface for the Rust
`codex-sandboxing` crate.

## Rust Counterpart

```text
Rust crate: codex-sandboxing
Rust path: codex/codex-rs/sandboxing
```

## Alignment Role

`pycodex.sandboxing` should own sandbox and permission-profile compatibility
surfaces that are not specific to one runtime entrypoint.

The current implementation re-exports already-ported structures from
`pycodex.core.tool_sandboxing` and `pycodex.protocol`. This preserves the public
import shape while deeper sandbox behavior remains split across core/protocol
modules.

## Rust Module Areas

Typical Rust sources to inspect before changing this package:

```text
codex/codex-rs/sandboxing/src/lib.rs
codex/codex-rs/core/src/safety.rs
codex/codex-rs/core/src/sandbox_tags.rs
codex/codex-rs/core/src/windows_sandbox.rs
codex/codex-rs/core/src/windows_sandbox_read_grants.rs
```

Related platform crates may include:

```text
codex/codex-rs/linux-sandbox
codex/codex-rs/windows-sandbox-rs
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
sandboxing.permission_profile
sandboxing.filesystem_policy
sandboxing.network_policy
sandboxing.approval_requirement
sandboxing.platform_shims
```

## Test Source Policy

Prefer Rust sandboxing/core safety tests before Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-sandboxing
# Rust module: src/lib.rs
# Rust test: tests::example_test_name
# Contract: sandboxing.permission_profile
```

## Current Movement Status

The former root module `pycodex/sandboxing.py` has been moved to this package as
`pycodex/sandboxing/__init__.py`.

This package is currently a compatibility surface. Deeper behavior remains in
`pycodex.core.tool_sandboxing` and `pycodex.protocol` until a focused sandboxing
alignment pass decides whether to move it here.
