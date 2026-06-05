# 2026-06-03 — Core Runtime Regression Sweep

Ran a broad regression pass across parser/config/network/exec/core-local runtime slices:

- `tests/test_cli_parser.py`
- `tests/test_core_network_approval.py`
- `tests/test_core_compact.py`
- `tests/test_core_config_edit.py`
- `tests/test_core_command_canonicalization.py`
- `tests/test_exec_session.py`
- `tests/test_exec_local_runtime.py`
- `tests/test_exec_core_runtime.py`
- `tests/test_exec_core_runtime_smoke_suite.py`
- `tests/test_core_smoke_suite.py`
- `tests/test_cli_core_smoke_suite.py`
- `tests/test_local_http_core_smoke_suite.py`
- `tests/test_exec_local_http_runtime_smoke_suite.py`

Result: `1806 passed, 2 skipped, 208 subtests passed`.

This confirms the current core execution-path work is stable for these flows. Remaining focus remains on app-server/MCP/streaming-daemon-adjacent gaps outside this high-priority slice.
