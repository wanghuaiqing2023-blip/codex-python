# Local HTTP Default Tool Loop

## Scope

- Moved the local HTTP `exec` path closer to Rust's normal user-facing runtime by enabling the shell/apply_patch tool loop by default.
- Kept an explicit escape hatch: `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=0` disables the local tool loop for tests or diagnosis.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:564`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request`
  - `function:codex-rs/core/src/session/turn.rs#built_tools`
  - `function:codex-rs/core/src/tools/spec_plan.rs#add_shell_tools:522`
- Rust source read:
  - `codex/codex-rs/exec/src/lib.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/core/src/tools/spec_plan.rs`

## Rust behavior confirmed

- `run_sampling_request` builds a `ToolRouter` for each turn before constructing the prompt.
- Tool planning adds shell tools whenever the turn has an execution environment.
- `apply_patch` is added as a core utility tool when an environment exists and the model supports the apply-patch tool type.
- There is no separate user-facing environment flag required before normal `exec` exposes and dispatches local command/file-edit tools.

## Python changes

- `pycodex/exec/local_runtime.py`
  - `local_http_exec_shell_tools_enabled()` now defaults to `True`.
  - Explicit truthy values still enable the loop.
  - Explicit falsey values (`0`, `false`, `off`, etc.) disable it.
- `tests/test_exec_local_runtime.py`
  - Added coverage for the new default-on/explicit-off behavior.
- `tests/test_cli_parser.py`
  - Updated tests that intentionally exercise the raw one-shot HTTP sampler to disable shell tools explicitly.
  - Existing shell-loop tests now cover the default-on CLI path.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`
- Focused CLI/runtime tests for the default shell-tool path and explicit raw-sampler path.
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- The local HTTP tool loop is still a Python compatibility implementation, not a full Rust `ToolRouter` port. It covers the common shell/apply_patch/write_stdin/request_permissions path while deeper MCP/plugin/dynamic tool behavior remains out of scope for the current core slice.
