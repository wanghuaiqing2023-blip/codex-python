"""Completed request-user-input transcript rendering.

Upstream source: ``codex/codex-rs/tui/src/history_cell/request_user_input.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from .base import adaptive_wrap_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::request_user_input",
    source="codex/codex-rs/tui/src/history_cell/request_user_input.rs",
)

SECRET_ANSWER_MASK = "******"
NOTE_PREFIX = "user_note: "


@dataclass(frozen=True)
class ToolRequestUserInputQuestion:
    id: str
    question: str
    is_secret: bool = False
    options: tuple[str, ...] | None = None

    @classmethod
    def coerce(
        cls, value: "ToolRequestUserInputQuestion | dict[str, Any] | Any"
    ) -> "ToolRequestUserInputQuestion":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            options = value.get("options")
            return cls(
                str(value.get("id", "")),
                str(value.get("question", "")),
                bool(value.get("is_secret", False)),
                None if options is None else tuple(str(option) for option in options),
            )
        options = getattr(value, "options", None)
        return cls(
            str(getattr(value, "id")),
            str(getattr(value, "question")),
            bool(getattr(value, "is_secret", False)),
            None if options is None else tuple(str(option) for option in options),
        )


@dataclass(frozen=True)
class ToolRequestUserInputAnswer:
    answers: tuple[str, ...] = ()

    @classmethod
    def coerce(
        cls, value: "ToolRequestUserInputAnswer | dict[str, Any] | Iterable[str] | Any"
    ) -> "ToolRequestUserInputAnswer":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            answers = value.get("answers", ())
        elif isinstance(value, (list, tuple)):
            answers = value
        else:
            answers = getattr(value, "answers", ())
        return cls(tuple(str(answer) for answer in answers))


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def split_request_user_input_answer(
    answer: ToolRequestUserInputAnswer | dict[str, Any] | Iterable[str] | Any,
) -> tuple[list[str], str | None]:
    answer = ToolRequestUserInputAnswer.coerce(answer)
    options: list[str] = []
    note: str | None = None
    for entry in answer.answers:
        if entry.startswith(NOTE_PREFIX):
            note = entry[len(NOTE_PREFIX) :]
        else:
            options.append(entry)
    return options, note


def wrap_with_prefix(
    text: str,
    width: int,
    initial_prefix: Span | str,
    subsequent_prefix: Span | str,
    style: Any = None,
) -> list[Line]:
    initial = initial_prefix if isinstance(initial_prefix, str) else initial_prefix.content
    subsequent = subsequent_prefix if isinstance(subsequent_prefix, str) else subsequent_prefix.content
    return adaptive_wrap_lines(
        [Line.from_spans([Span(str(text), style)])],
        max(1, int(width)),
        initial,
        subsequent,
    )


@dataclass
class RequestUserInputResultCell:
    questions: list[ToolRequestUserInputQuestion] = field(default_factory=list)
    answers: dict[str, ToolRequestUserInputAnswer] = field(default_factory=dict)
    interrupted: bool = False

    @classmethod
    def new(
        cls,
        questions: Iterable[ToolRequestUserInputQuestion | dict[str, Any] | Any],
        answers: Mapping[str, ToolRequestUserInputAnswer | dict[str, Any] | Iterable[str] | Any],
        interrupted: bool = False,
    ) -> "RequestUserInputResultCell":
        return cls(
            [ToolRequestUserInputQuestion.coerce(question) for question in questions],
            {
                str(key): ToolRequestUserInputAnswer.coerce(value)
                for key, value in answers.items()
            },
            bool(interrupted),
        )

    def _answered_count(self) -> int:
        return sum(
            1
            for question in self.questions
            if self.answers.get(question.id) is not None
            and bool(self.answers[question.id].answers)
        )

    def display_lines(self, width: int) -> list[Line]:
        width = max(1, int(width))
        total = len(self.questions)
        answered = self._answered_count()
        unanswered = max(0, total - answered)
        header = f"- Questions {answered}/{total} answered"
        if self.interrupted:
            header += " (interrupted)"
        lines = [Line.from_text(header)]

        for question in self.questions:
            answer = self.answers.get(question.id)
            answer_missing = answer is None or not answer.answers
            question_lines = wrap_with_prefix(
                question.question,
                width,
                "  ? ",
                "    ",
            )
            if answer_missing and question_lines:
                question_lines[-1] = Line.from_text(
                    line_text(question_lines[-1]) + " (unanswered)"
                )
            lines.extend(question_lines)

            if answer_missing:
                continue
            if question.is_secret:
                lines.extend(
                    wrap_with_prefix(
                        SECRET_ANSWER_MASK,
                        width,
                        "    answer: ",
                        "            ",
                        "cyan",
                    )
                )
                continue

            options, note = split_request_user_input_answer(answer)
            for option in options:
                lines.extend(
                    wrap_with_prefix(
                        option,
                        width,
                        "    answer: ",
                        "            ",
                        "cyan",
                    )
                )
            if note is not None:
                if question.options is not None:
                    label = "    note: "
                    continuation = "          "
                else:
                    label = "    answer: "
                    continuation = "            "
                lines.extend(wrap_with_prefix(note, width, label, continuation, "cyan"))

        if self.interrupted and unanswered > 0:
            lines.extend(
                wrap_with_prefix(
                    f"interrupted with {unanswered} unanswered",
                    width,
                    "  -> ",
                    "    ",
                    "cyan dim",
                )
            )
        return lines

    def raw_lines(self) -> list[Line]:
        total = len(self.questions)
        answered = self._answered_count()
        lines = [Line.from_text(f"Questions {answered}/{total} answered")]
        if self.interrupted:
            lines.append(Line.from_text("(interrupted)"))
        for question in self.questions:
            lines.append(Line.from_text(question.question))
            answer = self.answers.get(question.id)
            if answer is None or not answer.answers:
                lines.append(Line.from_text("(unanswered)"))
                continue
            if question.is_secret:
                lines.append(Line.from_text(f"answer: {SECRET_ANSWER_MASK}"))
                continue
            options, note = split_request_user_input_answer(answer)
            lines.extend(Line.from_text(f"answer: {option}") for option in options)
            if note is not None:
                lines.append(Line.from_text(f"note: {note}"))
        return lines


def display_lines(cell: RequestUserInputResultCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: RequestUserInputResultCell) -> list[Line]:
    return cell.raw_lines()


__all__ = [
    "NOTE_PREFIX",
    "RUST_MODULE",
    "RequestUserInputResultCell",
    "SECRET_ANSWER_MASK",
    "ToolRequestUserInputAnswer",
    "ToolRequestUserInputQuestion",
    "display_lines",
    "line_text",
    "raw_lines",
    "split_request_user_input_answer",
    "wrap_with_prefix",
]
