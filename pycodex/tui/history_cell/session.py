"""Session headers, onboarding guidance, and transcript cards.

Upstream source: ``codex/codex-rs/tui/src/history_cell/session.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from ..text_formatting import center_truncate_path
from ..version import CODEX_CLI_VERSION
from .base import CompositeHistoryCell, PlainHistoryCell, adaptive_wrap_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::session",
    source="codex/codex-rs/tui/src/history_cell/session.rs",
)

SESSION_HEADER_MAX_INNER_WIDTH = 56
CHANGE_MODEL_HINT_COMMAND = "/model"
CHANGE_MODEL_HINT_EXPLANATION = " to change"
DIR_LABEL = "directory:"
PERMISSIONS_LABEL = "permissions:"


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def _line_width(line: Line) -> int:
    return sum(_display_width(span.content) for span in line.spans)


def _coerce_line(line: Line | str | Iterable[Span | str]) -> Line:
    if isinstance(line, Line):
        return line
    if isinstance(line, str):
        return Line.from_text(line)
    return Line.from_spans(line)


def card_inner_width(width: int, max_inner_width: int) -> int | None:
    width = int(width)
    if width < 4:
        return None
    return min(max(0, width - 4), int(max_inner_width))


def with_border(lines: Iterable[Line | str | Iterable[Span | str]]) -> list[Line]:
    return with_border_internal([_coerce_line(line) for line in lines], None)


def with_border_with_inner_width(
    lines: Iterable[Line | str | Iterable[Span | str]], inner_width: int
) -> list[Line]:
    return with_border_internal([_coerce_line(line) for line in lines], int(inner_width))


def with_border_internal(lines: list[Line], forced_inner_width: int | None) -> list[Line]:
    max_line_width = max((_line_width(line) for line in lines), default=0)
    content_width = max(max_line_width, forced_inner_width or 0)
    border_inner_width = content_width + 2
    out = [Line.from_text("╭" + "─" * border_inner_width + "╮", style="dim")]
    for line in lines:
        used = _line_width(line)
        padding = " " * max(0, content_width - used)
        out.append(Line.from_spans([Span("│ ", "dim"), *line.spans, Span(padding + " │", "dim")]))
    out.append(Line.from_text("╰" + "─" * border_inner_width + "╯", style="dim"))
    return out


def padded_emoji(emoji: str) -> str:
    return f"{emoji}\u200a"


@dataclass
class TooltipHistoryCell:
    tip: str
    cwd: Path

    @classmethod
    def new(cls, tip: str, cwd: str | Path) -> "TooltipHistoryCell":
        return cls(str(tip), Path(cwd))

    def display_lines(self, width: int) -> list[Line]:
        wrap_width = max(1, int(width) - 2)
        body = Line.from_text(f"Tip: {self.tip}")
        return adaptive_wrap_lines([body], wrap_width, "  ", "  ")

    def raw_lines(self) -> list[Line]:
        return [Line.from_text(f"Tip: {self.tip}")]


@dataclass
class SessionInfoCell:
    cell: CompositeHistoryCell

    def display_lines(self, width: int) -> list[Line]:
        return self.cell.display_lines(width)

    def desired_height(self, width: int) -> int:
        return len(self.display_lines(width))

    def transcript_lines(self, width: int) -> list[Line]:
        method = getattr(self.cell, "transcript_lines", None)
        if callable(method):
            return method(width)
        return self.display_lines(width)

    def raw_lines(self) -> list[Line]:
        return self.cell.raw_lines()


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _permission_profile_name(profile: Any) -> str:
    if profile is None:
        return ""
    if isinstance(profile, str):
        return profile
    if isinstance(profile, dict):
        return str(profile.get("type", profile.get("name", "")))
    kind = getattr(profile, "kind", None)
    if kind is not None:
        return str(getattr(kind, "value", getattr(kind, "name", kind)))
    profile_type = getattr(profile, "type", None)
    if profile_type is not None:
        return str(getattr(profile_type, "value", getattr(profile_type, "name", profile_type)))
    return str(getattr(profile, "name", profile))


def has_yolo_permissions(approval_policy: Any, permission_profile: Any) -> bool:
    approval = str(getattr(approval_policy, "name", approval_policy)).lower()
    profile = _permission_profile_name(permission_profile).lower()
    if approval != "never":
        return False
    if profile in {"disabled", "unrestricted"}:
        return True
    if isinstance(permission_profile, dict):
        fs = str(permission_profile.get("file_system", "")).lower()
        network = str(permission_profile.get("network", "")).lower()
        return fs == "unrestricted" and network == "enabled"
    raw_fs = getattr(permission_profile, "file_system", "")
    raw_network = getattr(permission_profile, "network", "")
    fs = str(getattr(raw_fs, "type", getattr(raw_fs, "value", raw_fs))).lower()
    network = str(getattr(raw_network, "value", raw_network)).lower()
    return fs == "unrestricted" and network == "enabled"


def is_yolo_mode(config: Any) -> bool:
    permissions = _get(config, "permissions", {})
    approval_policy = _get(permissions, "approval_policy", None)
    value = _get(approval_policy, "value", approval_policy)
    effective = _get(permissions, "effective_permission_profile", None)
    profile = effective() if callable(effective) else _get(permissions, "permission_profile", effective)
    return has_yolo_permissions(value, profile)


def _reasoning_label(reasoning_effort: Any) -> str | None:
    if reasoning_effort is None:
        return None
    name = str(getattr(reasoning_effort, "name", reasoning_effort)).lower()
    mapping = {
        "minimal": "minimal",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "xhigh",
        "x_high": "xhigh",
        "none": "none",
    }
    return mapping.get(name, name)


@dataclass
class SessionHeaderHistoryCell:
    model: str
    reasoning_effort: Any | None
    show_fast_status: bool
    directory: Path
    version: str = CODEX_CLI_VERSION
    model_style: Any = None
    yolo_mode: bool = False

    @classmethod
    def new(
        cls,
        model: str,
        reasoning_effort: Any | None,
        show_fast_status: bool,
        directory: str | Path,
        version: str = CODEX_CLI_VERSION,
    ) -> "SessionHeaderHistoryCell":
        return cls.new_with_style(model, None, reasoning_effort, show_fast_status, directory, version)

    @classmethod
    def new_with_style(
        cls,
        model: str,
        model_style: Any,
        reasoning_effort: Any | None,
        show_fast_status: bool,
        directory: str | Path,
        version: str = CODEX_CLI_VERSION,
    ) -> "SessionHeaderHistoryCell":
        return cls(str(model), reasoning_effort, bool(show_fast_status), Path(directory), str(version), model_style)

    def with_yolo_mode(self, yolo_mode: bool) -> "SessionHeaderHistoryCell":
        self.yolo_mode = bool(yolo_mode)
        return self

    def format_directory(self, max_width: int | None = None) -> str:
        return self.format_directory_inner(self.directory, max_width)

    @staticmethod
    def format_directory_inner(directory: str | Path, max_width: int | None = None) -> str:
        directory = Path(directory)
        home = Path.home()
        try:
            rel = directory.relative_to(home)
            formatted = "~" if str(rel) == "." else str(Path("~") / rel)
        except Exception:
            formatted = str(directory)
        if max_width is not None:
            max_width = int(max_width)
            if max_width == 0:
                return ""
            if _display_width(formatted) > max_width:
                return center_truncate_path(formatted, max_width)
        return formatted

    def reasoning_label(self) -> str | None:
        return _reasoning_label(self.reasoning_effort)

    def display_lines(self, width: int) -> list[Line]:
        inner_width = card_inner_width(width, SESSION_HEADER_MAX_INNER_WIDTH)
        if inner_width is None:
            return []
        label_width = max(len(DIR_LABEL), len(PERMISSIONS_LABEL)) if self.yolo_mode else len(DIR_LABEL)
        title = Line.from_spans([Span(">_ ", "dim"), Span("OpenAI Codex", "bold"), Span(f" (v{self.version})", "dim")])
        model_label = f"{'model:':<{label_width}} "
        model_parts: list[Span | str] = [Span(model_label, "dim"), Span(self.model, self.model_style)]
        reasoning = self.reasoning_label()
        if reasoning:
            model_parts.extend([" ", reasoning])
        if self.show_fast_status:
            model_parts.extend(["   ", Span("fast", "magenta")])
        model_parts.extend(["   ", Span(CHANGE_MODEL_HINT_COMMAND, "cyan"), Span(CHANGE_MODEL_HINT_EXPLANATION, "dim")])
        dir_prefix = f"{DIR_LABEL:<{label_width}} "
        dir_max_width = max(0, inner_width - _display_width(dir_prefix))
        dir_line = Line.from_spans([Span(dir_prefix, "dim"), self.format_directory(dir_max_width)])
        lines = [title, Line.from_text(""), Line.from_spans(model_parts), dir_line]
        if self.yolo_mode:
            permissions_prefix = f"{PERMISSIONS_LABEL:<{label_width}} "
            lines.append(Line.from_spans([Span(permissions_prefix, "dim"), Span("YOLO mode", "magenta bold")]))
        return with_border(lines)

    def raw_lines(self) -> list[Line]:
        reasoning = f" {self.reasoning_label()}" if self.reasoning_label() else ""
        lines = [
            Line.from_text(f"OpenAI Codex (v{self.version})"),
            Line.from_text(f"model: {self.model}{reasoning}"),
            Line.from_text(f"directory: {self.format_directory(None)}"),
        ]
        if self.yolo_mode:
            lines.append(Line.from_text("permissions: YOLO mode"))
        return lines


def _help_cell() -> PlainHistoryCell:
    return PlainHistoryCell.new(
        [
            "  To get started, describe a task or try one of these commands:",
            "",
            "  /init - create an AGENTS.md file with instructions for Codex",
            "  /status - show current session configuration",
            "  /permissions - choose what Codex is allowed to do",
            "  /model - choose what model and reasoning effort to use",
            "  /review - review any changes and find issues",
        ]
    )


def new_session_info(
    config: Any,
    requested_model: str,
    session: Any,
    is_first_event: bool,
    tooltip_override: str | None,
    auth_plan: Any | None,
    show_fast_status: bool,
) -> SessionInfoCell:
    del auth_plan
    cwd = Path(_get(config, "cwd", "."))
    model = str(_get(session, "model", requested_model))
    reasoning = _get(session, "reasoning_effort", None)
    approval = _get(session, "approval_policy", None)
    profile = _get(session, "permission_profile", None)
    header = SessionHeaderHistoryCell.new(
        model,
        reasoning,
        show_fast_status,
        cwd,
        CODEX_CLI_VERSION,
    ).with_yolo_mode(has_yolo_permissions(approval, profile))
    parts: list[Any] = [header]
    if is_first_event:
        parts.append(_help_cell())
    else:
        show_tooltips = bool(_get(config, "show_tooltips", False))
        if show_tooltips and tooltip_override:
            parts.append(TooltipHistoryCell.new(tooltip_override, cwd))
        if str(requested_model) != model:
            parts.append(
                PlainHistoryCell.new(
                    [
                        "model changed:",
                        f"requested: {requested_model}",
                        f"used: {model}",
                    ]
                )
            )
    return SessionInfoCell(CompositeHistoryCell.new(parts))


def display_lines(cell: Any, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: Any) -> list[Line]:
    return cell.raw_lines()


def desired_height(cell: Any, width: int) -> int:
    method = getattr(cell, "desired_height", None)
    return int(method(width)) if callable(method) else len(cell.display_lines(width))


def transcript_lines(cell: Any, width: int) -> list[Line]:
    method = getattr(cell, "transcript_lines", None)
    return method(width) if callable(method) else cell.display_lines(width)


__all__ = [
    "CHANGE_MODEL_HINT_COMMAND",
    "CHANGE_MODEL_HINT_EXPLANATION",
    "DIR_LABEL",
    "PERMISSIONS_LABEL",
    "RUST_MODULE",
    "SESSION_HEADER_MAX_INNER_WIDTH",
    "SessionHeaderHistoryCell",
    "SessionInfoCell",
    "TooltipHistoryCell",
    "card_inner_width",
    "desired_height",
    "display_lines",
    "has_yolo_permissions",
    "is_yolo_mode",
    "line_text",
    "new_session_info",
    "padded_emoji",
    "raw_lines",
    "transcript_lines",
    "with_border",
    "with_border_internal",
    "with_border_with_inner_width",
]
