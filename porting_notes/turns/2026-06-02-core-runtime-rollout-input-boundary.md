# 2026-06-02 core runtime rollout input boundary

## Context

- The direct core CLI path now covers fresh `exec`, `exec resume`, and `review`
  behind `PYCODEX_EXEC_CORE=1`.
- The CLI core branch still selected rollout input items directly:
  - fresh exec persisted the initial user-turn items,
  - review persisted a synthetic review prompt/result item,
  - resume did not persist a new top-level rollout input from the CLI branch.
- That selection affects local rollout replay and belongs to the core runtime
  execution boundary rather than the top-level CLI parser.

## Python change

- Added `core_exec_rollout_input_items(command, plan, result)` to
  `pycodex.exec.core_runtime`.
- Updated the CLI core fresh exec and review persistence calls to use that
  helper.
- Kept local HTTP compatibility persistence logic unchanged.
- Added unit coverage for review, fresh exec, resume, and non-user-turn input
  selection.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - 11 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http" -q`
  - 12 passed, 524 deselected.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue moving direct core execution orchestration from `pycodex.cli.parser`
  into `pycodex.exec.core_runtime`.
- The next likely boundary is a core result persistence helper that owns the
  `persist_core_exec_rollout` call for fresh exec/review while preserving resume
  behavior.
