"""Parity tests for codex-rs/tui/src/history_cell/separators.rs."""

# Rust source: codex/codex-rs/tui/src/history_cell/separators.rs

from pycodex.tui.history_cell.separators import (
    DIVIDER,
    FinalMessageSeparator,
    RuntimeMetricTotals,
    RuntimeMetricsSummary,
    format_duration_ms,
    line_text,
    pluralize,
    runtime_metrics_label,
)


def test_format_duration_ms_matches_rust_threshold() -> None:
    assert format_duration_ms(999) == "999ms"
    assert format_duration_ms(1000) == "1.0s"
    assert format_duration_ms(2450) == "2.5s"


def test_pluralize_matches_rust_count_rule() -> None:
    assert pluralize(1, "call", "calls") == "call"
    assert pluralize(0, "call", "calls") == "calls"
    assert pluralize(2, "call", "calls") == "calls"


def test_runtime_metrics_label_includes_all_non_empty_metrics() -> None:
    summary = RuntimeMetricsSummary(
        tool_calls=RuntimeMetricTotals(count=3, duration_ms=2450),
        api_calls=RuntimeMetricTotals(count=2, duration_ms=1200),
        streaming_events=RuntimeMetricTotals(count=6, duration_ms=900),
        websocket_calls=RuntimeMetricTotals(count=1, duration_ms=700),
        websocket_events=RuntimeMetricTotals(count=4, duration_ms=1200),
        responses_api_overhead_ms=650,
        responses_api_inference_time_ms=1940,
        responses_api_engine_iapi_ttft_ms=410,
        responses_api_engine_service_ttft_ms=460,
        responses_api_engine_iapi_tbt_ms=1180,
        responses_api_engine_service_tbt_ms=1240,
    )

    label = runtime_metrics_label(summary)

    assert label is not None
    assert "Local tools: 3 calls (2.5s)" in label
    assert "Inference: 2 calls (1.2s)" in label
    assert "WebSocket: 1 events send (700ms)" in label
    assert "Streams: 6 events (900ms)" in label
    assert "4 events received (1.2s)" in label
    assert "Responses API overhead: 650ms" in label
    assert "Responses API inference: 1.9s" in label
    assert "TTFT: 410ms (iapi) 460ms (service)" in label
    assert "TBT: 1.2s (iapi) 1.2s (service)" in label


def test_final_separator_hides_short_worked_label_but_shows_metrics() -> None:
    cell = FinalMessageSeparator.new(
        12,
        {"tool_calls": {"count": 3, "duration_ms": 2450}},
    )

    rendered = line_text(cell.display_lines(600)[0])
    raw = line_text(cell.raw_lines()[0])

    assert "Worked for" not in rendered
    assert "Local tools: 3 calls (2.5s)" in rendered
    assert "Worked for" not in raw


def test_final_separator_includes_worked_label_after_one_minute() -> None:
    cell = FinalMessageSeparator.new(61, None)

    rendered = line_text(cell.display_lines(80)[0])
    raw = line_text(cell.raw_lines()[0])

    assert "Worked for 1m 01s" in rendered
    assert raw == "Worked for 1m 01s"


def test_final_separator_without_labels_is_visual_only() -> None:
    cell = FinalMessageSeparator.new(60, None)

    assert line_text(cell.display_lines(5)[0]) == DIVIDER * 5
    assert cell.raw_lines() == []


def test_final_separator_truncates_to_width() -> None:
    cell = FinalMessageSeparator.new(61, None)

    assert len(line_text(cell.display_lines(4)[0])) == 4
