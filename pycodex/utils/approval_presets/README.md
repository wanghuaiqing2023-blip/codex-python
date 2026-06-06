# pycodex.utils.approval_presets

Python counterpart for the Rust `codex-utils-approval-presets` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-approval-presets
Rust path: codex/codex-rs/utils/approval-presets
Cargo role: built-in approval policy and permission-profile presets
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/approval_presets/__init__.py` | crate public surface and built-in preset behavior |

## Alignment Unit

The acceptance unit is a module-scoped behavior contract:

```text
utils.approval_presets.builtin_order_and_ids
utils.approval_presets.read_only_preset
utils.approval_presets.auto_preset
utils.approval_presets.full_access_preset
utils.approval_presets.builtin_profile_resolution
utils.approval_presets.unknown_or_extended_profile_resolution
```

## Test Sources

This Rust crate disables crate tests in `Cargo.toml`, so the first parity batch
is source-contract based rather than Rust-test based.

Primary source:

```text
codex/codex-rs/utils/approval-presets/src/lib.rs
```

Primary Python parity test:

```text
tests/test_core_approval_presets.py
```

## Current Status

Status: module_completed_with_focused_validation.

The public Rust surface from `src/lib.rs` has been reviewed against the Python
exports. This crate has no Rust test target (`test = false`), so parity is
source-contract based and anchored by `tests/test_core_approval_presets.py`.
The surrounding protocol contracts referenced by the presets are covered by
Rust-anchored protocol tests:

```text
tests/test_protocol_config_types.py        # AskForApproval
tests/test_protocol_permission_models.py   # ActivePermissionProfile, PermissionProfile
```

## Stop Rule

This module contract is complete once `tests/test_core_approval_presets.py` and
the focused protocol dependency tests pass. Do not rescan this slice unless a
related test fails, Rust source changes, or a future task explicitly targets
this package.
