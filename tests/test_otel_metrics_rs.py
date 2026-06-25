"""Rust-derived tests for ``codex-otel`` metrics names, tags, and validation."""

import http.server
import threading

import pytest

from pycodex import otel
from pycodex.codex_api.common import ResponseEvent


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


def test_statsig_default_metrics_exporter_is_disabled_in_debug_builds() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module: src/config.rs
    # Rust test: tests::statsig_default_metrics_exporter_is_disabled_in_debug_builds
    # Contract: resolve_exporter maps built-in Statsig to None in debug/test builds.
    resolved = otel.resolve_exporter(otel.OtelExporter.Statsig())

    assert resolved.kind == "none"


def test_resolve_exporter_preserves_explicit_exporters_and_statsig_constants() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/config.rs
    # Anchor: resolve_exporter, STATSIG_* constants, OtelExporter::OtlpHttp.
    # Contract: non-Statsig exporters are cloned unchanged; Statsig constants keep Rust defaults.
    tls = otel.OtelTlsConfig(ca_certificate="ca.pem")
    exporter = otel.OtelExporter.OtlpHttp(
        "https://collector.example/v1/metrics",
        headers={"authorization": "Bearer token"},
        protocol=otel.OtelHttpProtocol.BINARY,
        tls=tls,
    )

    resolved = otel.resolve_exporter(exporter)

    assert resolved == exporter
    assert resolved is not exporter
    assert resolved.headers is not exporter.headers
    assert resolved.tls is not exporter.tls
    assert otel.STATSIG_OTLP_HTTP_ENDPOINT == "https://ab.chatgpt.com/otlp/v1/metrics"
    assert otel.STATSIG_API_KEY_HEADER == "statsig-api-key"
    assert otel.STATSIG_API_KEY == "client-MkRuleRQBd6qakfnDYqJVR9JuXcY57Ljly3vi5JVUIO"


def _test_otel_settings() -> otel.OtelSettings:
    return otel.OtelSettings(
        environment="test",
        service_name="codex-test",
        service_version="0.0.0",
        codex_home=".",
        exporter=otel.OtelExporter.None_(),
        trace_exporter=otel.OtelExporter.None_(),
        metrics_exporter=otel.OtelExporter.None_(),
        runtime_metrics=False,
    )


def test_resource_attributes_include_host_name_when_present() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Rust test: tests::resource_attributes_include_host_name_when_present
    # Contract: log resources include normalized host.name when a host name is present.
    attrs = otel.resource_attributes(
        _test_otel_settings(),
        host_name="opentelemetry-test",
        kind=otel.ResourceKind.LOGS,
    )

    assert dict(attrs)[otel.HOST_NAME_ATTRIBUTE] == "opentelemetry-test"


def test_resource_attributes_omit_host_name_when_missing_empty_or_trace_resource() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Rust test: tests::resource_attributes_omit_host_name_when_missing_or_empty
    # Contract: host.name is absent for missing/blank host names and trace resources.
    settings = _test_otel_settings()

    missing = otel.resource_attributes(settings, host_name=None, kind=otel.ResourceKind.LOGS)
    empty = otel.resource_attributes(settings, host_name="   ", kind=otel.ResourceKind.LOGS)
    trace_attrs = otel.resource_attributes(
        settings,
        host_name="opentelemetry-test",
        kind=otel.ResourceKind.TRACES,
    )

    assert otel.HOST_NAME_ATTRIBUTE not in dict(missing)
    assert otel.HOST_NAME_ATTRIBUTE not in dict(empty)
    assert otel.HOST_NAME_ATTRIBUTE not in dict(trace_attrs)


def test_log_export_target_excludes_trace_safe_events() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/provider.rs, src/targets.rs
    # Rust test: tests::log_export_target_excludes_trace_safe_events
    # Contract: log export targets include codex_otel targets except trace_safe targets.
    assert otel.is_log_export_target("codex_otel.log_only")
    assert otel.is_log_export_target("codex_otel.network_proxy")
    assert not otel.is_log_export_target("codex_otel.trace_safe")
    assert not otel.is_log_export_target("codex_otel.trace_safe.debug")


def test_trace_export_target_only_includes_trace_safe_prefix() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/provider.rs, src/targets.rs
    # Rust test: tests::trace_export_target_only_includes_trace_safe_prefix
    # Contract: trace-safe target detection only accepts the codex_otel.trace_safe prefix.
    assert otel.is_trace_safe_target("codex_otel.trace_safe")
    assert otel.is_trace_safe_target("codex_otel.trace_safe.summary")
    assert not otel.is_trace_safe_target("codex_otel.log_only")
    assert not otel.is_trace_safe_target("codex_otel.network_proxy")


def test_provider_export_filters_project_rust_target_policy() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Anchors: OtelProvider::{codex_export_filter,log_export_filter,trace_export_filter}
    # Contract: codex/log filters use log target policy; trace filter accepts spans or trace-safe targets.
    class Meta:
        def __init__(self, target: str, is_span: bool = False) -> None:
            self._target = target
            self._is_span = is_span

        def target(self) -> str:
            return self._target

        def is_span(self) -> bool:
            return self._is_span

    assert otel.codex_export_filter(Meta("codex_otel.log_only"))
    assert otel.log_export_filter(Meta("codex_otel.network_proxy"))
    assert not otel.log_export_filter(Meta("codex_otel.trace_safe"))
    assert otel.trace_export_filter(Meta("ordinary_target", is_span=True))
    assert otel.trace_export_filter(Meta("codex_otel.trace_safe.summary"))
    assert not otel.trace_export_filter(Meta("codex_otel.log_only"))


def test_otlp_build_header_map_skips_invalid_names_and_values() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/otlp.rs
    # Anchor: build_header_map uses HeaderName::from_bytes and HeaderValue::from_str.
    # Contract: invalid header names/values are ignored instead of failing the whole map.
    headers = otel.build_header_map(
        {
            "Authorization": "Bearer token",
            "x-trace-id": "abc123",
            "bad header": "skipped-name",
            "bad\nname": "skipped-name",
            "x-bad-value": "line\r\nbreak",
            "x-tab": "one\ttwo",
        }
    )

    assert headers == {
        "authorization": "Bearer token",
        "x-trace-id": "abc123",
        "x-tab": "one\ttwo",
    }


def test_otlp_resolve_timeout_prefers_signal_then_global_then_default() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/otlp.rs
    # Anchor: resolve_otlp_timeout, read_timeout_env.
    # Contract: signal-specific timeout wins, then OTEL_EXPORTER_OTLP_TIMEOUT, then Rust default.
    env = {
        "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "1234",
        otel.OTEL_EXPORTER_OTLP_TIMEOUT: "5678",
    }

    assert otel.resolve_otlp_timeout("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", env) == 1234
    assert otel.resolve_otlp_timeout("OTEL_EXPORTER_OTLP_METRICS_TIMEOUT", env) == 5678
    assert (
        otel.resolve_otlp_timeout("OTEL_EXPORTER_OTLP_METRICS_TIMEOUT", {})
        == otel.OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS
        == 10_000
    )


def test_otlp_timeout_ignores_negative_and_unparseable_env_values() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/otlp.rs
    # Anchor: read_timeout_env parses i64 and ignores negative/unparseable values.
    env = {
        "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT": "-1",
        otel.OTEL_EXPORTER_OTLP_TIMEOUT: "not-a-number",
    }

    assert (
        otel.resolve_otlp_timeout("OTEL_EXPORTER_OTLP_TRACES_TIMEOUT", env)
        == otel.OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS
    )


def test_otel_provider_disabled_exporters_clear_tracestate_without_validating_it() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Anchor: OtelProvider::from.
    # Contract: when log, trace, and resolved metrics exporters are disabled,
    # Rust clears process-global tracestate and returns Ok(None) before
    # validating the configured tracestate map.
    otel._reset_global_otel_state_for_tests()
    otel.set_tracestate_entries({"example": {"alpha": "old"}})
    settings = _test_otel_settings()
    settings.tracestate = {"BadKey": {"alpha": "one\ntwo"}}

    provider = otel.OtelProvider.from_settings(settings)

    assert provider is None
    assert otel.configured_tracestate_entries() == {}
    assert otel.global_metrics() is None
    assert otel.global_statsig_metrics_settings() is None


def test_otel_provider_trace_path_validates_span_attributes_before_installing_state() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Anchor: OtelProvider::from.
    # Contract: trace-enabled provider setup validates span attributes before
    # installing tracestate or mutating process-global provider state.
    otel._reset_global_otel_state_for_tests()
    settings = _test_otel_settings()
    settings.trace_exporter = otel.OtelExporter.OtlpHttp("http://127.0.0.1:1/v1/traces")
    settings.span_attributes = {"": "configured-value"}
    settings.tracestate = {"example": {"alpha": "new"}}

    with pytest.raises(ValueError, match="span attribute key"):
        otel.OtelProvider.from_settings(settings)

    assert otel.configured_tracestate_entries() == {}
    assert otel.global_metrics() is None


def test_otel_provider_rejects_header_unsafe_configured_tracestate_before_installing() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Rust test: tests/suite/otlp_http_loopback.rs::otel_provider_rejects_header_unsafe_configured_tracestate
    # Contract: provider setup rejects header-unsafe configured tracestate
    # values and does not install the invalid entries globally.
    otel._reset_global_otel_state_for_tests()
    settings = _test_otel_settings()
    settings.trace_exporter = otel.OtelExporter.OtlpHttp("http://127.0.0.1:1/v1/traces")
    settings.tracestate = {"example": {"alpha": "one\ntwo"}}

    with pytest.raises(ValueError, match="configured tracestate value"):
        otel.OtelProvider.from_settings(settings)

    assert otel.configured_tracestate_entries() == {}


def test_otel_provider_metrics_exporter_installs_global_metrics_client() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Anchor: OtelProvider::from metrics setup branch.
    # Contract: enabled metrics exporters create a MetricsConfig::otlp client,
    # preserve runtime-reader settings, install it globally, and install
    # configured tracestate after validation.
    otel._reset_global_otel_state_for_tests()
    settings = _test_otel_settings()
    settings.metrics_exporter = otel.OtelExporter.OtlpHttp(
        "http://127.0.0.1:1/v1/metrics",
        headers={"authorization": "Bearer token"},
    )
    settings.runtime_metrics = True
    settings.tracestate = {"example": {"alpha": "one"}}

    provider = otel.OtelProvider.from_settings(settings)

    assert provider is not None
    assert provider.logger is None
    assert provider.tracer is None
    metrics = provider.metrics()
    assert metrics is otel.global_metrics()
    assert metrics is not None
    assert metrics.config is not None
    assert metrics.config.runtime_reader is True
    assert metrics.config.exporter.kind == "otlp"
    assert metrics.config.exporter.exporter == settings.metrics_exporter
    assert otel.configured_tracestate_entries() == {"example": {"alpha": "one"}}
    timer = otel.start_global_timer("codex.provider.test", [("source", "unit")])
    timer.record([("result", "ok")])
    assert metrics.duration_records[-1].name == "codex.provider.test"
    provider.shutdown()
    assert metrics.shutdown_called is True


def test_routing_policy_user_prompt_log_and_trace_shapes_match_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_user_prompt_log_and_trace_events
    # Contract: prompt text and user identifiers are log-only; trace event keeps prompt length and input counts.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.API_KEY,
        "codex_exec",
        True,
        "tty",
        "cli",
    )

    manager.user_prompt(
        [
            {"type": "Text", "text": "super secret prompt"},
            {"type": "Image", "image_url": "https://example.com/image.png"},
            {"type": "LocalImage", "path": "/tmp/secret.png"},
        ]
    )

    assert manager.log_events[0]["target"] == otel.OTEL_LOG_ONLY_TARGET
    assert manager.log_events[0]["event.name"] == "codex.user_prompt"
    assert manager.log_events[0]["prompt"] == "super secret prompt"
    assert manager.log_events[0]["user.email"] == "engineer@example.com"
    assert manager.trace_events[0]["target"] == otel.OTEL_TRACE_SAFE_TARGET
    assert manager.trace_events[0]["event.name"] == "codex.user_prompt"
    assert manager.trace_events[0]["prompt_length"] == "19"
    assert manager.trace_events[0]["text_input_count"] == "1"
    assert manager.trace_events[0]["image_input_count"] == "1"
    assert manager.trace_events[0]["local_image_input_count"] == "1"
    assert "prompt" not in manager.trace_events[0]
    assert "user.email" not in manager.trace_events[0]
    assert "user.account_id" not in manager.trace_events[0]


def test_routing_policy_tool_result_log_and_trace_shapes_match_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_tool_result_log_and_trace_events
    # Contract: arguments/output and MCP identity are log-only; trace event keeps lengths/counts and origin summary.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.API_KEY,
        "codex_exec",
        True,
        "tty",
        "cli",
    )
    metrics = otel.MetricsClient()
    manager.with_metrics_without_metadata_tags(metrics)

    manager.tool_result_with_tags(
        "shell",
        "call-1",
        "secret arguments",
        42,
        True,
        "secret output\nsecond line",
        [],
        [("mcp_server", "internal-mcp"), ("mcp_server_origin", "stdio")],
    )

    assert manager.log_events[0]["target"] == otel.OTEL_LOG_ONLY_TARGET
    assert manager.log_events[0]["event.name"] == "codex.tool_result"
    assert manager.log_events[0]["arguments"] == "secret arguments"
    assert manager.log_events[0]["output"] == "secret output\nsecond line"
    assert manager.log_events[0]["mcp_server"] == "internal-mcp"
    assert manager.log_events[0]["mcp_server_origin"] == "stdio"
    assert manager.trace_events[0]["target"] == otel.OTEL_TRACE_SAFE_TARGET
    assert manager.trace_events[0]["event.name"] == "codex.tool_result"
    assert manager.trace_events[0]["arguments_length"] == "16"
    assert manager.trace_events[0]["output_length"] == "25"
    assert manager.trace_events[0]["output_line_count"] == "2"
    assert manager.trace_events[0]["tool_origin"] == "mcp"
    assert manager.trace_events[0]["mcp_tool"] == "true"
    assert "arguments" not in manager.trace_events[0]
    assert "output" not in manager.trace_events[0]
    assert "mcp_server" not in manager.trace_events[0]
    assert "mcp_server_origin" not in manager.trace_events[0]
    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            otel.TOOL_CALL_COUNT_METRIC,
            1,
            [("success", "true"), ("tool", "shell")],
        )
    ]


def test_routing_policy_auth_recovery_log_and_trace_shapes_match_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_auth_recovery_log_and_trace_events
    # Contract: auth recovery routing emits the same auth fields to log and trace events.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.CHATGPT,
        "codex_exec",
        True,
        "tty",
        "cli",
    )

    manager.record_auth_recovery(
        "managed",
        "reload",
        "recovery_succeeded",
        "req-401",
        "ray-401",
        "missing_authorization_header",
        "token_expired",
        None,
        True,
    )

    for event in (manager.log_events[0], manager.trace_events[0]):
        assert event["event.name"] == "codex.auth_recovery"
        assert event["auth.mode"] == "managed"
        assert event["auth.step"] == "reload"
        assert event["auth.outcome"] == "recovery_succeeded"
        assert event["auth.request_id"] == "req-401"
        assert event["auth.cf_ray"] == "ray-401"
        assert event["auth.error"] == "missing_authorization_header"
        assert event["auth.error_code"] == "token_expired"
        assert event["auth.state_changed"] == "true"
        assert "auth.recovery_reason" not in event

    assert manager.log_events[0]["target"] == otel.OTEL_LOG_ONLY_TARGET
    assert manager.trace_events[0]["target"] == otel.OTEL_TRACE_SAFE_TARGET


def _auth_env_metadata() -> otel.AuthEnvTelemetryMetadata:
    return otel.AuthEnvTelemetryMetadata(
        openai_api_key_env_present=True,
        codex_api_key_env_present=False,
        codex_api_key_env_enabled=True,
        provider_env_key_name="configured",
        provider_env_key_present=True,
        refresh_token_url_override_present=True,
    )


def test_routing_policy_api_request_auth_observability_matches_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_api_request_auth_observability
    # Contract: conversation/api request auth metadata is routed to both log and trace events.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.CHATGPT,
        "codex_exec",
        True,
        "tty",
        "cli",
    ).with_auth_env(_auth_env_metadata())
    metrics = otel.MetricsClient()
    manager.with_metrics_without_metadata_tags(metrics)

    manager.conversation_starts(
        "openai",
        reasoning_summary="auto",
        approval_policy="never",
        sandbox_policy="danger-full-access",
        mcp_servers=[],
    )
    manager.record_api_request(
        1,
        401,
        "http 401",
        42,
        auth_header_attached=True,
        auth_header_name="authorization",
        retry_after_unauthorized=True,
        recovery_mode="managed",
        recovery_phase="refresh_token",
        endpoint="/responses",
        request_id="req-401",
        cf_ray="ray-401",
        auth_error="missing_authorization_header",
        auth_error_code="token_expired",
    )

    conversation_log = manager.log_events[0]
    assert conversation_log["event.name"] == "codex.conversation_starts"
    assert conversation_log["auth.env_openai_api_key_present"] == "true"
    assert conversation_log["auth.env_provider_key_name"] == "configured"
    request_log = manager.log_events[1]
    assert request_log["event.name"] == "codex.api_request"
    assert request_log["auth.header_attached"] == "true"
    assert request_log["auth.header_name"] == "authorization"
    assert request_log["auth.retry_after_unauthorized"] == "true"
    assert request_log["auth.recovery_mode"] == "managed"
    assert request_log["auth.recovery_phase"] == "refresh_token"
    assert request_log["endpoint"] == "/responses"
    assert request_log["auth.error"] == "missing_authorization_header"
    assert request_log["auth.env_codex_api_key_enabled"] == "true"
    assert request_log["auth.env_refresh_token_url_override_present"] == "true"
    conversation_trace = manager.trace_events[0]
    assert conversation_trace["auth.env_provider_key_present"] == "true"
    request_trace = manager.trace_events[1]
    assert request_trace["auth.header_attached"] == "true"
    assert request_trace["auth.header_name"] == "authorization"
    assert request_trace["auth.retry_after_unauthorized"] == "true"
    assert request_trace["endpoint"] == "/responses"
    assert request_trace["auth.env_openai_api_key_present"] == "true"
    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            otel.API_CALL_COUNT_METRIC,
            1,
            [("status", "401"), ("success", "false")],
        )
    ]


def test_routing_policy_websocket_connect_auth_observability_matches_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_websocket_connect_auth_observability
    # Contract: websocket connect auth metadata is routed to log and trace events.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.CHATGPT,
        "codex_exec",
        True,
        "tty",
        "cli",
    ).with_auth_env(_auth_env_metadata())

    manager.record_websocket_connect(
        17,
        status=401,
        error="http 401",
        auth_header_attached=True,
        auth_header_name="authorization",
        retry_after_unauthorized=True,
        recovery_mode="managed",
        recovery_phase="reload",
        endpoint="/responses",
        connection_reused=False,
        request_id="req-ws-401",
        cf_ray="ray-ws-401",
        auth_error="missing_authorization_header",
        auth_error_code="token_expired",
    )

    connect_log = manager.log_events[0]
    assert connect_log["event.name"] == "codex.websocket_connect"
    assert connect_log["auth.header_attached"] == "true"
    assert connect_log["auth.header_name"] == "authorization"
    assert connect_log["auth.error"] == "missing_authorization_header"
    assert connect_log["endpoint"] == "/responses"
    assert connect_log["auth.connection_reused"] == "false"
    assert connect_log["auth.env_provider_key_name"] == "configured"
    connect_trace = manager.trace_events[0]
    assert connect_trace["auth.recovery_phase"] == "reload"
    assert connect_trace["auth.env_refresh_token_url_override_present"] == "true"


def test_routing_policy_websocket_request_transport_observability_matches_rust() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/events/session_telemetry.rs, tests/suite/otel_export_routing_policy.rs
    # Rust test: otel_export_routing_policy_routes_websocket_request_transport_observability
    # Contract: websocket request transport metadata and auth env tags route to log and trace events.
    manager = otel.SessionTelemetry.new(
        "thread-id",
        "gpt-5.1",
        "gpt-5.1",
        "account-id",
        "engineer@example.com",
        otel.TelemetryAuthMode.CHATGPT,
        "codex_exec",
        True,
        "tty",
        "cli",
    ).with_auth_env(_auth_env_metadata())
    metrics = otel.MetricsClient()
    manager.with_metrics_without_metadata_tags(metrics)

    manager.record_websocket_request(23, "stream error", connection_reused=True)

    request_log = manager.log_events[0]
    assert request_log["event.name"] == "codex.websocket_request"
    assert request_log["auth.connection_reused"] == "true"
    assert request_log["error.message"] == "stream error"
    assert request_log["auth.env_openai_api_key_present"] == "true"
    request_trace = manager.trace_events[0]
    assert request_trace["auth.connection_reused"] == "true"
    assert request_trace["auth.env_provider_key_present"] == "true"
    assert metrics.counter_records == [
        otel.MetricsCounterRecord(
            otel.WEBSOCKET_REQUEST_COUNT_METRIC,
            1,
            [("success", "false")],
        )
    ]


def test_record_responses_type_projection_matches_rust_source_contract() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/events/session_telemetry.rs
    # Anchor: SessionTelemetry::{responses_type,responses_item_type}.
    # Contract: ResponseEvent variants and ResponseItem variants map to the
    # stable otel.name strings used by the Rust responses span recorder.
    cases = [
        (ResponseEvent("created"), "created"),
        (ResponseEvent("completed", {"token_usage": None}), "completed"),
        (ResponseEvent("output_text_delta", "hello"), "text_delta"),
        (ResponseEvent("tool_call_input_delta", {"delta": "x"}), "tool_input_delta"),
        (ResponseEvent("reasoning_summary_delta", {"delta": "x"}), "reasoning_summary_delta"),
        (ResponseEvent("reasoning_content_delta", {"delta": "x"}), "reasoning_content_delta"),
        (ResponseEvent("reasoning_summary_part_added", {"summary_index": 0}), "reasoning_summary_part_added"),
        (ResponseEvent("server_model", "gpt-5"), "server_model"),
        (ResponseEvent("model_verifications", []), "model_verifications"),
        (ResponseEvent("server_reasoning_included", True), "server_reasoning_included"),
        (ResponseEvent("rate_limits", object()), "rate_limits"),
        (ResponseEvent("models_etag", "etag"), "models_etag"),
        (ResponseEvent("output_item_done", {"type": "message", "role": "assistant"}), "message_from_assistant"),
        (ResponseEvent("output_item_added", {"type": "function_call", "name": "shell"}), "function_call"),
    ]

    for event, expected in cases:
        assert otel.SessionTelemetry.responses_type(event) == expected

    item_cases = {
        "reasoning": "reasoning",
        "local_shell_call": "local_shell_call",
        "tool_search_call": "tool_search_call",
        "function_call_output": "function_call_output",
        "tool_search_output": "tool_search_output",
        "custom_tool_call": "custom_tool_call",
        "custom_tool_call_output": "custom_tool_call_output",
        "web_search_call": "web_search_call",
        "image_generation_call": "image_generation_call",
        "compaction": "compaction",
        "compaction_trigger": "compaction_trigger",
        "context_compaction": "context_compaction",
        "other": "other",
    }
    for item_type, expected in item_cases.items():
        assert otel.SessionTelemetry.responses_item_type({"type": item_type}) == expected


def test_record_responses_records_function_call_and_completed_token_usage_like_rust() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/events/session_telemetry.rs
    # Anchor: SessionTelemetry::record_responses.
    # Contract: output item events update the responses span's otel.name/from
    # fields and function-call tool name; completed events with token usage
    # record Rust's gen_ai/codex token fields.
    manager = otel.SessionTelemetry.new(
        "conversation-id",
        "gpt-5",
        "gpt-5",
        None,
        None,
        None,
        "codex_cli_rs",
        True,
        "tty",
        "cli",
    )
    span: dict[str, object] = {}

    manager.record_responses(
        span,
        ResponseEvent("output_item_added", {"type": "function_call", "name": "run_shell_command"}),
    )

    assert span["otel.name"] == "function_call"
    assert span["from"] == "output_item_added"
    assert span["tool_name"] == "run_shell_command"

    manager.record_responses(
        span,
        ResponseEvent(
            "completed",
            {
                "response_id": "resp-1",
                "token_usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 40,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 7,
                    "total_tokens": 125,
                },
                "end_turn": True,
            },
        ),
    )

    assert span["otel.name"] == "completed"
    assert span["gen_ai.usage.input_tokens"] == 100
    assert span["gen_ai.usage.cache_read.input_tokens"] == 40
    assert span["gen_ai.usage.output_tokens"] == 25
    assert span["codex.usage.reasoning_output_tokens"] == 7
    assert span["codex.usage.total_tokens"] == 125


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


def test_metrics_client_sends_enqueued_metric_like_send_suite() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module/test: src/metrics/client.rs, tests/suite/send.rs::client_sends_enqueued_metric.
    # Contract: a counter enqueued before shutdown is present in the exported/snapshot metric set.
    metrics = otel.MetricsClient.new(
        otel.MetricsConfig.in_memory("test", "codex-cli", "1.2.3").with_runtime_reader()
    )

    metrics.counter("codex.turns", 1, [("model", "gpt-5.1")])
    metrics.shutdown()

    assert metrics.snapshot() == {
        "metrics": [
            {
                "name": "codex.turns",
                "value": 1,
                "tags": [("model", "gpt-5.1")],
                "kind": "counter",
            }
        ]
    }


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


def test_otlp_http_exporter_sends_metrics_to_collector() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust module: src/metrics/client.rs
    # Rust test: tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_metrics_to_collector
    # Contract: MetricsClient::shutdown sends JSON OTLP HTTP metrics to the
    # configured endpoint; collector sees /v1/metrics, application/json, and
    # a body containing the metric name.
    captured: dict[str, object] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            captured["path"] = self.path
            captured["content_type"] = self.headers.get("content-type")
            captured["body"] = body
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/metrics"
        metrics = otel.MetricsClient.new(
            otel.MetricsConfig.otlp(
                "test",
                "codex-cli",
                "1.2.3",
                otel.OtelExporter.OtlpHttp(endpoint, protocol=otel.OtelHttpProtocol.JSON),
            )
        )

        metrics.counter("codex.turns", 1, [("source", "test")])
        metrics.shutdown()
        thread.join(timeout=2)

        assert metrics.last_export_error is None
        assert captured["path"] == "/v1/metrics"
        assert str(captured["content_type"]).startswith("application/json")
        assert b"codex.turns" in captured["body"]
    finally:
        server.server_close()
        thread.join(timeout=2)


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


def test_session_telemetry_records_startup_phase_metric_log_and_trace() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/events/session_telemetry.rs::record_startup_phase.
    # Contract: startup phases emit one duration metric plus matching log and trace events.
    metrics = otel.MetricsClient()
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
    ).with_metrics_without_metadata_tags(metrics)

    manager.record_startup_phase("load_config", 37, "ok")

    assert metrics.duration_records == [
        otel.MetricsDurationRecord(
            otel.STARTUP_PHASE_DURATION_METRIC,
            37,
            [("phase", "load_config"), ("status", "ok")],
        )
    ]
    assert manager.log_events[-1]["target"] == otel.OTEL_LOG_ONLY_TARGET
    assert manager.log_events[-1]["event.name"] == "codex.startup_phase"
    assert manager.log_events[-1]["startup.phase"] == "load_config"
    assert manager.log_events[-1]["startup.status"] == "ok"
    assert manager.log_events[-1]["duration_ms"] == "37"
    assert manager.trace_events[-1]["target"] == otel.OTEL_TRACE_SAFE_TARGET
    assert manager.trace_events[-1]["event.name"] == "codex.startup_phase"
    assert manager.trace_events[-1]["startup.phase"] == "load_config"
    assert manager.trace_events[-1]["startup.status"] == "ok"
    assert manager.trace_events[-1]["duration_ms"] == "37"


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


def test_otlp_http_exporter_sends_traces_to_collector() -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-otel
    # Rust modules: src/provider.rs, src/trace_context.rs
    # Rust test: tests/suite/otlp_http_loopback.rs::otlp_http_exporter_sends_traces_to_collector
    # Contract: trace provider exports JSON to /v1/traces, configured
    # tracestate fields are merged into propagated current-span context, and
    # configured span attributes plus service name are present in the body.
    captured: dict[str, object] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            captured["path"] = self.path
            captured["content_type"] = self.headers.get("content-type")
            captured["body"] = body
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            return

    otel._reset_global_otel_state_for_tests()
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/traces"
        settings = _test_otel_settings()
        settings.service_name = "codex-cli"
        settings.service_version = "1.2.3"
        settings.trace_exporter = otel.OtelExporter.OtlpHttp(endpoint, protocol=otel.OtelHttpProtocol.JSON)
        settings.span_attributes = {"test.configured_attribute": "configured-value"}
        settings.tracestate = {"example": {"alpha": "one", "beta": "two"}}
        provider = otel.OtelProvider.from_settings(settings)
        assert provider is not None
        span = provider.trace_span(
            "trace-loopback",
            {
                "otel.name": "trace-loopback",
                "otel.kind": "server",
                "rpc.system": "jsonrpc",
                "rpc.method": "trace-loopback",
            },
        )

        assert otel.set_parent_from_w3c_trace_context(
            span,
            otel.W3cTraceContext(
                traceparent="00-00000000000000000000000000000001-0000000000000002-01",
                tracestate="example=alpha:zero;keep:yes,other=value",
            ),
        )
        with span:
            propagated_trace = otel.current_span_w3c_trace_context()

        assert propagated_trace is not None
        assert propagated_trace.tracestate == "example=alpha:one;keep:yes;beta:two,other=value"

        provider.shutdown()
        thread.join(timeout=2)

        assert provider.last_trace_export_error is None
        assert captured["path"] == "/v1/traces"
        assert str(captured["content_type"]).startswith("application/json")
        body = captured["body"]
        assert b"trace-loopback" in body
        assert b"codex-cli" in body
        assert b"test.configured_attribute" in body
        assert b"configured-value" in body
    finally:
        server.server_close()
        thread.join(timeout=2)


def test_otlp_http_log_exporter_sends_logs_to_collector() -> None:
    # Source: rust_contract
    # Rust crate: codex-otel
    # Rust module: src/provider.rs
    # Anchor: build_logger OtlpHttp(Json) branch, OtelProvider::from, and
    # OtelProvider::shutdown.
    # Contract: an enabled OTLP HTTP JSON log exporter builds a logger provider
    # from settings and flushes log records to the configured collector endpoint
    # with configured headers during provider shutdown.
    captured: dict[str, object] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("content-length", "0")))
            captured["path"] = self.path
            captured["content_type"] = self.headers.get("content-type")
            captured["authorization"] = self.headers.get("authorization")
            captured["body"] = body
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, _format: str, *args: object) -> None:
            return

    otel._reset_global_otel_state_for_tests()
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/logs"
        settings = _test_otel_settings()
        settings.service_name = "codex-cli"
        settings.service_version = "1.2.3"
        settings.environment = "unit-test"
        settings.exporter = otel.OtelExporter.OtlpHttp(
            endpoint,
            headers={"authorization": "Bearer log-token"},
            protocol=otel.OtelHttpProtocol.JSON,
        )
        provider = otel.OtelProvider.from_settings(settings)
        assert provider is not None
        assert provider.logger is not None

        provider.emit_log_event(
            "codex.log_loopback",
            {"target": otel.OTEL_LOG_ONLY_TARGET, "request_id": "req-123"},
            body="log-loopback-body",
        )
        provider.shutdown()
        thread.join(timeout=2)

        assert provider.last_log_export_error is None
        assert captured["path"] == "/v1/logs"
        assert str(captured["content_type"]).startswith("application/json")
        assert captured["authorization"] == "Bearer log-token"
        body = captured["body"]
        assert b"resourceLogs" in body
        assert b"codex.log_loopback" in body
        assert b"log-loopback-body" in body
        assert b"codex-cli" in body
        assert b"unit-test" in body
        assert b"req-123" in body
    finally:
        server.server_close()
        thread.join(timeout=2)


def test_merge_tracestate_entries_validates_existing_and_configured_state() -> None:
    # Rust crate/module: codex-otel src/trace_context.rs.
    # Contract: invalid existing tracestate is ignored by Rust during propagation,
    # while invalid configured entries are rejected before installation.
    assert otel.merge_tracestate_entries(None, {"example": {"alpha": "one"}}) == "example=alpha:one"
    assert otel.merge_tracestate_entries("not a member", {"example": {"alpha": "one"}}) == "example=alpha:one"

    with pytest.raises(ValueError, match="configured tracestate value"):
        otel.merge_tracestate_entries("other=value", {"example": {"alpha": "bad,value"}})
