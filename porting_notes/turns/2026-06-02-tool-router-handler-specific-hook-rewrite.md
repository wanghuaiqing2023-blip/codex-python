# Tool Router Handler-Specific Hook Rewrite

## Source slice

- Graph query located hook-related Rust nodes in `codex-rs/core/src/tools/registry.rs` and handler-specific `post_tool_use_payload` / `with_updated_hook_input` implementations under `codex-rs/core/src/tools/handlers/`.
- Authoritative Rust behavior confirmed in:
  - `codex/codex-rs/core/src/tools/registry.rs`
  - `codex/codex-rs/core/src/tools/handlers/shell/shell_command.rs`
  - `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex/codex-rs/core/src/tools/handlers/apply_patch.rs`

## Confirmed Rust behavior

- PreToolUse hook input rewrites are applied through the selected tool runtime's `with_updated_hook_input`, not only through the default function-tool rewrite.
- Handler-specific rewrites preserve each tool's stable hook contract:
  - `shell_command` rewrites the `command` argument.
  - `exec_command` rewrites the `cmd` argument.
  - `apply_patch` rewrites the custom patch payload.
- Default function-tool post-hook response falls back to the function call output body, which matches the Python protocol payload shape.

## Python change

- `pycodex/core/tool_router.py` now applies pre-hook `updated_input` through the resolved tool handler when it exposes `with_updated_hook_input`.
- Added router coverage ensuring dispatch uses handler-specific hook input rewrite instead of always falling back to default function-tool serialization.

## Validation

- `python -m py_compile pycodex/core/tool_router.py tests/test_core_tool_router.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_router.py tests/test_core_tool_registry.py -q`
  - `78 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_unified_exec_handler.py tests/test_core_shell.py tests/test_core_apply_patch.py -q`
  - `85 passed, 2 skipped, 15 subtests passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py tests/test_core_tool_router.py -q`
  - `124 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

## Deferred

- No deep MCP/plugin/marketplace work was taken. Existing handler-specific MCP/apply_patch/shell/unified-exec hook contracts should continue to be validated only where they touch the core CLI/tool-dispatch path.
