# codex-hooks src/events/permission_request.rs Status

Rust crate: `codex-hooks`

Rust module: `src/events/permission_request.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Behavior Contract

- `PermissionRequestCommandInput` serialization keeps request `tool_name`,
  `tool_input`, optional subagent fields, and omits `run_id_suffix` from hook
  stdin because it is only used for run id decoration.
- Completed hook output parsing maps hook-specific `decision.behavior` to
  allow/deny/none, emits warning entries for system messages, and defaults
  blank/missing deny messages to Rust's fallback denial text.
- Reserved `updatedInput`, `updatedPermissions`, and `interrupt:true` fields
  fail closed, as do unsupported universal output fields and invalid
  JSON-looking stdout.
- Exit code 2 denies only with non-empty stderr; missing stderr, process
  errors, other non-zero exits, and missing status codes fail.
- Decision aggregation is conservative: any deny wins, otherwise allow wins,
  otherwise no hook decision is returned.

## Rust Evidence

- `codex/codex-rs/hooks/src/events/permission_request.rs`
- `codex/codex-rs/hooks/src/engine/output_parser.rs`
- Rust tests:
  - `permission_request_deny_overrides_earlier_allow`
  - `permission_request_returns_allow_when_no_handler_denies`
  - `permission_request_returns_none_when_no_handler_decides`
  - `permission_request_rejects_reserved_updated_input_field`
  - `permission_request_rejects_reserved_updated_permissions_field`
  - `permission_request_rejects_reserved_interrupt_field`

## Python Evidence

- `tests/test_hooks_events_permission_request_rs.py`

Focused validation:

```text
python -m pytest tests/test_hooks_events_permission_request_rs.py -q --tb=short
```

Passed on 2026-06-21 with `11 passed`.

Related hooks validation also passed with:

```text
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py -q --tb=short
python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short
```

Results: `100 passed` and `123 passed`.
