# codex-config src/cloud_requirements.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/cloud_requirements.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/cloud_requirements.rs` |
| Python module | `pycodex/config/cloud_requirements.py` |
| Python exports | `pycodex.config.CloudRequirementsLoadErrorCode`, `pycodex.config.CloudRequirementsLoadError`, `pycodex.config.CloudRequirementsLoader` |
| Python tests | `tests/test_config_cloud_requirements.py` |
| Status | `complete_candidate` |

`src/cloud_requirements.rs` owns the cloud requirements loader abstraction,
the loader error code taxonomy, loader error accessors, shared async
resolution, and default no-requirements behavior.

## Covered Behavior Areas

- `CloudRequirementsLoadErrorCode` mirrors Rust's `Auth`, `Timeout`, `Parse`,
  `RequestFailed`, and `Internal` variants.
- `CloudRequirementsLoadError.new` stores a code, optional status code, and
  display message.
- `CloudRequirementsLoadError.code()` and `status_code()` expose the stored
  values.
- `CloudRequirementsLoader.default` resolves to no requirements.
- `CloudRequirementsLoader.new` accepts a single async computation and shares
  it across concurrent `get()` calls.
- Resolved mapping results are cloned for callers so later caller mutation does
  not alter the cached loader result.
- Failed futures are shared and surfaced consistently to concurrent callers.

## Rust Test Inventory

Rust local tests covered by `tests/test_config_cloud_requirements.py`:

- `shared_future_runs_once`

Additional Python coverage records source-level contracts for default
`Ok(None)`, loader error accessors/display, cloned resolved mappings, and
shared failures.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused cloud requirements
  tests and promote this module from `complete_candidate` to `complete`.
