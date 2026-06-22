# codex-utils-pty/src/pipe.rs Status

Rust crate: `codex-utils-pty`

Rust module: `codex/codex-rs/utils/pty/src/pipe.rs`

Python module: `pycodex.utils.pty`

Status: `complete` for the pipe process behavior contract.

## Behavior Contract

The Python port mirrors the selected pipe module slice:

- empty program names fail before process construction with
  `missing program for pipe spawn`;
- `spawn_pipe_process(...)` uses piped stdin and forwards
  `ProcessHandle.writer_sender()` bytes to the child;
- `spawn_pipe_process_no_stdin(...)` connects child stdin to null so reads
  complete immediately with EOF;
- spawning applies Rust's `env_clear()` shape by passing only the supplied
  environment map to the child process;
- stdout and stderr are drained into separate receivers;
- Unix `spawn_pipe_process_no_stdin_with_inherited_fds(...)` preserves selected
  file descriptors across exec through the standard-library `pass_fds` boundary;
- Linux pipe spawning installs a `pre_exec` equivalent that detaches from the
  parent TTY before setting the parent-death signal with the captured parent
  pid;
- non-Unix inherited-fd requests are ignored, matching Rust's `cfg(not(unix))`
  behavior;
- non-Unix `arg0` requests are ignored, matching Rust's `cfg(not(unix))`
  behavior.

Long-running reader-abort and process-group termination effects are covered by
the sibling `process_group.rs` status and by higher-level runtime tests. Live
Linux parent-death signal validation remains an OS-boundary crate-level gap.

## Evidence

- Rust source: `codex/codex-rs/utils/pty/src/pipe.rs`
- Rust tests:
  - `pipe_process_round_trips_stdin`
  - `pipe_process_can_expose_split_stdout_and_stderr`
  - `pipe_spawn_no_stdin_can_preserve_inherited_fds`
  - related pipe tests in `codex/codex-rs/utils/pty/src/tests.rs`
- Python tests: `tests/test_utils_pty_pipe_rs.py`

Focused validation:

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_pipe_rs.py tests\test_utils_pty_process_rs.py tests\test_utils_pty_process_group_rs.py
python -m pytest tests/test_utils_pty_pipe_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_lib_rs.py tests/test_utils_pty_pty_rs.py tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k utils_pty -q --tb=short
```

Latest result on Windows:

```text
6 passed, 1 skipped
21 passed, 1 skipped
27 passed, 2 skipped
1 passed, 17 deselected
```
