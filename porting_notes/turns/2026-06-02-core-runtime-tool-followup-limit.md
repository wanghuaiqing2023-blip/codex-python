# Core runtime tool follow-up limit

## Context

The Python core user-turn runtime already has a real tool follow-up loop in `pycodex.core.turn_runtime.run_user_turn_sampling_from_session(...)`, including `max_tool_followups` validation and handling. The `exec` core command dispatcher, however, did not expose that runtime control through the fresh/review/resume command boundary.

Upstream `codex-rs/exec/src/lib.rs` keeps turn startup and event-loop execution in the runtime path rather than scattering per-command tool-loop decisions in the CLI. This slice keeps moving Python in the same direction by having `pycodex.exec.core_runtime` own another part of the command-to-agent-loop execution contract.

## Change

- Extended `run_core_exec_command(...)` with `max_tool_followups`.
- Passed that value through to:
  - `run_exec_user_turn_core_http_sampling` for fresh `exec`;
  - `run_exec_review_core_http_sampling` for `review`;
  - `run_exec_resume_user_turn_core_http_sampling` for `resume`.
- Updated the CLI core branch to pass the existing parsed tool-round limit into the core dispatcher. The default remains unbounded when no limit is configured.
- Added focused tests that verify the limit reaches each core runner and the CLI core entrypoint.

## Validation

- `python -m py_compile pycodex/exec/core_runtime.py pycodex/cli/parser.py tests/test_exec_core_runtime.py tests/test_cli_parser.py`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_exec_core_runtime.py tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_core_env_uses_in_memory_core_http_sampling tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_core_env_uses_core_review_runner tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner -q`
  - `19 passed`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_cli_parser.py -k "main_exec_core_env or main_review_core_env or main_exec_resume_core_env or main_exec_resume_local_http or local_http_max_tool" -q`
  - `12 passed, 524 deselected`
- `$env:PYTHONPATH='.'; uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - First run hit a transient/order-dependent `doctor --summary` failure; the isolated test passed.
  - Re-run passed: `741 passed, 1 skipped, 98 subtests passed`

## Follow-up

The environment variable name used by the CLI path still comes from the local HTTP compatibility layer. A future cleanup should give the direct core path its own naming and move more request construction / stream processing ownership out of `pycodex.exec.local_runtime`.
