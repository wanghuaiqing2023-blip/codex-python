# codex-config src/constraint.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/constraint.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/constraint.rs` |
| Python module | `pycodex/config/constraint.py` |
| Python exports | `pycodex.config.Constrained`, `pycodex.config.ConstraintError`, `pycodex.config.RequirementSource` |
| Python tests | `tests/test_config_constraint.py` |
| Status | `complete_candidate` |

`src/constraint.rs` owns the generic constrained-value helper, requirement
source display strings, and user-facing constraint error formatting used by
managed config and requirements handling.

## Covered Behavior Areas

- `Constrained.allow_any` accepts any value and stores successful updates.
- `Constrained.allow_any_from_default` exposes a default initial value in
  Python at the call site, matching Rust's `T: Default` intent.
- `Constrained.allow_only` rejects drift with Rust-shaped `InvalidValue`
  errors and preserves the previous value.
- `Constrained.normalized` applies the normalizer during initialization and
  `set`.
- `Constrained.can_set` probes validators without mutating the stored value
  and without applying the normalizer.
- `Constrained.add_validator` composes validators and checks the existing
  value before installing the combined validator.
- `ConstraintError` variants format as Rust's `thiserror` display strings.
- `RequirementSource` display strings mirror Rust source labels for unknown,
  MDM, cloud, system requirements files, legacy managed config files, and
  legacy MDM managed config.

## Rust Test Inventory

Rust local tests covered by `tests/test_config_constraint.py`:

- `constrained_allow_any_accepts_any_value`
- `constrained_allow_any_default_uses_default_value`
- `constrained_allow_only_rejects_different_values`
- `constrained_normalizer_applies_on_init_and_set`
- `constrained_add_validator_composes_with_existing_validator`
- `constrained_new_rejects_invalid_initial_value`
- `constrained_set_rejects_invalid_value_and_leaves_previous`
- `constrained_can_set_allows_probe_without_setting`

Additional Python coverage records source-level contracts for
`ConstraintError` display formatting and `can_set` not applying the normalizer.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused constraint tests and
  promote this module from `complete_candidate` to `complete`.
