# Core runtime allow_login_shell propagation

## Context

Rust's core tool spec path reads `turn_context.config.permissions.allow_login_shell` when building shell / unified exec tools. That setting controls both model-visible schema shape and runtime behavior: when login shells are disabled, the `login` option is hidden/rejected; when enabled, omitted `login` defaults to the configured value.

The Python in-memory exec path already parsed `allow_login_shell` into `ExecSessionConfig`, but `InMemoryCodexSession.new_default_turn()` did not expose `config.permissions.allow_login_shell` on the turn context. As a result, the default core tool router treated login shells as disabled even when the exec config allowed them.

## Change

- Added `allow_login_shell` to `InMemoryCodexSession` with a compatibility-preserving default of `False`.
- Exposed `turn.config.permissions.allow_login_shell` from `new_default_turn()`, matching the Rust lookup path.
- Passed `ExecSessionConfig.allow_login_shell` into the in-memory exec session built by `pycodex.exec.local_runtime._in_memory_exec_session(...)`.
- Added tests for:
  - turn config propagation in `InMemoryCodexSession`;
  - exec core sampling exposing/hiding the `login` tool argument based on `ExecSessionConfig.allow_login_shell`.

## Validation

- `python -m py_compile pycodex/core/session_runtime.py pycodex/exec/local_runtime.py tests/test_core_session_runtime.py tests/test_exec_local_runtime.py`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_core_session_runtime.py::SessionRuntimeTests::test_in_memory_session_turn_config_inherits_allow_login_shell tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_run_exec_user_turn_core_sampling_uses_config_allow_login_shell_for_tools tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_run_exec_user_turn_core_sampling_runs_default_exec_tool_loop -q`
  - `3 passed`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_core_session_runtime.py -q`
  - `81 passed`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_exec_local_runtime.py -k "core_sampling or allow_login_shell or default_exec_tool_loop or request_permissions_tool_spec_shape" -q`
  - `3 passed, 204 deselected`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http or allow_login_shell" -q`
  - `12 passed, 540 deselected`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `742 passed, 1 skipped, 98 subtests passed`

## Follow-up

The generic `InMemoryCodexSession` default remains conservative for compatibility. The exec path now supplies the Rust-configured default, but future direct session construction paths should choose explicit defaults based on their own upstream entrypoint semantics.
