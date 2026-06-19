# codex-config src/project_root_markers.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/project_root_markers.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/project_root_markers.rs` |
| Python module | `pycodex/config/project_root_markers.py` |
| Python exports | `pycodex.config.default_project_root_markers`, `pycodex.config.project_root_markers_from_config` |
| Python tests | `tests/test_config_project_root_markers.py` |
| Status | `complete_candidate` |

`src/project_root_markers.rs` owns reading the optional
`project_root_markers` top-level config key from merged TOML and providing the
default root-detection marker list.

## Covered Behavior Areas

- `DEFAULT_PROJECT_ROOT_MARKERS` contains only `.git`.
- `default_project_root_markers()` returns a new list containing the default
  marker, matching Rust's owned `Vec<String>` return.
- Non-table config values and missing `project_root_markers` return `None`.
- A specified string array returns the provided marker list.
- An explicitly empty array returns an empty list, preserving Rust's
  `Some(Vec::new())` root-detection-disabled signal.
- Specified non-array values or arrays containing non-string entries raise the
  Rust-equivalent invalid-data message:
  `project_root_markers must be an array of strings`.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from the module's documented invariants and public functions.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused project-root marker
  tests and promote this module from `complete_candidate` to `complete`.
