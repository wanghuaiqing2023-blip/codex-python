# codex-utils-pty/src/lib.rs Status

Rust crate: `codex-utils-pty`

Rust module: `codex/codex-rs/utils/pty/src/lib.rs`

Python module: `pycodex.utils.pty`

Status: `complete`

## Behavior Contract

The Python package root mirrors the Rust crate-root facade:

- public module ownership for pipe, process, process-group, and PTY helpers is
  represented by the merged dependency-light `pycodex.utils.pty` package;
- `DEFAULT_OUTPUT_BYTES_CAP` is `1024 * 1024`;
- crate-root re-export names are available at package root for pipe spawn
  helpers, driver/process handles, `TerminalSize`, `combine_output_receivers`,
  `spawn_from_driver`, `conpty_supported`, and `spawn_pty_process`;
- backwards-compatible aliases are preserved: `ExecCommandSession` is
  `ProcessHandle`, and `SpawnedPty` is `SpawnedProcess`.

## Evidence

- Rust source: `codex/codex-rs/utils/pty/src/lib.rs`
- Rust tests: `codex/codex-rs/utils/pty/src/tests.rs` imports and exercises the
  facade through crate-root names such as `ProcessDriver`, `SpawnedProcess`,
  `TerminalSize`, `combine_output_receivers`, `spawn_from_driver`,
  `spawn_pipe_process`, `spawn_pipe_process_no_stdin`, and
  `spawn_pty_process`.
- Python tests: `tests/test_utils_pty_lib_rs.py`

Focused validation:

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_lib_rs.py
python -m pytest tests/test_utils_pty_lib_rs.py -q --tb=short
```

Latest result:

```text
2 passed
```

