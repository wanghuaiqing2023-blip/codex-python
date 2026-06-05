# 2026-06-02 CLI in-memory core exec entrypoint

## Upstream slice

- Used the graph-guided core `exec` path and confirmed behavior from Rust source:
  - `codex-rs/exec/src/lib.rs`
    - `run_main` builds the exec config and submits user input into an exec session.
    - `run_exec_session` converts CLI prompt/images into `UserInput` and drives a turn.
  - `codex-rs/core/src/session/turn.rs`
    - `run_turn` owns the common loop: record input, build the sampling request, execute tool calls, run follow-up sampling, and finish with model output.

## Python change

- Added an explicit experimental `PYCODEX_EXEC_CORE=1` switch for fresh `codex exec` turns.
- When enabled, the CLI now runs through `run_exec_user_turn_core_http_sampling`, which:
  - builds the stdlib HTTP sampler from the existing model client/provider runtime;
  - enters the in-memory `run_exec_user_turn_core_sampling` loop;
  - reuses the same CLI config summary, result rendering, and rollout persistence paths as the local runtime.
- `exec resume` and `review` are intentionally left on the existing paths for now; this slice only advances the fresh user-turn entrypoint.

## Validation

- `uvx pytest tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_runtime_uses_env_provider_and_model -q`
  - 2 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_exec_local_http_default or main_exec_local_http_shell_tools_flag or main_exec_local_http_model_provider" -q`
  - 3 passed.
- `uvx pytest tests/test_exec_local_runtime.py -k "core_sampling or http_sampling_uses_core or default_local_http_runtime_uses_env_provider_and_model" -q`
  - 4 passed.
- `python -m py_compile pycodex/cli/parser.py pycodex/exec/local_runtime.py tests/test_cli_parser.py tests/test_exec_local_runtime.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 736 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Extend the direct core entrypoint beyond fresh turns once the resume/review rollout behavior is ready.
- Continue reducing reliance on the local HTTP compatibility naming; the new core path still reuses some local runtime helpers for auth, summary, and persistence.
