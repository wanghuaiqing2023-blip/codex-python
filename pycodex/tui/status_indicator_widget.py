"""Live task status row for ``codex-tui::status_indicator_widget``.

Rust source: ``codex/codex-rs/tui/src/status_indicator_widget.rs``.
Python renders to semantic ``Line`` values instead of mutating a ratatui buffer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, List, Optional

from ._porting import RustTuiModule
from .line_truncation import Line, Span, truncate_line_with_ellipsis_if_overflow, _display_width
from .motion import MotionMode, ReducedMotionIndicator, activity_indicator, shimmer_text
from .text_formatting import capitalize_first
from .wrapping import RtOptions, word_wrap_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="status_indicator_widget",
    source="codex/codex-rs/tui/src/status_indicator_widget.rs",
    status="complete",
)

STATUS_DETAILS_DEFAULT_MAX_LINES = 3
DETAILS_PREFIX = "  │ "


class StatusDetailsCapitalization(Enum):
    CapitalizeFirst = "capitalize_first"
    Preserve = "preserve"


@dataclass(frozen=True)
class KeyBinding:
    label: str

    def into_span(self) -> Span:
        return Span(self.label.lower())


@dataclass
class FrameRequester:
    scheduled: List[float] = field(default_factory=list)

    def schedule_frame(self) -> None:
        self.scheduled.append(0.0)

    def schedule_frame_in(self, delay_seconds: float) -> None:
        self.scheduled.append(delay_seconds)


@dataclass
class AppEventSender:
    interrupted: bool = False

    def interrupt(self) -> None:
        self.interrupted = True


@dataclass
class StatusIndicatorWidget:
    app_event_tx: AppEventSender
    frame_requester: FrameRequester
    animations_enabled: bool
    clock: Callable[[], float] = time.monotonic
    header_text: str = "Working"
    details_text: Optional[str] = None
    details_max_lines: int = STATUS_DETAILS_DEFAULT_MAX_LINES
    inline_message: Optional[str] = None
    show_interrupt_hint: bool = True
    interrupt_binding: Optional[KeyBinding] = field(default_factory=lambda: KeyBinding("esc"))
    elapsed_running: float = 0.0
    last_resume_at: float = field(default_factory=time.monotonic)
    is_paused: bool = False

    @classmethod
    def new(
        cls,
        app_event_tx: Optional[AppEventSender] = None,
        frame_requester: Optional[FrameRequester] = None,
        animations_enabled: bool = True,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> "StatusIndicatorWidget":
        now = clock()
        return cls(
            app_event_tx=app_event_tx or AppEventSender(),
            frame_requester=frame_requester or FrameRequester(),
            animations_enabled=animations_enabled,
            clock=clock,
            last_resume_at=now,
        )

    def interrupt(self) -> None:
        self.app_event_tx.interrupt()

    def update_header(self, header: str) -> None:
        self.header_text = header

    def update_details(
        self,
        details: Optional[str],
        capitalization: StatusDetailsCapitalization,
        max_lines: int,
    ) -> None:
        self.details_max_lines = max(1, int(max_lines))
        if details is None or details == "":
            self.details_text = None
            return
        trimmed = details.lstrip()
        self.details_text = (
            capitalize_first(trimmed)
            if capitalization is StatusDetailsCapitalization.CapitalizeFirst
            else trimmed
        )

    def update_inline_message(self, message: Optional[str]) -> None:
        if message is None:
            self.inline_message = None
            return
        trimmed = message.strip()
        self.inline_message = trimmed if trimmed else None

    def header(self) -> str:
        return self.header_text

    def details(self) -> Optional[str]:
        return self.details_text

    def set_interrupt_hint_visible(self, visible: bool) -> None:
        self.show_interrupt_hint = bool(visible)

    def set_interrupt_binding(self, binding: Any) -> None:
        if binding is None or isinstance(binding, KeyBinding):
            self.interrupt_binding = binding
        else:
            self.interrupt_binding = KeyBinding(str(binding))

    def pause_timer(self) -> None:
        self.pause_timer_at(self.clock())

    def resume_timer(self) -> None:
        self.resume_timer_at(self.clock())

    def pause_timer_at(self, now: float) -> None:
        if self.is_paused:
            return
        self.elapsed_running += max(0.0, now - self.last_resume_at)
        self.is_paused = True

    def resume_timer_at(self, now: float) -> None:
        if not self.is_paused:
            return
        self.last_resume_at = now
        self.is_paused = False
        self.frame_requester.schedule_frame()

    def elapsed_duration_at(self, now: float) -> float:
        elapsed = self.elapsed_running
        if not self.is_paused:
            elapsed += max(0.0, now - self.last_resume_at)
        return elapsed

    def elapsed_seconds_at(self, now: float) -> int:
        return int(self.elapsed_duration_at(now))

    def elapsed_seconds(self) -> int:
        return self.elapsed_seconds_at(self.clock())

    def wrapped_details_lines(self, width: int) -> List[Line]:
        if self.details_text is None or width == 0:
            return []
        prefix_width = _display_width(DETAILS_PREFIX)
        opts = (
            RtOptions.new(int(width))
            .initial_indent(Line([Span(DETAILS_PREFIX, style="dim")]))
            .subsequent_indent(Line([Span(" " * prefix_width, style="dim")]))
            .break_words(True)
        )
        source_lines = [Line([Span(line, style="dim")]) for line in self.details_text.splitlines()]
        out = word_wrap_lines(source_lines, opts)
        if len(out) > self.details_max_lines:
            out = out[: self.details_max_lines]
            content_width = max(1, int(width) - prefix_width)
            max_base_len = max(0, content_width - 1)
            last = out[-1]
            if last.spans:
                span = last.spans[-1]
                out[-1] = Line([
                    *last.spans[:-1],
                    Span(span.content[:max_base_len] + "…", style="dim"),
                ])
        return out

    def desired_height(self, width: int) -> int:
        return 1 + len(self.wrapped_details_lines(width))

    def render_lines(self, width: int, height: Optional[int] = None, now: Optional[float] = None) -> List[Line]:
        if width <= 0 or height == 0:
            return []
        if self.animations_enabled:
            self.frame_requester.schedule_frame_in(0.032)
        render_now = self.clock() if now is None else now
        pretty_elapsed = fmt_elapsed_compact(self.elapsed_seconds_at(render_now))
        motion_mode = MotionMode.from_animations_enabled(self.animations_enabled)

        spans: List[Span] = []
        indicator = activity_indicator(
            self.last_resume_at,
            motion_mode,
            ReducedMotionIndicator.Hidden,
        )
        if indicator is not None:
            spans.append(indicator)
            spans.append(Span(" "))
        spans.extend(shimmer_text(self.header_text, motion_mode))
        if spans:
            spans.append(Span(" "))
        if self.show_interrupt_hint and self.interrupt_binding is not None:
            spans.extend(
                [
                    Span(f"({pretty_elapsed} • ", style="dim"),
                    self.interrupt_binding.into_span(),
                    Span(" to interrupt)", style="dim"),
                ]
            )
        else:
            spans.append(Span(f"({pretty_elapsed})", style="dim"))
        if self.inline_message is not None:
            spans.append(Span(" · ", style="dim"))
            spans.append(Span(self.inline_message, style="dim"))

        lines = [truncate_line_with_ellipsis_if_overflow(Line(spans), int(width))]
        max_height = height if height is not None else 1 + self.details_max_lines
        if max_height > 1:
            lines.extend(self.wrapped_details_lines(width)[: max(0, max_height - 1)])
        return lines[:max_height]

    def render(self, area: Any = None, buf: Any = None) -> List[Line]:
        width = getattr(area, "width", 80) if area is not None else 80
        height = getattr(area, "height", None) if area is not None else None
        lines = self.render_lines(width, height)
        if buf is not None and hasattr(buf, "draw"):
            buf.draw(lines, area)
        return lines


def fmt_elapsed_compact(elapsed_secs: int) -> str:
    elapsed_secs = int(elapsed_secs)
    if elapsed_secs < 60:
        return f"{elapsed_secs}s"
    if elapsed_secs < 3600:
        minutes = elapsed_secs // 60
        seconds = elapsed_secs % 60
        return f"{minutes}m {seconds:02}s"
    hours = elapsed_secs // 3600
    minutes = (elapsed_secs % 3600) // 60
    seconds = elapsed_secs % 60
    return f"{hours}h {minutes:02}m {seconds:02}s"


def desired_height(widget: StatusIndicatorWidget, width: int) -> int:
    return widget.desired_height(width)


def render(widget: StatusIndicatorWidget, area: Any = None, buf: Any = None) -> List[Line]:
    return widget.render(area, buf)


__all__ = [
    "AppEventSender",
    "DETAILS_PREFIX",
    "FrameRequester",
    "KeyBinding",
    "RUST_MODULE",
    "STATUS_DETAILS_DEFAULT_MAX_LINES",
    "StatusDetailsCapitalization",
    "StatusIndicatorWidget",
    "desired_height",
    "fmt_elapsed_compact",
    "render",
]
