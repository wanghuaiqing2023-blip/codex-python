# 2026-06-02 core runtime result emission boundary

## Context

- The direct core path now owns resume target resolution, rollout input item
  selection, and core result persistence in `pycodex.exec.core_runtime`.
- The CLI core branch still emitted final results through the local HTTP helper
  and printed the core completion status message itself.
- That output is user-facing runtime behavior for the direct core path, so it
  belongs behind the core runtime boundary.

## Python change

- Added `emit_core_exec_result(...)` to `pycodex.exec.core_runtime`.
- The helper:
  - delegates final result rendering to the existing compatible emitter,
  - prints `pycodex: completed core non-interactive <command> execution.`
    using the top-level user-facing command name.
- Updated the CLI core branch to call `emit_core_exec_result(...)`.
- Added unit coverage for the helper and preserved existing CLI output tests.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - 14 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http" -q`
  - 12 passed, 524 deselected.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue moving core execution orchestration out of `pycodex.cli.parser`.
- The next useful slice is likely core config-summary rendering, so the core
  branch owns summary construction and emission together with result emission.
