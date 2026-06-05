# 2026-06-02 CLI in-memory core review entrypoint

## Upstream slice

- Continued the graph-guided `codex exec` path into review:
  - `codex-rs/exec/src/lib.rs`
    - `InitialOperation::Review` is built from CLI review args.
    - `review/start` starts a review turn using the review target and current config.
  - `codex-rs/core/src/client_common.rs`
    - `REVIEW_PROMPT` is the review thread system prompt.
  - `codex-rs/core/src/session/turn.rs`
    - review turns still use the common turn loop for request construction, tool execution, follow-up sampling, and final output.

## Python change

- Added `run_exec_review_core_http_sampling`.
- The new runner reuses the existing Python review conversion/rendering behavior:
  - convert the review request into the review user-turn prompt;
  - clear normal project/user instructions from the review config;
  - use `REVIEW_PROMPT` through `LocalHttpReviewModelInfo`;
  - run through `run_exec_user_turn_core_http_sampling`;
  - render JSON/plain review output into the normal review summary text and lifecycle events.
- `PYCODEX_EXEC_CORE=1` now covers fresh `codex exec`, `codex exec resume ...`, and `codex review ...`.

## Validation

- `uvx pytest tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_run_exec_review_core_http_sampling_uses_review_prompt_and_renders_output -q`
  - 2 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_review_core_env or main_review_local_http_runtime or main_review_alias" -q`
  - 3 passed.
- `uvx pytest tests/test_exec_local_runtime.py -k "review_core_http_sampling or review_http_sampling_uses_review_prompt or plain_text_output_emits_review_lifecycle or interrupted_output_uses_review" -q`
  - 4 passed.
- `python -m py_compile pycodex/cli/parser.py pycodex/exec/local_runtime.py tests/test_cli_parser.py tests/test_exec_local_runtime.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 740 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Split or rename `local_http_*` helpers that now serve both compatibility HTTP and direct core paths.
- Review deeper app-server detached/inline review behaviors remain deferred; this slice only advances the common CLI review path.
