# codex-otel Test Alignment

Rust crate: `codex-otel`
Python package: `pycodex.otel`

## Status

`module_progress`

The `src/metrics/names.rs`, `src/metrics/tags.rs`,
`src/metrics/validation.rs`, `src/metrics/config.rs`, `src/metrics/client.rs`,
`src/metrics/runtime_metrics.rs`, `src/metrics/timer.rs`, and
`src/metrics/process.rs` stable pure/helper contracts are covered. The
`src/trace_context.rs` traceparent and configured-tracestate pure/helper
contracts are also covered, along with the `src/events/session_telemetry.rs`
metrics-forwarding slice. Provider, OTLP exporter, session telemetry log/span
routing, native metrics exporter pipeline wiring, and live span/current-span
integration remain open.

## Rust-Derived Tests

| Rust source/test | Rust behavior | Python test | Status |
|---|---|---|---|
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
| `src/metrics/client.rs::MetricsClient::snapshot`, `tests/suite/snapshot.rs::snapshot_collects_metrics_without_shutdown` | Snapshot requires a runtime reader and collects current metric records without shutdown. | `tests/test_otel_metrics_rs.py::test_metrics_client_snapshot_requires_runtime_reader_and_collects_without_shutdown` | complete_slice |
| `src/metrics/client.rs::MetricsClient::shutdown`, `tests/suite/send.rs::{shutdown_flushes_in_memory_exporter,shutdown_without_metrics_exports_nothing}` | Shutdown succeeds when no metrics were recorded and does not create synthetic records. | `tests/test_otel_metrics_rs.py::test_metrics_client_shutdown_is_idempotent_and_exports_nothing_without_metrics` | complete_slice |
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
| `src/trace_context.rs::merge_tracestate_entries` | Invalid existing tracestate is ignored during propagation, while invalid configured entries are rejected. | `tests/test_otel_metrics_rs.py::test_merge_tracestate_entries_validates_existing_and_configured_state` | complete_slice |
| `src/events/session_telemetry.rs::{new,with_metrics,counter,tags_with_metadata}`, `tests/suite/manager_metrics.rs::manager_attaches_metadata_tags_to_metrics` | Session telemetry forwards metrics with metadata tags and per-call tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_attaches_metadata_tags_to_metrics` | complete_slice |
| `src/events/session_telemetry.rs::{with_metrics_without_metadata_tags,with_metrics_service_name}`, `tests/suite/manager_metrics.rs::{manager_allows_disabling_metadata_tags,manager_attaches_optional_service_name_tag}` | Metadata tags can be disabled, and optional service names are sanitized before becoming tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_can_disable_metadata_tags_and_add_service_name` | complete_slice |
| `src/events/session_telemetry.rs::{record_plugin_install_suggestion,record_plugin_install_elicitation_sent}`, `tests/suite/manager_metrics.rs` plugin install tests | Plugin install suggestion/elicitation metrics record the Rust metric names and low-cardinality tags. | `tests/test_otel_metrics_rs.py::test_session_telemetry_records_plugin_install_metrics_without_metadata_tags` | complete_slice |
| `src/events/session_telemetry.rs::{snapshot_metrics,runtime_metrics_summary}`, `tests/suite/snapshot.rs::manager_snapshot_metrics_collects_without_shutdown`, `tests/suite/runtime_summary.rs` | Session telemetry forwards snapshots without shutdown and projects runtime metrics summaries. | `tests/test_otel_metrics_rs.py::test_session_telemetry_snapshot_and_runtime_summary_forward_to_metrics` | complete_slice |
| `src/events/session_telemetry.rs::{tool_result_with_tags,record_api_request,record_websocket_request,log_sse_event,record_websocket_event,record_responses_websocket_timing_metrics}`, `tests/suite/runtime_summary.rs` | Tool/API/SSE/websocket helpers emit the metric names and durations consumed by runtime summaries, including responses websocket timing fields. | `tests/test_otel_metrics_rs.py::test_session_telemetry_runtime_summary_records_tool_api_streaming_and_websocket_metrics` | complete_slice |
| `src/events/session_telemetry.rs::{record_api_request,sse_event_failed,record_websocket_request,record_websocket_event}` | Failure paths use Rust fallback status/kind tags and `success=false`. | `tests/test_otel_metrics_rs.py::test_session_telemetry_api_sse_and_websocket_failure_tags_match_rust` | complete_slice |

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

## Remaining Gaps

- `src/provider.rs`, `src/otlp.rs`: OpenTelemetry provider startup, OTLP HTTP/gRPC exporter setup, TLS client setup, runtime detection, and live transport behavior.
- `src/metrics/client.rs`: native OpenTelemetry aggregation/exporter pipelines and OTLP exporter construction.
- `src/events/session_telemetry.rs`, `src/events/shared.rs`, integration suite routing tests: session telemetry log/span event routing and exported log/span shapes.
- `src/trace_context.rs`: live OpenTelemetry span parent/current-span integration.
