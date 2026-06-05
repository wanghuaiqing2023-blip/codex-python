# 2026-06-02 - CLI request_permissions cancel-output smoke

## Upstream slice

- Used the graph-guided core permission-tool path:
  - `codex-rs/core/src/tools/handlers/request_permissions.rs`
  - `codex-rs/core/src/tools/handlers/shell_spec.rs`
  - request-permission tests under `codex-rs/core/tests/suite`.
- Confirmed Rust returns the model-visible text `request_permissions was cancelled before receiving a response` when a request receives no approval response.

## Python progress

- Added a CLI-level local HTTP shell-tools smoke for `request_permissions`.
- The test enables `features.request_permissions_tool = true`, runs `codex exec` with `--ask-for-approval on-request`, and has the fake model call `request_permissions`.
- Because the non-interactive CLI path has no live approval callback, the tool loop returns the Rust-compatible cancel text and continues to a final assistant answer.
- The follow-up request is verified to include a `function_call_output` for the permission request, without a model-visible `name` field.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_request_permissions_on_request_returns_cancel_output`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_request_permissions_on_request_returns_cancel_output tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_on_request_requires_approval tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_on_request_requires_approval tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_success`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up debt

- Add a true CLI approval callback path only if the non-interactive CLI grows a user-facing permission prompt or external approval transport.
- Keep request-permission grant semantics covered in runtime tests until such a CLI callback exists.
