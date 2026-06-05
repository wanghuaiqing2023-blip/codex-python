# 2026-06-02 Core runtime parallel tool calls

## Upstream behavior

- `codex-rs/core/src/session/turn.rs` sets `Prompt.parallel_tool_calls` from
  `turn_context.model_info.supports_parallel_tool_calls`.
- `codex-rs/core/src/client.rs` forwards `prompt.parallel_tool_calls` into the
  Responses request body.
- Rust config editing preserves provider `supports_parallel_tool_calls` when the
  provider capability is enabled.

## Python port progress

- Added `supports_parallel_tool_calls` to the local exec `LocalHttpModelInfo`.
- Wired `[model_providers.<id>].supports_parallel_tool_calls = true` from the
  local exec config mapping into the model metadata used by core prompt
  assembly.
- Added focused coverage that:
  - default local HTTP runtime reads the provider capability from config;
  - core exec sampling emits `parallel_tool_calls: true` in the first request
    when model metadata enables it.

## Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_run_exec_user_turn_core_sampling_uses_model_parallel_tool_calls tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_runtime_uses_config_provider_parallel_tool_calls tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_run_exec_user_turn_core_sampling_uses_config_allow_login_shell_for_tools -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
