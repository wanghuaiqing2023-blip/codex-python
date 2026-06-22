# codex-utils-pty/src/pty.rs Status

Rust crate: `codex-utils-pty`

Rust module: `codex/codex-rs/utils/pty/src/pty.rs`

Python module: `pycodex.utils.pty`

Status: `complete` for the dependency-light PTY facade slice.

## Behavior Contract

The Python port mirrors this dependency-light PTY facade slice:

- `conpty_supported()` returns true on non-Windows platforms, matching the Rust
  `cfg(not(windows))` implementation;
- on Windows, `conpty_supported()` is modeled as a Windows 10+ version gate,
  standing in for the Rust `win::conpty_supported()` probe without binding to
  native ConPTY APIs;
- `spawn_process(...)` is exposed as the Rust module's thin wrapper over
  `spawn_process_with_inherited_fds(..., &[])`, preserving all other arguments
  and the requested terminal size;
- crate-root `spawn_pty_process(...)` follows the Rust `pub use
  pty::spawn_process as spawn_pty_process` facade relationship;
- empty PTY program names fail before backend selection with
  `missing program for PTY spawn`;
- the empty-program error is raised before the Unix inherited-fd dispatch,
  matching the Rust branch ordering in `spawn_process_with_inherited_fds`;
- `spawn_process_with_inherited_fds(...)` ignores inherited-fd requests on
  non-Unix platforms, matching Rust's `cfg(not(unix))` branch, including
  non-Windows/non-Unix targets rather than treating every non-Windows target
  as Unix;
- the portable PTY branch treats `arg0` as the `CommandBuilder::new(...)`
  command name, matching Rust `arg0.as_ref().unwrap_or(&program.to_string())`
  rather than the pipe branch's Unix `argv[0]` override semantics;
- on Unix, non-empty `inherited_fds` dispatch to a standard-library
  `openpty`/`preexec_fn` preserving branch instead of the portable PTY path;
- the Unix preserving branch sets CLOEXEC on master/slave fds, applies the
  initial `TerminalSize`, reports `failed to openpty` context on open errors,
  preserves stdio/requested/CLOEXEC fds in the child cleanup helper, and
  attaches a raw-PTY resize hook to the returned `ProcessHandle`;
- the Unix preserving branch installs the Rust `RawPidTerminator` shape by
  terminating the spawned child's process group directly from the returned
  `ProcessHandle`;
- `_PtyChildTerminator.kill()` mirrors the Rust PTY child terminator branch:
  on Unix with a cached process group it kills the process group before trying
  the direct child killer, treats direct-child NotFound as falling back to the
  process-group result, and ignores a direct-child error when the group kill
  succeeded;
- live Unix PTY inherited-fd, controlling-terminal, and resize behavior remain
  optional platform/runtime validation rather than module-completion blockers.

The current Python `spawn_pty_process(...)` still uses the dependency-light
pipe-backed compatibility runtime. Native PTY behavior, controlling-terminal
setup, PTY resize on owned handles, and Windows ConPTY integration remain
outside this facade slice as non-blocking runtime differences.

## Evidence

- Rust source: `codex/codex-rs/utils/pty/src/pty.rs`
- Rust tests:
  - `pty_python_repl_emits_output_and_exits`
  - `pipe_and_pty_share_interface`
  - PTY inherited-fd and resize tests in `codex/codex-rs/utils/pty/src/tests.rs`
- Python tests: `tests/test_utils_pty_pty_rs.py`

Focused validation:

```text
python -m py_compile pycodex\utils\pty\__init__.py tests\test_utils_pty_pty_rs.py tests\test_utils_pty_pipe_rs.py tests\test_utils_pty_process_rs.py tests\test_utils_pty_process_group_rs.py
python -m pytest tests/test_utils_pty_pty_rs.py -q --tb=short
python -m pytest tests/test_utils_pty_pty_rs.py tests/test_utils_pty_pipe_rs.py tests/test_utils_pty_process_rs.py tests/test_utils_pty_process_group_rs.py -q --tb=short
python -m pytest tests/test_external_crate_interfaces.py -k utils_pty -q --tb=short
```

Latest result on Windows:

```text
18 passed
41 passed, 1 skipped
1 passed, 17 deselected
```
