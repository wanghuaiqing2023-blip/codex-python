"""Informational, warning, update, and policy notice history cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/notices.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..terminal_hyperlinks import HyperlinkLine, annotate_web_urls
from .base import PlainHistoryCell, PrefixedWrappedHistoryCell, adaptive_wrap_lines

try:
    from ..version import CODEX_CLI_VERSION
except Exception:  # pragma: no cover - compatibility with older scaffold states.
    CODEX_CLI_VERSION = "unknown"


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::notices",
    source="codex/codex-rs/tui/src/history_cell/notices.rs",
)

TRUSTED_ACCESS_FOR_CYBER_URL = "https://chatgpt.com/cyber"
RELEASE_NOTES_URL = "https://github.com/openai/codex/releases/latest"
CODEX_REPO_URL = "https://github.com/openai/codex"


def _line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def line_text(line: Line) -> str:
    return _line_text(line)


def _plain_line(text: str) -> Line:
    return Line.from_text(text)


def _styled_line(*parts: Span | str) -> Line:
    return Line.from_spans(parts)


def _command_str(update_action: Any) -> str:
    command = getattr(update_action, "command_str", None)
    if callable(command):
        return str(command())
    if command is not None:
        return str(command)
    return str(update_action)


def _raw_lines_from_source(source: str) -> list[Line]:
    return [Line.from_text(line) for line in source.splitlines()] or [Line.from_text("")]


def _bordered(lines: list[Line], inner_width: int) -> list[Line]:
    """Dependency-light equivalent of Rust ``with_border_with_inner_width``."""

    width = max(1, int(inner_width))
    top = Line.from_text("+" + "-" * width + "+")
    bottom = Line.from_text("+" + "-" * width + "+")
    body: list[Line] = []
    for line in lines:
        text = _line_text(line)
        body.append(Line.from_text("|" + text.ljust(width)[:width] + "|"))
    return [top, *body, bottom]


@dataclass
class UpdateAvailableHistoryCell:
    latest_version: str
    update_action: Any | None = None

    @classmethod
    def new(
        cls, latest_version: str, update_action: Any | None = None
    ) -> "UpdateAvailableHistoryCell":
        return cls(str(latest_version), update_action)

    def _update_instruction(self) -> Line:
        if self.update_action is not None:
            return _styled_line("Run ", Span(_command_str(self.update_action), "cyan"), " to update.")
        return _styled_line(
            "See ",
            Span(CODEX_REPO_URL, "cyan underlined"),
            " for installation options.",
        )

    def display_lines(self, width: int) -> list[Line]:
        content = [
            _styled_line(
                Span("Update available!", "bold cyan"),
                " ",
                Span(f"{CODEX_CLI_VERSION} -> {self.latest_version}", "bold"),
            ),
            self._update_instruction(),
            Line.from_text(""),
            Line.from_text("See full release notes:"),
            _styled_line(Span(RELEASE_NOTES_URL, "cyan underlined")),
        ]
        requested = max(1, int(width) - 4)
        inner_width = min(max((_line_width(line) for line in content), default=1), requested)
        wrapped = adaptive_wrap_lines(content, inner_width)
        return _bordered(wrapped, inner_width)

    def raw_lines(self) -> list[Line]:
        if self.update_action is not None:
            update_instruction = f"Run {_command_str(self.update_action)} to update."
        else:
            update_instruction = f"See {CODEX_REPO_URL} for installation options."
        return [
            Line.from_text("Update available!"),
            Line.from_text(f"{CODEX_CLI_VERSION} -> {self.latest_version}"),
            Line.from_text(update_instruction),
            Line.from_text(""),
            Line.from_text("See full release notes:"),
            Line.from_text(RELEASE_NOTES_URL),
        ]

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        lines = annotate_web_urls(self.display_lines(width))
        destinations = {
            link.destination
            for line in lines
            for link in getattr(line, "hyperlinks", ())
        }
        if RELEASE_NOTES_URL not in destinations:
            lines.append(annotate_web_urls([Line.from_text(RELEASE_NOTES_URL)])[0])
        return lines

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)


def _line_width(line: Line) -> int:
    return len(_line_text(line))


def new_warning_event(message: str) -> PrefixedWrappedHistoryCell:
    return PrefixedWrappedHistoryCell.new(
        Line.from_spans([Span(str(message), "yellow")]),
        Span("! ", "yellow"),
        "  ",
    )


@dataclass
class CyberPolicyNoticeCell:
    def display_lines(self, width: int) -> list[Line]:
        lines = [
            _styled_line(
                Span("! ", "cyan"),
                Span("This chat was flagged for possible cybersecurity risk", "bold"),
            )
        ]
        body = _styled_line(
            Span(
                "  If this seems wrong, try rephrasing your request. To get authorized for security work, join the ",
                "dim",
            ),
            Span("Trusted Access for Cyber", "cyan underlined"),
            Span(" program.", "dim"),
        )
        lines.extend(adaptive_wrap_lines([body], max(1, int(width) - 2), "", "  "))
        lines.append(_styled_line("  ", Span(TRUSTED_ACCESS_FOR_CYBER_URL, "cyan underlined")))
        return lines

    def raw_lines(self) -> list[Line]:
        return [
            Line.from_text("This chat was flagged for possible cybersecurity risk"),
            Line.from_text(
                "If this seems wrong, try rephrasing your request. To get authorized for security work, join the Trusted Access for Cyber program."
            ),
            Line.from_text(TRUSTED_ACCESS_FOR_CYBER_URL),
        ]

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return annotate_web_urls(self.display_lines(width))

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)


def new_cyber_policy_error_event() -> CyberPolicyNoticeCell:
    return CyberPolicyNoticeCell()


@dataclass
class DeprecationNoticeCell:
    summary: str
    details: str | None = None

    def display_lines(self, width: int) -> list[Line]:
        lines = [_styled_line(Span("! ", "red bold"), Span(self.summary, "red"))]
        if self.details is not None:
            detail = _styled_line(Span(self.details, "dim"))
            lines.extend(adaptive_wrap_lines([detail], max(1, int(width) - 4)))
        return lines

    def raw_lines(self) -> list[Line]:
        lines = [Line.from_text(self.summary)]
        if self.details is not None:
            lines.extend(_raw_lines_from_source(self.details))
        return lines


def new_deprecation_notice(summary: str, details: str | None = None) -> DeprecationNoticeCell:
    return DeprecationNoticeCell(str(summary), None if details is None else str(details))


def new_info_event(message: str, hint: str | None = None) -> PlainHistoryCell:
    spans: list[Span | str] = [Span("- ", "dim"), str(message)]
    if hint is not None:
        spans.extend([" ", Span(str(hint), "dark_gray")])
    return PlainHistoryCell.new([Line.from_spans(spans)])


def new_error_event(message: str) -> PlainHistoryCell:
    return PlainHistoryCell.new([Line.from_spans([Span(f"! {message}", "red")])])


def display_lines(cell: Any, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: Any) -> list[Line]:
    return cell.raw_lines()


def display_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    return cell.display_hyperlink_lines(width)


def transcript_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    return cell.transcript_hyperlink_lines(width)


__all__ = [
    "CODEX_REPO_URL",
    "CyberPolicyNoticeCell",
    "DeprecationNoticeCell",
    "RELEASE_NOTES_URL",
    "RUST_MODULE",
    "TRUSTED_ACCESS_FOR_CYBER_URL",
    "UpdateAvailableHistoryCell",
    "display_hyperlink_lines",
    "display_lines",
    "line_text",
    "new_cyber_policy_error_event",
    "new_deprecation_notice",
    "new_error_event",
    "new_info_event",
    "new_warning_event",
    "raw_lines",
    "transcript_hyperlink_lines",
]
