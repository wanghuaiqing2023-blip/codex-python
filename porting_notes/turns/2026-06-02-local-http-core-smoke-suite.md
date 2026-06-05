# 2026-06-02 local HTTP core smoke suite

## Motivation

- The project now has focused CLI and runtime local HTTP smoke suites.
- Added a single combined entry point so ongoing core `exec` work can validate the common user-facing path and the Python runtime internals with one command.

## Python change

- Added `tests/test_local_http_core_smoke_suite.py`.
- The suite composes:
  - `tests.test_cli_local_http_smoke_suite.core_local_http_cli_smoke_suite()`
  - `tests.test_exec_local_http_runtime_smoke_suite.core_local_http_runtime_smoke_suite()`

## Validation

- `python -m py_compile tests\test_local_http_core_smoke_suite.py`
- `python -m unittest tests.test_local_http_core_smoke_suite`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_http_runtime_smoke_suite`

## Current focused smoke entry points

- All core local HTTP smoke: `python -m unittest tests.test_local_http_core_smoke_suite` currently runs 39 tests.
- CLI only: `python -m unittest tests.test_cli_local_http_smoke_suite` currently runs 25 tests.
- Runtime only: `python -m unittest tests.test_exec_local_http_runtime_smoke_suite` currently runs 14 tests.

## Known gaps

- This combined suite intentionally excludes non-core cloud/plugin/MCP/app-server areas unless they become necessary for the active `exec` runtime path.
