# codex-hooks src/engine/mod.rs status

Rust owner: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/mod.rs`

Python module: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `CommandShell`, `ConfiguredHandler::run_id`, and `HookListEntry` remain
  represented in the Python hooks facade.
- `_ClaudeHooksEngine.new(...)` mirrors Rust `ClaudeHooksEngine::new(...)`:
  disabled engines skip discovery and warnings, enabled engines load generated
  schemas, discover handlers, retain startup warnings, preserve shell config,
  and create an output spiller.
- `warnings()` returns startup discovery/plugin warnings without exposing the
  mutable backing list.
- `preview_*` methods delegate to dispatcher selection for the matching event,
  including tool-use/run-id suffix decoration for PreToolUse,
  PostToolUse, and PermissionRequest.
- `run_*` methods delegate execution to `execute_handlers(...)` and the
  event-specific parsers, then aggregate outcomes according to the event
  module contract.
- Engine-owned output spilling wraps additional contexts for SessionStart,
  PreToolUse, PostToolUse, and UserPromptSubmit, optional PostToolUse feedback,
  and Stop continuation fragments.
- `execute_handlers(...)` now records completion order for frozen parsed event
  dataclasses while preserving declaration-order return ordering.

## Rust Evidence

- `codex/codex-rs/hooks/src/engine/mod.rs`
- `codex/codex-rs/hooks/src/engine/mod_tests.rs`
- Representative Rust test/contract anchors:
  - `plugin_hook_load_warnings_are_startup_warnings`
  - managed/plugin `ClaudeHooksEngine::new(...)` startup discovery contracts
  - run/preview delegation through the event modules
  - engine-level `HookOutputSpiller` wrapping after event outcomes

## Python Evidence

- `tests/test_hooks_engine_mod_rs.py`
- Focused validation:
  - `python -m pytest tests/test_hooks_engine_mod_rs.py -q --tb=short`
    passed with `7 passed`.
  - `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py -q --tb=short`
    passed with `153 passed`.
  - `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
    passed with `176 passed`.
  - `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_mod_rs.py`
    passed.

## Remaining Gap

None for this module-scoped behavior contract.
