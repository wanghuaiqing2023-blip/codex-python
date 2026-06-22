# pycodex.rollout_trace Test Alignment

Rust crate: `codex-rollout-trace`
Rust path: `codex/codex-rs/rollout-trace`

## Status

`complete`

All Rust `codex-rollout-trace` module-local tests and source-derived
dependency-light contracts tracked for the Python projection have focused
Python parity tests. Crate-focused validation passed on 2026-06-22 with
`100 passed`, plus external facade smoke and `py_compile`.

## Rust-Derived Tests

| Rust module | Rust tests/contracts | Python tests | Status |
|---|---|---|---|
| `src/mcp.rs` | `disabled_mcp_trace_leaves_request_meta_unchanged` | `tests/test_rollout_trace_mcp_rs.py::test_disabled_mcp_trace_leaves_request_meta_unchanged` | complete |
| `src/mcp.rs` | `enabled_mcp_trace_adds_bridge_correlation_meta` | `tests/test_rollout_trace_mcp_rs.py::test_enabled_mcp_trace_adds_bridge_correlation_meta` | complete |
| `src/mcp.rs` | `McpCallTraceContext::add_request_meta` source contract for `None` and non-object metadata | `tests/test_rollout_trace_mcp_rs.py::test_enabled_mcp_trace_creates_meta_object_and_preserves_non_object_meta` | complete |
| `src/thread.rs`, `src/mcp.rs` | `ThreadTraceContext::start_mcp_call_trace` and `McpCallTraceContext::add_request_meta` source contract for trace-owned MCP UUID correlation | `tests/test_rollout_trace_mcp_rs.py::test_start_mcp_call_trace_records_correlation_and_request_meta` | complete_slice |
| `src/thread.rs` | disabled `ThreadTraceContext::start_mcp_call_trace` no-op source contract | `tests/test_rollout_trace_mcp_rs.py::test_disabled_thread_mcp_trace_records_nothing` | complete_slice |
| `src/reducer/mod.rs`, `src/reducer/tool.rs` | `RawTraceEventPayload::McpToolCallCorrelationAssigned` dispatch and `TraceReducer::assign_mcp_tool_call_correlation` source contract | `tests/test_rollout_trace_mcp_rs.py::test_mcp_correlation_replays_onto_tool_call` | complete_slice |
| `src/reducer/tool.rs` | MCP correlation unknown-tool and duplicate-correlation reducer guards | `tests/test_rollout_trace_mcp_rs.py::test_mcp_correlation_rejects_unknown_and_duplicate_tool_calls` | complete_slice |
| `src/payload.rs` | `RawPayloadKind` serde tagged enum and `RawPayloadRef` shape | `tests/test_rollout_trace_raw_event_writer_rs.py::test_raw_payload_kind_and_ref_match_payload_rs_serde_shape` | complete_slice |
| `src/raw_event.rs` | `RawTraceEventPayload` internally tagged serde shape and `RawToolCallRequester` shape | `tests/test_rollout_trace_raw_event_writer_rs.py::test_raw_trace_event_payload_is_internally_tagged_and_flattened` | complete_slice |
| `src/raw_event.rs` | `RawTraceEventPayload::raw_payload_refs` variant-specific reference extraction | `tests/test_rollout_trace_raw_event_writer_rs.py::test_raw_payload_refs_follow_raw_event_rs_variant_contract` | complete_slice |
| `src/writer.rs`, `src/reducer/mod.rs` | `TraceWriter::create`, `write_json_payload`, `append`, and replayed rollout status/thread/turn/inference/raw-payload registry contract from `writer_records_payload_refs_and_replays_rollout_status` | `tests/test_rollout_trace_raw_event_writer_rs.py::test_writer_records_manifest_payloads_and_event_sequence` | complete_slice |
| `src/bundle.rs`, `src/reducer/mod.rs` | bundle layout constants, public `REDUCED_STATE_FILE_NAME`, `TraceBundleManifest::new` standard layout, and fixed `RAW_EVENT_LOG_FILE_NAME` replay path | `tests/test_rollout_trace_raw_event_writer_rs.py::test_bundle_layout_constants_and_fixed_replay_log_name` | complete_slice |
| `src/reducer/mod.rs` | `TraceReducer::apply_event` raw-payload bookkeeping followed by explicit `RawTraceEventPayload::Other` no-reducer error | `tests/test_rollout_trace_raw_event_writer_rs.py::test_other_raw_event_replay_errors_like_reducer_mod_rs` | complete_slice |
| `src/payload.rs`, `src/raw_event.rs`, `src/writer.rs` | dependency-light facade smoke | `tests/test_external_crate_interfaces.py::test_rollout_trace_facade` | complete_slice |
| `src/thread.rs` | `create_in_root_writes_replayable_lifecycle_events` writer-side lifecycle contract before reducer replay | `tests/test_rollout_trace_thread_rs.py::test_create_in_root_writes_thread_lifecycle_events` | complete_slice |
| `src/thread.rs` | `spawned_thread_start_appends_to_root_bundle` writer-side child trace contract before reducer replay | `tests/test_rollout_trace_thread_rs.py::test_spawned_thread_start_appends_to_root_bundle` | complete_slice |
| `src/thread.rs` | `disabled_thread_context_accepts_trace_calls_without_writing` no-op and lazy-dispatch contract | `tests/test_rollout_trace_thread_rs.py::test_disabled_thread_context_accepts_trace_calls_without_writing_or_building_dispatch` | complete_slice |
| `src/thread.rs` | `record_codex_turn_started` source contract for envelope context and typed payload | `tests/test_rollout_trace_thread_rs.py::test_record_codex_turn_started_uses_thread_context` | complete_slice |
| `src/thread.rs`, `src/code_cell.rs`, `src/inference.rs`, `src/compaction.rs` | `ThreadTraceContext::{start_code_cell_trace,code_cell_trace_context,inference_trace_context,compaction_trace_context}` delegated context construction and disabled no-op source contracts | `tests/test_rollout_trace_thread_rs.py::test_delegated_trace_contexts_use_thread_and_turn_context`, `tests/test_rollout_trace_thread_rs.py::test_disabled_thread_context_accepts_trace_calls_without_writing_or_building_dispatch` | complete_slice |
| `src/reducer/mod.rs`, `src/reducer/thread.rs` | `replay_bundle`, `start_thread`, `end_thread`, `start_codex_turn`, `end_codex_turn` root lifecycle reduction from `create_in_root_writes_replayable_lifecycle_events` | `tests/test_rollout_trace_reducer_thread_rs.py::test_replay_bundle_reduces_root_thread_lifecycle` | complete_slice |
| `src/reducer/thread.rs` | child thread metadata precedence and child end does not end rollout from `spawned_thread_start_appends_to_root_bundle` | `tests/test_rollout_trace_reducer_thread_rs.py::test_replay_bundle_reduces_spawned_thread_without_ending_rollout` | complete_slice |
| `src/reducer/thread.rs` | duplicate thread start guard | `tests/test_rollout_trace_reducer_thread_rs.py::test_replay_bundle_rejects_duplicate_thread_start` | complete_slice |
| `src/reducer/thread.rs` | unknown and mismatched Codex turn end guards | `tests/test_rollout_trace_reducer_thread_rs.py::test_replay_bundle_rejects_unknown_and_mismatched_codex_turn_end` | complete_slice |
| `src/inference.rs` | `disabled_attempt_adds_no_request_headers` | `tests/test_rollout_trace_inference_rs.py::test_disabled_attempt_adds_no_request_headers` | complete_slice |
| `src/inference.rs`, `src/reducer/inference.rs` | `enabled_context_records_replayable_inference_attempt` request/response lifecycle contract | `tests/test_rollout_trace_inference_rs.py::test_enabled_attempt_records_replayable_inference_attempt` | complete_slice |
| `src/inference.rs` | `enabled_attempt_adds_inference_request_header` | `tests/test_rollout_trace_inference_rs.py::test_enabled_attempt_adds_inference_request_header` | complete_slice |
| `src/inference.rs` | `traced_response_item_preserves_reasoning_content_omitted_by_normal_serializer` | `tests/test_rollout_trace_inference_rs.py::test_traced_response_item_preserves_reasoning_content_omitted_by_normal_serializer` | complete_slice |
| `src/inference.rs` | `InferenceTraceAttempt::take_terminal_attempt` terminal event guard | `tests/test_rollout_trace_inference_rs.py::test_attempt_terminal_event_is_recorded_once` | complete_slice |
| `src/reducer/inference.rs` | `cancelled_inference_reduces_partial_response_items` | `tests/test_rollout_trace_inference_rs.py::test_cancelled_inference_reduces_partial_response_items` | complete_slice |
| `src/reducer/inference.rs` | `cancelled_turn_closes_running_inference_call` | `tests/test_rollout_trace_inference_rs.py::test_cancelled_turn_closes_running_inference_call` | complete_slice |
| `src/reducer/inference.rs` | `late_cancelled_inference_preserves_turn_end_status` | `tests/test_rollout_trace_inference_rs.py::test_late_cancelled_inference_preserves_turn_end_status_and_payload` | complete_slice |
| `src/compaction.rs` | disabled no-op compaction context contract from `disabled_thread_context_accepts_trace_calls_without_writing` | `tests/test_rollout_trace_compaction_rs.py::test_disabled_compaction_context_records_nothing` | complete_slice |
| `src/compaction.rs`, `src/reducer/compaction.rs` | `start_attempt`, `record_completed`, `start_compaction_request`, and `complete_compaction_request` request lifecycle | `tests/test_rollout_trace_compaction_rs.py::test_enabled_compaction_attempt_records_and_replays_request_lifecycle` | complete_slice |
| `src/compaction.rs`, `src/reducer/compaction.rs` | `record_failed` failed request lifecycle | `tests/test_rollout_trace_compaction_rs.py::test_compaction_failed_request_replays_failed_without_response_payload` | complete_slice |
| `src/compaction.rs`, `src/reducer/compaction.rs` | `record_installed` and request-id association for checkpoint install | `tests/test_rollout_trace_compaction_rs.py::test_compaction_installed_records_checkpoint_and_request_ids` | complete_slice |
| `src/reducer/compaction.rs` | completion unknown-request and compaction-id mismatch guards | `tests/test_rollout_trace_compaction_rs.py::test_compaction_reducer_rejects_unknown_request_and_mismatched_compaction` | complete_slice |
| `src/reducer/compaction.rs` | duplicate request-start guard | `tests/test_rollout_trace_compaction_rs.py::test_compaction_reducer_rejects_duplicate_request_start` | complete_slice |
| `src/reducer/compaction.rs` | duplicate install, unknown turn, and thread/turn mismatch guards | `tests/test_rollout_trace_compaction_rs.py::test_compaction_install_rejects_duplicate_unknown_turn_and_thread_mismatch` | complete_slice |
| `src/reducer/conversation.rs` | compaction checkpoint `input_history` and `replacement_history` array guards | `tests/test_rollout_trace_compaction_rs.py::test_compaction_install_rejects_malformed_checkpoint_payload` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `request_snapshots_reuse_history_without_deduping_new_identical_items` | `tests/test_rollout_trace_conversation_rs.py::test_request_snapshots_reuse_history_without_deduping_new_identical_items` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `response_outputs_enter_thread_conversation_on_completion` | `tests/test_rollout_trace_conversation_rs.py::test_response_outputs_enter_thread_conversation_on_completion` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `later_full_request_reuses_prior_json_tool_call_by_position` | `tests/test_rollout_trace_conversation_rs.py::test_later_full_request_reuses_prior_json_tool_call_by_position` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `incremental_request_carries_prior_request_and_response_items_forward` | `tests/test_rollout_trace_conversation_rs.py::test_incremental_request_carries_prior_request_and_response_items_forward` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `full_request_snapshot_can_reorder_existing_items_and_insert_summary` | `tests/test_rollout_trace_conversation_rs.py::test_full_request_snapshot_can_reorder_existing_items_and_insert_summary` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `reasoning_body_preserves_text_summary_and_encoded_content` | `tests/test_rollout_trace_conversation_rs.py::test_reasoning_body_preserves_text_summary_and_encoded_content` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `encrypted_reasoning_reuses_response_item_in_later_request` | `tests/test_rollout_trace_conversation_rs.py::test_encrypted_reasoning_reuses_response_item_in_later_request` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `encrypted_reasoning_upgrades_when_later_sighting_has_more_readable_body` | `tests/test_rollout_trace_conversation_rs.py::test_encrypted_reasoning_upgrades_when_later_sighting_has_more_readable_body` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `same_encrypted_reasoning_with_different_text_reuses_first_readable_body` | `tests/test_rollout_trace_conversation_rs.py::test_same_encrypted_reasoning_with_different_text_reuses_first_readable_body` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `compaction_boundary_repeats_prefix_and_reuses_replacement_items` | `tests/test_rollout_trace_conversation_rs.py::test_compaction_boundary_repeats_prefix_and_reuses_replacement_items` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `context_compaction_boundary_repeats_prefix_and_reuses_replacement_items` | `tests/test_rollout_trace_conversation_rs.py::test_context_compaction_boundary_repeats_prefix_and_reuses_replacement_items` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/tool.rs` | `tool_call_links_model_call_and_followup_output_items` | `tests/test_rollout_trace_conversation_rs.py::test_tool_call_links_model_call_and_followup_output_items` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `model_visible_call_id_reuse_with_different_content_is_reducer_error` | `tests/test_rollout_trace_conversation_rs.py::test_model_visible_call_id_reuse_with_different_content_is_reducer_error` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/conversation/normalize.rs` | `unsupported_model_item_is_reducer_error` | `tests/test_rollout_trace_conversation_rs.py::test_unsupported_model_item_is_reducer_error` | complete_slice |
| `src/reducer/conversation/normalize.rs` | `normalize_model_item` missing/non-string type source contract | `tests/test_rollout_trace_conversation_rs.py::test_normalize_rejects_model_items_without_string_type` | complete_slice |
| `src/reducer/conversation/normalize.rs` | `normalize_message_item` missing/non-string role source contract | `tests/test_rollout_trace_conversation_rs.py::test_normalize_rejects_messages_without_string_role` | complete_slice |
| `src/reducer/conversation/normalize.rs` | `role_from_str` accepted role enum source contract | `tests/test_rollout_trace_conversation_rs.py::test_normalize_rejects_unsupported_message_role` | complete_slice |
| `src/reducer/conversation/normalize.rs` | `normalize_reasoning_item` and `append_reasoning_parts` malformed reasoning guards | `tests/test_rollout_trace_conversation_rs.py::test_normalize_rejects_malformed_reasoning_parts` | complete_slice |
| `src/reducer/conversation.rs` | `missing_request_input_is_reducer_error` | `tests/test_rollout_trace_conversation_rs.py::test_missing_request_input_is_reducer_error` | complete_slice |
| `src/reducer/conversation.rs` | `unknown_previous_response_id_is_reducer_error` | `tests/test_rollout_trace_conversation_rs.py::test_unknown_previous_response_id_is_reducer_error` | complete_slice |
| `src/reducer/conversation.rs`, `src/reducer/inference.rs` | `inference_start_rejects_unknown_codex_turn` | `tests/test_rollout_trace_conversation_rs.py::test_inference_start_rejects_unknown_codex_turn` | complete_slice |
| `src/reducer/conversation/normalize.rs` | `custom_tool_call_body`, `custom_tool_call`, and `custom_tool_call_output` source contracts | `tests/test_rollout_trace_conversation_rs.py::test_custom_tool_call_variants_follow_normalize_rs_contract` | complete_slice |
| `src/reducer/conversation/normalize.rs` | hosted call/output source contracts for `tool_search_call`, `web_search_call`, `image_generation_call`, `local_shell_call`, `tool_search_output`, and `mcp_tool_call_output` | `tests/test_rollout_trace_conversation_rs.py::test_hosted_call_variants_use_json_backed_function_call_contract` | complete_slice |
| `src/model/conversation.rs` | `ProducerRef` internally tagged snake_case serde source contract | `tests/test_rollout_trace_model_rs.py::test_producer_ref_variants_follow_model_conversation_rs_serde_shape` | complete_slice |
| `src/model/session.rs`, `src/model/conversation.rs`, `src/model/runtime.rs` | plain model enum `rename_all = "snake_case"` serde source contracts for rollout/execution/conversation/code-cell/terminal statuses and kinds | `tests/test_rollout_trace_model_rs.py::test_plain_model_enums_follow_snake_case_serde_values` | complete_slice |
| `src/model/conversation.rs`, `src/model/runtime.rs`, `src/model/session.rs` | tagged model enum serde source contracts for `ConversationPart`, `AgentOrigin`, `TerminalRequest`, and `TraceAnchor` | `tests/test_rollout_trace_model_rs.py::test_tagged_model_variants_omit_unrelated_optional_fields` | complete_slice |
| `src/model/runtime.rs` | `ToolCallRequester`, `ToolCallKind`, and `ToolCallSummary` internally tagged snake_case serde source contracts | `tests/test_rollout_trace_model_rs.py::test_runtime_tool_model_variants_follow_model_runtime_rs_serde_shape` | complete_slice |
| `src/model/runtime.rs` | `TerminalRequest` and `ToolCallSummary` active-variant `Option` fields serialize as JSON `null` under Rust's derived serde, while unrelated variant fields remain omitted | `tests/test_rollout_trace_model_rs.py::test_runtime_tagged_option_fields_emit_null_for_active_variant`, `tests/test_rollout_trace_tool_dispatch_rs.py::test_enabled_dispatch_records_started_and_completed_payloads` | complete_slice |
| `src/model/runtime.rs` | `InteractionEdgeKind` snake_case serde source contract and reduced `InteractionEdge.kind` projection | `tests/test_rollout_trace_model_rs.py::test_interaction_edge_kind_follows_model_runtime_rs_serde_shape`, `tests/test_rollout_trace_agents_rs.py` | complete_slice |
| `src/model/runtime.rs` | `CodeCell`, `ToolCall`, `TerminalSession`, `TerminalOperation`, `TerminalResult`, `TerminalModelObservation`, and `InteractionEdge` public struct serde field contracts | `tests/test_rollout_trace_model_rs.py::test_runtime_model_structs_follow_model_runtime_rs_field_shape` | complete_slice |
| `src/model/session.rs`, `src/model/conversation.rs`, `src/model/runtime.rs` | `AgentThread`, `CodexTurn`, `ConversationItem`, `InferenceCall`, `TokenUsage`, `CompactionRequest`, and `Compaction` public struct serde field contracts | `tests/test_rollout_trace_model_rs.py::test_session_and_conversation_model_structs_follow_public_field_shape` | complete_slice |
| `src/model/mod.rs` | `RolloutTrace` public reduced graph serde fields omit reducer-private state | `tests/test_rollout_trace_model_rs.py::test_rollout_trace_projection_omits_python_reducer_internal_fields` | complete_slice |
| `src/reducer/code_cell.rs`, `src/reducer/tool.rs` | `code_cell_lifecycle_links_nested_tools_waits_and_outputs` | `tests/test_rollout_trace_code_cell_rs.py::test_code_cell_lifecycle_links_nested_tools_waits_and_outputs` | complete_slice |
| `src/reducer/code_cell.rs` | `fast_code_cell_lifecycle_waits_for_source_item` | `tests/test_rollout_trace_code_cell_rs.py::test_fast_code_cell_lifecycle_waits_for_source_item` | complete_slice |
| `src/reducer/code_cell.rs` | `cancelled_turn_terminates_unfinished_code_cell` | `tests/test_rollout_trace_code_cell_rs.py::test_cancelled_turn_terminates_unfinished_code_cell` | complete_slice |
| `src/reducer/code_cell.rs` | `runtime_code_cell_ids_can_repeat_across_threads` | `tests/test_rollout_trace_code_cell_rs.py::test_runtime_code_cell_ids_can_repeat_across_threads` | complete_slice |
| `src/reducer/tool/terminal.rs` | `exec_tool_reduces_to_terminal_operation_and_session` | `tests/test_rollout_trace_terminal_rs.py::test_exec_tool_reduces_to_terminal_operation_and_session` | complete_slice |
| `src/reducer/tool/terminal.rs` | `write_stdin_operation_reuses_existing_terminal_session` | `tests/test_rollout_trace_terminal_rs.py::test_write_stdin_operation_reuses_existing_terminal_session` | complete_slice |
| `src/reducer/tool/terminal.rs` | `dispatch_write_stdin_payload_reduces_to_terminal_operation` | `tests/test_rollout_trace_terminal_rs.py::test_dispatch_write_stdin_payload_reduces_to_terminal_operation` | complete_slice |
| `src/reducer/tool/terminal.rs` | `code_mode_write_stdin_result_projects_structured_exec_fields` | `tests/test_rollout_trace_terminal_rs.py::test_code_mode_write_stdin_result_projects_structured_exec_fields` | complete_slice |
| `src/reducer/tool/agents.rs` | `child_thread_metadata_creates_spawn_origin_without_delivery_edge` | `tests/test_rollout_trace_agents_rs.py::test_child_thread_metadata_creates_spawn_origin_without_delivery_edge` | complete_slice |
| `src/reducer/tool/agents.rs` | `spawn_runtime_payload_falls_back_to_child_thread_without_delivery_item` | `tests/test_rollout_trace_agents_rs.py::test_spawn_runtime_payload_falls_back_to_child_thread_without_delivery_item` | complete_slice |
| `src/reducer/tool/agents.rs` | `spawn_runtime_payload_targets_delivered_child_message` | `tests/test_rollout_trace_agents_rs.py::test_spawn_runtime_payload_targets_delivered_child_message` | complete_slice |
| `src/reducer/tool/agents.rs` | `send_message_runtime_payload_targets_delivered_child_message` | `tests/test_rollout_trace_agents_rs.py::test_send_message_runtime_payload_targets_delivered_child_message` | complete_slice |
| `src/reducer/tool/agents.rs` | `close_agent_runtime_payload_targets_thread` | `tests/test_rollout_trace_agents_rs.py::test_close_agent_runtime_payload_targets_thread` | complete_slice |
| `src/reducer/tool/agents.rs` | `agent_result_edge_links_child_result_to_parent_notification`, including Rust `latest_assistant_message_item_for_turn` tie-break behavior for same-millisecond assistant messages | `tests/test_rollout_trace_agents_rs.py::test_agent_result_edge_links_child_result_to_parent_notification` | complete_slice |
| `src/reducer/tool/agents.rs` | `agent_result_edge_falls_back_to_child_thread_without_result_message` | `tests/test_rollout_trace_agents_rs.py::test_agent_result_edge_falls_back_to_child_thread_without_result_message` | complete_slice |
| `src/tool_dispatch.rs` | `suppresses_only_noncanonical_dispatch_boundaries` | `tests/test_rollout_trace_tool_dispatch_rs.py::test_suppresses_only_noncanonical_dispatch_boundaries` | complete_slice |
| `src/tool_dispatch.rs` | `ToolDispatchTraceContext::start` and `record_completed` writer-side source contract | `tests/test_rollout_trace_tool_dispatch_rs.py::test_enabled_dispatch_records_started_and_completed_payloads` | complete_slice |
| `src/tool_dispatch.rs` | `ToolDispatchPayload::log_payload_preview` and `truncate_preview` 160-char boundary, ellipsis, and UTF-8 char-count source contract | `tests/test_rollout_trace_tool_dispatch_rs.py::test_dispatch_preview_truncates_by_rust_char_boundary` | complete_slice |
| `src/tool_dispatch.rs` | `dispatched_tool_kind` alias mapping and `dispatched_tool_label` namespace qualification source contracts | `tests/test_rollout_trace_tool_dispatch_rs.py::test_dispatch_kind_aliases_and_namespaced_labels_follow_tool_dispatch_rs` | complete_slice |
| `src/tool_dispatch.rs` | `ToolDispatchPayload::into_json_payload` raw `ToolInvocation.payload` shapes for `Function`, `ToolSearch`, `Custom`, and `LocalShell` variants | `tests/test_rollout_trace_tool_dispatch_rs.py::test_dispatch_payload_json_variants_follow_tool_dispatch_rs` | complete_slice |
| `src/tool_dispatch.rs` | `requester_fields` and `record_failed` source contracts | `tests/test_rollout_trace_tool_dispatch_rs.py::test_enabled_dispatch_records_code_cell_requester_and_failed_result` | complete_slice |
| `src/protocol_event.rs`, `src/thread.rs` | `protocol_wrapper_records_selected_events_as_raw_payloads` | `tests/test_rollout_trace_protocol_event_rs.py::test_protocol_wrapper_records_selected_events_as_raw_payloads` | complete_slice |
| `src/protocol_event.rs` | `codex_turn_trace_event` source contract for started/completed/aborted turn lifecycle | `tests/test_rollout_trace_protocol_event_rs.py::test_record_codex_turn_event_maps_lifecycle_status_and_context` | complete_slice |
| `src/protocol_event.rs` | `tool_runtime_trace_event` source contract for exec runtime events and `UserShell` filtering | `tests/test_rollout_trace_protocol_event_rs.py::test_record_tool_call_event_maps_exec_runtime_and_filters_user_shell` | complete_slice |
| `src/protocol_event.rs` | `TraceExecutionStatus` and MCP/collab status source contracts | `tests/test_rollout_trace_protocol_event_rs.py::test_record_tool_call_event_maps_patch_mcp_and_collab_status` | complete_slice |

## Validation

2026-06-22:

- `python -m pytest tests\test_rollout_trace_raw_event_writer_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `90 passed`
- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `9 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `91 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_tool_dispatch_rs.py`
  - passed
- `python -m pytest tests\test_rollout_trace_raw_event_writer_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `92 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_raw_event_writer_rs.py`
  - passed
- `python -m pytest tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `93 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_tool_dispatch_rs.py`
  - passed
- `python -m pytest tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `94 passed`
- `python -m pytest tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `95 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_raw_event_writer_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `89 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_conversation_rs.py -q --tb=short`
  - `23 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `88 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_thread_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_raw_event_writer_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `79 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_raw_event_writer_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `84 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `11 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `77 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_agents_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `76 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_terminal_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `2 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `75 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `1 passed`
- `python -m pytest tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `74 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_model_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_conversation_rs.py -q --tb=short`
  - `19 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `73 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_conversation_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_inference_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `72 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_inference_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_inference_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `71 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_inference_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_mcp_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_mcp_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `2 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `64 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_agents_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py -q --tb=short`
  - `69 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_agents_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_raw_event_writer_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_raw_event_writer_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_thread_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py -q --tb=short`
  - `11 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_thread_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_reducer_thread_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_reducer_thread_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_inference_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py -q --tb=short`
  - `20 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_inference_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_compaction_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py -q --tb=short`
  - `25 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_compaction_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_code_cell_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_conversation_rs.py -q --tb=short`
  - `18 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py -q --tb=short`
  - `47 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_conversation_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_terminal_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py -q --tb=short`
  - `51 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_terminal_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `54 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_tool_dispatch_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_protocol_event_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py -q --tb=short`
  - `58 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_protocol_event_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_mcp_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py -q --tb=short`
  - `62 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_mcp_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_tool_dispatch_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `96 passed`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_tool_dispatch_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_code_cell_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `97 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_code_cell_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_code_cell_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `98 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_code_cell_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_rollout_trace_protocol_event_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py -q --tb=short`
  - `99 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_protocol_event_rs.py`
  - passed

2026-06-22:

- Rust source: `codex-rollout-trace/src/lib.rs` crate-root `pub use` facade and `src/model/mod.rs` public model reexports.
- Python test: `tests/test_rollout_trace_lib_rs.py::test_crate_root_reexports_follow_lib_rs_public_surface`
  - Contract: `pycodex.rollout_trace.__all__` explicitly covers the Rust crate-root public surface while private reducer implementation helpers remain unexported.
- `python -m pytest tests\test_rollout_trace_lib_rs.py -q --tb=short`
  - `1 passed`
- `python -m pytest tests\test_rollout_trace_mcp_rs.py tests\test_rollout_trace_raw_event_writer_rs.py tests\test_rollout_trace_thread_rs.py tests\test_rollout_trace_reducer_thread_rs.py tests\test_rollout_trace_inference_rs.py tests\test_rollout_trace_compaction_rs.py tests\test_rollout_trace_conversation_rs.py tests\test_rollout_trace_code_cell_rs.py tests\test_rollout_trace_terminal_rs.py tests\test_rollout_trace_tool_dispatch_rs.py tests\test_rollout_trace_protocol_event_rs.py tests\test_rollout_trace_agents_rs.py tests\test_rollout_trace_model_rs.py tests\test_rollout_trace_lib_rs.py -q --tb=short`
  - `100 passed`
- `python -m pytest tests\test_external_crate_interfaces.py -k rollout_trace -q --tb=short`
  - `1 passed, 17 deselected`
- `python -m py_compile pycodex\rollout_trace\__init__.py tests\test_rollout_trace_lib_rs.py`
  - passed
