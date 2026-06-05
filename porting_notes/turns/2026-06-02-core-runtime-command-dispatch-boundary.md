# Core runtime command dispatch boundary

## Context

The upstream `codex-rs/exec/src/lib.rs` `run_exec_session` flow keeps the exec session orchestration in one runtime path: it starts or resumes the thread, emits the config summary, starts either a user turn or review turn, processes events until completion, and then prints final output. The Python port already had separate core-facing helpers for resume target resolution, config summary emission, result persistence, and final result emission, but the CLI still directly selected the fresh/review/resume runners.

## Change

- Added `run_core_exec_command(...)` to `pycodex.exec.core_runtime`.
- Moved core command dispatch out of `pycodex.cli.parser`:
  - fresh `exec` runs through `run_exec_user_turn_core_http_sampling`;
  - `review` runs through `run_exec_review_core_http_sampling` and persists the rendered review turn;
  - `resume` runs through `run_exec_resume_user_turn_core_http_sampling` with the already resolved `CoreExecResumeTarget` and does not separately persist a new rollout.
- Updated the CLI core branch so it prepares config/runtime, emits the summary, delegates execution to `run_core_exec_command`, and then emits the final result.
- Added focused unit tests for fresh exec, review, and resume command dispatch from the core runtime boundary.

## Validation

- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_local_http_default_uses_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - `20 passed`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http" -q`
  - `12 passed, 524 deselected`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `741 passed, 1 skipped, 98 subtests passed`

## Follow-up

This is still a boundary extraction: the actual fresh/review/resume execution functions continue to delegate into the local runtime compatibility implementation. The next core-path slice should move request construction, stream event processing, or tool-dispatch loop ownership further into `pycodex.exec.core_runtime` / `pycodex.core`, reducing the remaining local HTTP naming and compatibility coupling.
