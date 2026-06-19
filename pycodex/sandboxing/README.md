# pycodex.sandboxing

This package contains the Python public import surface for the Rust
`codex-sandboxing` crate.

## Rust Counterpart

```text
Rust crate: codex-sandboxing
Rust path: codex/codex-rs/sandboxing
```

## Alignment Role

`pycodex.sandboxing` owns sandbox and permission-profile compatibility surfaces
that are not specific to one runtime entrypoint.

The current implementation re-exports already-ported structures from
`pycodex.core.tools.sandboxing`, `pycodex.core.sandboxing`, and
`pycodex.protocol`. The crate-aligned `manager.py` module now provides the
Rust `src/manager.rs` request/response shape, sandbox selection, additional
permission merging, macOS Seatbelt command wrapping, Linux helper command
wrapping, WSL1/bubblewrap guard behavior, and legacy compatibility policy
projection.

`policy_transforms.py` provides the Rust `src/policy_transforms.rs`
permission-profile transformation surface, including additional-permission
normalization, merge/intersection helpers, effective runtime policy projection,
glob scan-depth merging, and platform-sandbox requirement checks.

`landlock.py` provides the Rust `src/landlock.rs` argv-building surface through
the existing `pycodex.linux_sandbox` helpers, including permission-profile JSON
argv construction, legacy Landlock flagging, managed-network proxy flagging, and
the `codex-linux-sandbox` arg0 alias.

`bwrap.py` provides the Rust `src/bwrap.rs` bubblewrap prerequisite warning
surface, including WSL1 detection, PATH lookup that skips workspace-local
helpers, user-namespace stderr failure detection, and timeout/error-tolerant
probing.

`seatbelt.py` provides the Rust `src/seatbelt.rs` macOS sandbox-exec policy
construction surface, including proxy loopback port detection, dynamic network
and Unix-domain-socket policy generation, protected metadata carveouts,
unreadable glob deny-rule translation, and the `sandbox-exec` argv shape.

## Rust Module Areas

Typical Rust sources to inspect before changing this package:

```text
codex/codex-rs/sandboxing/src/lib.rs
codex/codex-rs/sandboxing/src/manager.rs
codex/codex-rs/sandboxing/src/policy_transforms.rs
codex/codex-rs/sandboxing/src/landlock.rs
codex/codex-rs/sandboxing/src/seatbelt.rs
codex/codex-rs/sandboxing/src/bwrap.rs
```

Related platform crates may include:

```text
codex/codex-rs/linux-sandbox
codex/codex-rs/windows-sandbox-rs
```

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Current and planned contract areas:

```text
sandboxing.manager -> codex-sandboxing/src/manager.rs
sandboxing.policy_transforms -> codex-sandboxing/src/policy_transforms.rs
sandboxing.landlock -> codex-sandboxing/src/landlock.rs
sandboxing.seatbelt -> codex-sandboxing/src/seatbelt.rs
sandboxing.bwrap -> codex-sandboxing/src/bwrap.rs
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
`pycodex.core.tools.sandboxing`, `pycodex.core.sandboxing`, and
`pycodex.protocol` until focused sandboxing alignment passes move or wrap each
Rust module.

2026-06-17: `src/manager.rs` advanced to complete-candidate as
`pycodex.sandboxing.manager`. The manager delegates Linux argv construction to
the existing `pycodex.linux_sandbox` helper and preserves the non-macOS
seatbelt unavailable error.

2026-06-17: `src/policy_transforms.rs` advanced to complete-candidate as
`pycodex.sandboxing.policy_transforms`. The module reuses already ported
handler/protocol primitives for merge/intersection behavior and exposes the
crate-owned canonical import path for sandboxing callers.

2026-06-17: `src/landlock.rs` advanced to complete-candidate as
`pycodex.sandboxing.landlock`. The module is a crate-aligned facade over
`pycodex.linux_sandbox`, where the shared Linux helper argv construction already
has Rust-derived coverage.

2026-06-17: `src/bwrap.rs` advanced to complete-candidate as
`pycodex.sandboxing.bwrap`. The module owns bubblewrap prerequisite warning and
probe helpers; actual bubblewrap sandbox execution remains outside this module.

2026-06-17: `src/seatbelt.rs` advanced to complete-candidate as
`pycodex.sandboxing.seatbelt`. The module owns macOS Seatbelt policy text and
argv construction helpers.

2026-06-17: `src/manager.rs` refreshed after the Seatbelt module pass. The
manager now delegates macOS argv construction to `pycodex.sandboxing.seatbelt`
and mirrors Rust's Linux WSL1/bubblewrap guard.

2026-06-17: `codex-sandboxing` advanced to complete after focused crate
validation passed 87 tests across sandboxing, Landlock, sandbox tags, and
protocol permission models.
