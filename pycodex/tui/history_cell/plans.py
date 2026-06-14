"""Proposed-plan and plan-update history cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/plans.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line
from ..terminal_hyperlinks import (
    HyperlinkLine,
    annotate_web_urls,
    plain_hyperlink_lines,
    prefix_hyperlink_lines,
    visible_lines,
)
from .base import adaptive_wrap_lines, plain_lines
from .messages import raw_lines_from_source

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::plans",
    source="codex/codex-rs/tui/src/history_cell/plans.rs",
)

PLAN_PREFIX = "> "
PLAN_BODY_PREFIX = "  "
PLAN_BRANCH_PREFIX = "  | "
PLAN_BRANCH_CONTINUATION = "    "
PROPOSED_PLAN_STYLE = "proposed_plan"


class StepStatus(Enum):
    Completed = "completed"
    InProgress = "in_progress"
    Pending = "pending"

    @classmethod
    def coerce(cls, value: "StepStatus | str | Any") -> "StepStatus":
        if isinstance(value, cls):
            return value
        name = str(getattr(value, "name", value)).replace("-", "_").lower()
        if name in {"completed", "complete", "done"}:
            return cls.Completed
        if name in {"inprogress", "in_progress", "in progress"}:
            return cls.InProgress
        if name == "pending":
            return cls.Pending
        raise ValueError(f"unknown plan step status: {value!r}")

    def rust_debug(self) -> str:
        if self is StepStatus.Completed:
            return "Completed"
        if self is StepStatus.InProgress:
            return "InProgress"
        return "Pending"


@dataclass(frozen=True)
class PlanItemArg:
    step: str
    status: StepStatus

    @classmethod
    def coerce(cls, value: "PlanItemArg | dict[str, Any] | Any") -> "PlanItemArg":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls(str(value.get("step", "")), StepStatus.coerce(value.get("status", "pending")))
        return cls(str(getattr(value, "step")), StepStatus.coerce(getattr(value, "status")))


@dataclass(frozen=True)
class UpdatePlanArgs:
    explanation: str | None = None
    plan: tuple[PlanItemArg, ...] = ()

    @classmethod
    def coerce(cls, value: "UpdatePlanArgs | dict[str, Any] | Any") -> "UpdatePlanArgs":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            explanation = value.get("explanation")
            plan = value.get("plan", ())
        else:
            explanation = getattr(value, "explanation", None)
            plan = getattr(value, "plan", ())
        return cls(
            None if explanation is None else str(explanation),
            tuple(PlanItemArg.coerce(item) for item in plan),
        )


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def _coerce_hyperlink_line(line: HyperlinkLine | Line | str) -> HyperlinkLine:
    if isinstance(line, HyperlinkLine):
        return line
    return HyperlinkLine.new(line)


def _plain_hyperlink_lines(lines: Iterable[HyperlinkLine | Line | str]) -> list[HyperlinkLine]:
    return [_coerce_hyperlink_line(line) for line in lines]


@dataclass
class StreamingPlanTailCell:
    lines: list[HyperlinkLine] = field(default_factory=list)
    stream_continuation: bool = False

    @classmethod
    def new(
        cls, lines: Iterable[HyperlinkLine | Line | str], is_stream_continuation: bool
    ) -> "StreamingPlanTailCell":
        return cls(_plain_hyperlink_lines(lines), bool(is_stream_continuation))

    def display_lines(self, _width: int) -> list[Line]:
        return visible_lines(self.lines)

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return list(self.lines)

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(visible_lines(self.lines))

    def is_stream_continuation(self) -> bool:
        return self.stream_continuation


@dataclass
class ProposedPlanCell:
    plan_markdown: str
    cwd: Path

    def display_lines(self, width: int) -> list[Line]:
        return visible_lines(self.display_hyperlink_lines(width))

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        lines = [
            HyperlinkLine.new(Line.from_text(f"{PLAN_PREFIX}Proposed Plan")),
            HyperlinkLine.new(Line.from_text(" ")),
        ]
        body_source = raw_lines_from_source(self.plan_markdown)
        if not body_source:
            body_source = [Line.from_text("(empty)", style="dim italic")]
        wrap_width = max(1, int(width) - 4)
        wrapped_body = adaptive_wrap_lines(body_source, wrap_width)
        body = prefix_hyperlink_lines(annotate_web_urls(wrapped_body), PLAN_BODY_PREFIX, PLAN_BODY_PREFIX)
        body.append(HyperlinkLine.new(Line.from_text(" ")))
        for line in body:
            line.style(PROPOSED_PLAN_STYLE)
        return [*lines, *body]

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return raw_lines_from_source(self.plan_markdown)


@dataclass
class ProposedPlanStreamCell:
    lines: list[HyperlinkLine] = field(default_factory=list)
    stream_continuation: bool = False

    def display_lines(self, _width: int) -> list[Line]:
        return visible_lines(self.lines)

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return list(self.lines)

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(visible_lines(self.lines))

    def is_stream_continuation(self) -> bool:
        return self.stream_continuation


@dataclass
class PlanUpdateCell:
    explanation: str | None = None
    plan: tuple[PlanItemArg, ...] = ()

    def _note_lines(self, width: int, text: str) -> list[Line]:
        return adaptive_wrap_lines([Line.from_text(text, style="dim italic")], max(1, int(width) - 4))

    def _step_lines(self, width: int, item: PlanItemArg) -> list[Line]:
        if item.status is StepStatus.Completed:
            box = "[x] "
            style = "crossed_out dim"
        elif item.status is StepStatus.InProgress:
            box = "[>] "
            style = "cyan bold"
        else:
            box = "[ ] "
            style = "dim"
        return adaptive_wrap_lines(
            [Line.from_text(item.step, style=style)],
            max(1, int(width) - 4),
            box,
            "  ",
        )

    def display_lines(self, width: int) -> list[Line]:
        lines = [Line.from_text(f"{PLAN_PREFIX}Updated Plan")]
        indented: list[Line] = []
        note = (self.explanation or "").strip()
        if note:
            indented.extend(self._note_lines(width, note))
        if not self.plan:
            indented.append(Line.from_text("(no steps provided)", style="dim italic"))
        else:
            for item in self.plan:
                indented.extend(self._step_lines(width, item))
        lines.extend(adaptive_wrap_lines(indented, max(1, int(width)), PLAN_BRANCH_PREFIX, PLAN_BRANCH_CONTINUATION))
        return lines

    def raw_lines(self) -> list[Line]:
        lines = [Line.from_text("Updated Plan")]
        note = (self.explanation or "").strip()
        if note:
            lines.extend(raw_lines_from_source(note))
        if not self.plan:
            lines.append(Line.from_text("(no steps provided)"))
        else:
            lines.extend(
                Line.from_text(f"{item.status.rust_debug()}: {item.step}") for item in self.plan
            )
        return lines


def new_plan_update(update: UpdatePlanArgs | dict[str, Any] | Any) -> PlanUpdateCell:
    update = UpdatePlanArgs.coerce(update)
    return PlanUpdateCell(update.explanation, update.plan)


def new_proposed_plan(plan_markdown: str, cwd: str | Path) -> ProposedPlanCell:
    return ProposedPlanCell(str(plan_markdown), Path(cwd))


def new_proposed_plan_stream(
    lines: Iterable[HyperlinkLine | Line | str], is_stream_continuation: bool
) -> ProposedPlanStreamCell:
    return ProposedPlanStreamCell(_plain_hyperlink_lines(lines), bool(is_stream_continuation))


def display_lines(cell: Any, width: int) -> list[Line]:
    return cell.display_lines(width)


def display_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    return cell.display_hyperlink_lines(width)


def transcript_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    return cell.transcript_hyperlink_lines(width)


def raw_lines(cell: Any) -> list[Line]:
    return cell.raw_lines()


def is_stream_continuation(cell: Any) -> bool:
    method = getattr(cell, "is_stream_continuation", None)
    return bool(method()) if callable(method) else False


__all__ = [
    "PLAN_BODY_PREFIX",
    "PLAN_BRANCH_CONTINUATION",
    "PLAN_BRANCH_PREFIX",
    "PLAN_PREFIX",
    "PlanItemArg",
    "PlanUpdateCell",
    "ProposedPlanCell",
    "ProposedPlanStreamCell",
    "RUST_MODULE",
    "StepStatus",
    "StreamingPlanTailCell",
    "UpdatePlanArgs",
    "display_hyperlink_lines",
    "display_lines",
    "is_stream_continuation",
    "line_text",
    "new_plan_update",
    "new_proposed_plan",
    "new_proposed_plan_stream",
    "raw_lines",
    "transcript_hyperlink_lines",
]
