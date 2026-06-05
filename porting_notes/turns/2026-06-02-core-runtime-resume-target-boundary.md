# 2026-06-02 core runtime resume target boundary

## Context

- The Rust dependency graph continues to identify
  `codex-rs/exec/src/lib.rs::run_exec_session` as the central CLI execution
  entrypoint for fresh exec, resume, review, and session startup.
- The Python CLI core branch already routes fresh `exec`, `exec resume`, and
  `review` through direct in-memory core execution behind `PYCODEX_EXEC_CORE=1`.
- Resume-specific thread/session resolution was still embedded in
  `pycodex.cli.parser`, even though it is runtime session preparation logic.

## Python change

- Added `CoreExecResumeTarget` to `pycodex.exec.core_runtime`.
- Added `resolve_core_exec_resume_target(...)`, which:
  - rejects missing resume arguments with the existing user-facing error,
  - distinguishes direct UUID thread ids from named sessions,
  - aligns the model client to the selected local rollout,
  - returns the resolved thread id, session name, and rollout path.
- Updated the CLI core branch to consume the resolved target instead of
  performing direct resume resolution itself.
- Kept the local HTTP branch unchanged on the compatibility helper names.

## Validation

- `uvx pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner -q`
  - 8 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_resume_core_env or main_exec_resume_local_http or align_local_http_exec_resume" -q`
  - 10 passed, 526 deselected.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 741 passed, 1 skipped, 98 subtests passed.
- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
  - passed.

## Follow-up

- Continue moving direct core execution orchestration from `pycodex.cli.parser`
  into `pycodex.exec.core_runtime`, while leaving local HTTP compatibility
  behavior stable.
- The next likely slice is a core execution result wrapper that owns summary
  rendering, persistence selection, and final result emission for the core path.
