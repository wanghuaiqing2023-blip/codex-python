# pycodex.utils.pty Test Alignment

Rust crate: `codex-utils-pty`

Rust anchor: `codex/codex-rs/utils/pty`

## Module-derived tests

| Python test | Rust source | Behavior contract |
| --- | --- | --- |
| `tests/test_utils_pty_process_rs.py::test_terminal_size_default_and_u16_bounds_match_rust_type` | `src/process.rs::TerminalSize` | TerminalSize defaults to 24x80 and rows/cols are u16 cell counts. |
| `tests/test_utils_pty_process_rs.py::test_process_handle_resize_without_pty_or_resizer_reports_rust_error` | `src/process.rs::ProcessHandle::resize` | Resizing a handle without PTY handles or a resizer reports `process is not attached to a PTY`. |
| `tests/test_utils_pty_process_rs.py::test_writer_sender_after_close_stdin_is_closed` | `src/process.rs::ProcessHandle::close_stdin` | Closing stdin removes the internal writer path so a later writer sender does not forward bytes. |
| `tests/test_utils_pty_process_rs.py::test_driver_backed_process_can_resize_via_resizer_hook` | Rust test `driver_backed_process_can_resize_via_resizer_hook` | Driver-backed sessions install the resizer hook and forward the requested TerminalSize to it. |
| `tests/test_utils_pty_process_group_rs.py` | `src/process_group.rs` and Rust terminate/detach call sites in `src/tests.rs` | Process-group helpers mirror Unix/no-op cfg behavior, Linux parent-death signal error/race branches, EPERM `setsid` fallback, process-group SIGKILL/SIGTERM dispatch, ESRCH best-effort handling, and unexpected OS error propagation. |
| `tests/test_utils_pty_pipe_rs.py` | `src/pipe.rs` and Rust tests `pipe_process_round_trips_stdin`, `pipe_process_can_expose_split_stdout_and_stderr`, `pipe_spawn_no_stdin_can_preserve_inherited_fds` | Pipe spawning rejects empty programs, wires piped/null stdin, applies env_clear, exposes split stdout/stderr, preserves selected inherited file descriptors on Unix, and installs Linux pre-exec detach/parent-death setup. |
| `tests/test_utils_pty_pty_rs.py` | `src/pty.rs` and `src/lib.rs` re-export | PTY facade reports non-Windows ConPTY support as true, exposes `spawn_process` as the Rust thin wrapper over `spawn_process_with_inherited_fds(..., &[])`, keeps crate-root `spawn_pty_process` following that Rust facade, preserves the PTY missing-program error text before inherited-fd dispatch, ignores inherited-fd requests on all cfg(not(unix)) targets including non-Windows/non-Unix platforms, treats portable-PTY `arg0` as the Rust `CommandBuilder::new(...)` command name instead of pipe-style argv0 replacement, dispatches Unix inherited-fd PTY spawning to the native preserving branch, preserves `openpty` setup/error context and fd cleanup rules, installs a raw-PTY resize hook for the preserving branch, mirrors the `RawPidTerminator` process-group-only termination shape for the preserving branch, and mirrors `PtyChildTerminator::kill` process-group/direct-child ordering and error combination. |
| `tests/test_utils_pty_lib_rs.py` | `src/lib.rs` | Crate-root public facade exports constants, process/pipe/PTY helper names, and backwards-compatible aliases. |
| `tests/test_external_crate_interfaces.py::test_utils_pty_pipe_process_public_contract` | `src/lib.rs`, `src/pipe.rs`, `src/pty.rs` | The public facade exposes pipe spawn helpers, default terminal size, stdin writes, output queues, exit state, and no-stdin behavior. |

## Focused validation

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_process_rs.py
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_lib_rs.py
python -m pytest tests/test_utils_pty_lib_rs.py -q --tb=short
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_pty_rs.py tests\test_utils_pty_pipe_rs.py tests\test_utils_pty_process_rs.py tests\test_utils_pty_process_group_rs.py
python -m pytest tests/test_utils_pty_pty_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_pipe_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_process_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_lib_rs.py tests/test_utils_pty_pty_rs.py tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k utils_pty -q --tb=short
```

Latest result:

```text
18 passed
2 passed
6 passed, 1 skipped
4 passed
11 passed
41 passed, 1 skipped
1 passed, 17 deselected
```

## Non-blocking Runtime Notes

The crate is complete for the dependency-light Python port. Native PTY behavior
can still receive optional live Unix validation for inherited file descriptor
preservation, controlling-terminal behavior, and raw PTY resize; exact
portable-pty behavior, Linux parent-death signal live validation, and Windows
ConPTY integration remain platform/runtime checks rather than crate-completion
blockers.
