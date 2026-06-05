# Parser fallback runtime hardening via helper

## Follow-up
The prior env-isolation fix patched individual parser tests to force `core_exec_enabled=False` when asserting remote/app-server fallback behavior.

## Additional stabilization
I updated `TopLevelCliParserTests._main_with_local_http_exec_disabled` in `tests/test_cli_parser.py` to always set:
- `PYCODEX_EXEC_LOCAL_HTTP=0`
- `PYCODEX_EXEC_CORE=0`

This makes all tests using this helper deterministic under ambient API-key environments and reduces accidental routing to the direct core runtime.

## Validation
- `python -m pytest -q tests/test_cli_parser.py`
- `python -m pytest -q tests/test_cli_core_smoke_suite.py tests/test_exec_core_runtime_smoke_suite.py tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`
