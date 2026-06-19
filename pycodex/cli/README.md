# pycodex.cli

This package contains Python counterparts for Rust top-level CLI behavior.

## Rust Counterpart

```text
Primary Rust crate: codex-cli
Primary Rust path: codex/codex-rs/cli
```

## Alignment Role

`pycodex.cli` should own top-level command parsing, command dispatch, command
surface compatibility, login/features/update command shims, and user-facing
CLI exit messages.

It should delegate runtime behavior to `pycodex.exec`, `pycodex.core`,
`pycodex.config`, and other domain packages.

## Rust Module Areas

Typical Rust module counterparts include:

```text
codex/codex-rs/cli/src/main.rs
codex/codex-rs/cli/tests/
```

Related command crates may include:

```text
codex/codex-rs/login
codex/codex-rs/features
codex/codex-rs/tui
```

## Python Modules

Current Python implementation files include:

| Python module/file | Role |
|---|---|
| `pycodex/cli/parser.py` | top-level parser and command dispatch |
| `pycodex/cli/app_cmd.py` | desktop app command workspace path handling |
| `pycodex/cli/login.py` | login/logout/status command behavior and auth persistence |
| `pycodex/cli/features.py` | features command behavior |
| `pycodex/cli/doctor_updates.py` | doctor checks, redaction, rendering helpers, and rollout/state DB thread inventory diagnostics |
| `pycodex/cli/app_exit.py` | user-facing app-exit formatting |
| `pycodex/cli/exit_status.py` | process exit-status code mapping |
| `pycodex/cli/wsl_paths.py` | WSL path conversion helpers |
| `pycodex/cli/state_db_recovery.py` | local state DB startup recovery helpers |
| `pycodex/tui/__init__.py` | canonical TUI entrypoint compatibility behavior |

`pycodex/tui.py` has been replaced by the canonical `pycodex/tui/` package. `pycodex/cli/tui.py` has been deleted; use `pycodex.tui` directly.

## Module Status Files

| Status file | Scope |
|---|---|
| `pycodex/cli/MAIN_RS_STATUS.md` | Tracks only Rust `codex-cli/src/main.rs`; top-level parser/dispatch shell is complete-candidate. |
| `pycodex/cli/LIB_RS_STATUS.md` | Tracks only Rust `codex-cli/src/lib.rs`; library-boundary exports and host sandbox command surfaces are complete-candidate. |
| `pycodex/cli/DESKTOP_APP_MOD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/desktop_app/mod.rs`; current-OS desktop app dispatch is complete-candidate. |
| `pycodex/cli/DESKTOP_APP_MAC_RS_STATUS.md` | Tracks only Rust `codex-cli/src/desktop_app/mac.rs`; native macOS open/install flow is complete-candidate. |
| `pycodex/cli/DESKTOP_APP_WINDOWS_RS_STATUS.md` | Tracks only Rust `codex-cli/src/desktop_app/windows.rs`; Windows desktop app open/install flow is complete-candidate. |
| `pycodex/cli/DOCTOR_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor.rs`; sibling `src/doctor/*` modules are tracked separately in `TEST_ALIGNMENT.md`. |
| `pycodex/cli/DOCTOR_BACKGROUND_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/background.rs`; passive app-server diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_THREAD_INVENTORY_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/thread_inventory.rs`; rollout/state DB parity diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_UPDATES_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/updates.rs`; update diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_RUNTIME_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/runtime.rs`; runtime/search diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_GIT_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/git.rs`; Git diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_SYSTEM_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/system.rs`; system/environment detail ordering is complete-candidate. |
| `pycodex/cli/DOCTOR_TITLE_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/title.rs`; terminal-title diagnostics are complete-candidate. |
| `pycodex/cli/DOCTOR_PROGRESS_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/progress.rs`; stderr rendering internals are documented as an adaptation. |
| `pycodex/cli/DOCTOR_OUTPUT_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/output.rs`; human report rendering is complete and focused validation passed. |
| `pycodex/cli/DOCTOR_OUTPUT_DETAIL_RS_STATUS.md` | Tracks only Rust `codex-cli/src/doctor/output/detail.rs`; sibling output/report modules remain separate module boundaries. |
| `pycodex/cli/LOGIN_RS_STATUS.md` | Tracks only Rust `codex-cli/src/login.rs`; direct login/logout/status command-surface behavior is complete-candidate. |
| `pycodex/cli/MARKETPLACE_CMD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/marketplace_cmd.rs`; plugin marketplace CLI shim is complete-candidate. |
| `pycodex/cli/MCP_CMD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/mcp_cmd.rs`; MCP CLI helper/surface shim is complete-candidate. |
| `pycodex/cli/PLUGIN_CMD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/plugin_cmd.rs`; plugin CLI selector/surface shim is complete-candidate. |
| `pycodex/cli/REMOTE_CONTROL_CMD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/remote_control_cmd.rs`; remote-control CLI output shim is complete-candidate. |
| `pycodex/cli/APP_CMD_RS_STATUS.md` | Tracks only Rust `codex-cli/src/app_cmd.rs`; desktop app workspace path normalization is complete-candidate. |
| `pycodex/cli/DEBUG_SANDBOX_RS_STATUS.md` | Tracks only Rust `codex-cli/src/debug_sandbox.rs`; parent debug-sandbox orchestration is complete and focused validation passed. |
| `pycodex/cli/PID_TRACKER_RS_STATUS.md` | Tracks only Rust `codex-cli/src/debug_sandbox/pid_tracker.rs`; macOS PID descendant tracking shim is complete-candidate. |
| `pycodex/cli/SEATBELT_RS_STATUS.md` | Tracks only Rust `codex-cli/src/debug_sandbox/seatbelt.rs`; Seatbelt denial parsing/filtering shim is complete-candidate. |
| `pycodex/cli/STATE_DB_RECOVERY_RS_STATUS.md` | Tracks only Rust `codex-cli/src/state_db_recovery.rs`; local state DB startup recovery is complete-candidate. |
| `pycodex/cli/EXIT_STATUS_RS_STATUS.md` | Tracks only Rust `codex-cli/src/exit_status.rs`; exit-code propagation is complete-candidate. |
| `pycodex/cli/WSL_PATHS_RS_STATUS.md` | Tracks only Rust `codex-cli/src/wsl_paths.rs`; WSL path normalization is complete-candidate. |

## Alignment Unit

The default acceptance unit is a module-scoped behavior contract.

Initial contract areas:

```text
cli.top_level_parser
cli.command_dispatch
cli.app_exit
cli.login_command
cli.features_command
```

## Test Source Policy

Prefer Rust CLI tests and command-surface source behavior before
Python-inferred tests.

Python tests should record Rust source comments when touched:

```python
# Source: rust_test_migrated
# Rust crate: codex-cli
# Rust module: src/main.rs
# Rust test: tests::example_test_name
# Contract: cli.top_level_parser
```

## Current Movement Status

No code movement is required for the first structural pass. This README is the
local map for future CLI alignment.
