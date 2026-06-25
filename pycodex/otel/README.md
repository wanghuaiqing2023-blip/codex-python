# pycodex.otel

Rust crate: `codex-otel`

Rust anchor: `codex/codex-rs/otel`

This package mirrors selected public crate interfaces exported from
`otel/src/lib.rs`.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/lib.rs` | `pycodex.otel` | complete | Public re-export facade covers the dependency-light Python projection for config, trace-context, timer, metrics names/tags/client/runtime summary, provider setup, OTLP HTTP JSON transport, and session telemetry helper/event slices. |
| `src/config.rs` | `OtelExporter`, `OtelSettings`, `OtelTlsConfig`, `resolve_exporter`, `validate_span_attributes` | complete_slice | Dataclass/config shape, empty span-attribute-key validation, debug-build Statsig disablement, non-Statsig exporter cloning, and stable Statsig defaults are covered by Rust-derived/source-contract tests. |
| `src/trace_context.rs` | `W3cTraceContext`, traceparent/tracestate helpers | complete_slice | Traceparent validation, trace context extraction shape, configured tracestate validation, tracestate field upsert/merge, and dependency-light current-span parent propagation are covered by Rust-derived tests. |
| `src/metrics/names.rs` | metric constants | complete_slice | Stable Rust metric names are covered by Rust-derived tests. |
| `src/metrics/tags.rs` | tag constants, `SessionMetricTagValues`, `bounded_originator_tag_value` | complete_slice | Tag order, optional tag skipping, and known-originator bounding are covered by Rust-derived tests. |
| `src/metrics/validation.rs` | validation helpers and `MetricsError` variants | complete_slice | Metric/tag character sets and invalid component/name error fields are covered by Rust-derived tests. |
| `src/metrics/config.rs` | `MetricsConfig`, `MetricsExporter`, `MetricsClient.new` config projection | complete_slice | Config builder defaults, by-value update semantics, default tags, runtime-reader/export-interval flags, and tag validation are covered by Rust-derived tests. |
| `src/metrics/client.rs` | `MetricsClient` dependency-light record/snapshot/shutdown/export projection | complete_slice | Counter/histogram/duration validation, default/per-call tag merge and override, enqueued counter flush/snapshot projection, runtime snapshot gate/collection, shutdown empty-record behavior, and real local OTLP HTTP JSON metrics POST are covered by Rust-derived tests. |
| `src/metrics/runtime_metrics.rs` | `RuntimeMetricTotals`, `RuntimeMetricsSummary`, snapshot aggregation helpers | complete_slice | Empty checks, saturating merges, responses-only summary projection, snapshot counter/histogram aggregation, and Rust `f64_to_u64` clamping/rounding are covered by Rust-derived tests. |
| `src/metrics/timer.rs` | `Timer`, `MetricsClient.start_timer`, `MetricsClient.record_duration` | complete_slice | Timer duration recording, additional-tag ordering, and millisecond duration capture are covered by Rust-derived tests. |
| `src/metrics/process.rs` | `record_process_start_once` | complete_slice | Process-start counter recording, once-only behavior, and bounded originator tags are covered by Rust-derived tests. |
| `src/provider.rs` | `OtelProvider`, `resource_attributes`, export target filters | complete_slice | Resource service/env/host attributes, log-resource host-name gating, trace-resource host omission, log/trace export target filtering, disabled-exporter no-provider state clearing, provider validation ordering, dependency-light metrics-client/global install, and real local OTLP HTTP JSON log/trace POST are covered by Rust-derived/source-contract tests. |
| `src/targets.rs` | target classification helpers | complete_slice | `codex_otel` log-target and `codex_otel.trace_safe` trace-target prefix classification is covered by Rust-derived tests. |
| `src/otlp.rs` | `build_header_map`, `resolve_otlp_timeout`, OTLP HTTP JSON helper | complete_slice | Header-name/value filtering, OTLP timeout env precedence/default handling, and real local OTLP HTTP JSON metrics/log/trace transport are covered by Rust-derived/source-contract tests. |
| `src/events/session_telemetry.rs` | `SessionTelemetry` metrics-forwarding and event-shape projection | complete_slice | Metadata tag forwarding, metadata-tag disabling, service-name sanitization, plugin install metrics, startup-phase metric/log/trace projection, API/tool/SSE/websocket metric helpers, responses websocket timing extraction, Responses stream span-recording fields, snapshot forwarding, runtime summary forwarding, and selected user-prompt/tool-result/auth-recovery/API/websocket log-vs-trace routing are covered by Rust-derived tests. |

## Native Runtime Differences

The Python port intentionally does not embed Rust's native OpenTelemetry SDK provider/exporter runtime, Tokio runtime identity, OTLP gRPC transport, rustls/TLS client construction, or native span/current-span objects. Those are non-blocking implementation differences for this dependency-light port. Stable module contracts that affect PyCodex behavior are covered by Rust-derived tests, including real local OTLP HTTP JSON metrics/log/trace POST probes.

`codex-otel` is `complete` for the dependency-light Python projection.

## Tests

- `tests/test_otel_metrics_rs.py`
