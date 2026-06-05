# 2026-06-02 core runtime persist result boundary

## Context

- The direct core path now owns resume target resolution and rollout input item
  selection in `pycodex.exec.core_runtime`.
- The CLI core branch still called `persist_core_exec_rollout` directly for
  fresh exec and review, while resume implicitly skipped persistence by not
  entering either branch.
- Rust's `run_exec_session` keeps this kind of session/rollout behavior inside
  the execution path instead of the top-level CLI parser.

## Python change

- Added `persist_core_exec_result(...)` to `pycodex.exec.core_runtime`.
- The helper:
  - persists fresh exec and review results through `persist_core_exec_rollout`,
  - uses `core_exec_rollout_input_items(...)` for command-specific input item
    selection,
  - returns `False` and skips persistence for resume.
- Updated the CLI core branch to call `persist_core_exec_result(...)` instead
  of `persist_core_exec_rollout(...)` directly.
- Updated CLI tests so the parser asserts the runtime persistence boundary is
  called, while `tests/test_exec_core_runtime.py` owns detailed persistence
  behavior coverage.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - 13 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http" -q`
  - 12 passed, 524 deselected.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue moving core execution orchestration from `pycodex.cli.parser` into
  `pycodex.exec.core_runtime`.
- The next likely slice is a core result-emission wrapper that owns final result
  rendering and completion status messaging for the direct core path.
