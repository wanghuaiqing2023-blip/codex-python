# 2026-06-02 CLI/local HTTP smoke suite stability

## Upstream slice

- Continued the graph-guided core path around common `exec` behavior:
  - `core/src/session/turn.rs`
  - `core/src/client.rs`
  - `core/src/stream_events_utils.rs`
  - `core/src/exec.rs`
- The implementation work stayed on user-facing CLI/runtime compatibility rather than expanding MCP, plugin, marketplace, or app-server internals.

## Python changes

- Stabilized CLI compatibility paths that were blocking the broader smoke gate:
  - `app` platform detection now follows `sys.platform`, which keeps mocked/non-Windows tests from taking the Windows branch.
  - `cloud --help` prints root cloud help, and human cloud list output consistently writes to the injected stdout.
  - MCP stdio compatibility stub rejects unknown `codex` tool arguments with a structured error instead of silently accepting them.
  - Remote-control JSON output no longer shadows the `json` module, and `stop` prints only the final status line.
  - Responses API proxy response dumps now omit automatic HTTP framework headers and use the same filtered response headers as forwarding.
- `exec` optional stdin append now tolerates an unreadable default stdin when an explicit prompt argument is already present.

## Validation

- `uvx pytest tests/test_core_stream_events_utils.py --maxfail=1 -q`
  - 112 passed.
- `uvx pytest tests/test_exec_run.py tests/test_exec_local_runtime.py tests/test_exec_session.py --maxfail=1 -q`
  - 349 passed, 12 subtests passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 735 passed, 1 skipped, 98 subtests passed.
- `python -m py_compile pycodex/cli/parser.py pycodex/exec/run.py tests/test_cli_parser.py tests/test_exec_run.py`
  - passed.

## Follow-up

- Keep using the three smoke suites as the near-term gate for common `exec` and local runtime behavior.
- Next core slice should focus on reducing mocked local HTTP assumptions and making a direct end-to-end `pycodex exec` path usable with real request construction, stream handling, tool dispatch, and final answer generation.
