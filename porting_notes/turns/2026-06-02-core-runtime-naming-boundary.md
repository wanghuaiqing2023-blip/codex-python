# 2026-06-02 core runtime naming boundary

## Context

- The CLI direct core path now covers fresh `exec`, `exec resume`, and `review` through `PYCODEX_EXEC_CORE=1`.
- Those paths still reused several `local_http_*` helper names for summary rendering, rollout persistence, and review parent-thread input rendering.
- This turn keeps behavior stable while adding clearer core-facing names for the helpers that now serve both compatibility and direct-core execution.

## Python change

- Added core-facing aliases in `pycodex.exec.local_runtime`:
  - `core_exec_enabled`
  - `core_exec_config_summary`
  - `core_exec_initial_messages_from_rollout`
  - `core_review_rollout_input_items`
  - `persist_core_exec_rollout`
  - `persist_core_exec_resume_rollout`
- Updated the CLI core branch to use those core-facing names.
- Kept the existing `local_http_*` names exported for compatibility and for the existing local HTTP path.

## Validation

- `uvx pytest tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_core_runtime_aliases_preserve_local_runtime_helpers tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_runtime_uses_env_provider_and_model -q`
  - 5 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_exec_resume_core_env or main_review_core_env or main_review_local_http_runtime" -q`
  - 4 passed.
- `uvx pytest tests/test_exec_local_runtime.py -k "core_runtime_aliases or core_http_resume_runner or review_core_http_sampling or default_local_http_runtime_uses_env_provider" -q`
  - 4 passed.
- `python -m py_compile pycodex/cli/parser.py pycodex/exec/local_runtime.py tests/test_cli_parser.py tests/test_exec_local_runtime.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue splitting core runtime helpers out of `local_runtime.py` once the common CLI path is stable enough to make a structural move without hiding behavior changes.
- Keep old compatibility exports until downstream tests and callers no longer rely on the `local_http_*` names.
