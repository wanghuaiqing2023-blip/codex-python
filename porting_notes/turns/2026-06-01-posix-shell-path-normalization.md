# 2026-06-01 Posix Shell Path Normalization

## Graph-selected slice

- Upstream graph nodes used as navigation:
  - `codex-rs/core/src/shell.rs#Shell::derive_exec_args`
  - `codex-rs/core/src/tools/handlers/shell/shell_command.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec.rs`
- The slice advances `tool dispatch -> shell/unified exec command construction -> process invocation` behavior.

## Rust source checked

- `codex/codex-rs/core/src/shell.rs`
- `codex/codex-rs/core/src/shell_tests.rs`

## Python changes

- Normalized POSIX shell executable paths in `Shell.derive_exec_args` so Bash/Zsh/Sh command argv uses slash paths such as `/bin/bash`, even when tests run on Windows.
- Left PowerShell and Cmd path rendering unchanged.
- Updated unified exec tests to assert Rust-shaped POSIX shell argv instead of host-`Path` stringification.

## Validation

- `python -m unittest tests.test_core_unified_exec_handler tests.test_core_shell_handler tests.test_core_apply_patch tests.test_core_view_image_handler`
  - Passed: 78 tests, 1 skipped.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - Passed: 198 tests.

## Follow-up debt

- Broader discovery still has failures outside this slice, especially in multi-agent and peripheral extension paths.
- `PORTING_STATUS.md` is currently deleted in the worktree; this turn intentionally did not recreate it.
