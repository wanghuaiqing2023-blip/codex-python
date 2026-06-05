# 2026-06-02 core runtime default runtime boundary

## Context

- The Rust graph still points to `codex-rs/exec/src/lib.rs::run_exec_session`
  as the high-impact CLI entrypoint for the common exec flow.
- Python already has a direct core path for fresh `exec`, `exec resume`, and
  `review` behind `PYCODEX_EXEC_CORE=1`.
- The CLI core branch still depended on local HTTP helper names for model
  runtime construction and resume rollout alignment.

## Python change

- Extended `pycodex.exec.core_runtime` with core-facing facade names:
  - `build_default_core_exec_runtime`
  - `align_core_exec_resume_model_client`
- Updated the CLI core branch to use those facade names.
- Kept the local HTTP branch on `build_default_local_http_exec_runtime` and
  `align_local_http_exec_resume_model_client`.
- Updated facade and CLI tests so core and local HTTP resume paths patch their
  own import boundaries.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner -q`
  - 5 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_resume_core_env or main_exec_resume_local_http or align_local_http_exec_resume" -q`
  - 10 passed, 526 deselected.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - first run exposed an order-sensitive doctor test failure, but that test
    passed when run directly.
  - rerun completed with 741 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Continue moving core-path orchestration behind `pycodex.exec.core_runtime`
  until the CLI can treat direct core execution as the primary runtime path.
- Investigate the transient doctor smoke failure if it recurs.
