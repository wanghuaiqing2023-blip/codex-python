# Local HTTP zero max_output_tokens

## Upstream graph and source slice

- Graph node: `class:codex-rs/core/src/tools/context.rs#ExecCommandToolOutput`
- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec.rs#ExecCommandArgs`
- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs#WriteStdinArgs`
- Source: `codex/codex-rs/core/src/tools/context.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`

Rust parses `max_output_tokens` as `Option<usize>` for both `exec_command` and
`write_stdin`. A model-supplied value of `0` is therefore valid and is preserved
through `ExecCommandToolOutput`, where model-facing output is truncated with a
zero-token budget instead of falling back to the default output budget.

## Python changes

- Preserved `max_output_tokens=0` in local HTTP shell invocation parsing.
- `exec_command` output now truncates to the zero-token marker when requested.
- `write_stdin` now passes a zero-sized output budget to the active session
  manager instead of treating the argument as unset.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_max_output_tokens_zero_truncates_all_output tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_max_output_tokens_uses_token_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_preserves_zero_max_output_tokens tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_passes_max_output_tokens`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
