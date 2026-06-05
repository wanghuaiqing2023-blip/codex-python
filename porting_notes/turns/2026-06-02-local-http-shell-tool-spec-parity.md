# Local HTTP Shell Tool Spec Parity

## Scope

- Continued the core `exec -> model request -> tool dispatch -> final answer` path.
- Aligned the local HTTP model-visible shell tool specs with Rust Codex's `shell_spec` implementation.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/tools/handlers/shell_spec.rs#create_exec_command_tool`
  - `function:codex-rs/core/src/tools/handlers/shell_spec.rs#create_write_stdin_tool`
  - `function:codex-rs/core/src/tools/handlers/shell_spec.rs#unified_exec_output_schema`
  - `class:codex-rs/core/src/tools/handlers/shell_spec.rs#CommandToolOptions`
  - `function:codex-rs/core/src/tools/spec_plan.rs#add_shell_tools`
- Rust source read:
  - `codex/codex-rs/core/src/tools/handlers/shell_spec.rs`
  - `codex/codex-rs/core/src/tools/spec_plan.rs`

## Rust behavior confirmed

- `exec_command` exposes `cmd`, `workdir`, `shell`, `tty`, `yield_time_ms`, and `max_output_tokens`.
- `login` is exposed only when `allow_login_shell` is true.
- `additional_permissions` is exposed only when exec permission approvals are enabled.
- `cwd`, `timeout`, and `timeout_ms` are not model-visible `exec_command` schema fields in Rust.
- `write_stdin` shares the unified exec output schema.

## Python changes

- `pycodex/exec/local_runtime.py`
  - `local_http_shell_tool_spec()` now delegates to `pycodex.core.shell_spec.create_exec_command_tool()` with `CommandToolOptions`.
  - `local_http_write_stdin_tool_spec()` now delegates to `pycodex.core.shell_spec.create_write_stdin_tool()`.
  - `local_http_exec_command_output_schema()` now delegates to `pycodex.core.shell_spec.unified_exec_output_schema()`.
  - The parser still accepts compatibility aliases such as `cwd`, `timeout`, and `timeout_ms` when older callers provide them, but these are no longer advertised to the model.
- `tests/test_exec_local_runtime.py`
  - Updated shell tool spec assertions to reflect Rust-visible fields.
  - Added coverage for the disabled `allow_login_shell` / disabled exec-permission-approvals option path.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- Local HTTP currently defaults `allow_login_shell=True` and `exec_permission_approvals_enabled=True` because the lightweight local exec path does not yet thread the full Rust feature/config flags into tool spec construction.
