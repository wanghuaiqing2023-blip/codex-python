"""Rust-derived tests for ``codex-otel`` metrics names, tags, and validation."""

import pytest

from pycodex import otel


def test_metric_name_constants_match_rust_names_rs() -> None:
    # Rust crate/module: codex-otel src/metrics/names.rs.
    # Contract: public metric constants use Rust's stable dotted metric names.
    assert otel.TOOL_CALL_COUNT_METRIC == "codex.tool.call"
    assert otel.TOOL_CALL_DURATION_METRIC == "codex.tool.call.duration_ms"
    assert otel.TOOL_CALL_UNIFIED_EXEC_METRIC == "codex.tool.unified_exec"
    assert otel.PROCESS_START_METRIC == "codex.process.start"
    assert otel.API_CALL_COUNT_METRIC == "codex.api_request"
    assert otel.API_CALL_DURATION_METRIC == "codex.api_request.duration_ms"
    assert otel.SSE_EVENT_COUNT_METRIC == "codex.sse_event"
    assert otel.SSE_EVENT_DURATION_METRIC == "codex.sse_event.duration_ms"
    assert otel.WEBSOCKET_REQUEST_COUNT_METRIC == "codex.websocket.request"
    assert otel.WEBSOCKET_REQUEST_DURATION_METRIC == "codex.websocket.request.duration_ms"
    assert otel.WEBSOCKET_EVENT_COUNT_METRIC == "codex.websocket.event"
    assert otel.WEBSOCKET_EVENT_DURATION_METRIC == "codex.websocket.event.duration_ms"
    assert otel.RESPONSES_API_OVERHEAD_DURATION_METRIC == "codex.responses_api_overhead.duration_ms"
    assert otel.RESPONSES_API_INFERENCE_TIME_DURATION_METRIC == "codex.responses_api_inference_time.duration_ms"
    assert otel.RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC == "codex.responses_api_engine_iapi_ttft.duration_ms"
    assert otel.RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC == "codex.responses_api_engine_service_ttft.duration_ms"
    assert otel.RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC == "codex.responses_api_engine_iapi_tbt.duration_ms"
    assert otel.RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC == "codex.responses_api_engine_service_tbt.duration_ms"
    assert otel.TURN_E2E_DURATION_METRIC == "codex.turn.e2e_duration_ms"
    assert otel.TURN_TTFT_DURATION_METRIC == "codex.turn.ttft.duration_ms"
    assert otel.TURN_TTFM_DURATION_METRIC == "codex.turn.ttfm.duration_ms"
    assert otel.TURN_NETWORK_PROXY_METRIC == "codex.turn.network_proxy"
    assert otel.TURN_MEMORY_METRIC == "codex.turn.memory"
    assert otel.TURN_TOOL_CALL_METRIC == "codex.turn.tool.call"
    assert otel.TURN_TOKEN_USAGE_METRIC == "codex.turn.token_usage"
    assert otel.GUARDIAN_REVIEW_COUNT_METRIC == "codex.guardian.review"
    assert otel.GUARDIAN_REVIEW_DURATION_METRIC == "codex.guardian.review.duration_ms"
    assert otel.GUARDIAN_REVIEW_TTFT_DURATION_METRIC == "codex.guardian.review.ttft.duration_ms"
    assert otel.GUARDIAN_REVIEW_TOKEN_USAGE_METRIC == "codex.guardian.review.token_usage"
    assert otel.GOAL_CREATED_METRIC == "codex.goal.created"
    assert otel.GOAL_RESUMED_METRIC == "codex.goal.resumed"
    assert otel.GOAL_COMPLETED_METRIC == "codex.goal.completed"
    assert otel.GOAL_BUDGET_LIMITED_METRIC == "codex.goal.budget_limited"
    assert otel.GOAL_USAGE_LIMITED_METRIC == "codex.goal.usage_limited"
    assert otel.GOAL_BLOCKED_METRIC == "codex.goal.blocked"
    assert otel.GOAL_TOKEN_COUNT_METRIC == "codex.goal.token_count"
    assert otel.GOAL_DURATION_SECONDS_METRIC == "codex.goal.duration_s"
    assert otel.PLUGIN_INSTALL_ELICITATION_SENT_METRIC == "codex.plugins.install_elicitation.sent"
    assert otel.PLUGIN_INSTALL_SUGGESTION_METRIC == "codex.plugins.install_suggestion"
    assert otel.CURATED_PLUGINS_STARTUP_SYNC_METRIC == "codex.plugins.startup_sync"
    assert otel.CURATED_PLUGINS_STARTUP_SYNC_FINAL_METRIC == "codex.plugins.startup_sync.final"
    assert otel.HOOK_RUN_METRIC == "codex.hooks.run"
    assert otel.HOOK_RUN_DURATION_METRIC == "codex.hooks.run.duration_ms"
    assert otel.STARTUP_PHASE_DURATION_METRIC == "codex.startup.phase.duration_ms"
    assert otel.STARTUP_PREWARM_DURATION_METRIC == "codex.startup_prewarm.duration_ms"
    assert otel.STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC == "codex.startup_prewarm.age_at_first_turn_ms"
    assert otel.THREAD_STARTED_METRIC == "codex.thread.started"
    assert otel.THREAD_SKILLS_ENABLED_TOTAL_METRIC == "codex.thread.skills.enabled_total"
    assert otel.THREAD_SKILLS_KEPT_TOTAL_METRIC == "codex.thread.skills.kept_total"
    assert otel.THREAD_SKILLS_DESCRIPTION_TRUNCATED_CHARS_METRIC == "codex.thread.skills.description_truncated_chars"
    assert otel.THREAD_SKILLS_TRUNCATED_METRIC == "codex.thread.skills.truncated"


def test_session_metric_tags_include_expected_tags_in_order() -> None:
    # Rust crate/module/test: codex-otel src/metrics/tags.rs
    # session_metric_tags_include_expected_tags_in_order.
    tags = otel.SessionMetricTagValues(
        auth_mode="api_key",
        session_source="cli",
        originator="codex_cli",
        service_name="desktop_app",
        model="gpt-5.1",
        app_version="1.2.3",
    ).into_tags()

    assert tags == [
        (otel.AUTH_MODE_TAG, "api_key"),
        (otel.SESSION_SOURCE_TAG, "cli"),
        (otel.ORIGINATOR_TAG, "codex_cli"),
        (otel.SERVICE_NAME_TAG, "desktop_app"),
        (otel.MODEL_TAG, "gpt-5.1"),
        (otel.APP_VERSION_TAG, "1.2.3"),
    ]


def test_session_metric_tags_skip_missing_optional_tags() -> None:
    # Rust crate/module/test: codex-otel src/metrics/tags.rs
    # session_metric_tags_skip_missing_optional_tags.
    tags = otel.SessionMetricTagValues(
        auth_mode=None,
        session_source="exec",
        originator="codex_exec",
        service_name=None,
        model="gpt-5.1",
        app_version="1.2.3",
    ).into_tags()

    assert tags == [
        (otel.SESSION_SOURCE_TAG, "exec"),
        (otel.ORIGINATOR_TAG, "codex_exec"),
        (otel.MODEL_TAG, "gpt-5.1"),
        (otel.APP_VERSION_TAG, "1.2.3"),
    ]


def test_bounded_originator_tag_value_matches_known_low_cardinality_values() -> None:
    # Rust crate/module: codex-otel src/metrics/tags.rs.
    # Rust item: bounded_originator_tag_value.
    assert otel.bounded_originator_tag_value("codex_exec") == "codex_exec"
    assert otel.bounded_originator_tag_value("codex-app-server") == "codex-app-server"
    assert otel.bounded_originator_tag_value("not a known originator!") == "other"


def test_metrics_validation_rejects_invalid_names_and_tags() -> None:
    # Rust crate/module/tests: codex-otel src/metrics/validation.rs and
    # tests/suite/validation.rs invalid_tag_component_is_rejected,
    # counter_rejects_invalid_tag_key, histogram_rejects_invalid_tag_value,
    # counter_rejects_invalid_metric_name.
    with pytest.raises(otel.InvalidMetricName) as metric_err:
        otel.validate_metric_name("bad name")
    assert metric_err.value.name == "bad name"

    with pytest.raises(otel.InvalidTagComponent) as key_err:
        otel.validate_tag_key("bad key")
    assert key_err.value.label == "tag key"
    assert key_err.value.value == "bad key"

    with pytest.raises(otel.InvalidTagComponent) as value_err:
        otel.validate_tag_value("bad value")
    assert value_err.value.label == "tag value"
    assert value_err.value.value == "bad value"


def test_metrics_validation_allows_rust_character_sets() -> None:
    # Rust crate/module: codex-otel src/metrics/validation.rs.
    # Contract: metric names accept ASCII alnum plus '.', '_', '-'; tag components
    # also accept '/'.
    otel.validate_metric_name("codex.request_latency-1")
    otel.validate_tag_key("service_name")
    otel.validate_tag_value("codex/app-server-1.2.3")


def test_runtime_metric_totals_merge_saturates_and_empty_matches_rust() -> None:
    # Rust crate/module: codex-otel src/metrics/runtime_metrics.rs.
    # Contract: RuntimeMetricTotals::is_empty checks both fields, and merge uses
    # saturating_add for count and duration_ms.
    totals = otel.RuntimeMetricTotals()
    assert totals.is_empty()

    totals.merge(otel.RuntimeMetricTotals(count=1, duration_ms=2))
    assert totals == otel.RuntimeMetricTotals(count=1, duration_ms=2)
    assert not totals.is_empty()

    near_max = otel.RuntimeMetricTotals(count=otel.U64_MAX, duration_ms=otel.U64_MAX - 1)
    near_max.merge(otel.RuntimeMetricTotals(count=1, duration_ms=10))
    assert near_max == otel.RuntimeMetricTotals(count=otel.U64_MAX, duration_ms=otel.U64_MAX)


def test_runtime_metrics_summary_merge_and_responses_api_summary_matches_rust() -> None:
    # Rust crate/module: codex-otel src/metrics/runtime_metrics.rs.
    # Contract: RuntimeMetricsSummary::merge saturates totals and overwrites
    # scalar timing fields only when the incoming value is non-zero; the
    # responses_api_summary projection copies only responses API timing fields.
    summary = otel.RuntimeMetricsSummary(
        tool_calls=otel.RuntimeMetricTotals(count=1, duration_ms=2),
        responses_api_overhead_ms=10,
        turn_ttft_ms=7,
    )
    summary.merge(
        otel.RuntimeMetricsSummary(
            tool_calls=otel.RuntimeMetricTotals(count=3, duration_ms=4),
            responses_api_overhead_ms=0,
            responses_api_inference_time_ms=20,
            turn_ttft_ms=0,
            turn_ttfm_ms=9,
        )
    )

    assert summary.tool_calls == otel.RuntimeMetricTotals(count=4, duration_ms=6)
    assert summary.responses_api_overhead_ms == 10
    assert summary.responses_api_inference_time_ms == 20
    assert summary.turn_ttft_ms == 7
    assert summary.turn_ttfm_ms == 9

    responses_only = summary.responses_api_summary()
    assert responses_only.tool_calls.is_empty()
    assert responses_only.api_calls.is_empty()
    assert responses_only.streaming_events.is_empty()
    assert responses_only.websocket_calls.is_empty()
    assert responses_only.websocket_events.is_empty()
    assert responses_only.responses_api_overhead_ms == 10
    assert responses_only.responses_api_inference_time_ms == 20
    assert responses_only.turn_ttft_ms == 0
    assert responses_only.turn_ttfm_ms == 0


def test_runtime_metrics_summary_from_snapshot_collects_runtime_metrics() -> None:
    # Rust crate/module/test: codex-otel tests/suite/runtime_summary.rs
    # runtime_metrics_summary_collects_tool_api_and_streaming_metrics.
    # Contract: RuntimeMetricsSummary::from_snapshot aggregates Rust metric names
    # into tool/API/SSE/websocket totals and response/turn timing fields.
    snapshot = {
        "metrics": [
            {"name": otel.TOOL_CALL_COUNT_METRIC, "value": 1},
            {"name": otel.TOOL_CALL_DURATION_METRIC, "sum": 250.0},
            {"name": otel.API_CALL_COUNT_METRIC, "value": 1},
            {"name": otel.API_CALL_DURATION_METRIC, "sum": 300.0},
            {"name": otel.SSE_EVENT_COUNT_METRIC, "value": 1},
            {"name": otel.SSE_EVENT_DURATION_METRIC, "sum": 120.0},
            {"name": otel.WEBSOCKET_REQUEST_COUNT_METRIC, "value": 1},
            {"name": otel.WEBSOCKET_REQUEST_DURATION_METRIC, "sum": 400.0},
            {"name": otel.WEBSOCKET_EVENT_COUNT_METRIC, "values": [1, 1]},
            {"name": otel.WEBSOCKET_EVENT_DURATION_METRIC, "values": [80.0, 20.0]},
            {"name": otel.RESPONSES_API_OVERHEAD_DURATION_METRIC, "sum": 124.0},
            {"name": otel.RESPONSES_API_INFERENCE_TIME_DURATION_METRIC, "sum": 457.0},
            {"name": otel.RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC, "sum": 211.0},
            {"name": otel.RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC, "sum": 233.0},
            {"name": otel.RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC, "sum": 377.0},
            {"name": otel.RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC, "sum": 399.0},
            {"name": otel.TURN_TTFT_DURATION_METRIC, "sum": 95.0},
            {"name": otel.TURN_TTFM_DURATION_METRIC, "sum": 180.0},
        ]
    }

    assert otel.RuntimeMetricsSummary.from_snapshot(snapshot) == otel.RuntimeMetricsSummary(
        tool_calls=otel.RuntimeMetricTotals(count=1, duration_ms=250),
        api_calls=otel.RuntimeMetricTotals(count=1, duration_ms=300),
        streaming_events=otel.RuntimeMetricTotals(count=1, duration_ms=120),
        websocket_calls=otel.RuntimeMetricTotals(count=1, duration_ms=400),
        websocket_events=otel.RuntimeMetricTotals(count=2, duration_ms=100),
        responses_api_overhead_ms=124,
        responses_api_inference_time_ms=457,
        responses_api_engine_iapi_ttft_ms=211,
        responses_api_engine_service_ttft_ms=233,
        responses_api_engine_iapi_tbt_ms=377,
        responses_api_engine_service_tbt_ms=399,
        turn_ttft_ms=95,
        turn_ttfm_ms=180,
    )


def test_runtime_metrics_summary_from_snapshot_matches_rust_f64_to_u64_edges() -> None:
    # Rust crate/module: codex-otel src/metrics/runtime_metrics.rs.
    # Contract: f64_to_u64 returns 0 for non-finite or non-positive values,
    # clamps overflow to u64::MAX, and rounds positive finite values.
    snapshot = {
        "metrics": [
            {"name": otel.TOOL_CALL_COUNT_METRIC, "values": [-1, float("nan"), float("inf"), 1.5]},
            {"name": otel.TOOL_CALL_DURATION_METRIC, "values": [0, -3, float("-inf"), 2.5]},
            {"name": otel.API_CALL_DURATION_METRIC, "sum": float(otel.U64_MAX) * 2},
        ]
    }

    summary = otel.RuntimeMetricsSummary.from_snapshot(snapshot)

    assert summary.tool_calls == otel.RuntimeMetricTotals(count=2, duration_ms=3)
    assert summary.api_calls == otel.RuntimeMetricTotals(count=0, duration_ms=otel.U64_MAX)


def test_timer_record_adds_additional_tags_before_base_tags() -> None:
    # Rust crate/module/test: codex-otel src/metrics/timer.rs and
    # tests/suite/timing.rs::timer_result_records_success.
    # Contract: Timer::record records elapsed duration through the metrics client
    # and passes additional tags before the timer's base tags.
    class FakeMetricsClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, list[tuple[str, str]]]] = []

        def record_duration(self, name: str, duration_ms: int, tags: list[tuple[str, str]]) -> None:
            self.calls.append((name, duration_ms, tags))

    client = FakeMetricsClient()
    timer = otel.Timer("codex.request_latency", [("route", "chat")], client)

    timer.record([("status", "ok")])

    assert len(client.calls) == 1
    name, duration_ms, tags = client.calls[0]
    assert name == "codex.request_latency"
    assert duration_ms >= 0
    assert tags == [("status", "ok"), ("route", "chat")]


def test_metrics_client_start_timer_and_record_duration_match_timing_contract() -> None:
    # Rust crate/module/test: codex-otel src/metrics/client.rs,
    # src/metrics/timer.rs, and tests/suite/timing.rs::record_duration_records_histogram.
    # Contract: MetricsClient validates metric names/tags, stores duration samples
    # in milliseconds, and start_timer returns a Timer bound to the client.
    metrics = otel.MetricsClient(default_tags={"service": "codex-cli"})

    timer = metrics.start_timer("codex.request_latency", [("route", "chat")])
    timer.record(())
    metrics.record_duration("codex.request_latency", 15, [("route", "chat")])

    assert len(metrics.duration_records) == 2
    assert metrics.duration_records[0].name == "codex.request_latency"
    assert dict(metrics.duration_records[0].tags) == {"service": "codex-cli", "route": "chat"}
    assert metrics.duration_records[1] == otel.MetricsDurationRecord(
        "codex.request_latency",
        15,
        [("route", "chat"), ("service", "codex-cli")],
    )


def test_record_process_start_once_records_bounded_originator_once() -> None:
    # Rust crate/module: codex-otel src/metrics/process.rs.
    # Contract: record_process_start_once records PROCESS_START_METRIC with inc=1
    # and bounded originator on the first call only; later calls return false.
    otel._reset_process_start_once_for_tests()
    metrics = otel.MetricsClient()

    assert otel.record_process_start_once(metrics, "not a known originator!") is True
    assert otel.record_process_start_once(metrics, "codex_exec") is False

    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            otel.PROCESS_START_METRIC,
            1,
            [(otel.ORIGINATOR_TAG, "other")],
        )
    ]


def test_metrics_config_builders_match_rust_defaults_and_by_value_updates() -> None:
    # Rust crate/module: codex-otel src/metrics/config.rs.
    # Contract: MetricsConfig::{otlp,in_memory} set Rust defaults, and builder
    # methods return updated configs with export_interval/runtime_reader/tags.
    exporter = otel.OtelExporter.OtlpHttp("https://example.test/metrics")
    otlp_config = otel.MetricsConfig.otlp("test", "codex-cli", "1.2.3", exporter)

    assert otlp_config.environment == "test"
    assert otlp_config.service_name == "codex-cli"
    assert otlp_config.service_version == "1.2.3"
    assert otlp_config.exporter == otel.MetricsExporter.Otlp(exporter)
    assert otlp_config.export_interval is None
    assert otlp_config.runtime_reader is False
    assert otlp_config.default_tags == {}

    updated = otlp_config.with_export_interval(15).with_runtime_reader().with_tag("service", "codex-cli")

    assert otlp_config.export_interval is None
    assert otlp_config.runtime_reader is False
    assert otlp_config.default_tags == {}
    assert updated.export_interval == 15
    assert updated.runtime_reader is True
    assert updated.default_tags == {"service": "codex-cli"}

    in_memory_config = otel.MetricsConfig.in_memory("dev", "codex", "0.0.0", exporter="memory")
    assert in_memory_config.exporter == otel.MetricsExporter.InMemory("memory")


def test_metrics_config_with_tag_rejects_invalid_components_from_rust_validation_suite() -> None:
    # Rust crate/module/test: codex-otel tests/suite/validation.rs
    # invalid_tag_component_is_rejected.
    config = otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3")

    with pytest.raises(otel.InvalidTagComponent) as key_err:
        config.with_tag("bad key", "value")
    assert key_err.value.label == "tag key"
    assert key_err.value.value == "bad key"

    with pytest.raises(otel.InvalidTagComponent) as value_err:
        config.with_tag("route", "bad value")
    assert value_err.value.label == "tag value"
    assert value_err.value.value == "bad value"


def test_metrics_client_new_uses_config_default_tags_and_histogram_validation() -> None:
    # Rust crate/module/tests: codex-otel src/metrics/config.rs,
    # src/metrics/client.rs, tests/suite/snapshot.rs, and
    # tests/suite/validation.rs::histogram_rejects_invalid_tag_value.
    # Contract: MetricsClient::new consumes MetricsConfig default tags for metric
    # records, and per-metric histogram tags are validated.
    config = (
        otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3")
        .with_tag("service", "codex-cli")
        .with_runtime_reader()
    )
    metrics = otel.MetricsClient.new(config)

    metrics.counter("codex.tool.call", 1, [("tool", "shell")])
    metrics.histogram("codex.request_latency", 3, [("route", "chat")])

    assert metrics.config == config
    assert metrics.counter_records == [
        otel.MetricsCounterRecord("codex.tool.call", 1, [("service", "codex-cli"), ("tool", "shell")])
    ]
    assert metrics.histogram_records == [
        otel.MetricsHistogramRecord("codex.request_latency", 3, [("route", "chat"), ("service", "codex-cli")])
    ]

    with pytest.raises(otel.InvalidTagComponent) as value_err:
        metrics.histogram("codex.request_latency", 3, [("route", "bad value")])
    assert value_err.value.label == "tag value"
    assert value_err.value.value == "bad value"


def test_metrics_client_merges_default_and_per_call_tags_like_send_suite() -> None:
    # Rust crate/module/test: codex-otel src/metrics/client.rs and
    # tests/suite/send.rs::send_builds_payload_with_tags_and_histograms.
    # Contract: default tags are merged with per-call tags and per-call tags
    # override defaults with the same key.
    metrics = otel.MetricsClient(default_tags={"service": "codex-cli", "env": "prod"})

    metrics.counter("codex.turns", 1, [("model", "gpt-5.1"), ("env", "dev")])
    metrics.histogram("codex.tool_latency", 25, [("tool", "shell")])

    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            "codex.turns",
            1,
            [("env", "dev"), ("model", "gpt-5.1"), ("service", "codex-cli")],
        )
    ]
    assert metrics.histogram_records == [
        otel.MetricsHistogramRecord(
            "codex.tool_latency",
            25,
            [("env", "prod"), ("service", "codex-cli"), ("tool", "shell")],
        )
    ]


def test_metrics_client_merges_default_tags_per_record_without_mutating_defaults() -> None:
    # Rust crate/module/test: codex-otel tests/suite/send.rs
    # send_merges_default_tags_per_line.
    # Contract: each metric starts from default tags, per-call overrides apply to
    # that record only, and later records see the original defaults.
    metrics = otel.MetricsClient(default_tags={"service": "codex-cli", "env": "prod", "region": "us"})

    metrics.counter("codex.alpha", 1, [("env", "dev"), ("component", "alpha")])
    metrics.counter("codex.beta", 2, [("service", "worker"), ("component", "beta")])

    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            "codex.alpha",
            1,
            [("component", "alpha"), ("env", "dev"), ("region", "us"), ("service", "codex-cli")],
        ),
        otel.MetricsCounterRecord(
            "codex.beta",
            2,
            [("component", "beta"), ("env", "prod"), ("region", "us"), ("service", "worker")],
        ),
    ]
    assert metrics.default_tags == {"service": "codex-cli", "env": "prod", "region": "us"}


def test_metrics_client_snapshot_requires_runtime_reader_and_collects_without_shutdown() -> None:
    # Rust crate/module/test: codex-otel src/metrics/client.rs and
    # tests/suite/snapshot.rs::snapshot_collects_metrics_without_shutdown.
    # Contract: snapshot requires with_runtime_reader and collects the current
    # metric records without calling shutdown.
    unavailable = otel.MetricsClient.new(otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3"))
    with pytest.raises(otel.RuntimeSnapshotUnavailable):
        unavailable.snapshot()

    config = (
        otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3")
        .with_tag("service", "codex-cli")
        .with_runtime_reader()
    )
    metrics = otel.MetricsClient.new(config)
    metrics.counter("codex.tool.call", 1, [("tool", "shell"), ("success", "true")])

    snapshot = metrics.snapshot()

    assert metrics.shutdown_called is False
    assert snapshot == {
        "metrics": [
            {
                "name": "codex.tool.call",
                "value": 1,
                "tags": [("service", "codex-cli"), ("success", "true"), ("tool", "shell")],
                "kind": "counter",
            }
        ]
    }


def test_metrics_client_shutdown_is_idempotent_and_exports_nothing_without_metrics() -> None:
    # Rust crate/module/test: codex-otel tests/suite/send.rs
    # shutdown_flushes_in_memory_exporter and shutdown_without_metrics_exports_nothing.
    # Contract: shutdown succeeds, is safe to call when no metrics were recorded,
    # and does not create synthetic records.
    metrics = otel.MetricsClient()

    metrics.shutdown()
    metrics.shutdown()

    assert metrics.shutdown_called is True
    assert metrics.counter_records == []
    assert metrics.histogram_records == []
    assert metrics.duration_records == []


def test_session_telemetry_attaches_metadata_tags_to_metrics() -> None:
    # Rust crate/module/test: codex-otel tests/suite/manager_metrics.rs
    # manager_attaches_metadata_tags_to_metrics.
    # Contract: SessionTelemetry forwards metrics with auth/session/originator/
    # model/app-version metadata tags before per-call tags.
    metrics = otel.MetricsClient(default_tags={"service": "codex-cli"})
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        None,
        otel.TelemetryAuthMode.API_KEY,
        "test_originator",
        True,
        "tty",
        "cli",
    ).with_metrics(metrics)

    manager.counter("codex.session_started", 1, [("source", "tui")])
    manager.shutdown_metrics()

    assert metrics.shutdown_called is True
    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            "codex.session_started",
            1,
            [
                ("app.version", otel.CODEX_OTEL_APP_VERSION),
                ("auth_mode", "api_key"),
                ("model", "gpt-5.1"),
                ("originator", "test_originator"),
                ("service", "codex-cli"),
                ("session_source", "cli"),
                ("source", "tui"),
            ],
        )
    ]


def test_session_telemetry_can_disable_metadata_tags_and_add_service_name() -> None:
    # Rust crate/module/tests: codex-otel tests/suite/manager_metrics.rs
    # manager_allows_disabling_metadata_tags and manager_attaches_optional_service_name_tag.
    metrics_without_metadata = otel.MetricsClient()
    manager_without_metadata = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-4o",
        "gpt-4o",
        "account-id",
        None,
        otel.TelemetryAuthMode.API_KEY,
        "test_originator",
        True,
        "tty",
        "cli",
    ).with_metrics_without_metadata_tags(metrics_without_metadata)

    manager_without_metadata.counter("codex.session_started", 1, [("source", "tui")])

    assert metrics_without_metadata.counter_records == [
        otel.MetricsCounterRecord("codex.session_started", 1, [("source", "tui")])
    ]

    metrics = otel.MetricsClient()
    manager = (
        otel.SessionTelemetry.new("thread-id", "gpt-5.1", "gpt-5.1", None, None, None, "test originator", False, "tty", "cli")
        .with_metrics_service_name("my app/server client")
        .with_metrics(metrics)
    )

    manager.counter("codex.session_started", 1, [])

    assert dict(metrics.counter_records[0].tags)["service_name"] == "my_app_server_client"
    assert dict(metrics.counter_records[0].tags)["originator"] == "test_originator"


def test_session_telemetry_records_plugin_install_metrics_without_metadata_tags() -> None:
    # Rust crate/module/tests: codex-otel tests/suite/manager_metrics.rs
    # manager_records_plugin_install_suggestion_metric and
    # manager_records_plugin_install_elicitation_sent_metric.
    metrics = otel.MetricsClient()
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        None,
        otel.TelemetryAuthMode.API_KEY,
        "test_originator",
        False,
        "tty",
        "cli",
    ).with_metrics_without_metadata_tags(metrics)

    manager.record_plugin_install_suggestion(
        "connector",
        "connector_calendar",
        "Google Calendar",
        "accept",
        True,
        False,
    )
    manager.record_plugin_install_elicitation_sent("plugin", "slack@openai-curated", "Slack")

    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            otel.PLUGIN_INSTALL_SUGGESTION_METRIC,
            1,
            [("completed", "false"), ("response_action", "accept"), ("tool_type", "connector")],
        ),
        otel.MetricsCounterRecord(
            otel.PLUGIN_INSTALL_ELICITATION_SENT_METRIC,
            1,
            [("tool_type", "plugin")],
        ),
    ]


def test_session_telemetry_snapshot_and_runtime_summary_forward_to_metrics() -> None:
    # Rust crate/module/tests: codex-otel tests/suite/snapshot.rs
    # manager_snapshot_metrics_collects_without_shutdown and
    # tests/suite/runtime_summary.rs::runtime_metrics_summary_collects_tool_api_and_streaming_metrics.
    config = (
        otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3")
        .with_tag("service", "codex-cli")
        .with_runtime_reader()
    )
    metrics = otel.MetricsClient.new(config)
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        None,
        otel.TelemetryAuthMode.API_KEY,
        "test_originator",
        True,
        "tty",
        "cli",
    ).with_metrics(metrics)

    manager.counter("codex.tool.call", 1, [("tool", "shell"), ("success", "true")])
    manager.record_duration(otel.TOOL_CALL_DURATION_METRIC, 250, [("tool", "shell"), ("success", "true")])

    snapshot = manager.snapshot_metrics()
    summary = manager.runtime_metrics_summary()

    assert metrics.shutdown_called is False
    assert snapshot["metrics"][0]["tags"] == [
        ("app.version", otel.CODEX_OTEL_APP_VERSION),
        ("auth_mode", "api_key"),
        ("model", "gpt-5.1"),
        ("originator", "test_originator"),
        ("service", "codex-cli"),
        ("session_source", "cli"),
        ("success", "true"),
        ("tool", "shell"),
    ]
    assert summary is not None
    assert summary.tool_calls == otel.RuntimeMetricTotals(count=1, duration_ms=250)


def test_session_telemetry_runtime_summary_records_tool_api_streaming_and_websocket_metrics() -> None:
    # Rust crate/module/test: codex-otel tests/suite/runtime_summary.rs
    # runtime_metrics_summary_collects_tool_api_and_streaming_metrics.
    # Contract: SessionTelemetry helper methods emit the metric names/tags that
    # RuntimeMetricsSummary::from_snapshot aggregates.
    config = otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3").with_runtime_reader()
    metrics = otel.MetricsClient.new(config)
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        None,
        otel.TelemetryAuthMode.API_KEY,
        "test_originator",
        True,
        "tty",
        "cli",
    ).with_metrics(metrics)

    manager.tool_result_with_tags("shell", "call-1", '{"cmd":"echo"}', 250, True, "ok")
    manager.record_api_request(1, 200, None, 300, endpoint="/responses")
    manager.record_websocket_request(400, None, False)
    manager.log_sse_event("response.created", "{}", 120)
    manager.record_websocket_event('{"type":"response.created"}', 80)
    manager.record_websocket_event(
        '{"type":"responsesapi.websocket_timing","timing_metrics":{'
        '"responses_duration_excl_engine_and_client_tool_time_ms":124,'
        '"engine_service_total_ms":457,'
        '"engine_iapi_ttft_total_ms":211,'
        '"engine_service_ttft_total_ms":233,'
        '"engine_iapi_tbt_across_engine_calls_ms":377,'
        '"engine_service_tbt_across_engine_calls_ms":399}}',
        20,
    )
    manager.record_duration(otel.TURN_TTFT_DURATION_METRIC, 95, [])
    manager.record_duration(otel.TURN_TTFM_DURATION_METRIC, 180, [])

    summary = manager.runtime_metrics_summary()

    assert summary == otel.RuntimeMetricsSummary(
        tool_calls=otel.RuntimeMetricTotals(count=1, duration_ms=250),
        api_calls=otel.RuntimeMetricTotals(count=1, duration_ms=300),
        streaming_events=otel.RuntimeMetricTotals(count=1, duration_ms=120),
        websocket_calls=otel.RuntimeMetricTotals(count=1, duration_ms=400),
        websocket_events=otel.RuntimeMetricTotals(count=2, duration_ms=100),
        responses_api_overhead_ms=124,
        responses_api_inference_time_ms=457,
        responses_api_engine_iapi_ttft_ms=211,
        responses_api_engine_service_ttft_ms=233,
        responses_api_engine_iapi_tbt_ms=377,
        responses_api_engine_service_tbt_ms=399,
        turn_ttft_ms=95,
        turn_ttfm_ms=180,
    )


def test_session_telemetry_api_sse_and_websocket_failure_tags_match_rust() -> None:
    # Rust crate/module: codex-otel src/events/session_telemetry.rs.
    # Contract: API, SSE, and websocket helpers record success=false plus Rust
    # kind/status fallback tags for failed or malformed events.
    manager = otel.SessionTelemetry.new("thread-id", "gpt-5.1", "gpt-5.1", None, None, None, "origin", False, "tty", "cli")
    metrics = otel.MetricsClient()
    manager.with_metrics_without_metadata_tags(metrics)

    manager.record_api_request(1, None, "network error", 7, endpoint="/responses")
    manager.sse_event_failed(None, 8, "idle timeout waiting for SSE")
    manager.record_websocket_request(9, "connection failed", False)
    manager.record_websocket_event("not json", 10)

    assert metrics.counter_records == [
        otel.MetricsCounterRecord(otel.API_CALL_COUNT_METRIC, 1, [("status", "none"), ("success", "false")]),
        otel.MetricsCounterRecord(otel.SSE_EVENT_COUNT_METRIC, 1, [("kind", "unknown"), ("success", "false")]),
        otel.MetricsCounterRecord(otel.WEBSOCKET_REQUEST_COUNT_METRIC, 1, [("success", "false")]),
        otel.MetricsCounterRecord(otel.WEBSOCKET_EVENT_COUNT_METRIC, 1, [("kind", "parse_error"), ("success", "false")]),
    ]
    assert [record.duration_ms for record in metrics.duration_records] == [7, 8, 9, 10]


def test_trace_context_parses_valid_and_rejects_invalid_traceparent() -> None:
    # Rust crate/module/tests: codex-otel src/trace_context.rs
    # parses_valid_w3c_trace_context, invalid_traceparent_returns_none,
    # missing_traceparent_returns_none.
    valid = otel.W3cTraceContext(
        traceparent="00-00000000000000000000000000000001-0000000000000002-01",
        tracestate=None,
    )
    assert otel.context_from_w3c_trace_context(valid) == valid

    assert otel.context_from_w3c_trace_context(
        otel.W3cTraceContext(traceparent="not-a-traceparent", tracestate=None)
    ) is None
    assert otel.context_from_w3c_trace_context(
        otel.W3cTraceContext(traceparent=None, tracestate="vendor=value")
    ) is None
    assert otel.context_from_w3c_trace_context(
        otel.W3cTraceContext(
            traceparent="00-00000000000000000000000000000000-0000000000000002-01",
            tracestate=None,
        )
    ) is None
    assert otel.context_from_w3c_trace_context(
        otel.W3cTraceContext(
            traceparent="00-00000000000000000000000000000001-0000000000000000-01",
            tracestate=None,
        )
    ) is None


def test_tracestate_validation_rejects_header_unsafe_configured_values() -> None:
    # Rust crate/module/test: codex-otel tests/suite/otlp_http_loopback.rs
    # otel_provider_rejects_header_unsafe_configured_tracestate.
    with pytest.raises(ValueError, match="configured tracestate value"):
        otel.validate_tracestate_entries({"example": {"alpha": "one\ntwo"}})

    with pytest.raises(ValueError, match="configured tracestate field key example.bad:key"):
        otel.validate_tracestate_member("example", {"bad:key": "one"})

    with pytest.raises(ValueError, match="configured tracestate value for example.alpha"):
        otel.validate_tracestate_member("example", {"alpha": "one;two"})

    with pytest.raises(ValueError, match="invalid configured tracestate"):
        otel.validate_tracestate_member("BadKey", {"alpha": "one"})


def test_merge_tracestate_entries_upserts_configured_fields_like_rust() -> None:
    # Rust crate/module/test: codex-otel src/trace_context.rs and
    # tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_traces_to_collector.
    # Contract: configured member fields upsert selected semicolon fields without
    # replacing unrelated fields, and configured members are placed at the front.
    merged = otel.merge_tracestate_entries(
        "example=alpha:zero;keep:yes,other=value",
        {"example": {"alpha": "one", "beta": "two"}},
    )

    assert merged == "example=alpha:one;keep:yes;beta:two,other=value"


def test_merge_tracestate_entries_validates_existing_and_configured_state() -> None:
    # Rust crate/module: codex-otel src/trace_context.rs.
    # Contract: invalid existing tracestate is ignored by Rust during propagation,
    # while invalid configured entries are rejected before installation.
    assert otel.merge_tracestate_entries(None, {"example": {"alpha": "one"}}) == "example=alpha:one"
    assert otel.merge_tracestate_entries("not a member", {"example": {"alpha": "one"}}) == "example=alpha:one"

    with pytest.raises(ValueError, match="configured tracestate value"):
        otel.merge_tracestate_entries("other=value", {"example": {"alpha": "bad,value"}})
