# codex-exec-server/src/local_process.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/local_process.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the environment construction slice:

- `child_env(params)` returns exactly `params.env` when `env_policy` is absent.
- when `env_policy` is present, `shell_environment_policy` converts
  `ExecEnvPolicy` into a `ShellEnvironmentPolicy` with `use_profile = false`.
- the shell environment is created from that policy first.
- `params.env` overlays the policy-created environment, so request env values
  win over policy `set` values.
- Windows PATHEXT insertion is inherited from the already-ported protocol
  shell-environment helper, matching upstream behavior.

Windows ConPTY spawning, terminal resize, and exact Windows/job-object
process-tree termination remain optional platform/runtime checks for this
dependency-light port.

The Python port also mirrors the in-memory read response shaping slice:

- unknown process ids map to `invalid_request("unknown process id ...")`.
- starting process entries map to `invalid_request("process id ... is starting")`.
- retained chunks are filtered by `seq > after_seq`.
- `max_bytes` limits later chunks while still returning the first available
  chunk even if it exceeds the limit.
- exit state increments `next_seq` and is reported as an exited terminal event
  without requiring output chunks.
- closed state is reported separately from exit state.
- late retained output after exit keeps its sequence number and visible exit
  code.
- closed processes are evicted after the Rust retention delay, while avoiding
  removal of a replacement process with the same id.

The Python port also mirrors the in-memory write and terminate status slices:

- writes to unknown processes return `WriteStatus::UnknownProcess`.
- writes to starting entries return `WriteStatus::Starting`.
- writes to running processes without TTY or piped stdin return
  `WriteStatus::StdinClosed`.
- writes to TTY or piped-stdin processes record bytes and return
  `WriteStatus::Accepted`.
- writer failure maps to `internal_error("failed to write to process stdin")`.
- terminating unknown, starting, or already-exited processes returns
  `TerminateResponse { running: false }`.
- terminating a running process marks it terminated and returns
  `TerminateResponse { running: true }`.

The Python port also mirrors the start-tracking and spawn-error slice:

- empty argv maps to `invalid_params("argv must not be empty")` without
  inserting a process entry.
- existing process ids map to `invalid_request("process ... already exists")`.
- a temporary `Starting` entry is inserted before spawn.
- spawn failure removes that `Starting` entry and maps the error to
  `internal_error`.
- spawn success installs a running entry configured from `tty` and
  `pipe_stdin`.

The Python port also mirrors the dependency-light non-TTY pipe runtime slice:

- when no test spawn hook is provided and `tty` is false, start spawns a real
  subprocess with stdout/stderr pipes.
- absent `env_policy`, the child environment is exactly the request env passed
  through `child_env`.
- stdout and stderr bytes are retained as `ExecOutputStream::Stdout` and
  `ExecOutputStream::Stderr` chunks.
- `exec_read(wait_ms)` waits for output, exit, or closed state changes.
- process exit records an exit terminal event and exposes the exit code.
- closed is reported after both output streams finish and the exit code exists.
- when `pipe_stdin` is true, `exec_write` writes bytes to the real subprocess
  stdin writer and returns `WriteStatus::Accepted`.
- on POSIX, non-TTY pipe subprocesses are started in a child process group and
  termination targets that process group, matching the `codex_utils_pty`
  pipe backend used by Rust `LocalProcess`.

The Python port also mirrors the dependency-light POSIX PTY runtime slice:

- when no test spawn hook is provided, `tty` is true, and the platform is
  POSIX, start spawns a real subprocess attached to a standard-library PTY.
- the PTY is initialized with Rust's `TerminalSize::default()` dimensions
  of 24 rows by 80 columns.
- both local process stream tasks use `ExecOutputStream::Pty`, matching
  Rust's `params.tty` stream mapping for stdout and stderr receivers.
- `exec_write` writes bytes to the PTY master even when `pipe_stdin` is
  false, matching Rust's PTY session writer semantics.
- on Windows, where the Python standard library has no ConPTY equivalent,
  the dependency-light boundary remains the existing Rust-shaped internal
  error used by the process-handler boundary tests.
- POSIX PTY termination also targets the child process group through the same
  dependency-light wrapper.

The Python port also mirrors the `ExecBackend`/`ExecProcess` facade slice:

- `LocalProcess.start(...)` returns `StartedExecProcess` with a process handle.
- `LocalExecProcess.process_id()` returns the owned process id.
- `LocalExecProcess.read(...)`, `write(...)`, and `terminate(...)` delegate to
  the same retained-output, stdin, and terminate handlers used by JSON-RPC.
- `subscribe_events()` returns replay-then-live output, exited, and closed
  events from the process event log.
- `subscribe_wake()` exposes the latest process-owned sequence number when
  output, exit, or closed state changes.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/local_process.rs`
- Rust tests:
  - `child_env_defaults_to_exact_env`
  - `child_env_applies_policy_then_overlay`
- Python tests: `tests/test_exec_server_local_process_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_local_process_rs.py
python -m pytest tests/test_exec_server_local_process_rs.py -q --tb=short
```

Latest result:

```text
20 passed
```

Completion validation on 2026-06-21:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_local_process_rs.py
python -m pytest tests/test_exec_server_local_process_rs.py -q --tb=short
21 passed
python -m pytest tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_handler_rs.py -q --tb=short
43 passed
```
