# codex-cli src/debug_sandbox/pid_tracker.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/debug_sandbox/pid_tracker.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/debug_sandbox/pid_tracker.rs` |
| Python module | `pycodex/cli/debug_sandbox.py` |
| Python exports | `pycodex/cli/__init__.py` PID tracker helpers |
| Python tests | `tests/test_cli_debug_sandbox.py` |
| Status | `complete_candidate` |

`src/debug_sandbox/pid_tracker.rs` owns the macOS debug-sandbox process
descendant tracker used to discover recursive child pids for cleanup after a
Seatbelt-backed child process exits.

Rust uses native macOS `kqueue`, `kevent`, and `proc_listchildpids`. Python
keeps this as a dependency-free compatibility boundary: invalid roots are
rejected like Rust, liveness follows `kill(pid, 0)` semantics, child listing is
platform guarded, and descendant collection is exposed through injectable
helpers. On macOS the default child listing uses a best-effort `pgrep -P`
snapshot rather than a long-running kqueue watcher.

## Completed Behavior Areas

- `PidTracker::new` non-positive root rejection is mirrored by
  `DebugSandboxPidTracker.new`.
- `pid_is_alive` invalid-pid and permission-error semantics are mirrored by
  `debug_sandbox_pid_is_alive`.
- `list_child_pids` is represented by `debug_sandbox_list_child_pids` as a
  macOS-only, no-dependency `pgrep -P` snapshot boundary.
- Recursive root/descendant collection is represented by
  `collect_debug_sandbox_descendant_pids`.
- `PidTracker::stop` is represented by `DebugSandboxPidTracker.stop`, which
  returns the collected pid set at the Python boundary.

## Rust Test Inventory

The Rust module contains local tests for:

- `pid_is_alive_detects_current_process`
- `list_child_pids_includes_spawned_child` on macOS
- `pid_tracker_collects_spawned_children` on macOS
- `pid_tracker_collects_bash_subshell_descendants` on macOS

They are represented by:

- `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_pid_tracker_new_rejects_non_positive_root_like_rust`
- `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_pid_tracker_collects_recursive_descendants_like_rust`
- `tests/test_cli_debug_sandbox.py::CliDebugSandboxTests::test_pid_tracker_child_listing_boundary_is_platform_guarded`

## Remaining Gaps

- Python does not implement Rust's native long-running kqueue watcher. This is
  intentionally documented as a native macOS implementation difference; the
  Python boundary preserves the module's observable helper contracts and offers
  injectable recursion for parity tests.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
