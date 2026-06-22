# pycodex.otel

Rust crate: `codex-otel`

Rust anchor: `codex/codex-rs/otel`

This package mirrors selected public crate interfaces exported from
`otel/src/lib.rs`.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/lib.rs` | `pycodex.otel` | partial | Public re-export facade exists for config, trace-context, timer, metrics names/tags, and compatibility stubs. Full provider/session telemetry runtime remains open. |
| `src/config.rs` | `OtelExporter`, `OtelSettings`, `OtelTlsConfig`, `validate_span_attributes` | partial | Basic dataclass/config shape and empty span-attribute-key validation are present; exporter resolution, serde naming, and Statsig default policy still need a dedicated module audit. |
| `src/trace_context.rs` | `W3cTraceContext`, traceparent/tracestate helpers | complete_slice | Traceparent validation, trace context extraction shape, configured tracestate validation, and tracestate field upsert/merge are covered by Rust-derived tests. Live span parent integration remains open. |
| `src/metrics/names.rs` | metric constants | complete_slice | Stable Rust metric names are covered by Rust-derived tests. |
| `src/metrics/tags.rs` | tag constants, `SessionMetricTagValues`, `bounded_originator_tag_value` | complete_slice | Tag order, optional tag skipping, and known-originator bounding are covered by Rust-derived tests. |
| `src/metrics/validation.rs` | validation helpers and `MetricsError` variants | complete_slice | Metric/tag character sets and invalid component/name error fields are covered by Rust-derived tests. |
| `src/metrics/config.rs` | `MetricsConfig`, `MetricsExporter`, `MetricsClient.new` config projection | complete_slice | Config builder defaults, by-value update semantics, default tags, runtime-reader/export-interval flags, and tag validation are covered by Rust-derived tests. |
| `src/metrics/client.rs` | `MetricsClient` dependency-light record/snapshot/shutdown projection | complete_slice | Counter/histogram/duration validation, default/per-call tag merge and override, runtime snapshot gate/collection, and shutdown empty-record behavior are covered by Rust-derived tests. |
| `src/metrics/runtime_metrics.rs` | `RuntimeMetricTotals`, `RuntimeMetricsSummary`, snapshot aggregation helpers | complete_slice | Empty checks, saturating merges, responses-only summary projection, snapshot counter/histogram aggregation, and Rust `f64_to_u64` clamping/rounding are covered by Rust-derived tests. |
| `src/metrics/timer.rs` | `Timer`, `MetricsClient.start_timer`, `MetricsClient.record_duration` | complete_slice | Timer duration recording, additional-tag ordering, and millisecond duration capture are covered by Rust-derived tests. |
| `src/metrics/process.rs` | `record_process_start_once` | complete_slice | Process-start counter recording, once-only behavior, and bounded originator tags are covered by Rust-derived tests. |
| `src/events/session_telemetry.rs` | `SessionTelemetry` metrics-forwarding projection | complete_slice | Metadata tag forwarding, metadata-tag disabling, service-name sanitization, plugin install metrics, API/tool/SSE/websocket metric helpers, responses websocket timing extraction, snapshot forwarding, and runtime summary forwarding are covered by Rust-derived tests. |

## Known Gaps

- OpenTelemetry provider/exporter startup, OTLP HTTP/gRPC transport, TLS client setup, runtime metrics reader wiring, and real OpenTelemetry exporter behavior are not implemented.
- Session telemetry log/span event routing and native OpenTelemetry metrics aggregation/exporter pipelines are not yet ported beyond dependency-light compatibility surfaces.
- Live span parent/current-span integration remains open.

`codex-otel` is `module_progress`, not strict `complete`.

## Tests

- `tests/test_otel_metrics_rs.py`
