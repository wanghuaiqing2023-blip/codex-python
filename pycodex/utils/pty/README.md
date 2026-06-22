# pycodex.utils.pty

Rust crate: `codex-utils-pty`

Rust anchor: `codex/codex-rs/utils/pty`

This package mirrors the public process/session helper surface used by core
execution paths. It is intentionally dependency-light and standard-library
first. Native ConPTY, inherited file-descriptor PTY spawning, and exact
portable-pty behavior are treated as non-blocking runtime/operational
differences after the module-owned Rust behavior contracts are covered.

## Module status

| Rust module | Python surface | Status | Evidence |
| --- | --- | --- | --- |
| `src/lib.rs` public facade | package-root exports and aliases | complete | Crate-root constants, helper re-exports, and `ExecCommandSession` / `SpawnedPty` aliases are covered by `tests/test_utils_pty_lib_rs.py`. |
| `src/process.rs` | `TerminalSize`, `ProcessHandle`, `ProcessDriver`, `spawn_from_driver` | complete | Terminal size defaults/u16 bounds, no-PTY resize error text, close-stdin writer removal, and driver-backed resize hook forwarding are covered by `tests/test_utils_pty_process_rs.py`. |
| `src/process_group.rs` | `process_group` helper namespace | complete | Unix/no-op platform branching, parent-death signal error/race behavior, EPERM `setsid` fallback, process-group SIGKILL/SIGTERM dispatch, ESRCH best-effort handling, and unexpected OS error propagation are covered by `tests/test_utils_pty_process_group_rs.py`. |
| `src/pipe.rs` | `spawn_pipe_process`, `spawn_pipe_process_no_stdin`, `spawn_pipe_process_no_stdin_with_inherited_fds` | complete | Missing-program errors, piped stdin, null stdin, env_clear behavior, split stdout/stderr, Unix inherited-fd preservation, and Linux pre-exec detach/parent-death setup are covered by `tests/test_utils_pty_pipe_rs.py`. |
| `src/pty.rs` facade slice | `conpty_supported`, `spawn_process`, `spawn_pty_process`, `spawn_process_with_inherited_fds`, `_PtyChildTerminator` | complete | Platform support shape, `spawn_process` empty-inherited-fd delegation, crate-root `spawn_pty_process` alias behavior, PTY missing-program error text including inherited-fd branch priority, cfg(not(unix)) inherited-fd ignore behavior including non-Windows/non-Unix targets, portable-PTY `arg0` command-builder semantics, Unix inherited-fd dispatch to the native preserving branch, `openpty` setup/error context, child fd cleanup preservation rules, raw-PTY resize hook installation, preserving-branch RawPidTerminator process-group-only termination, and PTY child terminator process-group/direct-child kill ordering and error combination are covered by `tests/test_utils_pty_pty_rs.py`; live Unix PTY inherited-fd/controlling-terminal validation and Windows ConPTY are non-blocking runtime notes. |

The crate is `complete` for the dependency-light Python port. Native PTY
behavior, inherited file descriptor PTY live validation on a Unix runner, exact
portable-pty behavior, Linux parent-death signal live validation, and Windows
ConPTY integration remain optional platform/runtime checks rather than crate
completion blockers.
