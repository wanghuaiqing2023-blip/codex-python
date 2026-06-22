# codex-utils-pty/src/process_group.rs Status

Rust crate: `codex-utils-pty`

Rust module: `codex/codex-rs/utils/pty/src/process_group.rs`

Python module: `pycodex.utils.pty`

Status: `complete`

## Behavior Contract

The Python port mirrors the source-level process-group helper slice:

- non-Unix platforms keep the helper functions as no-ops, with
  `terminate_process_group(...)` returning `False`;
- `set_parent_death_signal(...)` is a no-op off Linux, propagates Linux
  `prctl` failures, and sends SIGTERM to the current process when the captured
  parent PID no longer matches after `prctl`;
- Unix `detach_from_tty()` calls `setsid()` and falls back to
  `set_process_group()` only for `EPERM`;
- `kill_process_group_by_pid(...)` resolves a child's process group and sends
  `SIGKILL` to the group;
- missing process groups (`ESRCH`/not found) are treated as best-effort success
  for kill helpers and as `False` for termination;
- unexpected OS errors are propagated to the caller;
- `kill_child_process_group(...)` is a no-op when the child has no pid.

Live Linux parent-death signal integration remains OS-boundary validation, but
the module-owned branching and error/race behavior is covered with injected
`ctypes`/`os` boundaries.

## Evidence

- Rust source: `codex/codex-rs/utils/pty/src/process_group.rs`
- Rust runtime tests: `pipe_process_detaches_from_parent_session`,
  `pipe_terminate_aborts_detached_readers`, and
  `pty_terminate_kills_background_children_in_same_process_group`
  in `codex/codex-rs/utils/pty/src/tests.rs`
- Python tests: `tests/test_utils_pty_process_group_rs.py`

Focused validation:

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_process_group_rs.py
python -m pytest tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_lib_rs.py tests/test_utils_pty_pty_rs.py tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k utils_pty -q --tb=short
```

Latest result:

```text
11 passed
26 passed, 2 skipped
1 passed, 17 deselected
```
