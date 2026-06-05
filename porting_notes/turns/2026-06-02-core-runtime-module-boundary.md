# 2026-06-02 core runtime module boundary

## Context

- The direct in-memory core execution path is now available for fresh `exec`,
  `exec resume`, and `review` behind `PYCODEX_EXEC_CORE=1`.
- The implementation remains in `pycodex.exec.local_runtime` while the Python
  port keeps local HTTP compatibility behavior stable.
- This turn adds a core-facing module boundary so future core CLI work can
  depend on `pycodex.exec.core_runtime` instead of continuing to grow the
  transitional local runtime namespace.

## Python change

- Added `pycodex.exec.core_runtime` as a facade over the existing core-facing
  helpers and runners:
  - `core_exec_enabled`
  - `core_exec_config_summary`
  - `core_exec_initial_messages_from_rollout`
  - `core_review_rollout_input_items`
  - `persist_core_exec_rollout`
  - `persist_core_exec_resume_rollout`
  - direct core user-turn, resume, and review runners
- Updated the CLI core branch to import those helpers from
  `pycodex.exec.core_runtime`.
- Kept local HTTP compatibility imports in `pycodex.exec.local_runtime`.
- Added facade tests in `tests/test_exec_core_runtime.py`.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner -q`
  - 5 passed.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue moving core-path behavior behind `pycodex.exec.core_runtime` as each
  slice becomes stable.
- Keep `local_runtime` compatibility exports until existing callers and tests
  no longer depend on them.
