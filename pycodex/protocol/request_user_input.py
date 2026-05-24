"""request_user_input protocol types.

Ported from ``codex/codex-rs/protocol/src/request_user_input.rs``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_bool(value: Mapping[str, JsonValue], key: str, default: bool = False) -> bool:
    raw = value.get(key, default)
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


@dataclass(frozen=True)
class RequestUserInputQuestionOption:
    label: str
    description: str

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputQuestionOption":
        data = _mapping(value, "request user input question option")
        return cls(label=_required_str(data, "label"), description=_required_str(data, "description"))

    def to_mapping(self) -> dict[str, str]:
        return {"label": self.label, "description": self.description}


@dataclass(frozen=True)
class RequestUserInputQuestion:
    id: str
    header: str
    question: str
    is_other: bool = False
    is_secret: bool = False
    options: tuple[RequestUserInputQuestionOption, ...] | None = None

    def __post_init__(self) -> None:
        if self.options is not None and not isinstance(self.options, tuple):
            object.__setattr__(self, "options", tuple(self.options))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputQuestion":
        data = _mapping(value, "request user input question")
        options = data.get("options")
        if options is not None:
            if not isinstance(options, list | tuple):
                raise TypeError("options must be a list")
            parsed_options = tuple(RequestUserInputQuestionOption.from_mapping(item) for item in options)
        else:
            parsed_options = None
        return cls(
            id=_required_str(data, "id"),
            header=_required_str(data, "header"),
            question=_required_str(data, "question"),
            is_other=_optional_bool(data, "isOther"),
            is_secret=_optional_bool(data, "isSecret"),
            options=parsed_options,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "id": self.id,
            "header": self.header,
            "question": self.question,
            "isOther": self.is_other,
            "isSecret": self.is_secret,
        }
        if self.options is not None:
            data["options"] = [option.to_mapping() for option in self.options]
        return data


@dataclass(frozen=True)
class RequestUserInputArgs:
    questions: tuple[RequestUserInputQuestion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.questions, tuple):
            object.__setattr__(self, "questions", tuple(self.questions))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputArgs":
        data = _mapping(value, "request user input args")
        questions = data["questions"]
        if not isinstance(questions, list | tuple):
            raise TypeError("questions must be a list")
        return cls(tuple(RequestUserInputQuestion.from_mapping(question) for question in questions))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"questions": [question.to_mapping() for question in self.questions]}


@dataclass(frozen=True)
class RequestUserInputAnswer:
    answers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.answers, tuple):
            object.__setattr__(self, "answers", tuple(self.answers))
        if not all(isinstance(answer, str) for answer in self.answers):
            raise TypeError("answers must be strings")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputAnswer":
        data = _mapping(value, "request user input answer")
        answers = data["answers"]
        if not isinstance(answers, list | tuple):
            raise TypeError("answers must be a list")
        return cls(tuple(answers))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"answers": list(self.answers)}


@dataclass(frozen=True)
class RequestUserInputResponse:
    answers: dict[str, RequestUserInputAnswer]

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputResponse":
        data = _mapping(value, "request user input response")
        raw_answers = data["answers"]
        if not isinstance(raw_answers, Mapping):
            raise TypeError("answers must be a mapping")
        return cls({str(key): RequestUserInputAnswer.from_mapping(answer) for key, answer in raw_answers.items()})

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"answers": {key: answer.to_mapping() for key, answer in self.answers.items()}}


@dataclass(frozen=True)
class RequestUserInputEvent:
    call_id: str
    questions: tuple[RequestUserInputQuestion, ...]
    turn_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.questions, tuple):
            object.__setattr__(self, "questions", tuple(self.questions))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestUserInputEvent":
        data = _mapping(value, "request user input event")
        questions = data["questions"]
        if not isinstance(questions, list | tuple):
            raise TypeError("questions must be a list")
        return cls(
            call_id=_required_str(data, "call_id"),
            turn_id=str(data.get("turn_id", "")),
            questions=tuple(RequestUserInputQuestion.from_mapping(question) for question in questions),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "questions": [question.to_mapping() for question in self.questions],
        }
