"""Turn separators and runtime-metrics labels for transcript history.

Upstream source: ``codex/codex-rs/tui/src/history_cell/separators.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from ..status_indicator_widget import fmt_elapsed_compact

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::separators",
    source="codex/codex-rs/tui/src/history_cell/separators.rs",
)

DIVIDER = "\u2500"
LABEL_SEPARATOR = " \u2022 "


@dataclass(frozen=True)
class RuntimeMetricTotals:
    count: int = 0
    duration_ms: int = 0

    @classmethod
    def coerce(cls, value: Any) -> "RuntimeMetricTotals":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        if isinstance(value, dict):
            return cls(
                count=int(value.get("count", 0) or 0),
                duration_ms=int(value.get("duration_ms", 0) or 0),
            )
        return cls(
            count=int(getattr(value, "count", 0) or 0),
            duration_ms=int(getattr(value, "duration_ms", 0) or 0),
        )


@dataclass(frozen=True)
class RuntimeMetricsSummary:
    tool_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    api_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    websocket_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    streaming_events: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    websocket_events: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    responses_api_overhead_ms: int = 0
    responses_api_inference_time_ms: int = 0
    responses_api_engine_iapi_ttft_ms: int = 0
    responses_api_engine_service_ttft_ms: int = 0
    responses_api_engine_iapi_tbt_ms: int = 0
    responses_api_engine_service_tbt_ms: int = 0

    @classmethod
    def coerce(cls, value: Any) -> "RuntimeMetricsSummary | None":
        if value is None:
            return None
        if isinstance(value, cls):
            return value

        def get(name: str, default: Any = 0) -> Any:
            if isinstance(value, dict):
                return value.get(name, default)
            return getattr(value, name, default)

        return cls(
            tool_calls=RuntimeMetricTotals.coerce(get("tool_calls")),
            api_calls=RuntimeMetricTotals.coerce(get("api_calls")),
            websocket_calls=RuntimeMetricTotals.coerce(get("websocket_calls")),
            streaming_events=RuntimeMetricTotals.coerce(get("streaming_events")),
            websocket_events=RuntimeMetricTotals.coerce(get("websocket_events")),
            responses_api_overhead_ms=int(get("responses_api_overhead_ms", 0) or 0),
            responses_api_inference_time_ms=int(
                get("responses_api_inference_time_ms", 0) or 0
            ),
            responses_api_engine_iapi_ttft_ms=int(
                get("responses_api_engine_iapi_ttft_ms", 0) or 0
            ),
            responses_api_engine_service_ttft_ms=int(
                get("responses_api_engine_service_ttft_ms", 0) or 0
            ),
            responses_api_engine_iapi_tbt_ms=int(
                get("responses_api_engine_iapi_tbt_ms", 0) or 0
            ),
            responses_api_engine_service_tbt_ms=int(
                get("responses_api_engine_service_tbt_ms", 0) or 0
            ),
        )


def format_duration_ms(duration_ms: int) -> str:
    duration_ms = int(duration_ms)
    if duration_ms >= 1000:
        return f"{duration_ms / 1000:.1f}s"
    return f"{duration_ms}ms"


def pluralize(count: int, singular: str, plural: str) -> str:
    return singular if int(count) == 1 else plural


def runtime_metrics_label(summary: RuntimeMetricsSummary | dict[str, Any] | Any) -> str | None:
    summary = RuntimeMetricsSummary.coerce(summary)
    if summary is None:
        return None

    parts: list[str] = []
    if summary.tool_calls.count > 0:
        duration = format_duration_ms(summary.tool_calls.duration_ms)
        calls = pluralize(summary.tool_calls.count, "call", "calls")
        parts.append(f"Local tools: {summary.tool_calls.count} {calls} ({duration})")
    if summary.api_calls.count > 0:
        duration = format_duration_ms(summary.api_calls.duration_ms)
        calls = pluralize(summary.api_calls.count, "call", "calls")
        parts.append(f"Inference: {summary.api_calls.count} {calls} ({duration})")
    if summary.websocket_calls.count > 0:
        duration = format_duration_ms(summary.websocket_calls.duration_ms)
        parts.append(
            f"WebSocket: {summary.websocket_calls.count} events send ({duration})"
        )
    if summary.streaming_events.count > 0:
        duration = format_duration_ms(summary.streaming_events.duration_ms)
        stream_label = pluralize(summary.streaming_events.count, "Stream", "Streams")
        events = pluralize(summary.streaming_events.count, "event", "events")
        parts.append(
            f"{stream_label}: {summary.streaming_events.count} {events} ({duration})"
        )
    if summary.websocket_events.count > 0:
        duration = format_duration_ms(summary.websocket_events.duration_ms)
        parts.append(f"{summary.websocket_events.count} events received ({duration})")
    if summary.responses_api_overhead_ms > 0:
        duration = format_duration_ms(summary.responses_api_overhead_ms)
        parts.append(f"Responses API overhead: {duration}")
    if summary.responses_api_inference_time_ms > 0:
        duration = format_duration_ms(summary.responses_api_inference_time_ms)
        parts.append(f"Responses API inference: {duration}")

    ttft_parts: list[str] = []
    if summary.responses_api_engine_iapi_ttft_ms > 0:
        duration = format_duration_ms(summary.responses_api_engine_iapi_ttft_ms)
        ttft_parts.append(f"{duration} (iapi)")
    if summary.responses_api_engine_service_ttft_ms > 0:
        duration = format_duration_ms(summary.responses_api_engine_service_ttft_ms)
        ttft_parts.append(f"{duration} (service)")
    if ttft_parts:
        parts.append(f"TTFT: {' '.join(ttft_parts)}")

    tbt_parts: list[str] = []
    if summary.responses_api_engine_iapi_tbt_ms > 0:
        duration = format_duration_ms(summary.responses_api_engine_iapi_tbt_ms)
        tbt_parts.append(f"{duration} (iapi)")
    if summary.responses_api_engine_service_tbt_ms > 0:
        duration = format_duration_ms(summary.responses_api_engine_service_tbt_ms)
        tbt_parts.append(f"{duration} (service)")
    if tbt_parts:
        parts.append(f"TBT: {' '.join(tbt_parts)}")

    return LABEL_SEPARATOR.join(parts) if parts else None


def _line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def _take_prefix_by_width(text: str, width: int) -> tuple[str, int]:
    used = 0
    out: list[str] = []
    for char in text:
        next_width = _display_width(char)
        if used + next_width > width:
            break
        out.append(char)
        used += next_width
    return "".join(out), used


@dataclass
class FinalMessageSeparator:
    elapsed_seconds: int | None = None
    runtime_metrics: RuntimeMetricsSummary | dict[str, Any] | Any | None = None

    @classmethod
    def new(
        cls,
        elapsed_seconds: int | None,
        runtime_metrics: RuntimeMetricsSummary | dict[str, Any] | Any | None,
    ) -> "FinalMessageSeparator":
        return cls(elapsed_seconds, RuntimeMetricsSummary.coerce(runtime_metrics))

    def _label_parts(self) -> list[str]:
        parts: list[str] = []
        if self.elapsed_seconds is not None and int(self.elapsed_seconds) > 60:
            parts.append(f"Worked for {fmt_elapsed_compact(int(self.elapsed_seconds))}")
        metrics_label = runtime_metrics_label(self.runtime_metrics)
        if metrics_label is not None:
            parts.append(metrics_label)
        return parts

    def display_lines(self, width: int) -> list[Line]:
        width = max(0, int(width))
        label_parts = self._label_parts()
        if not label_parts:
            return [Line.from_spans([Span(DIVIDER * width, "dim")])]

        label = f"{DIVIDER} {LABEL_SEPARATOR.join(label_parts)} {DIVIDER}"
        prefix, label_width = _take_prefix_by_width(label, width)
        suffix = DIVIDER * max(0, width - label_width)
        return [Line.from_spans([Span(prefix + suffix, "dim")])]

    def raw_lines(self) -> list[Line]:
        label_parts = self._label_parts()
        if not label_parts:
            return []
        return [Line.from_text(LABEL_SEPARATOR.join(label_parts))]


def display_lines(cell: FinalMessageSeparator, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: FinalMessageSeparator) -> list[Line]:
    return cell.raw_lines()


def line_text(line: Line) -> str:
    return _line_text(line)


__all__ = [
    "DIVIDER",
    "LABEL_SEPARATOR",
    "FinalMessageSeparator",
    "RUST_MODULE",
    "RuntimeMetricTotals",
    "RuntimeMetricsSummary",
    "display_lines",
    "format_duration_ms",
    "line_text",
    "pluralize",
    "raw_lines",
    "runtime_metrics_label",
]
