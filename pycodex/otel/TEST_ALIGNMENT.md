# codex-otel Test Alignment

Rust crate: `codex-otel`
Python package: `pycodex.otel`

## Status

`complete`

The `src/config.rs` exporter-resolution/default-Statsig slice,
`src/provider.rs` resource/filter helper slice, `src/targets.rs` target
classification slice, `src/otlp.rs` header/timeout helper slice,
`src/metrics/names.rs`, `src/metrics/tags.rs`,
`src/metrics/validation.rs`, `src/metrics/config.rs`, `src/metrics/client.rs`,
`src/metrics/runtime_metrics.rs`, `src/metrics/timer.rs`, and
`src/metrics/process.rs` stable pure/helper contracts are covered. The
`src/trace_context.rs` traceparent and configured-tracestate pure/helper
contracts are also covered, along with the `src/provider.rs` dependency-light
provider setup decision/validation/global-install slice and the `src/events/session_telemetry.rs`
metrics-forwarding slice and the selected user-prompt/tool-result/auth-recovery/API/websocket
log-vs-trace routing slice. The Rust OTLP HTTP metrics/log/trace loopback paths are covered by
real local HTTP POST tests. Native OpenTelemetry SDK provider/exporter identity, Tokio runtime
identity, OTLP gRPC transport, rustls/TLS client setup, and native span/current-span object identity
are documented as non-blocking implementation differences for the dependency-light Python projection.

## Rust-Derived Tests

| Rust source/test | Rust behavior | Python test | Status |
|---|---|---|---|
| `src/config.rs::tests::statsig_default_metrics_exporter_is_disabled_in_debug_builds` | `resolve_exporter(OtelExporter::Statsig)` resolves to `None` in debug/test builds. | `tests/test_otel_metrics_rs.py::test_statsig_default_metrics_exporter_is_disabled_in_debug_builds` | complete_slice |
| `src/config.rs::resolve_exporter`, `STATSIG_*` constants | Non-Statsig exporters are cloned unchanged and Statsig constants keep Rust defaults. | `tests/test_otel_metrics_rs.py::test_resolve_exporter_preserves_explicit_exporters_and_statsig_constants` | complete_slice |
| `src/provider.rs::tests::resource_attributes_include_host_name_when_present` | Log resources include `host.name` when a non-empty host name is available. | `tests/test_otel_metrics_rs.py::test_resource_attributes_include_host_name_when_present` | complete_slice |
| `src/provider.rs::tests::resource_attributes_omit_host_name_when_missing_or_empty` | Missing/blank host names and trace resources omit `host.name`. | `tests/test_otel_metrics_rs.py::test_resource_attributes_omit_host_name_when_missing_empty_or_trace_resource` | complete_slice |
| `src/provider.rs::tests::log_export_target_excludes_trace_safe_events`, `src/targets.rs` | Log export targets include `codex_otel*` targets except `codex_otel.trace_safe*`. | `tests/test_otel_metrics_rs.py::test_log_export_target_excludes_trace_safe_events` | complete_slice |
| `src/provider.rs::tests::trace_export_target_only_includes_trace_safe_prefix`, `src/targets.rs` | Trace-safe target detection only accepts the `codex_otel.trace_safe` prefix. | `tests/test_otel_metrics_rs.py::test_trace_export_target_only_includes_trace_safe_prefix` | complete_slice |
| `src/provider.rs::OtelProvider::{codex_export_filter,log_export_filter,trace_export_filter}` | Provider filters route log targets through log policy and trace targets through span/trace-safe policy. | `tests/test_otel_metrics_rs.py::test_provider_export_filters_project_rust_target_policy` | complete_slice |
| `src/provider.rs::OtelProvider::from` | Disabled log/trace/resolved-metrics exporters clear process-global tracestate and return no provider before validating configured tracestate. | `tests/test_otel_metrics_rs.py::test_otel_provider_disabled_exporters_clear_tracestate_without_validating_it` | complete_slice |
| `src/provider.rs::OtelProvider::from` | Trace-enabled setup validates span attributes before installing tracestate or global provider state. | `tests/test_otel_metrics_rs.py::test_otel_provider_trace_path_validates_span_attributes_before_installing_state` | complete_slice |
| `tests/suite/otlp_http_loopback.rs::otel_provider_rejects_header_unsafe_configured_tracestate`, `src/provider.rs::OtelProvider::from` | Header-unsafe configured tracestate is rejected before global tracestate install. | `tests/test_otel_metrics_rs.py::test_otel_provider_rejects_header_unsafe_configured_tracestate_before_installing` | complete_slice |
| `src/provider.rs::OtelProvider::from` | Enabled metrics exporters build a `MetricsConfig::otlp` client, preserve runtime-reader config, install global metrics, and install validated tracestate. | `tests/test_otel_metrics_rs.py::test_otel_provider_metrics_exporter_installs_global_metrics_client` | complete_slice |
| `src/provider.rs::{OtelProvider::from,OtelProvider::shutdown,build_logger}` | An enabled OTLP HTTP JSON log exporter builds a logger provider from settings and flushes log records to the configured collector endpoint with configured headers during shutdown. | `tests/test_otel_metrics_rs.py::test_otlp_http_log_exporter_sends_logs_to_collector` | complete_slice |
| `src/otlp.rs::build_header_map` | Invalid header names/values are skipped while valid headers are inserted. | `tests/test_otel_metrics_rs.py::test_otlp_build_header_map_skips_invalid_names_and_values` | complete_slice |
| `src/otlp.rs::{resolve_otlp_timeout,read_timeout_env}` | Signal timeout env wins over global timeout env, then falls back to Rust's 10s default. | `tests/test_otel_metrics_rs.py::test_otlp_resolve_timeout_prefers_signal_then_global_then_default` | complete_slice |
| `src/otlp.rs::read_timeout_env` | Negative and unparseable timeout env values are ignored. | `tests/test_otel_metrics_rs.py::test_otlp_timeout_ignores_negative_and_unparseable_env_values` | complete_slice |
| `src/metrics/names.rs` | Public metric constants keep Rust's stable dotted metric names. | `tests/test_otel_metrics_rs.py::test_metric_name_constants_match_rust_names_rs` | complete_slice |
| `src/metrics/tags.rs::session_metric_tags_include_expected_tags_in_order` | `SessionMetricTagValues.into_tags` emits auth/session/originator/service/model/app-version tags in Rust order. | `tests/test_otel_metrics_rs.py::test_session_metric_tags_include_expected_tags_in_order` | complete_slice |
| `src/metrics/tags.rs::session_metric_tags_skip_missing_optional_tags` | Missing optional auth/service tags are skipped without changing required tag order. | `tests/test_otel_metrics_rs.py::test_session_metric_tags_skip_missing_optional_tags` | complete_slice |
| `src/metrics/tags.rs::bounded_originator_tag_value` | Known low-cardinality sanitized originators pass through; unknown originators map to `other`. | `tests/test_otel_metrics_rs.py::test_bounded_originator_tag_value_matches_known_low_cardinality_values` | complete_slice |
| `src/metrics/validation.rs`, `tests/suite/validation.rs` | Invalid metric names, tag keys, and tag values are rejected with Rust-shaped error fields. | `tests/test_otel_metrics_rs.py::test_metrics_validation_rejects_invalid_names_and_tags` | complete_slice |
| `src/metrics/validation.rs` | Metric names allow ASCII alnum plus `.`, `_`, `-`; tag components additionally allow `/`. | `tests/test_otel_metrics_rs.py::test_metrics_validation_allows_rust_character_sets` | complete_slice |
| `src/metrics/config.rs::MetricsConfig::{otlp,in_memory,with_export_interval,with_runtime_reader,with_tag}` | Config builders set Rust defaults, return updated configs by value, and validate default tags. | `tests/test_otel_metrics_rs.py::test_metrics_config_builders_match_rust_defaults_and_by_value_updates`, `tests/test_otel_metrics_rs.py::test_metrics_config_with_tag_rejects_invalid_components_from_rust_validation_suite` | complete_slice |
| `src/metrics/client.rs::MetricsClient::new`, `tests/suite/snapshot.rs`, `tests/suite/validation.rs::histogram_rejects_invalid_tag_value` | Metrics client consumes config default tags, keeps runtime-reader config state, and validates per-metric histogram tags. | `tests/test_otel_metrics_rs.py::test_metrics_client_new_uses_config_default_tags_and_histogram_validation` | complete_slice |
| `src/metrics/client.rs::MetricsClientInner::attributes`, `tests/suite/send.rs::send_builds_payload_with_tags_and_histograms` | Default and per-call tags merge through sorted map semantics; per-call tags override matching defaults. | `tests/test_otel_metrics_rs.py::test_metrics_client_merges_default_and_per_call_tags_like_send_suite` | complete_slice |
| `tests/suite/send.rs::send_merges_default_tags_per_line` | Per-call tag overrides apply to one record without mutating default tags used by later records. | `tests/test_otel_metrics_rs.py::test_metrics_client_merges_default_tags_per_record_without_mutating_defaults` | complete_slice |
| `tests/suite/send.rs::client_sends_enqueued_metric` | A counter enqueued before shutdown is present in the exported metric set with the expected value and attributes. | `tests/test_otel_metrics_rs.py::test_metrics_client_sends_enqueued_metric_like_send_suite` | complete_slice |
| `src/metrics/client.rs::MetricsClient::snapshot`, `tests/suite/snapshot.rs::snapshot_collects_metrics_without_shutdown` | Snapshot requires a runtime reader and collects current metric records without shutdown. | `tests/test_otel_metrics_rs.py::test_metrics_client_snapshot_requires_runtime_reader_and_collects_without_shutdown` | complete_slice |
| `src/metrics/client.rs::MetricsClient::shutdown`, `tests/suite/send.rs::{shutdown_flushes_in_memory_exporter,shutdown_without_metrics_exports_nothing}` | Shutdown succeeds when no metrics were recorded and does not create synthetic records. | `tests/test_otel_metrics_rs.py::test_metrics_client_shutdown_is_idempotent_and_exports_nothing_without_metrics` | complete_slice |
| `tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_metrics_to_collector`, `src/metrics/client.rs::build_otlp_metric_exporter` | OTLP HTTP JSON metrics shutdown sends a real POST to `/v1/metrics` with `application/json` content and a body containing the metric name. | `tests/test_otel_metrics_rs.py::test_otlp_http_exporter_sends_metrics_to_collector` | complete_slice |
| `src/metrics/runtime_metrics.rs::RuntimeMetricTotals` | `is_empty` checks count and duration; `merge` uses saturating addition. | `tests/test_otel_metrics_rs.py::test_runtime_metric_totals_merge_saturates_and_empty_matches_rust` | complete_slice |
| `src/metrics/runtime_metrics.rs::RuntimeMetricsSummary::{merge,responses_api_summary}` | Totals merge with saturation, non-zero scalar timings overwrite, and response summaries project only response API timing fields. | `tests/test_otel_metrics_rs.py::test_runtime_metrics_summary_merge_and_responses_api_summary_matches_rust` | complete_slice |
| `tests/suite/runtime_summary.rs::runtime_metrics_summary_collects_tool_api_and_streaming_metrics` | Runtime snapshots aggregate tool/API/SSE/websocket counters and durations plus response/turn timing fields. | `tests/test_otel_metrics_rs.py::test_runtime_metrics_summary_from_snapshot_collects_runtime_metrics` | complete_slice |
| `src/metrics/runtime_metrics.rs::f64_to_u64` | Non-finite/non-positive values become `0`, positive finite values round, and overflow clamps to `u64::MAX`. | `tests/test_otel_metrics_rs.py::test_runtime_metrics_summary_from_snapshot_matches_rust_f64_to_u64_edges` | complete_slice |
| `src/metrics/timer.rs::Timer::record`, `tests/suite/timing.rs::timer_result_records_success` | Timer records elapsed duration through the client and prepends additional tags before base tags. | `tests/test_otel_metrics_rs.py::test_timer_record_adds_additional_tags_before_base_tags` | complete_slice |
| `src/metrics/client.rs::{record_duration,start_timer}`, `tests/suite/timing.rs::record_duration_records_histogram` | Metrics client records duration samples in milliseconds and `start_timer` returns a timer bound to the client. | `tests/test_otel_metrics_rs.py::test_metrics_client_start_timer_and_record_duration_match_timing_contract` | complete_slice |
| `src/metrics/process.rs::record_process_start_once` | Process-start metric records at most once per process and bounds the originator tag. | `tests/test_otel_metrics_rs.py::test_record_process_start_once_records_bounded_originator_once` | complete_slice |
| `src/trace_context.rs::{context_from_w3c_trace_context,context_from_trace_headers}` unit tests | Valid W3C traceparent values are accepted; invalid, missing, or zero trace/span IDs are rejected. | `tests/test_otel_metrics_rs.py::test_trace_context_parses_valid_and_rejects_invalid_traceparent` | complete_slice |
| `src/trace_context.rs::{validate_tracestate_entries,validate_tracestate_member}`, `tests/suite/otlp_http_loopback.rs::otel_provider_rejects_header_unsafe_configured_tracestate` | Configured tracestate rejects header-unsafe member values, invalid field keys/values, and malformed member keys. | `tests/test_otel_metrics_rs.py::test_tracestate_validation_rejects_header_unsafe_configured_values` | complete_slice |
| `src/trace_context.rs::merge_tracestate_entries`, `tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_traces_to_collector` | Configured tracestate fields upsert selected semicolon fields, preserve unrelated fields, and place configured members at the front. | `tests/test_otel_metrics_rs.py::test_merge_tracestate_entries_upserts_configured_fields_like_rust` | complete_slice |
| `tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_traces_to_collector`, `src/provider.rs::{OtelProvider::from,tracing_layer}`, `src/trace_context.rs::{set_parent_from_w3c_trace_context,current_span_w3c_trace_context}` | OTLP HTTP JSON traces shutdown sends a real POST to `/v1/traces`, current-span tracestate merges configured fields, and exported body includes span name, service name, and configured span attributes. | `tests/test_otel_metrics_rs.py::test_otlp_http_exporter_sends_traces_to_collector` | complete_slice |
| `src/trace_context.rs::merge_tracestate_entries` | Invalid existing tracestate is ignored during propagation, while invalid configured entries are rejected. | `tests/test_otel_metrics_rs.py::test_merge_tracestate_entries_validates_existing_and_configured_state` | complete_slice |
| `src/events/session_telemetry.rs::{new,with_metrics,counter,tags_with_metadata}`, `tests/suite/manager_metrics.rs::manager_attaches_metadata_tags_to_metrics` | Session telemetry forwards metrics with metadata tags and per-call tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_attaches_metadata_tags_to_metrics` | complete_slice |
| `src/events/session_telemetry.rs::{with_metrics_without_metadata_tags,with_metrics_service_name}`, `tests/suite/manager_metrics.rs::{manager_allows_disabling_metadata_tags,manager_attaches_optional_service_name_tag}` | Metadata tags can be disabled, and optional service names are sanitized before becoming tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_can_disable_metadata_tags_and_add_service_name` | complete_slice |
| `src/events/session_telemetry.rs::{record_plugin_install_suggestion,record_plugin_install_elicitation_sent}`, `tests/suite/manager_metrics.rs` plugin install tests | Plugin install suggestion/elicitation metrics record the Rust metric names and low-cardinality tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_records_plugin_install_metrics_without_metadata_tags` | complete_slice |
| `src/events/session_telemetry.rs::{snapshot_metrics,runtime_metrics_summary}`, `tests/suite/snapshot.rs::manager_snapshot_metrics_collects_without_shutdown`, `tests/suite/runtime_summary.rs` | Session telemetry forwards snapshots without shutdown and projects runtime metrics summaries. | `tests/test_otel_metrics_rs.py::test_session_telemetry_snapshot_and_runtime_summary_forward_to_metrics` | complete_slice |
| `src/events/session_telemetry.rs::record_startup_phase` | Startup phase recording emits one duration metric and matching log/trace events with phase, status, and duration fields. | `tests/test_otel_metrics_rs.py::test_session_telemetry_records_startup_phase_metric_log_and_trace` | complete_slice |
| `src/events/session_telemetry.rs::{tool_result_with_tags,record_api_request,record_websocket_request,log_sse_event,record_websocket_event,record_responses_websocket_timing_metrics}`, `tests/suite/runtime_summary.rs` | Tool/API/SSE/websocket helpers emit the metric names and durations consumed by runtime summaries, including responses websocket timing fields. | `tests/test_otel_metrics_rs.py::test_session_telemetry_runtime_summary_records_tool_api_streaming_and_websocket_metrics` | complete_slice |
| `src/events/session_telemetry.rs::{record_api_request,sse_event_failed,record_websocket_request,record_websocket_event}` | Failure paths use Rust fallback status/kind tags and `success=false`. | `tests/test_otel_metrics_rs.py::test_session_telemetry_api_sse_and_websocket_failure_tags_match_rust` | complete_slice |
| `src/events/session_telemetry.rs::{record_responses,responses_type,responses_item_type}` | Responses stream events update the active responses span with Rust `otel.name`, source, function-call tool name, and completed token-usage fields. | `tests/test_otel_metrics_rs.py::test_record_responses_type_projection_matches_rust_source_contract`, `tests/test_otel_metrics_rs.py::test_record_responses_records_function_call_and_completed_token_usage_like_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_user_prompt_log_and_trace_events`, `src/events/session_telemetry.rs::user_prompt` | Prompt text and user identifiers route only to log events; trace events keep prompt length and input counts. | `tests/test_otel_metrics_rs.py::test_routing_policy_user_prompt_log_and_trace_shapes_match_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_tool_result_log_and_trace_events`, `src/events/session_telemetry.rs::tool_result_with_tags` | Tool arguments/output/MCP identity route only to log events; trace events keep lengths, line count, and origin summary. | `tests/test_otel_metrics_rs.py::test_routing_policy_tool_result_log_and_trace_shapes_match_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_auth_recovery_log_and_trace_events`, `src/events/session_telemetry.rs::record_auth_recovery` | Auth recovery routing emits the same auth fields to log and trace events. | `tests/test_otel_metrics_rs.py::test_routing_policy_auth_recovery_log_and_trace_shapes_match_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_api_request_auth_observability`, `src/events/session_telemetry.rs::{conversation_starts,record_api_request}` | API request observability routes auth/header/recovery/env fields to log and trace events with Rust field names. | `tests/test_otel_metrics_rs.py::test_routing_policy_api_request_auth_observability_matches_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_websocket_connect_auth_observability`, `src/events/session_telemetry.rs::record_websocket_connect` | Websocket connect observability routes auth/header/recovery/env/connection fields to log and trace events. | `tests/test_otel_metrics_rs.py::test_routing_policy_websocket_connect_auth_observability_matches_rust` | complete_slice |
| `tests/suite/otel_export_routing_policy.rs::otel_export_routing_policy_routes_websocket_request_transport_observability`, `src/events/session_telemetry.rs::record_websocket_request` | Websocket request observability routes transport error, success, env, and connection-reuse fields to log and trace events. | `tests/test_otel_metrics_rs.py::test_routing_policy_websocket_request_transport_observability_matches_rust` | complete_slice |

## Validation

2026-06-22:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `89 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `10 passed`
- `python -m pytest tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `99 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `100 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `13 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `103 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `106 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `20 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `110 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `24 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `114 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `28 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `118 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed
- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `30 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `120 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `32 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `122 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 provider/targets follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `37 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `127 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 OTLP helper follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `40 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `130 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 routing-policy follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `43 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `133 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 API/websocket routing-policy follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `46 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `136 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 provider setup follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `50 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `140 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 OTLP HTTP metrics loopback follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `51 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `141 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 OTLP HTTP trace loopback follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `52 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `142 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 OTLP HTTP log loopback follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `53 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `143 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 Responses stream span-recording follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `55 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_core_runtime_dependency_packages_have_python_interfaces_and_readmes tests\test_otel_metrics_rs.py tests\test_core_guardian_metrics.py tests\test_core_rollout.py -q --tb=short`
  - `145 passed`
- `python -m py_compile pycodex\otel\__init__.py tests\test_otel_metrics_rs.py`
  - passed

2026-06-23 metrics client enqueued send follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `56 passed`

2026-06-23 startup-phase telemetry follow-up:

- `python -m pytest tests\test_otel_metrics_rs.py -q --tb=short`
  - `57 passed`

## Native Runtime Differences

- `src/provider.rs`, `src/otlp.rs`: Rust's native OpenTelemetry provider/exporter startup, OTLP gRPC exporter setup, rustls/TLS client setup, and Tokio runtime detection are not embedded in Python. Dependency-light provider setup decisions plus real local OTLP HTTP JSON metrics/log/trace loopback contracts are covered.
- `src/metrics/client.rs`: Rust's native OpenTelemetry aggregation/exporter pipeline identity is not embedded in Python. The Python projection covers validation, tag merge semantics, snapshot/shutdown behavior, in-memory export projection, and local OTLP HTTP JSON metrics transport.
- `src/events/session_telemetry.rs`, `src/events/shared.rs`: selected Rust log/span routing contracts that affect common PyCodex behavior are covered for user-prompt, tool-result, auth recovery, API, websocket, Responses stream span recording, startup phase, metrics forwarding, snapshots, and runtime summary.
- `src/trace_context.rs`: Rust's native OpenTelemetry span/current-span object identity is not embedded in Python. The dependency-light span facade covers W3C propagation, parent setting, configured tracestate merge, and local trace loopback behavior.
