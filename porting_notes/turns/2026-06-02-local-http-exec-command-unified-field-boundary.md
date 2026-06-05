# Local HTTP exec_command unified field boundary

## Upstream reference

- `codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- `codex/codex-rs/protocol/src/models.rs`

Rust keeps the unified `exec_command` argument surface separate from the older
`shell_command` surface. `ExecCommandArgs` accepts `cmd` and `workdir`; it does
not define legacy `command`, `cwd`, `script`, `argv`, `timeout`, or
`timeout_ms` fields. Serde ignores unknown fields, so those aliases should not
affect unified exec execution.

## Python changes

- Added a `unified_exec` parsing mode for local HTTP shell invocation
  reconstruction.
- `exec_command` now reads only `cmd` for the command and only `workdir` for the
  working directory.
- `exec_command` ignores legacy timeout aliases; local helper timeout remains
  available through the helper's own `timeout` parameter.
- Legacy `shell` / `shell_command` calls still accept `command`, `cwd`, and
  timeout aliases for compatibility.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_ignores_legacy_cwd_and_timeout_aliases tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_honors_workdir_argument tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_accepts_cwd_alias tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_uses_workdir_and_timeout_arguments`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
