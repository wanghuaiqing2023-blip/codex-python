# 2026-06-02 local HTTP runtime smoke suite

## Motivation

- The CLI local HTTP smoke suite now covers end-to-end `codex exec` behavior, but the Python runtime had no matching focused entry point for local HTTP agent-loop internals.
- Added a small standard-library `unittest` suite to make ongoing bug fixing easier without running unrelated app/cloud/plugin tests.

## Python change

- Added `tests/test_exec_local_http_runtime_smoke_suite.py`.
- The suite collects existing runtime tests for:
  - default shell argv and approval policy command parity
  - resume/history reconstruction
  - rollout normalization for orphan and missing local-shell outputs
  - response-item tool call/output timeline reconstruction
  - local-shell command execution rendering
  - multi-round shell-tool followup
  - apply_patch and request_permissions followup paths

## Validation

- `python -m py_compile tests\test_exec_local_http_runtime_smoke_suite.py`
- `python -m unittest tests.test_exec_local_http_runtime_smoke_suite`
- `python -m unittest tests.test_cli_local_http_smoke_suite`

## Current focused smoke entry points

- CLI path: `python -m unittest tests.test_cli_local_http_smoke_suite` currently runs 25 tests.
- Runtime path: `python -m unittest tests.test_exec_local_http_runtime_smoke_suite` currently runs 14 tests.

## Known gaps

- This suite is intentionally focused on the active core local HTTP runtime path and does not include MCP/plugin/marketplace/cloud tests.
