# Core runtime config summary boundary

## Context

The Python `exec` core path is being separated from the older local HTTP naming while preserving the same user-visible CLI behavior. After moving resume target resolution, rollout input selection, persistence, and result emission behind `pycodex.exec.core_runtime`, the remaining CLI-owned presentation step was the initial config/session summary.

## Change

- Added `emit_core_exec_config_summary(...)` to `pycodex.exec.core_runtime`.
- Kept the existing human and JSON event-processor behavior intact:
  - human output uses the stderr/version path;
  - JSON output uses the stdout `output=` path;
  - resume summaries include rollout-derived initial messages when a rollout path is available.
- Updated the core `exec` CLI branch to call the new core helper instead of building and printing the summary inline.
- Added focused tests for human and JSON summary emission.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - `16 passed`
- `uvx pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http" -q`
  - `12 passed, 524 deselected`
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `741 passed, 1 skipped, 98 subtests passed`

## Follow-up

The core execution path now has a clearer Python-facing boundary, but much of the actual implementation still delegates to local HTTP runtime internals. Next high-value work is to keep moving request construction, stream handling, tool dispatch, and final answer assembly behind direct core-runtime names and then replace compatibility delegation slice by slice.
