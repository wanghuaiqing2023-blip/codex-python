# codex-analytics test alignment

Rust crate: `codex-analytics`

Python package: `pycodex/analytics`

Status: `complete`

## Certified Modules

- `codex/codex-rs/analytics/src/accepted_lines.rs` -> `pycodex/analytics/__init__.py`

## Certified Module Slices

- `codex/codex-rs/analytics/src/client.rs` pure enqueue/batching slice -> `pycodex/analytics/__init__.py`
  - `track_request` relevant request filtering
  - `track_response` relevant response filtering
  - `track_event_request_batches`
  - `TrackEventRequest::should_send_in_isolated_request`
  - `AnalyticsEventsQueue::should_enqueue_app_used`
  - `AnalyticsEventsQueue::should_enqueue_plugin_used`
- `codex/codex-rs/analytics/src/client.rs` dependency-light HTTP transport slice -> `pycodex/analytics/__init__.py`
  - `send_track_events` empty/auth/backend gating
  - `send_track_events` base URL trimming and `/codex/analytics-events/events` path construction
  - `send_track_events_request` JSON payload, auth headers, content type, and batch POST behavior
- `codex/codex-rs/analytics/src/events.rs` metadata/event wrapper slice -> `pycodex/analytics/__init__.py`
  - `codex_app_metadata`
  - `codex_plugin_metadata`
  - `codex_plugin_used_metadata`
  - `codex_hook_run_metadata`
  - `plugin_state_event_type`
- `codex/codex-rs/analytics/src/events.rs` accepted-line event request shape -> `accepted_line_fingerprint_event_requests`
- `codex/codex-rs/analytics/src/lib.rs` time helpers -> `now_unix_seconds`, `now_unix_millis`
- `codex/codex-rs/analytics/src/facts.rs` public fact enum/data slice -> `pycodex/analytics/__init__.py`
  - `TurnSubmissionType`, `ThreadInitializationMode`, `TurnStatus`
  - `CompactionTrigger`, `CompactionReason`, `CompactionImplementation`, `CompactionPhase`, `CompactionStrategy`, `CompactionStatus`
  - `TurnSteerRequestError`/`InputError` to `TurnSteerRejectionReason` mapping
  - `CodexCompactionEvent` and `TurnResolvedConfigFact` field surfaces
- `codex/codex-rs/analytics/src/reducer.rs` custom fact ingestion slice -> `pycodex/analytics/__init__.py`
  - `AnalyticsReducer.ingest_client_request`
  - `AnalyticsReducer.ingest_client_response`
  - unrelated client request suppression
  - unrelated client response suppression
  - `ingest_skill_invoked`
  - `ingest_app_mentioned`
  - `ingest_app_used`
  - `ingest_hook_run`
  - `ingest_plugin_used`
  - `ingest_plugin_state_changed`
  - `skill_id_for_local_skill` and local skill path normalization
- `codex/codex-rs/analytics/src/reducer.rs` turn-event assembly slice -> `pycodex/analytics/__init__.py`
  - `CodexTurnEventParams` field projection
  - required turn event prerequisites
  - token usage projection
  - completed tool item count buckets
  - accepted-line latest diff cache
  - accepted-line aggregate emission on completed turn
  - latest TurnDiffUpdated wins before completion
  - large accepted-line aggregate upload omits computed fingerprints
  - `PendingTurnStartState`
  - `analytics_turn_status`
  - `AnalyticsReducer.track_turn_start_request`
  - `AnalyticsReducer.ingest_turn_start_error_response`
  - `AnalyticsReducer.ingest_turn_start_response`
  - `AnalyticsReducer.ingest_turn_resolved_config`
  - `AnalyticsReducer.ingest_turn_started`
  - `AnalyticsReducer.ingest_turn_completed`
  - `AnalyticsReducer.ingest_turn_completed_notification`
  - TurnStart pending request removal on error response
  - failed/interrupted/completed notification status projection
  - missing-started notification leaves `started_at` null
- `codex/codex-rs/analytics/src/reducer.rs` turn-steer event slice -> `pycodex/analytics/__init__.py`
  - `CodexTurnSteerEventParams` field projection
  - accepted/rejected result projection
  - typed rejection reason mapping
  - accepted steer count increment
  - `AnalyticsReducer.track_turn_steer_request`
  - `AnalyticsReducer.ingest_turn_steer_response`
  - `AnalyticsReducer.ingest_turn_steer_error_response`
  - missing-pending response/error suppression
  - pending request removal after accepted response
- `codex/codex-rs/analytics/src/reducer.rs` compaction event slice -> `pycodex/analytics/__init__.py`
  - `CodexCompactionEventParams` field projection
  - compaction custom fact ingestion with connection/thread metadata
- `codex/codex-rs/analytics/src/events.rs` thread-initialized event slice -> `pycodex/analytics/__init__.py`
  - `ThreadInitializedEventParams` field projection
  - `subagent_thread_started_event_request`
  - subagent source and parent-thread projection
  - reducer subagent thread metadata state insertion
  - subagent parent connection inheritance for later reducer events
- `codex/codex-rs/analytics/src/reducer.rs` initialize/thread lifecycle cache slice -> `pycodex/analytics/__init__.py`
  - `ConnectionState`
  - `ThreadAnalyticsState`
  - `AnalyticsReducer.ingest_initialize`
  - `AnalyticsReducer.ingest_thread_response`
  - thread response suppression before Initialize
  - cached app-server client/runtime metadata projection
- `codex/codex-rs/analytics/src/reducer.rs` guardian review result helper slice -> `pycodex/analytics/__init__.py`
  - `ReviewStatus` and `ReviewResolution` serde values
  - `guardian_review_result` terminal-status mapping
  - `effective_permissions_review_result` approval/scope mapping
- `codex/codex-rs/analytics/src/reducer.rs` item review summary slice -> `pycodex/analytics/__init__.py`
  - `final_approval_outcome`
  - `item_review_summary_key`
  - `AnalyticsReducer.record_item_review_summary`
  - `apply_tool_item_review_summary`
  - thread/turn/item scoped review summary lookup
- `codex/codex-rs/analytics/src/reducer.rs` review event emission slice -> `pycodex/analytics/__init__.py`
  - `AnalyticsReducer.emit_review_event`
  - `AnalyticsReducer.track_pending_review`
  - `AnalyticsReducer.ingest_review_response`
  - `AnalyticsReducer.ingest_effective_permissions_approval_response`
  - `AnalyticsReducer.ingest_server_request_aborted`
  - `AnalyticsReducer.ingest_guardian_review_completed`
  - `guardian_review_subject_metadata`
  - `guardian_review_requested_additional_permissions`
  - `guardian_review_requested_network_access`
  - user review event projection
  - guardian completed notification event projection
  - permissions review event projection without tool-item summary denormalization
  - effective permissions response projection with session approval resolution
  - aborted request remove-once/idempotency behavior
  - observed review duration projection
- `codex/codex-rs/analytics/src/reducer.rs` tool item lifecycle slice -> `pycodex/analytics/__init__.py`
  - `AnalyticsReducer.ingest_item_started`
  - `AnalyticsReducer.ingest_item_completed`
  - `AnalyticsReducer.thread_context`
  - `tracked_tool_item_id`
  - `tool_item_event`
  - inherited thread connection/runtime lookup for subagent tool-item events
  - command execution status to terminal outcome mapping
  - command execution source to tool-name mapping
  - command action count projection
  - file-change outcome and operation count projection
  - MCP tool-call outcome/server/tool/error projection
  - dynamic tool-call outcome/content count projection
  - collab-agent tool/status/thread/model/agent-state projection
  - web-search action/query projection
  - image-generation outcome/presence projection
  - started-at retention/removal
  - missing-turn-state completion suppression
  - completion updates turn tool counts
- `codex/codex-rs/analytics/src/events.rs` guardian review event serialization slice -> `pycodex/analytics/__init__.py`
  - `GuardianReviewEventParams` field projection
  - `GuardianReviewEventPayload` metadata flattening
- `codex/codex-rs/analytics/src/reducer.rs` guardian review custom fact slice -> `pycodex/analytics/__init__.py`
  - `ingest_guardian_review`
  - optional target item projection
  - network-access reviewed-action tagged shape
- `codex/codex-rs/analytics/src/events.rs` review event serialization slice -> `pycodex/analytics/__init__.py`
  - `ReviewSubjectKind`, `Reviewer`, and `ReviewTrigger` serde values
  - `CodexReviewEventParams` field projection
- `codex/codex-rs/analytics/src/events.rs` command/file-change/MCP/dynamic/collab/web-search/image-generation tool-item event slice -> `pycodex/analytics/__init__.py`
  - `CodexToolItemEventBase` field projection
  - `CodexCommandExecutionEventParams` field projection
  - `CodexFileChangeEventParams` field projection
  - `CodexMcpToolCallEventParams` field projection
  - `CodexDynamicToolCallEventParams` field projection
  - `CodexCollabAgentToolCallEventParams` field projection
  - `CodexWebSearchEventParams` field projection
  - `CodexImageGenerationEventParams` field projection
  - `FinalApprovalOutcome`, `ToolItemTerminalStatus`, `ToolItemFailureKind`, and `CommandExecutionSource` serialized values

## Rust Tests And Contracts

- Rust `src/accepted_lines.rs` tests are migrated in `tests/test_analytics_accepted_lines_rs.py`.
- Rust `analytics_client_tests::accepted_line_fingerprints_event_serializes_expected_shape` is migrated in `tests/test_analytics_accepted_lines_rs.py`.
- Rust `src/client_tests.rs` enqueue-filtering and batching tests are migrated in `tests/test_analytics_client_rs.py`.
- Rust `src/client.rs::{send_track_events,send_track_events_request}` source contracts for Codex-backend auth gating, base URL trimming, JSON request shape, auth header forwarding, and per-batch POST are covered by `tests/test_analytics_client_rs.py::test_send_track_events_posts_batches_with_auth_to_codex_backend` and `tests/test_analytics_client_rs.py::test_send_track_events_skips_without_codex_backend_auth`.
- Rust `analytics_client_tests::{app_mentioned_event_serializes_expected_shape,app_used_event_serializes_expected_shape,plugin_used_event_serializes_expected_shape,plugin_management_event_serializes_expected_shape,plugin_management_event_can_use_remote_plugin_id_override,hook_run_event_serializes_expected_shape,hook_run_metadata_maps_sources_and_statuses,hook_run_metadata_maps_stopped_status}` app/plugin/hook metadata serialization tests are migrated in `tests/test_analytics_events_rs.py`.
- Rust `analytics_client_tests::{normalize_path_for_skill_id_repo_scoped_uses_relative_path,normalize_path_for_skill_id_user_scoped_uses_absolute_path,normalize_path_for_skill_id_admin_scoped_uses_absolute_path,normalize_path_for_skill_id_repo_root_not_in_skill_path_uses_absolute_path}` are migrated in `tests/test_analytics_events_rs.py`.
- Rust `src/facts.rs` serde/data contracts are covered by Rust-source-derived tests in `tests/test_analytics_facts_rs.py`.
- Rust `analytics_client_tests::{app_used_dedupe_is_keyed_by_turn_and_connector,plugin_used_dedupe_is_keyed_by_turn_and_plugin,unrelated_client_requests_are_ignored_by_reducer,unrelated_client_responses_are_ignored_by_reducer,reducer_ingests_skill_invoked_fact,reducer_includes_plugin_id_for_plugin_skill_invocations,reducer_ingests_hook_run_fact,reducer_ingests_app_and_plugin_facts,reducer_ingests_plugin_state_changed_fact}` are migrated in `tests/test_analytics_reducer_rs.py`.
- Rust `analytics_client_tests::{turn_event_serializes_expected_shape,turn_lifecycle_emits_turn_event,turn_event_counts_completed_tool_items,turn_does_not_emit_without_required_prerequisites,turn_start_error_response_discards_pending_start_request,turn_lifecycle_emits_failed_turn_event,turn_lifecycle_emits_interrupted_turn_event_without_error,turn_completed_without_started_notification_emits_null_started_at,reducer_emits_large_accepted_line_aggregates_without_fingerprints,reducer_emits_accepted_line_fingerprints_once_from_latest_turn_diff_on_completion}` are covered by Rust-test-derived tests in `tests/test_analytics_turn_event_rs.py`.
- Rust `reducer::tests::managed_full_disk_with_restricted_network_reports_external_sandbox` is migrated in `tests/test_analytics_turn_event_rs.py`.
- Rust `analytics_client_tests::{accepted_turn_steer_emits_expected_event,rejected_turn_steer_uses_request_connection_metadata,rejected_turn_steer_maps_active_turn_not_steerable_error_type,rejected_turn_steer_maps_input_too_large_error_type,turn_steer_does_not_emit_without_pending_request,accepted_steers_increment_turn_steer_count}` are covered by Rust-test-derived tests in `tests/test_analytics_turn_steer_rs.py`.
- Rust `analytics_client_tests::{compaction_event_serializes_expected_shape,compaction_event_ingests_custom_fact,compaction_implementation_serializes_remote_v2}` are covered by Rust-test-derived tests in `tests/test_analytics_compaction_rs.py`.
- Rust `analytics_client_tests::{thread_initialized_event_serializes_expected_shape,subagent_thread_started_review_serializes_expected_shape,subagent_thread_started_thread_spawn_serializes_parent_thread_id,subagent_thread_started_memory_consolidation_serializes_expected_shape,subagent_thread_started_other_serializes_expected_shape,subagent_thread_started_other_serializes_explicit_parent_thread_id,subagent_thread_started_publishes_without_initialize,subagent_thread_started_inherits_parent_connection_for_new_thread}` are covered by Rust-test-derived tests in `tests/test_analytics_thread_initialized_rs.py`.
- Rust `analytics_client_tests::initialize_caches_client_and_thread_lifecycle_publishes_once_initialized` is migrated in `tests/test_analytics_thread_initialized_rs.py`.
- Rust `reducer::tests::guardian_review_result_maps_terminal_statuses` is migrated in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::review_event_serializes_expected_shape` is migrated in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::guardian_review_event_ingests_custom_fact_with_optional_target_item` is migrated in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::{terminal_reviews_denormalize_counts_onto_tool_item_events,item_review_summaries_do_not_cross_threads_with_reused_item_ids}` and Rust `reducer.rs::final_approval_outcome` source contract are covered in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::{command_execution_approval_response_publishes_user_review_event,permissions_reviews_emit_events_without_denormalizing_onto_tool_items,effective_session_permissions_response_publishes_session_user_review_event}` are covered by Rust-test-derived tests in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::aborted_server_request_publishes_aborted_user_review_event_once` is migrated in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::guardian_completed_notification_publishes_review_event_with_thread_metadata` is migrated in `tests/test_analytics_review_rs.py`.
- Rust `analytics_client_tests::command_execution_event_serializes_expected_shape` is migrated in `tests/test_analytics_tool_item_events_rs.py`.
- Rust `analytics_client_tests::{item_lifecycle_notifications_publish_command_execution_event,item_completed_without_turn_state_does_not_create_turn_state,subagent_tool_items_inherit_parent_connection_metadata}` are migrated in `tests/test_analytics_tool_item_events_rs.py`.
- Rust `reducer.rs::tool_item_event` FileChange/McpToolCall/DynamicToolCall/CollabAgentToolCall/WebSearch/ImageGeneration source contracts are covered in `tests/test_analytics_tool_item_events_rs.py`.
- Rust `events.rs` `CodexFileChangeEventParams` and `CodexMcpToolCallEventParams` source contracts are covered in `tests/test_analytics_tool_item_events_rs.py`.
- Rust `events.rs` `CodexDynamicToolCallEventParams` and `CodexCollabAgentToolCallEventParams` source contracts are covered in `tests/test_analytics_tool_item_events_rs.py`.
- Rust `events.rs` `CodexWebSearchEventParams`, `WebSearchActionKind`, and `CodexImageGenerationEventParams` source contracts are covered in `tests/test_analytics_tool_item_events_rs.py`.

## Python Tests

- `tests/test_analytics_accepted_lines_rs.py`
- `tests/test_analytics_client_rs.py`
- `tests/test_analytics_events_rs.py`
- `tests/test_analytics_facts_rs.py`
- `tests/test_analytics_reducer_rs.py`
- `tests/test_analytics_turn_event_rs.py`
- `tests/test_analytics_turn_steer_rs.py`
- `tests/test_analytics_compaction_rs.py`
- `tests/test_analytics_thread_initialized_rs.py`
- `tests/test_analytics_review_rs.py`
- `tests/test_analytics_tool_item_events_rs.py`

## Validation

- `python -m pytest tests/test_analytics_review_rs.py -q --tb=short` (`15 passed`)
- `python -m pytest tests/test_analytics_events_rs.py -q --tb=short` (`12 passed`)
- `python -m pytest tests/test_analytics_compaction_rs.py -q --tb=short` (`3 passed`)
- `python -m pytest tests/test_analytics_reducer_rs.py -q --tb=short` (`9 passed`)
- `python -m pytest tests/test_analytics_turn_event_rs.py -q --tb=short` (`10 passed`)
- `python -m pytest tests/test_analytics_turn_steer_rs.py -q --tb=short` (`5 passed`)
- `python -m pytest tests/test_analytics_thread_initialized_rs.py -q --tb=short` (`9 passed`)
- `python -m pytest tests/test_analytics_tool_item_events_rs.py -q --tb=short` (`13 passed`)
- `python -m pytest tests/test_analytics_client_rs.py -q --tb=short` (`5 passed`)
- `python -m pytest tests/test_analytics_accepted_lines_rs.py tests/test_analytics_client_rs.py tests/test_analytics_events_rs.py tests/test_analytics_facts_rs.py tests/test_analytics_reducer_rs.py tests/test_analytics_turn_event_rs.py tests/test_analytics_turn_steer_rs.py tests/test_analytics_compaction_rs.py tests/test_analytics_thread_initialized_rs.py tests/test_analytics_review_rs.py tests/test_analytics_tool_item_events_rs.py -q --tb=short` (`89 passed`)
- `python -m pytest tests\test_analytics_accepted_lines_rs.py tests\test_analytics_client_rs.py tests\test_analytics_events_rs.py tests\test_analytics_facts_rs.py tests\test_analytics_reducer_rs.py tests\test_analytics_turn_event_rs.py tests\test_analytics_turn_steer_rs.py tests\test_analytics_compaction_rs.py tests\test_analytics_thread_initialized_rs.py tests\test_analytics_review_rs.py tests\test_analytics_tool_item_events_rs.py tests\test_external_agent_sessions_rs.py tests\test_connectors_rs.py -q --tb=short` (`118 passed`)
- `python -m pytest tests/test_core_compact.py tests/test_core_turn_metadata.py -q --tb=short` (`32 passed`)
- `python -m py_compile pycodex/analytics/__init__.py tests/test_analytics_turn_event_rs.py` passed

## Native Runtime Differences

- `src/client.rs`: Rust's native Tokio analytics queueing, exact async `AuthManager` identity, exact `reqwest` client/timeout behavior, and background queue flush lifecycle are not embedded in Python. Dependency-light Codex-backend auth gating, batching, disabled-client suppression, dedupe, and real local HTTP POST transport are covered.
- `src/reducer.rs`: Rust's full app-server protocol runtime orchestration is not embedded in Python. Reducer projection contracts for custom facts, request/response relevance, initialize/thread lifecycle caching, subagent inheritance, turn lifecycle, turn steer lifecycle, tool item lifecycle, compaction, thread initialization, review, and guardian completion are covered by Rust-derived tests.
- `src/events.rs` and `src/facts.rs`: Python covers the Rust-tested and source-anchored event/fact surfaces used by common PyCodex behavior, including accepted-line, app/plugin/hook, review/guardian-review, command/file-change/MCP/dynamic/collab/web-search/image-generation, compaction, config, and turn-steer surfaces.
