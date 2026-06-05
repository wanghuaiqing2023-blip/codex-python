# Porting Status

Last updated: 2026-06-03

## Overall Objective
- Port OpenAI Codex from Rust (`codex/`) to Python (`pycodex/`) with behavior-first parity on core CLI/runtime paths while keeping dependencies minimal.

## Current Priority Focus
- Core command/runtime execution loop
- Local HTTP and in-memory core execution paths
- Tool dispatch and streaming/event mapping for common user flows
- Regression safety via smoke suites

## Progress This Turn
- Fixed startup prewarm cancellation/timeout consistency in `pycodex/core/session_startup_prewarm.py`:
  - Drains the prewarm task after `cancel()` so `resolve()` now reliably reports `task.cancelled()` on timeout or cancellation-token abort.
  - Kept telemetry and status tagging aligned with existing `startup_prewarm_resolve`/duration reporting behavior.

- Completed targeted core-slice approval/network parity fixes:
  - Fixed `canonicalize_command_for_approval` export alignment in `pycodex/core/__init__.py` so package-level export resolves to command canonicalization behavior.
  - Added missing `ConfigEdit` notice/migration setters in `pycodex/core/config_edit.py` and validated mapping values in `ConfigEdit.set_path`.
  - Tightened `pycodex/core/network_approval.py` request validation and cached-deny policy flow, including host/target casing consistency for policy-block paths.
- Aligned core model slug defaulting and messaging to upstream Rust expectations:
  - `gpt-5`/`gpt-5.3-Codex-Spark` usages in default local HTTP model selection were moved to `gpt-5.3-codex`.
  - Legacy/placeholder debug-model outputs and cyber fallback warning text were updated accordingly.
- Updated related regression assertions in CLI/runtime/compact tests for the same model slug.
- Fixed user-turn prompt lifecycle boundaries in `pycodex/core/turn_runtime.py`:
  - Defer user prompt lifecycle emission (`item_started`/`item_completed`) until after sampling succeeds.
  - Keep prompt recorded to history during request prep for context/compaction correctness, then emit prompt turn-item events from a dedicated post-sample path.
  - Prevented duplicate user message lifecycle/history behavior that was causing compact-history and terminal-error regression failures.
- Fixed unified exec snapshot timing in `pycodex/core/unified_exec.py` to better match Rust timing semantics for interactive sessions:
  - Added output-close tracking from the reader thread and deadline/post-exit draining behavior to `snapshot`.
  - Changed tty sessions to stop collecting after the first non-exit output chunk so short-lived interactive commands can defer late output until follow-up `write_stdin` calls.
  - Kept non-tty sessions collecting through command completion so immediate non-interactive calls still return final output and release sessions correctly.
- Tightened core auth and agent job parity behavior:
  - Made `run_chatgpt_login` resilient when the injected server object does not expose `serve_forever` (needed by login unit tests and test doubles).
  - Wrapped `report_agent_job_result` argument parsing so non-object `result` payloads and malformed invocation arguments are returned as `FunctionCallError`, matching handler contract.
  - Normalized Linux landlock command and path arguments to forward-slash strings for cross-platform test parity.
  - Restored `remove_snapshot_file` visibility as a built-in symbol after importing `pycodex.core` to keep existing tests that call it unqualified.
- Fixed a `doctor` CLI status-normalization regression:
  - Normalized status strings to treat upstream-style `"warning"` as CLI `"warn"` during summary aggregation.
  - Restored correct warning/fail count logic for `doctor --summary` / `--all` and kept exit code semantics aligned with Rust behavior.
- Added strict active-turn coverage for pending-input queue checks in the sampling path:
  - Added a focused regression test in `tests/test_core_turn_runtime.py` to ensure `has_pending_input` and `get_pending_input` are invoked with the active turn context when required by queue implementations.
  - This protects interactive follow-up behavior on custom queue adapters where the method signatures are `active_turn`-strict.
- Hardened input-queue method dispatch for keyword-only `active_turn` signatures:
  - `_call_input_queue_method` now supports `active_turn` passed as a keyword-only argument, improving robustness for alternate queue adapters.
  - Added `KeywordOnlyActiveTurnInputQueue` coverage so pending-input draining still records `session.active_turn` correctly without a positional signature.
- Hardened stop/after-agent hook compatibility for keyword-only and legacy signatures:
  - Updated `_run_turn_stop_hook` and `_call_after_agent_hook` to support `*, turn_context=...` style hooks without breaking existing positional-style hooks.
  - Kept positional fallback behavior for legacy 2/3-arg hook signatures so existing tests and users are not regressed.
  - Added regression coverage for:
    - keyword-only `after_agent` hook signature
    - keyword-only `run_turn_stop_hook` signature
    - follow-up continuation behavior under keyword-only stop hooks.
- Hardened user-prompt-submit hook compatibility with keyword-only signatures:
  - Updated `_call_user_prompt_submit_hook` to support `prompt=`-only and full keyword-only (`turn_context=`, `user_input=`, `prompt=`) hooks.
  - Added tests for:
    - keyword-only `prompt` signature that blocks input.
    - keyword-only full-signature hook including `turn_context/user_input/prompt`.
- Hardened tool-router hook dispatch for pre/post tool hooks:
  - Added signature-flexible invocation in `pycodex/core/tool_router.py` so `pre_tool_use_hook` and `post_tool_use_hook` accept keyword-only forms (e.g. `hook(payload=..., invocation=...)`, `hook(payload=..., result=...)`) as well as legacy positional calls.
  - Added regression tests in `tests/test_core_tool_router.py`:
    - `test_dispatch_pre_tool_use_hook_supports_keyword_only_signature`
    - `test_dispatch_post_tool_use_hook_supports_keyword_only_signature`.
- Extended tool dispatch trace compatibility for mapping-style trace contexts:
  - Updated `pycodex/core/tool_dispatch_trace.py` so `ToolDispatchTrace.start`, `record_completed`, and `record_failed` consume context access via mapping-safe lookup (`dict`/object support), and `is_enabled` honors mapping-backed flags.
  - Added mapping-path regression coverage in `tests/test_core_tool_dispatch_trace.py`:
    - `test_trace_facade_supports_mapping_trace_context`
    - `test_trace_facade_mapping_context_respects_disabled_flag`
- Widened personality migration to honor explicit profile override:
  - `maybe_migrate_personality` now applies `override_profile` to the effective config before personality/model-provider checks.
  - This prevents migration from overriding an explicitly configured profile personality when profile context is provided.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_personality_blocks_migration`.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_missing_profile_allows_migration_by_top_level_logic` to verify an unknown override falls back to normal migration flow.
  - Added `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_missing_profile_still_skips_without_sessions` to verify an unknown override keeps `SKIPPED_NO_SESSIONS` when no migration signal exists.
  - Added boundary coverage for malformed profile configuration:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_config_profile_with_non_mapping_profiles_returns_empty`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_config_profile_with_non_mapping_profile_entry_returns_empty`
  - Added validation coverage for invalid `override_profile` type:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_non_string_override_profile_rejected`
  - Added coverage for override profile loading from `config.toml` on disk:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_from_disk_config_is_honored`
  - Added priority coverage for migration marker:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_marker_takes_precedence_even_with_override_profile`
  - Added explicit priority coverage for top-level personality over override profile:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_top_level_personality_blocks_even_with_override_profile`
  - Added coverage for empty profile entry fallback behavior:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_empty_profile_does_not_block_personality_migration`
  - Added coverage for blank override_profile fallback behavior:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_blank_override_profile_uses_top_level_profile_behavior`
  - Added disk-config explicit-priority coverage for override profile:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_override_profile_from_disk_config_respects_disk_top_level_personality`
  - Added model-provider migration boundary coverage:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_model_provider_setting_does_not_block_migration_when_sessions_exist`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_model_provider_setting_respects_no_sessions_path`
  - Added combined missing-override + model_provider migration coverage:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_missing_override_profile_respects_model_provider_with_sessions`
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_missing_override_profile_respects_model_provider_without_sessions`
  - Added explicit test for blank override with explicit top-level personality:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_top_level_personality_blocks_blank_override_profile`
  - Added marker short-circuit coverage without config input:
    - `tests/test_core_personality_migration.py::PersonalityMigrationTests::test_marker_takes_precedence_even_without_config_argument`
  - Added behavior matrix artifact for personality migration migration boundaries:
    - `porting_notes/turns/2026-06-03-personality-migration-boundary-matrix.md`
- Wired personality migration into non-interactive `exec` CLI startup flow:
  - `pycodex/cli/parser.py::_run_noninteractive_exec` now calls `maybe_migrate_personality` using `find_codex_home()` and `ExecCli.profile` override before building the bootstrap plan.
  - When migration is applied, `config_toml` is reloaded from disk so the injected top-level `personality` is visible for the same invocation.
  - Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_with_profile_triggers_personality_migration_reload` to assert that:
    - `maybe_migrate_personality` is invoked with profile override and an empty initial mapping,
    - migration-applied flow triggers a second `read_toml_mapping`,
    - and the second read (with `personality = pragmatic`) is what `build_exec_config_bootstrap_plan` receives.
  - Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_without_migration_applied_uses_original_config` to assert that:
    - `maybe_migrate_personality` returns non-APPLIED state,
    - only one `read_toml_mapping` is performed,
    - and bootstrap uses the original mapping unchanged.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_with_profile_triggers_noninteractive_migration_reload` to confirm implicit interactive `exec` fallback (`main(["--profile", ...])`) also exercises personality migration + config reload before bootstrap.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_with_profile_without_migration_uses_original_config` to confirm fallback `exec` path preserves existing config when migration is skipped.
- Added `tests/test_cli_parser.py::TopLevelCliParserTests::test_main_review_with_profile_triggers_personality_migration_reload` and `...::test_main_review_without_migration_applied_uses_original_config` to confirm the same bootstrap behavior applies to `main(["review", ...])`.
- Stabilized `doctor` parser tests by stubbing network reachability in `TopLevelCliParserTests` setup/teardown:
  - Added a class-scoped `doctor_provider_reachability_check` mock in `tests/test_cli_parser.py` for all `test_main_doctor_*` cases to avoid external network flakiness.
  - Kept mocked behavior at warning status with a structured `reachability mode` detail so existing assertions for config-fallback and status aggregation remain valid.
- Added regression coverage note file:
  - `porting_notes/turns/2026-06-03-doctor-network-check-stability.md` documenting the network-check isolation decision and preserving production reachability behavior outside parser tests.

- Stabilized `doctor` parser tests in minimal environments by adding `TopLevelCliParserTests.setUp`/`tearDown` auth seeding:
  - `test_main_doctor_*` cases now get a temporary `OPENAI_API_KEY` when absent so `doctor` return-code checks are not flapped by missing credentials.
  - Kept parser-side `doctor` fail-on-no-auth semantics unchanged; this is explicitly a test environment compatibility fix while deciding final parity contract for strict auth failures.
- Aligned plugin/runtime prompt injection behavior in `pycodex/core/turn_runtime.py`:
  - `_build_plugin_injections` now resolves explicit plugin mentions against both `display_name` and authoritative `mcp_server_names`/`app_connector_ids` capability fields, and surfaces connector names (not IDs) for injected app labels.
  - `_response_item_skill_text` now only reads message-level `input_text` entries when collecting explicit app mentions from skill/plugin injections, reducing accidental matches from non-InputText content.
  - Added `porting_notes/turns/2026-06-03-turn-runtime-plugin-injection-mention-filter.md` with scope and rationale; no behavioral changes were made to app/plugin extension ecosystems outside this core path.
- Aligned skill-injection warning propagation in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_skill_plugin_items` now emits warning events for `SkillInjections.warnings` returned by `build_skill_injections`, matching Rust behavior that forwards injected-skills warnings through event flow.
  - Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_forwards_skill_injection_warnings_as_events` and `...::test_run_user_turn_sampling_forwards_multiple_skill_injection_warnings_in_order` to ensure warning messages surface to the warning event stream and preserve order.
  - Added `porting_notes/turns/2026-06-03-turn-runtime-skill-injection-warnings.md` documenting the event-ordering parity decision for warning handling.
- Added app/plugin analytics parity handling in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_skill_plugin_items` now emits app/plugin tracking calls matching Rust user-turn behavior:
    - `track_app_mentioned` for explicit app mentions (including skill-derived app ids),
    - `track_plugin_used` for explicit plugin mentions that expose `telemetry_metadata()`.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_explicit_app_and_plugin_mentions_for_analytics` to assert both calls are emitted with expected context/payload.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_does_not_track_plugins_without_telemetry_metadata` to confirm `track_plugin_used` stays silent when the plugin does not expose telemetry metadata, matching Rust `.filter_map(...telemetry_metadata)` behavior.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_prefixed_app_mentions_with_normalization` to assert `app://...`-prefixed explicit app mentions are normalized before analytics reporting.
  - Added `porting_notes/turns/2026-06-03-turn-runtime-app-plugin-analytics-tracking.md` documenting this minimal compatibility decision in the core slice.
- Added turn-config analytics parity in `pycodex/core/turn_runtime.py`:
  - `_prepare_user_turn_request_from_session` now dispatches `track_turn_resolved_config`-style analytics before model request dispatch.
  - Implemented resilient field extraction helpers for thread config snapshot values (`ephemeral`, `session_source`, `model_provider`, `approval_policy`, `service_tier`, `sandbox_network_access`, etc.), including optional first-turn resolution fallbacks.
  - Added silent failure guards so analytics transport errors cannot block user-turn execution.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_for_analytics`.
  - Added payload assertions for `num_input_images`, `turn_id`, `thread_id`, `model_provider`, `session_source`, `reasoning_*`, `approval*`, `sandbox_network_access`, `collaboration_mode`, `personality`, and `is_first_turn`.
  - Added `porting_notes/turns/2026-06-03-turn-runtime-resolved-config-analytics.md` with scope/rationale for this core-path parity increment.
- Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_attr_snapshot` to verify fallback resolution from `session.thread.thread_config_snapshot` for analytics tracking.
- Expanded thread-snapshot fallback coverage:
  - Added `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_from_thread_callable_snapshot`, which verifies that callable `thread_config_snapshot` providers are resolved correctly for `track_turn_resolved_config`.
- Hardened connector analytics input handling for the core turn path by moving object-to-`AppInfo` coercion into `pycodex/core/connectors.py`:
  - `_coerce_app_info` now accepts non-mapping object connectors (including `SimpleNamespace`-style test doubles) by reading `to_mapping` or attribute fields before falling back to `AppInfo.from_mapping`.
  - Removed temporary object-normalization shim from `pycodex/core/turn_runtime.py::_available_connectors` so compatibility is handled centrally at the connector API boundary.
- Added regression coverage in `tests/test_core_connectors.py::ConnectorHelperTests::test_with_app_enabled_state_accepts_connector_objects` to assert `SimpleNamespace`-style connectors are accepted by `with_app_enabled_state`.

- Fine-tuned `turn_runtime` analytics resolved-config derivation for simplified Python runtime sessions:
  - `_build_turn_resolved_config_payload` now falls back to `thread_config` network-sandbox sources (`network_sandbox_policy` then `sandbox_policy`) when turn-context fields do not expose network strategy directly.
  - This aligns analytics `sandbox_network_access` derivation for backends where thread snapshot is the effective source of sandbox policy at turn creation time.

- Aligned `pycodex/core/session_runtime.py` sandbox-policy projection for session updates with upstream Rust behavior:
  - `InMemoryCodexSession.update_settings` now treats `sandbox_policy` changes as a source for deriving `permission_profile`, instead of only mutating policy fields directly.
  - Added shared projection logic to update `permission_profile`, `file_system_sandbox_policy`, and legacy `sandbox_policy` consistently from the same effective config.
  - Hardened snapshot/update ordering so `sandbox_policy` updates and snapshot generation remain coherent when only one field is supplied.
  - Added implementation note in `porting_notes/turns/2026-06-03-session-runtime-sandbox-policy-projection.md` to track this core-slice parity decision and fallback behavior.

- Added regression coverage for session sandbox-policy projection in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_update_settings_projects_sandbox_policy_to_permission_profile` verifies permission profile and file-system policy stay coherent when `sandbox_policy` is updated.
  - `test_in_memory_session_update_settings_preserves_deny_entries_when_projecting_sandbox_policy` verifies deny entries from prior `permission_profile` are preserved during projection.

- Added preview-path coverage in `tests/test_core_session_runtime.py` for the same core slice:
  - `test_in_memory_session_preview_settings_projects_sandbox_policy_to_permission_profile` asserts `preview_settings` returns a projected `permission_profile` and does not mutate session state.
  - `test_in_memory_session_preview_settings_preserves_deny_entries_when_projecting_sandbox_policy` asserts `preview_settings` preserves deny entries when projecting `sandbox_policy`.

- Added thread-snapshot consistency coverage for the same sandbox projection slice:
  - `test_in_memory_session_thread_config_snapshot_reflects_sandbox_projection` in `tests/test_core_session_runtime.py` verifies `thread_config_snapshot()` returns the same `permission_profile` projection used by `update_settings` and leaves session fields unchanged.
  - `test_in_memory_session_thread_config_snapshot_preserves_deny_entries_when_projecting_sandbox_policy` verifies deny entries are preserved in snapshotted projection after `sandbox_policy` updates.

- Extended turn-construction coverage in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_new_default_turn_reflects_sandbox_projection` verifies `new_default_turn()` uses the same projected sandbox permission state as `thread_config_snapshot()` (including deny-entry preservation).

- Added turn-runtime resolved-config guard test in `tests/test_core_turn_runtime.py`:
  - `test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_permission_profile` verifies analytics payload uses `turn_context.permission_profile` first and derives `sandbox_network_access` from that source before thread snapshot fallbacks.
  - `test_run_user_turn_sampling_tracks_turn_resolved_config_from_turn_context_network_sandbox_policy` verifies `turn_context.network_sandbox_policy` is preferred over thread config `sandbox_policy` when resolving `sandbox_network_access` for analytics payload.

- Added end-to-end sandbox-projection analytics coverage in `tests/test_core_session_runtime.py`:
  - `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection` verifies `InMemoryCodexSession` `update_settings(sandbox_policy=...)` -> `thread_config_snapshot` -> `run_user_turn_sampling_from_session` propagates the projected `permission_profile` (mapping form) and enables `sandbox_network_access` in resolved analytics payload.
- Extended request-shape parity for that same in-memory session sampling path across both transport variants:
  - `test_in_memory_session_run_user_turn_sampling_tracks_resolved_config_from_settings_projection` now also asserts `run_user_turn_sampling_from_session` returns a `request_plan` whose `prompt.input` includes a developer permissions-instructions message containing `<permissions instructions>` and network access text, confirming sandbox policy context is actually passed to model prompt input.
  - `test_in_memory_session_runs_user_turn_http_sampling` now carries the same assertion for the HTTP sampling path, confirming request prompt-shape parity is transport-agnostic.
  - `test_in_memory_session_prompt_instructions_injection_consistent_between_sampling_variants` compares extracted permissions-prompt developer entries from both request constructors and verifies permissions-marker counts align across sampling and HTTP sampling.
- Added note: `porting_notes/turns/2026-06-03-session-turn-runtime-request-prompt-parity.md`.

## Test Coverage Added/Run
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_debug_models_returns_supported_default_models`
- `python -m pytest -q tests/test_cli_parser.py -k "main_exec_allows_strict_config or main_exec_reads_stdin_prompt_when_no_prompt_argument or main_exec_dash_reads_forced_stdin_prompt or main_exec_prepares_noninteractive_plan"`
- `python -m pytest -q tests/test_cli_parser.py`
- `python -m unittest tests.test_cli_core_smoke_suite tests.test_exec_core_runtime_smoke_suite tests.test_core_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`
- `python -m pytest -q tests/test_core_network_approval.py`
- `python -m pytest -q tests/test_core_unified_exec.py::CoreUnifiedExecHeadTailBufferTests`
- `python -m pytest -q tests/test_core_unified_exec.py tests/test_core_unified_exec_handler.py`
- `python -m pytest -q tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_default_session_exec_command_then_write_stdin`
- `python -m pytest -q tests/test_core_config_edit.py tests/test_core_command_canonicalization.py`
- `python -m pytest tests/test_cli_parser.py tests/test_core_network_approval.py tests/test_core_compact.py tests/test_core_config_edit.py tests/test_core_command_canonicalization.py tests/test_exec_session.py tests/test_exec_local_runtime.py tests/test_exec_core_runtime.py tests/test_exec_core_runtime_smoke_suite.py tests/test_core_smoke_suite.py tests/test_cli_core_smoke_suite.py tests/test_local_http_core_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py`
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_debug_models_returns_supported_default_models tests/test_cli_parser.py::TopLevelCliParserTests::test_main_prompt_without_subcommand_uses_local_http_exec_when_available tests/test_core_compact.py::CompactTests::test_collect_user_messages_filters_context_and_legacy_warnings tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_default_local_http_model_precedence`
- `python -m pytest -q tests/test_exec_core_runtime_smoke_suite.py tests/test_core_smoke_suite.py`
- `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_runtime.py`
- `python -m pytest -q tests/test_core_session_runtime.py -k "run_user_turn_sampling_tracks_resolved_config_from_settings_projection or runs_user_turn_http_sampling"`
- `python -m pytest -q tests/test_core_session_runtime.py -k "prompt_instructions_injection_consistent_between_sampling_variants"`
- `python -m pytest -q tests/test_cli_login.py tests/test_core_agent_jobs.py tests/test_core_shell_snapshot.py tests/test_core_spawn_landlock.py`
- `python -m pytest -q tests/test_core_session_startup_prewarm.py`
  - Result: 6 passed
- `python -m pytest -q tests/test_core_tool_router.py tests/test_core_tool_parallel.py tests/test_core_tool_dispatch_trace.py`
  - Result: 197 passed
- `python -m pytest -q tests/test_core_tool_dispatch_trace.py tests/test_core_tool_router.py`
  - Result: 68 passed
- `python -m pytest -q tests/test_core_tool_router.py`
  - Result: 56 passed
- `python -m pytest -q tests -k "not app_server and not sdk and not argument-comment-lint"`
- `python -m pytest -q tests -k "not app_server and not sdk and not argument-comment-lint"`
  - Result in this environment: 5086 passed, 7 skipped (260 deselected, 391 subtests), including all core-runtime/exec/CLI smoke slices.
- `python -m pytest -q`
  - Result in this environment: 5476 passed, 45 skipped
- `python -m pytest -q tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_summary_counts_warning_status_as_warning tests/test_cli_parser.py::TopLevelCliParserTests::test_main_doctor_all_requests_installation_path_details`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_empty_input_pending_input_uses_active_turn_with_keyword_only_queue`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py -k "keyword_only"`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py -k "user_prompt_submit_hook_keyword_only"`
  - Result: 2 passed
- `python -m pytest -q tests/test_core_turn_runtime.py`
- `python -m pytest -q tests/test_core_turn_runtime.py`
  - Result: 88 passed
- `python -m pytest -q codex/sdk/python/tests`
  - Result: 46 passed (including app-server suites)

## Open Known Gaps
- `doctor` auth gating parity needs an explicit decision:
  - In unauthenticated environments, `doctor` currently includes `auth.credentials: fail` and returns non-zero.
  - A follow-up is needed to decide strict upstream parity (keep fail semantics) versus parser-level compatibility defaults for missing credentials in environment-based tests.
- Remaining failures are now concentrated in app-server, MCP/plugin tooling, and broader streaming/daemon-adjacent paths outside this focused core slice.
- Follow-up work should continue to expand from this slice only where it unblocks `exec -> context -> model request -> stream handling -> tool dispatch -> final answer`.

## 2026-06-05 canonical crate migration batch 1

Moved the first existing implementation batch into Rust-tree-aligned canonical Python package paths: `pycodex/features`, `pycodex/features/managed.py`, `pycodex/git_utils`, and `pycodex/network_proxy`. Updated project/test imports, validated the new paths, then deleted the legacy `pycodex/core/features.py`, `pycodex/core/managed_features.py`, `pycodex/core/git_info.py`, and `pycodex/core/network_proxy_loader.py` files without keeping long-term shims.
## 2026-06-05 canonical crate migration batch 2: rollout

Moved `pycodex/core/rollout.py` to the Rust-tree-aligned canonical package `pycodex/rollout`, updated project/test imports, validated the new path, and deleted the legacy core file without retaining a long-term shim. Kept `session_rollout_init_error.py` and `thread_rollout_truncation.py` under `pycodex/core` because their Rust anchors are `core/src/*`, not the `codex-rollout` crate.
## 2026-06-05 canonical crate migration batch 3: utils string and approval presets

Moved `pycodex/core/string_utils.py` to `pycodex/utils/string` and `pycodex/core/approval_presets.py` to `pycodex/utils/approval_presets`, updated imports/tests, validated the new paths, and deleted the legacy core files without retaining long-term shims. Deliberately left `pycodex/core/paths.py` in place because it mixes `utils/home-dir` and `state` source anchors and should be split deliberately later.
## 2026-06-05 canonical crate migration batch 4: split core paths

Split `pycodex/core/paths.py` into `pycodex/utils/home_dir` for `codex-utils-home-dir` behavior and `pycodex/state` for state runtime DB path helpers. Updated imports/tests, validated canonical paths, and deleted the legacy core file without retaining a long-term shim. Marked `codex-utils-home-dir` as implemented and `codex-state` as partial helper shim in the crate ledger.
## 2026-06-05 canonical crate migration batch 5: remove apply_patch and execpolicy legacy shims

Deleted the legacy `pycodex/core/apply_patch.py` and `pycodex/core/exec_policy.py` compatibility shims after moving imports/tests to `pycodex.apply_patch` and `pycodex.execpolicy`. Removed the corresponding `pycodex.core` facade re-exports and fixed cycle-prone imports by making apply-patch dependencies lazy or type-only. Validated the canonical paths before and after deleting the shims.
## 2026-06-05 canonical crate migration batch 6: remove root TOML shim and canonicalize TUI

Deleted `pycodex/_toml.py`, replaced the legacy `pycodex/tui.py` shim with the canonical `pycodex/tui` package, and deleted `pycodex/cli/tui.py`. Updated imports/docs/tests to use `pycodex.config.toml_compat` and `pycodex.tui` directly. Validated canonical imports and targeted config/TUI tests.
## 2026-06-05 canonical crate migration batch 7: core-skills package

- Created canonical package `pycodex/core_skills` for already-ported helpers from `codex/codex-rs/core-skills`.
- Mapped config rules, injections, invocation utilities, mention helpers, and rendering helpers out of `pycodex/core`.
- Updated production and focused test imports to use canonical `pycodex.core_skills.*` modules.
- Old `pycodex/core/skill_*` files are intentionally retained until the touched-slice validation passes, then they should be deleted in the same migration batch.
- Focused validation passed before deletion: `62 passed`, import smoke passed.
- Deleted old coordinates: `pycodex/core/skill_config_rules.py`, `pycodex/core/skill_injections.py`, `pycodex/core/skill_invocation_utils.py`, `pycodex/core/skill_mentions.py`, `pycodex/core/skill_rendering.py`.
- Post-deletion validation passed: `62 passed`, import smoke passed.
- Old `pycodex.core.skill_*` import residual check found no matches.

## 2026-06-05 canonical crate migration batch 8: linux-sandbox and tools helpers

- Prepared canonical package `pycodex/linux_sandbox` for Linux sandbox command-construction helpers.
- Prepared canonical package/module `pycodex/tools/original_image_detail.py` for image-detail helper behavior from the tools crate.
- Updated production and focused test imports away from `pycodex.core.landlock` and `pycodex.core.original_image_detail`.
- Old core files are retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `12 passed`, import smoke passed.
- Deleted old coordinates: `pycodex/core/landlock.py`, `pycodex/core/original_image_detail.py`.
- Post-deletion validation passed: `12 passed`, import smoke passed.
- Old `pycodex.core.landlock` / `pycodex.core.original_image_detail` import residual check found no matches.

## 2026-06-05 canonical migration batch 9: utils/plugins mention syntax

- Prepared canonical package `pycodex/utils/plugins` for Rust `codex-rs/utils/plugins` mention syntax helpers.
- Updated imports away from `pycodex.core.mention_syntax` and removed the `pycodex.core` facade export for mention sigils.
- Old `pycodex/core/mention_syntax.py` is retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `40 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/mention_syntax.py`.
- Post-deletion validation passed: `40 passed`, import smoke passed.
- Old `pycodex.core.mention_syntax` import residual check found no matches.

## 2026-06-05 canonical migration batch 10: tools/tool_discovery

- Prepared canonical `pycodex/tools/tool_discovery.py` for Rust `codex-rs/tools/src/tool_discovery.rs`.
- Moved `AppInfo` protocol shape to `pycodex/app_server_protocol/apps.py`, matching Rust's `codex_app_server_protocol::AppInfo` source.
- Moved `ToolSearchSourceInfo` out of core tool-search entry and into tools/tool_discovery.
- Updated imports away from `pycodex.core.tool_discovery` and removed the matching `pycodex.core` facade exports.
- Old `pycodex/core/tool_discovery.py` is retained until focused validation passes, then should be deleted in this batch.
- Focused validation before deletion passed: `133 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/tool_discovery.py`.
- Post-deletion validation passed: `133 passed`, import smoke passed.
- Old `pycodex.core.tool_discovery` import residual check found no matches.

## 2026-06-06 canonical migration batch 11: tools/request_plugin_install split

- Prepared canonical `pycodex/tools/request_plugin_install.py` for Rust `codex-rs/tools/src/request_plugin_install.rs` protocol helpers.
- Prepared `pycodex/app_server_protocol/elicitation.py` for MCP elicitation shapes used by request-plugin-install.
- Trimmed `pycodex/core/request_plugin_install.py` so core keeps handler/spec/persistence behavior and imports tools protocol helpers instead of defining them.
- Updated imports away from `pycodex.core` for moved request-plugin-install protocol symbols.
- Focused validation passed after split: `94 passed`, import smoke passed.
- Exact residual check found no imports of moved request-plugin-install protocol symbols from `pycodex.core` or `pycodex.core.request_plugin_install`.
- `pycodex/core/request_plugin_install.py` intentionally remains as the Rust core handler/spec/persistence adapter; this batch was a split, not full deletion.

## 2026-06-06 canonical migration batch 12: core/tools/tool_search_entry

- Prepared canonical `pycodex/core/tools/tool_search_entry.py` for Rust `codex-rs/core/src/tools/tool_search_entry.rs`.
- Added `pycodex/core/tools` as the Python coordinate for core-runtime tool behavior under Rust core's tools module tree.
- Updated production and focused test imports away from the old `pycodex.core.tool_search_entry` path.
- Removed the matching `pycodex.core` facade exports for tool-search entry conversion helpers.
- Focused validation before deletion passed: `87 passed`, import smoke passed.
- Deleted old coordinate: `pycodex/core/tool_search_entry.py`.
- Post-deletion validation passed: `87 passed`.
- Old `pycodex.core.tool_search_entry` import residual check found no matches.

## 2026-06-06 canonical migration batch 13: plugins, extension tools, remote skills, connectors split

- Moved remote skill API helpers from `pycodex/core/remote_skills.py` to `pycodex/core_skills/remote.py`, matching Rust `codex-rs/core-skills/src/remote.rs`.
- Moved extension tool adapter behavior from `pycodex/core/extension_tools.py` to `pycodex/core/tools/handlers/extension_tools.py`, matching Rust `codex-rs/core/src/tools/handlers/extension_tools.rs`.
- Moved explicit plugin/app mention behavior from `pycodex/core/plugin_mentions.py` to `pycodex/core/plugins/mentions.py`, matching Rust `codex-rs/core/src/plugins/mentions.rs`.
- Created `pycodex/connectors` for Rust `codex-rs/connectors`, with `accessible.py`, `merge.py`, and `metadata.py`.
- Trimmed `pycodex/core/connectors.py` so it keeps Rust `core/src/connectors.rs` policy/config behavior and calls `pycodex.connectors` through private aliases for external crate behavior.
- Removed `pycodex.core` facade exports for the moved remote-skill, extension-tool, plugin-mention, and connector-crate helpers.
- Deleted old coordinates: `pycodex/core/remote_skills.py`, `pycodex/core/extension_tools.py`, and `pycodex/core/plugin_mentions.py`.
- Focused validation after deletion passed: `180 passed`, `4 subtests passed`, import smoke passed.
- Old import residual check found no matches for `pycodex.core.remote_skills`, `pycodex.core.extension_tools`, or `pycodex.core.plugin_mentions`.
- Moved connector-crate helper residual check found no public old-coordinate imports; `pycodex/core/connectors.py` intentionally retains only private aliases for core-to-connectors calls.

## 2026-06-06 canonical migration batch 14: core-skills model split

- Created `pycodex/core_skills/model.py` for Rust `codex-rs/core-skills/src/model.rs` skill model types.
- Moved the defining coordinate for `SkillMetadata`, `SkillDependencies`, and `SkillToolDependency` out of `pycodex/core/mcp_skill_dependencies.py`.
- Updated core-skills modules and focused tests to import skill model types from `pycodex.core_skills.model`.
- Kept `pycodex/core/mcp_skill_dependencies.py` as the Rust `core/src/mcp_skill_dependencies.rs` behavior module; it now imports model types instead of defining them.
- Kept `pycodex/core/skills.py` as the Rust `core/src/skills.rs` facade; `pycodex.core.skills.SkillMetadata` re-exports the canonical core-skills model type.
- Removed root `pycodex.core` facade exports for the moved model definitions.
- Focused validation passed: `72 passed`, import smoke passed.
- Old model-definition residual check found the model classes only in `pycodex/core_skills/model.py`.

## 2026-06-06 canonical migration batch 15: simple core tool handlers

- Moved `pycodex/core/plan_handler.py` to `pycodex/core/tools/handlers/plan.py`, matching Rust `codex-rs/core/src/tools/handlers/plan.rs`.
- Moved `pycodex/core/request_user_input_handler.py` to `pycodex/core/tools/handlers/request_user_input.py`, matching Rust `codex-rs/core/src/tools/handlers/request_user_input.rs`.
- Moved `pycodex/core/request_permissions_handler.py` to `pycodex/core/tools/handlers/request_permissions.py`, matching Rust `codex-rs/core/src/tools/handlers/request_permissions.rs`.
- Moved `pycodex/core/test_sync_handler.py` to `pycodex/core/tools/handlers/test_sync.py`, matching Rust `codex-rs/core/src/tools/handlers/test_sync.rs`.
- Updated production imports and focused tests to use canonical handler coordinates instead of root `pycodex.core` or old top-level core modules.
- Removed root `pycodex.core` facade exports for the moved handler symbols.
- Deleted old coordinates after focused validation.
- Focused validation before and after deletion passed: `260 passed`, `1 skipped`.
- Old import residual check found no matches for the four old handler module paths or moved root-facade imports.

## 2026-06-06 canonical migration batch 16: view-image and tool-search handlers

- Moved `pycodex/core/view_image_handler.py` to `pycodex/core/tools/handlers/view_image.py`, matching Rust `codex-rs/core/src/tools/handlers/view_image.rs`.
- Moved `pycodex/core/tool_search_handler.py` to `pycodex/core/tools/handlers/tool_search.py`, matching Rust `codex-rs/core/src/tools/handlers/tool_search.rs`.
- Kept `ToolSearchOutput` in `pycodex/core/tool_context.py`, because it is a tool output context type rather than a handler implementation.
- Updated production imports and focused tests to use canonical handler coordinates.
- Removed root `pycodex.core` facade exports for the moved handler symbols.
- Deleted old coordinates after focused validation.
- Focused validation before and after deletion passed: `304 passed`.
- Old import residual check found no matches for the two old handler module paths or moved root-facade imports.

## 2026-06-06 canonical migration batch 17: goal and plugin-install handlers

- Moved `pycodex/core/goal_handler.py` to `pycodex/core/tools/handlers/goal/__init__.py`, matching Rust `codex-rs/core/src/tools/handlers/goal.rs` plus `goal/{create,get,update}_goal.rs` and `goal_spec.rs`.
- Moved `pycodex/core/request_plugin_install.py` to `pycodex/core/tools/handlers/request_plugin_install.py`, matching Rust `request_plugin_install.rs`, `request_plugin_install_spec.rs`, `list_available_plugins_to_install.rs`, and `list_available_plugins_to_install_spec.rs`.
- Updated production imports in `spec_plan`, connector policy/exposure helpers, and the root `pycodex.core` facade to use canonical handler coordinates.
- Updated focused tests to import the goal handler directly from the canonical handler package.
- Deleted old coordinates by moving the files; no root-level `pycodex/core/goal_handler.py` or `pycodex/core/request_plugin_install.py` handler files remain.
- Focused validation passed: `84 passed`.
- Old root handler import residual check found no matches for `pycodex.core.goal_handler` or `pycodex.core.request_plugin_install`.

## 2026-06-06 canonical migration batch 18: core/tools public layer

- Moved `pycodex/core/tool_context.py` to `pycodex/core/tools/context.py`, matching Rust `codex-rs/core/src/tools/context.rs`.
- Moved `pycodex/core/tool_registry.py` to `pycodex/core/tools/registry.py`, matching Rust `codex-rs/core/src/tools/registry.rs`.
- Moved `pycodex/core/tool_router.py` to `pycodex/core/tools/router.py`, matching Rust `codex-rs/core/src/tools/router.rs`.
- Moved `pycodex/core/spec_plan.py` to `pycodex/core/tools/spec_plan.py`, matching Rust `codex-rs/core/src/tools/spec_plan.rs`.
- Moved `pycodex/core/tool_runtimes.py` to `pycodex/core/tools/runtimes/__init__.py`, matching Rust `codex-rs/core/src/tools/runtimes/mod.rs` plus runtime submodules.
- Updated production and focused test imports away from the old root `pycodex.core.tool_*` and `pycodex.core.spec_plan` module paths.
- Deleted old coordinates by moving the files; no root-level public tools module files remain for this batch.
- Focused public-tools validation passed: `573 passed`, `2 skipped`.
- Import smoke for the five canonical modules passed.
- Old import residual check found no matches for moved root paths.
- Wider adjacent validation including `turn_runtime` and `session_runtime` reported 6 failures in sandbox/settings assertions; these were recorded as adjacent risk, not treated as a blocker for this coordinate migration because the failed assertions are outside the moved import/registry/router behavior.

## 2026-06-06 adjacent runtime bug convergence: settings snapshots and analytics

- Resolved the adjacent failures discovered after batch 18.
- Updated `ThreadConfigSnapshot.sandbox_policy()` to mirror Rust `core/src/codex_thread.rs`: derive the compatibility `SandboxPolicy` from `PermissionProfile.to_legacy_sandbox_policy(cwd)` instead of returning the file-system sandbox policy.
- Added `file_system_sandbox_policy` to the Python snapshot object so the in-memory runtime can expose the projected split policy needed by Python-side session tests and turn context assembly.
- Updated `InMemoryCodexSession.update_settings` to reuse the already-computed snapshot permission profile and file-system policy, preventing value-equivalent but object-distinct projections.
- Updated turn resolved-config analytics to fall back from turn context to config/thread snapshot for `reasoning_effort`, `reasoning_summary`, `collaboration_mode`, and `personality` when using lightweight session mocks.
- Adjusted one Python test expectation from `preview.sandbox_policy` to `preview.sandbox_policy()` to match the Rust method contract.
- Focused runtime validation passed: `192 passed`.
- Original adjacent validation set passed: `765 passed`, `2 skipped`.

## 2026-06-06 canonical migration batch 19: remaining core/tools support layer

- Moved `pycodex/core/tool_dispatch_trace.py` to `pycodex/core/tools/tool_dispatch_trace.py`, matching Rust `codex-rs/core/src/tools/tool_dispatch_trace.rs`.
- Moved `pycodex/core/tool_lifecycle.py` to `pycodex/core/tools/lifecycle.py`, matching Rust `codex-rs/core/src/tools/lifecycle.rs`.
- Moved `pycodex/core/tool_parallel.py` to `pycodex/core/tools/parallel.py`, matching Rust `codex-rs/core/src/tools/parallel.rs`.
- Moved `pycodex/core/tool_orchestrator.py` to `pycodex/core/tools/orchestrator.py`, matching Rust `codex-rs/core/src/tools/orchestrator.rs`.
- Moved `pycodex/core/tool_sandboxing.py` to `pycodex/core/tools/sandboxing.py`, matching Rust `codex-rs/core/src/tools/sandboxing.rs`.
- Updated production and focused test imports away from old root `pycodex.core.tool_*` module paths.
- Deleted old coordinates by moving the files; no root-level support-layer tool files remain for this batch.
- Focused validation passed: `634 passed`, `2 skipped`.
- Import smoke for the five canonical support-layer modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 20: hosted/network/hook/events tool modules

- Moved `pycodex/core/hosted_spec.py` to `pycodex/core/tools/hosted_spec.py`, matching Rust `codex-rs/core/src/tools/hosted_spec.rs`.
- Moved `pycodex/core/network_approval.py` to `pycodex/core/tools/network_approval.py`, matching Rust `codex-rs/core/src/tools/network_approval.rs`.
- Moved `pycodex/core/hook_names.py` to `pycodex/core/tools/hook_names.py`, matching Rust `codex-rs/core/src/tools/hook_names.rs`.
- Moved `pycodex/core/tool_events.py` to `pycodex/core/tools/events.py`, matching Rust `codex-rs/core/src/tools/events.rs`.
- Updated production and focused test imports away from old root module paths.
- Deleted old coordinates by moving the files.
- Focused validation passed: `662 passed`, `2 skipped`.
- Import smoke for the four canonical modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 21: code-mode tool subtree

- Moved `pycodex/core/code_mode.py` to `pycodex/core/tools/code_mode/__init__.py`, matching Rust `codex-rs/core/src/tools/code_mode/mod.rs`.
- Confirmed Rust code mode is a subtree with `execute_handler.rs`, `execute_spec.rs`, `wait_handler.rs`, `wait_spec.rs`, and `response_adapter.rs`.
- Kept the Python implementation as one package module for this batch; no internal behavior split was attempted.
- Updated production and focused test imports away from `pycodex.core.code_mode`.
- Deleted the old root coordinate by moving the file.
- Focused validation passed: `349 passed`.
- Import smoke for `pycodex.core.tools.code_mode` passed.
- Old import residual check found no matches for `pycodex.core.code_mode`.

## 2026-06-06 canonical migration batch 22: shell and unified-exec handlers

- Moved `pycodex/core/shell_handler.py` to `pycodex/core/tools/handlers/shell.py`, matching Rust `codex-rs/core/src/tools/handlers/shell.rs`.
- Moved `pycodex/core/shell_spec.py` to `pycodex/core/tools/handlers/shell_spec.py`, matching Rust `codex-rs/core/src/tools/handlers/shell_spec.rs`.
- Moved `pycodex/core/unified_exec_handler.py` to `pycodex/core/tools/handlers/unified_exec.py`, matching Rust `codex-rs/core/src/tools/handlers/unified_exec.rs`.
- Updated production and focused test imports away from old root module paths.
- Reduced `pycodex/core/tools/handlers/__init__.py` to a light package initializer to avoid eager-import cycles when importing a single handler submodule.
- Deleted old coordinates by moving the files.
- Focused validation passed: `354 passed`, `2 skipped`.
- Import smoke for the three canonical handler modules passed.
- Old import residual check found no matches for moved root paths.

## 2026-06-06 canonical migration batch 23: dynamic tool handler

- Moved `pycodex/core/dynamic_tool_handler.py` to `pycodex/core/tools/handlers/dynamic.py`, matching Rust `codex-rs/core/src/tools/handlers/dynamic.rs`.
- Updated production and focused test imports away from `pycodex.core.dynamic_tool_handler`.
- Deleted the old root coordinate by moving the file.
- Focused validation passed: `235 passed`.
- Import smoke for `pycodex.core.tools.handlers.dynamic` passed.
- Old import residual check found no matches for the moved root path.

## 2026-06-06 canonical migration batch 24: MCP handlers

- Moved `pycodex/core/mcp_tool_handler.py` to `pycodex/core/tools/handlers/mcp.py`, matching Rust `codex-rs/core/src/tools/handlers/mcp.rs`.
- Moved `pycodex/core/mcp_resource_handler.py` to `pycodex/core/tools/handlers/mcp_resource.py`, matching Rust `codex-rs/core/src/tools/handlers/mcp_resource.rs` and `mcp_resource_spec.rs`.
- Updated production and focused test imports away from old root module paths.
- Deleted old coordinates by moving the files.
- Focused validation passed: `151 passed`.
- Import smoke for the two canonical MCP handler modules passed.
- Old import residual check found no matches for moved root paths.
- Scope note: this was coordinate-only MCP shim preservation, not deep MCP feature expansion.

## 2026-06-06 - canonical migration batch 25: agent and multi-agent handlers

- Rust anchors:
  - `codex/codex-rs/core/src/tools/handlers/agent_jobs.rs`
  - `codex/codex-rs/core/src/tools/handlers/agent_jobs_spec.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_common.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_spec.rs`
  - `codex/codex-rs/core/src/tools/handlers/multi_agents_v2.rs`
- Python targets:
  - `pycodex/core/tools/handlers/agent_jobs.py`
  - `pycodex/core/tools/handlers/multi_agents_common.py`
  - `pycodex/core/tools/handlers/multi_agents_spec.py`
  - `pycodex/core/tools/handlers/multi_agents.py`
  - `pycodex/core/tools/handlers/multi_agents_v2.py`
- Change:
  - Moved the previously core-level agent job and multi-agent handler modules into the Rust-aligned `core/tools/handlers` coordinate.
  - Rewrote imports to the new canonical paths.
  - Removed the old root-level module files instead of leaving compatibility aliases, matching the current no-duplicate-coordinate policy.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - Import smoke for the new handler modules: passed.
  - `python -m pytest tests/test_core_agent_jobs.py tests/test_core_multi_agents_common.py tests/test_core_multi_agents_spec.py tests/test_core_multi_agents_v1_handler.py tests/test_core_multi_agents_v2_handler.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_session_runtime.py`: `195 passed`.
- Scope note:
  - Deep multi-agent orchestration remains deprioritized as an extension area; this batch preserves and relocates the existing shim/handler behavior under the upstream handler coordinate.

## 2026-06-06 - canonical migration batch 26: agent/config/context/state core subpackages

- Rust anchors:
  - `codex/codex-rs/core/src/agent/agent_resolver.rs`
  - `codex/codex-rs/core/src/agent/control.rs`
  - `codex/codex-rs/core/src/agent/registry.rs`
  - `codex/codex-rs/core/src/agent/status.rs`
  - `codex/codex-rs/core/src/config/agent_roles.rs`
  - `codex/codex-rs/core/src/config/edit.rs`
  - `codex/codex-rs/core/src/context/mod.rs`
  - `codex/codex-rs/core/src/context/permissions_instructions.rs`
  - `codex/codex-rs/core/src/state/auto_compact_window.rs`
- Python targets:
  - `pycodex/core/agent/agent_resolver.py`
  - `pycodex/core/agent/control.py`
  - `pycodex/core/agent/registry.py`
  - `pycodex/core/agent/status.py`
  - `pycodex/core/config/agent_roles.py`
  - `pycodex/core/config/edit.py`
  - `pycodex/core/context/__init__.py`
  - `pycodex/core/context/permissions_instructions.py`
  - `pycodex/core/state/auto_compact_window.py`
- Change:
  - Moved selected root-level Python modules into Rust-aligned core subpackages.
  - Converted `pycodex/core/context.py` into the `pycodex.core.context` package initializer so `context/permissions_instructions.py` can live under the Rust-aligned context coordinate without a Python module/package name conflict.
  - Updated imports and top-level `pycodex.core` re-exports to the new canonical paths.
  - Removed old root-level files instead of leaving compatibility aliases.
- Validation:
  - New canonical module import smoke: passed.
  - Old selected file path check: old files absent, new files present.
  - Residual old import search: no old module-path leakage; one harmless top-level re-export import false positive (`agent_status_from_event`).
  - `python -m pytest tests/test_core_agent_control.py tests/test_core_agent_registry.py tests/test_core_agent_resolver.py tests/test_core_agent_roles.py tests/test_core_agent_status.py tests/test_core_auto_compact_window.py tests/test_core_config_edit.py tests/test_core_context.py tests/test_core_context_updates.py tests/test_core_permissions_instructions.py tests/test_core_realtime_context.py tests/test_core_request_permissions_handler.py tests/test_core_request_plugin_install_handler.py tests/test_core_session_runtime.py`: `266 passed, 1 skipped`.
- Scope note:
  - This batch is coordinate consolidation plus import preservation. It does not expand deep agent orchestration beyond the behavior already implemented.

## 2026-06-06 - canonical migration batch 27: unified_exec package coordinate

- Rust anchors:
  - `codex/codex-rs/core/src/unified_exec/mod.rs`
  - `codex/codex-rs/core/src/unified_exec/errors.rs`
  - `codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
  - `codex/codex-rs/core/src/unified_exec/process.rs`
  - `codex/codex-rs/core/src/unified_exec/process_manager.rs`
  - `codex/codex-rs/core/src/unified_exec/process_state.rs`
- Python target:
  - `pycodex/core/unified_exec/__init__.py`
- Change:
  - Converted the old root-level `pycodex/core/unified_exec.py` module into the Rust-aligned `pycodex/core/unified_exec/` package initializer.
  - Kept the public import path `pycodex.core.unified_exec` stable, so existing callers did not need import rewrites.
  - Removed the old root-level file coordinate instead of keeping a duplicate alias.
- Validation:
  - New package import smoke: passed.
  - Old file absent and new package initializer present.
  - `python -m pytest tests/test_core_unified_exec.py tests/test_core_unified_exec_handler.py tests/test_core_exec.py tests/test_exec_local_runtime.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_code_mode.py`: `540 passed, 2 skipped`.
- Scope note:
  - This batch is a coordinate conversion only. It does not yet split Python `unified_exec` internals into the Rust submodules (`errors`, `head_tail_buffer`, `process`, `process_manager`, `process_state`).

## 2026-06-06 - canonical migration batch 28: handler utils and tools crate tool definition

- Rust anchors:
  - `codex/codex-rs/core/src/tools/handlers/mod.rs`
  - `codex/codex-rs/tools/src/tool_definition.rs`
- Python targets:
  - `pycodex/core/tools/handlers/utils.py`
  - `pycodex/tools/tool_definition.py`
- Change:
  - Moved the old root-level `pycodex/core/handler_utils.py` into the Rust-aligned handler helper coordinate.
  - Moved the old root-level `pycodex/core/tool_definition.py` into `pycodex/tools/`, matching the upstream `codex-rs/tools` crate instead of the core crate.
  - Rewrote imports to the new canonical paths and preserved the top-level `pycodex.core.ToolDefinition` re-export.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_handler_utils.py tests/test_core_tool_definition.py tests/test_core_apply_patch.py tests/test_core_request_permissions_handler.py tests/test_core_unified_exec_handler.py tests/test_core_session_runtime.py tests/test_exec_local_runtime.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_code_mode.py`: `514 passed, 3 skipped`.
- Scope note:
  - This batch is coordinate consolidation only. It preserves existing behavior while removing misleading root-level coordinates.

## 2026-06-06 - canonical migration batch 29: session and turn runtime package coordinates

- Rust anchors:
  - `codex/codex-rs/core/src/session/mod.rs`
  - `codex/codex-rs/core/src/session/session.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/core/src/session/turn_context.rs`
  - `codex/codex-rs/core/src/codex_thread.rs`
- Python targets:
  - `pycodex/core/session/runtime.py`
  - `pycodex/core/session/turn/prompt.py`
  - `pycodex/core/session/turn/request.py`
  - `pycodex/core/session/turn/runtime.py`
  - `pycodex/core/session/turn/sampler.py`
- Change:
  - Moved the old root-level session/turn runtime files into Rust-aligned `core/session` coordinates.
  - Rewrote imports from the old `pycodex.core.session_runtime` and `pycodex.core.turn_*` paths to the new canonical package paths.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
  - Repaired a Windows encoding side effect in `tests/test_exec_local_runtime.py` where multibyte UTF-8 string literals had been damaged during path rewrite.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_prompt.py tests/test_core_turn_request.py tests/test_core_turn_runtime.py tests/test_core_turn_sampler.py tests/test_core_http_transport.py tests/test_exec_local_runtime.py tests/test_core_codex_thread.py tests/test_core_codex_thread_unittest.py tests/test_core_compact_remote.py tests/test_core_compact_remote_v2.py`: `527 passed`.
- Scope note:
  - This batch keeps the Python session/turn implementation as coarse runtime modules for now. It does not yet split `turn/runtime.py` internally into all Rust `turn.rs` sub-concepts.

## 2026-06-06 - canonical migration batch 30: plugin rendering and context manager updates

- Rust anchors:
  - `codex/codex-rs/core/src/plugins/render.rs`
  - `codex/codex-rs/core/src/context_manager/updates.rs`
- Python targets:
  - `pycodex/core/plugins/render.py`
  - `pycodex/core/context_manager/updates.py`
- Change:
  - Moved the old root-level `pycodex/core/app_plugin_rendering.py` into the Rust-aligned plugin rendering coordinate.
  - Moved the old root-level `pycodex/core/context_updates.py` into the Rust-aligned context manager updates coordinate.
  - Created `pycodex/core/context_manager/__init__.py` for the new package coordinate.
  - Rewrote imports to the new canonical paths.
  - Removed old root-level file coordinates instead of keeping duplicate aliases.
- Validation:
  - Residual old import search across `pycodex/` and `tests/`: clean.
  - New canonical module import smoke: passed.
  - `python -m pytest tests/test_core_context_updates.py tests/test_core_context.py tests/test_core_plugin_mentions.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_http_transport.py`: `286 passed`.
- Scope note:
  - This batch is coordinate consolidation only. `http_transport.py` remains at `pycodex/core/http_transport.py` because no direct Rust coordinate exists and it functions as a Python stdlib transport adapter.

## 2026-06-06 - canonical migration batch 31: http transport adapter package

- Functional Rust anchors:
  - `codex/codex-rs/core/src/client.rs`
  - `codex/codex-rs/core/src/client_common.rs`
  - `codex/codex-rs/core/src/responses_retry.rs`
  - `codex/codex-rs/core/src/session/turn.rs`
  - `codex/codex-rs/protocol/src/protocol.rs`
- Python target:
  - `pycodex/core/http_transport/__init__.py`
  - `pycodex/core/http_transport/README.md`
- Change:
  - Converted the old root-level `pycodex/core/http_transport.py` module into a dedicated `pycodex/core/http_transport/` package.
  - Preserved the public import path `pycodex.core.http_transport`.
  - Added a package README documenting why this Python adapter has no single Rust file coordinate and which Rust behavior slices it corresponds to.
  - Removed the old root-level file coordinate.
- Validation:
  - Package import smoke: passed.
  - Old file absent, new package initializer and README present.
  - `python -m pytest tests/test_core_http_transport.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_exec_local_runtime.py`: `454 passed`.
- Scope note:
  - This package is intentionally documented as a Python stdlib HTTP/SSE compatibility adapter spanning client, retry, protocol, and turn sampling behavior.
