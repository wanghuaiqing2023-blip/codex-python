# pycodex.hooks

Python porting target for Rust `codex-hooks`.

Rust coordinate:

- Crate: `codex-hooks`
- Rust path: `codex/codex-rs/hooks`
- Python package: `pycodex/hooks`

Status: `complete`

Implemented module contracts:

- `src/config_rules.rs` hook state resolution from config layers. Python now
  mirrors Rust's user/session-only layer filter, disabled-layer inclusion,
  lowest-to-highest precedence walk, field-by-field state merge, and malformed
  entry skipping.
- `src/legacy_notify.rs` historical user-notification JSON projection and
  legacy notify hook execution semantics, including skipped absent `client`,
  empty-command success, and spawn-error failed-continue behavior.
- `src/output_spill.rs` hook output spilling to
  `<temp>/hook_outputs/<thread_id>/<uuid>.txt`, inline preservation below the
  token limit, standard truncation previews with recovery paths, and prompt
  fragment `hook_run_id` preservation.
- `src/schema.rs` dependency-light hook command schema surface, including the
  registered generated fixture names, canonical JSON ordering, fixture
  directory replacement, turn-scoped `turn_id` schema extension, optional
  subagent fields, and flat subagent field projection.
- `src/engine/output_parser.rs` stdout JSON parsing and structured output
  contracts, including universal output projection, serde-like object/enum
  rejection, PreToolUse hook-specific versus legacy decision precedence,
  PermissionRequest reserved-field failures and default deny message,
  PostToolUse invalid block reasons, and start/stop/user-prompt output
  structures.
- `src/engine/schema_loader.rs` generated hook schema loader surface,
  including the 20-field `GeneratedHookSchemas` inventory, one-time cached
  `generated_hook_schemas()` access, and named invalid-schema errors.
- `src/engine/dispatcher.rs` command-handler selection and dispatch helpers,
  including matcher-aware event filtering, declaration-order preservation,
  duplicate/alias matching behavior, run summary projection, event scope
  mapping, completed summary projection, and async completion-order tracking
  with declaration-order return ordering.
- `src/engine/command_runner.rs` command execution boundary, including
  default shell argv construction, custom shell args plus handler command
  ordering, handler environment overlay, cwd/stdin/stdout/stderr piping,
  spawn-error result projection, timeout killing and error text, lossy output
  decoding, and timestamp/duration result fields.
- `src/engine/discovery.rs` handler discovery boundary, including matcher
  normalization/validation, persisted state enabled and trust gating,
  commandWindows selection, list-entry generation, unsupported handler
  warnings, and TOML hook parsing while ignoring malformed state entries.
- `src/engine/mod.rs` engine facade/orchestration boundary, including
  enabled/disabled startup construction, generated-schema initialization,
  discovery warning exposure, preview delegation, run delegation through
  dispatcher/event parsers, tool-use/run-id suffix decoration, permission
  decision aggregation, and engine-owned spilling for additional context,
  post-tool feedback, and stop continuation fragments.
- `src/registry.rs` hook registry configuration/defaults, legacy notify
  registration filter, engine delegation, after-agent dispatch abort ordering,
  list-hooks feature gate/discovery forwarding, and argv command projection.
- `src/events/common.rs` shared event helpers, including matcher semantics,
  context aggregation, serialization-failure hook events, and tool-use run-id
  decoration.
- `src/events/permission_request.rs` permission-request command input
  serialization, completed-output parsing for allow/deny/none decisions,
  reserved-field failures, exit-code 2 denial, and conservative decision
  resolution.
- `src/events/compact.rs` pre/post compact command input serialization and
  completed-output parsing for lifecycle metadata, JSON schema failures,
  `continue:false` stop behavior, warnings, plain stdout no-op, and process
  failure cases.
- `src/events/pre_tool_use.rs` pre-tool-use command input serialization,
  completed-output parsing for permission decisions, legacy block decisions,
  additional context, invalid JSON, exit-code 2 blocking, and latest
  completion-order updated input selection.
- `src/events/post_tool_use.rs` post-tool-use command input serialization,
  completed-output parsing for additional context, feedback, stop, invalid
  JSON, exit-code 2 model feedback, and unsupported output fields.
- `src/events/session_start.rs` session/subagent start source and target
  matching plus completed-output parsing for context, stop, and invalid JSON
  cases.
- `src/events/stop.rs` stop/subagent-stop target matching, completed-output
  parsing for stop, block, invalid JSON, exit-code 2, and process failure
  cases, plus blocked-result aggregation and continuation prompt fragments.
- `src/events/user_prompt_submit.rs` user-prompt-submit completed-output
  parsing for context, `continue:false` stop, Claude `decision:block`,
  invalid block decisions, exit-code 2 blocking, invalid JSON, and process
  failure cases.
- `src/types.rs` core hook result, hook execution, and `HookPayload` /
  `HookEvent::AfterAgent` serialization shape. The Python mapping preserves
  Rust's second-precision UTC timestamp, omitted absent `client`, and nested
  `hook_event` object.
- `src/declarations.rs` plugin hook declaration projection, including
  `plugin_id.as_key()` key-source formatting, `HookEventsToml`
  event/group/handler ordering, and persisted hook key generation.
- `src/lib.rs` crate-root `HOOK_EVENT_NAMES`,
  `HOOK_EVENT_NAMES_WITH_MATCHERS`, `hook_event_key_label(...)`, and
  `hook_key(...)` compatibility surface.

Known module-local gaps:

- None. Live shell/platform integration remains covered by the sibling
  command-runner and registry/core integration validation boundaries.

Validation:

- `python -m pytest tests/test_hooks_types_rs.py -q --tb=short`
  passed with `2 passed`.
- `python -m pytest tests/test_hooks_declarations_rs.py -q --tb=short`
  passed with `1 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_hooks_legacy_notify_rs.py -q --tb=short`
  passed with `5 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py -q --tb=short`
  passed with `13 passed`.
- `python -m pytest tests/test_hooks_output_spill_rs.py -q --tb=short`
  passed with `4 passed`.
- `python -m pytest tests/test_hooks_registry_rs.py -q --tb=short`
  passed with `7 passed`.
- `python -m pytest tests/test_hooks_events_common_rs.py -q --tb=short`
  passed with `12 passed`.
- `python -m pytest tests/test_hooks_events_session_start_rs.py -q --tb=short`
  passed with `6 passed`.
- `python -m pytest tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_hooks_events_stop_rs.py -q --tb=short`
  passed with `12 passed`.
- `python -m pytest tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short`
  passed with `16 passed`.
- `python -m pytest tests/test_hooks_events_post_tool_use_rs.py -q --tb=short`
  passed with `11 passed`.
- `python -m pytest tests/test_hooks_events_permission_request_rs.py -q --tb=short`
  passed with `11 passed`.
- `python -m pytest tests/test_hooks_events_compact_rs.py -q --tb=short`
  passed with `11 passed`.
- `python -m pytest tests/test_hooks_schema_rs.py -q --tb=short`
  passed with `5 passed`.
- `python -m pytest tests/test_hooks_engine_output_parser_rs.py -q --tb=short`
  passed with `6 passed`.
- `python -m pytest tests/test_hooks_engine_schema_loader_rs.py -q --tb=short`
  passed with `3 passed`.
- `python -m pytest tests/test_hooks_engine_dispatcher_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_hooks_engine_command_runner_rs.py -q --tb=short`
  passed with `5 passed`.
- `python -m pytest tests/test_hooks_engine_discovery_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m pytest tests/test_hooks_engine_mod_rs.py -q --tb=short`
  passed with `7 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py -q --tb=short`
  passed with `138 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py -q --tb=short`
  passed with `146 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py -q --tb=short`
  passed with `153 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `161 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `169 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_hooks_engine_command_runner_rs.py tests/test_hooks_engine_discovery_rs.py tests/test_hooks_engine_mod_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `176 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py -q --tb=short`
  passed with `133 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_hooks_engine_dispatcher_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `156 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py -q --tb=short`
  passed with `125 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_hooks_engine_schema_loader_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `148 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py -q --tb=short`
  passed with `122 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_hooks_engine_output_parser_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `145 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py -q --tb=short`
  passed with `50 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `73 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py -q --tb=short`
  passed with `62 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `85 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py -q --tb=short`
  passed with `78 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `101 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py -q --tb=short`
  passed with `89 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `112 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py -q --tb=short`
  passed with `100 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `123 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py -q --tb=short`
  passed with `111 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `134 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py -q --tb=short`
  passed with `116 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_hooks_legacy_notify_rs.py tests/test_hooks_output_spill_rs.py tests/test_hooks_registry_rs.py tests/test_hooks_events_common_rs.py tests/test_hooks_events_session_start_rs.py tests/test_hooks_events_user_prompt_submit_rs.py tests/test_hooks_events_stop_rs.py tests/test_hooks_events_pre_tool_use_rs.py tests/test_hooks_events_post_tool_use_rs.py tests/test_hooks_events_permission_request_rs.py tests/test_hooks_events_compact_rs.py tests/test_hooks_schema_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `139 passed`.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `31 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k hooks -q --tb=short`
  passed with `1 passed, 17 deselected`.
- Combined hooks validation passed with `27 passed, 17 deselected`.
- `python -m pytest tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `23 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_types_rs.py`
  passed.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_mod_rs.py`
  passed.
