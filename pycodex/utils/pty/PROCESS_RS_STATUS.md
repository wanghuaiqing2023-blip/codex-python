# codex-utils-pty/src/process.rs Status

Rust crate: `codex-utils-pty`

Rust module: `codex/codex-rs/utils/pty/src/process.rs`

Python module: `pycodex.utils.pty`

Status: `complete`

## Behavior Contract

The Python port mirrors the selected process module slice:

- `TerminalSize::default()` uses 24 rows by 80 columns.
- `TerminalSize` rows and columns are unsigned 16-bit cell counts.
- `ProcessHandle.resize(...)` reports `process is not attached to a PTY` when
  neither owned PTY handles nor a driver resizer are available.
- `ProcessHandle.close_stdin()` removes the internal writer path so a later
  `writer_sender()` behaves like Rust's closed fallback sender and does not
  forward bytes to the original process writer.
- `spawn_from_driver(ProcessDriver { resizer: Some(...) })` installs the driver
  resizer hook on the returned session.
- resizing a driver-backed session forwards the exact requested
  `TerminalSize` into that hook.

Owned portable-pty handles, raw Unix PTY resizing, and Windows ConPTY resizing
remain native runtime boundaries.

## Evidence

- Rust source: `codex/codex-rs/utils/pty/src/process.rs`
- Rust test: `driver_backed_process_can_resize_via_resizer_hook`
- Python tests: `tests/test_utils_pty_process_rs.py`

Focused validation:

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_process_rs.py
python -m pytest tests/test_utils_pty_process_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_lib_rs.py tests/test_utils_pty_pty_rs.py tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k utils_pty -q --tb=short
```

Latest result:

```text
4 passed
23 passed, 2 skipped
1 passed, 17 deselected
```
