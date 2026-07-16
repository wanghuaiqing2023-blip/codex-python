"""Turn protocol types ported from ``protocol/v2/turn.rs``."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol.plan_tool import PlanItemArg, StepStatus

from .thread_data import Turn

JsonValue = Any
UNSET = object()


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class TurnStatus(_StringEnum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    IN_PROGRESS = "inProgress"


class AdditionalContextKind(_StringEnum):
    UNTRUSTED = "untrusted"
    APPLICATION = "application"


class TurnPlanStepStatus(_StringEnum):
    PENDING = "pending"
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TurnEnvironmentParams:
    environment_id: str
    cwd: Path | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", _ensure_str(self.environment_id, "environment_id"))
        object.__setattr__(self, "cwd", _path_str(self.cwd, "cwd"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnEnvironmentParams":
        data = _mapping(value, "TurnEnvironmentParams")
        return cls(
            environment_id=_ensure_str(_pick(data, "environment_id", "environmentId"), "environment_id"),
            cwd=_path_str(data["cwd"], "cwd"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class AdditionalContextEntry:
    value: str
    kind: AdditionalContextKind | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _ensure_str(self.value, "value"))
        object.__setattr__(self, "kind", AdditionalContextKind.parse(self.kind))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AdditionalContextEntry":
        data = _mapping(value, "AdditionalContextEntry")
        return cls(value=_ensure_str(data["value"], "value"), kind=AdditionalContextKind.parse(data["kind"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"value": self.value, "kind": self.kind.value}


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _usize(self.start, "start"))
        object.__setattr__(self, "end", _usize(self.end, "end"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ByteRange":
        data = _mapping(value, "ByteRange")
        return cls(start=_usize(data["start"], "start"), end=_usize(data["end"], "end"))

    def to_mapping(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class TextElement:
    byte_range: ByteRange | Mapping[str, JsonValue]
    placeholder: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "byte_range", _byte_range(self.byte_range))
        object.__setattr__(self, "placeholder", _optional_str(self.placeholder, "placeholder"))

    @classmethod
    def new(cls, byte_range: ByteRange | Mapping[str, JsonValue], placeholder: str | None = None) -> "TextElement":
        return cls(byte_range=byte_range, placeholder=placeholder)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TextElement":
        data = _mapping(value, "TextElement")
        return cls(
            byte_range=ByteRange.from_mapping(_pick(data, "byte_range", "byteRange")),
            placeholder=_optional_str(data.get("placeholder"), "placeholder"),
        )

    def set_placeholder(self, placeholder: str | None) -> "TextElement":
        return TextElement(byte_range=self.byte_range, placeholder=placeholder)

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"byte_range": self.byte_range.to_mapping()}
        if self.placeholder is not None:
            result["placeholder"] = self.placeholder
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"byteRange": self.byte_range.to_mapping()}
        if self.placeholder is not None:
            result["placeholder"] = self.placeholder
        return result


@dataclass(frozen=True)
class UserInput:
    type: str
    fields: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "fields", _normalize_user_input_fields(self.type, self.fields))

    @classmethod
    def text(
        cls,
        text: str,
        text_elements: Iterable[TextElement | Mapping[str, JsonValue]] = (),
    ) -> "UserInput":
        return cls("text", {"text": text, "textElements": [_text_element(item).to_camel_mapping() for item in text_elements]})

    @classmethod
    def image(cls, url: str, detail: JsonValue | None = None) -> "UserInput":
        return cls("image", {"url": _ensure_str(url, "url"), "detail": detail})

    @classmethod
    def local_image(cls, path: Path | str, detail: JsonValue | None = None) -> "UserInput":
        return cls("localImage", {"path": _path_str(path, "path"), "detail": detail})

    @classmethod
    def skill(cls, name: str, path: Path | str) -> "UserInput":
        return cls("skill", {"name": _ensure_str(name, "name"), "path": _path_str(path, "path")})

    @classmethod
    def mention(cls, name: str, path: str) -> "UserInput":
        return cls("mention", {"name": _ensure_str(name, "name"), "path": _ensure_str(path, "path")})

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "UserInput":
        data = dict(_mapping(value, "UserInput"))
        type_ = _ensure_str(data.pop("type"), "type")
        return cls(type_, data)

    def text_char_count(self) -> int:
        if self.type != "text":
            return 0
        return len(str(self.fields.get("text", "")))

    def into_core(self) -> dict[str, JsonValue]:
        return self.to_mapping()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"type": self.type, **_serialize_mapping(self.fields)}


@dataclass(frozen=True)
class TurnStartParams:
    thread_id: str
    input: tuple[UserInput, ...]
    responsesapi_client_metadata: Mapping[str, str] | None = None
    additional_context: Mapping[str, AdditionalContextEntry | Mapping[str, JsonValue]] | None = None
    environments: tuple[TurnEnvironmentParams, ...] | None = None
    cwd: Path | str | None = None
    runtime_workspace_roots: tuple[Path | str, ...] | None = None
    approval_policy: JsonValue | None = None
    approvals_reviewer: JsonValue | None = None
    sandbox_policy: JsonValue | None = None
    permissions: str | None = None
    model: str | None = None
    service_tier: JsonValue = UNSET
    effort: JsonValue | None = None
    summary: JsonValue | None = None
    personality: JsonValue | None = None
    output_schema: JsonValue | None = None
    collaboration_mode: JsonValue | None = None

    def __post_init__(self) -> None:
        _normalize_turn_start_like(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnStartParams":
        data = _mapping(value, "TurnStartParams")
        return cls(
            thread_id=_ensure_str(_pick(data, "thread_id", "threadId"), "thread_id"),
            input=tuple(UserInput.from_mapping(item) for item in _list(data["input"], "input")),
            responsesapi_client_metadata=_str_map(_pick(data, "responsesapi_client_metadata", "responsesapiClientMetadata")),
            additional_context=_additional_context_map(_pick(data, "additional_context", "additionalContext")),
            environments=tuple(TurnEnvironmentParams.from_mapping(item) for item in _list(_pick(data, "environments"), "environments")) if _pick(data, "environments") is not None else None,
            cwd=_pick(data, "cwd"),
            runtime_workspace_roots=_path_tuple(_pick(data, "runtime_workspace_roots", "runtimeWorkspaceRoots"), "runtime_workspace_roots"),
            approval_policy=_pick(data, "approval_policy", "approvalPolicy"),
            approvals_reviewer=_pick(data, "approvals_reviewer", "approvalsReviewer"),
            sandbox_policy=_pick(data, "sandbox_policy", "sandboxPolicy"),
            permissions=_optional_str(data.get("permissions"), "permissions"),
            model=_optional_str(data.get("model"), "model"),
            service_tier=_pick(data, "service_tier", "serviceTier", default=UNSET),
            effort=data.get("effort"),
            summary=data.get("summary"),
            personality=data.get("personality"),
            output_schema=_pick(data, "output_schema", "outputSchema"),
            collaboration_mode=_pick(data, "collaboration_mode", "collaborationMode"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _turn_start_like_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _turn_start_like_mapping(self, camel=True)


@dataclass(frozen=True)
class TurnStartResponse:
    turn: Turn | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn", _turn(self.turn))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"turn": self.turn.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"turn": self.turn.to_camel_mapping()}


@dataclass(frozen=True)
class TurnSteerParams:
    thread_id: str
    input: tuple[UserInput, ...]
    expected_turn_id: str
    responsesapi_client_metadata: Mapping[str, str] | None = None
    additional_context: Mapping[str, AdditionalContextEntry | Mapping[str, JsonValue]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "input", tuple(_user_input(item) for item in self.input))
        object.__setattr__(self, "expected_turn_id", _ensure_str(self.expected_turn_id, "expected_turn_id"))
        object.__setattr__(self, "responsesapi_client_metadata", _str_map(self.responsesapi_client_metadata))
        object.__setattr__(self, "additional_context", _additional_context_map(self.additional_context))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class TurnSteerResponse:
    turn_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))

    def to_mapping(self) -> dict[str, str]:
        return {"turn_id": self.turn_id}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"turnId": self.turn_id}


@dataclass(frozen=True)
class TurnInterruptParams:
    thread_id: str
    turn_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))

    def to_mapping(self) -> dict[str, str]:
        return {"thread_id": self.thread_id, "turn_id": self.turn_id}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"threadId": self.thread_id, "turnId": self.turn_id}


@dataclass(frozen=True)
class TurnInterruptResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "TurnInterruptResponse":
        if value is not None:
            _mapping(value, "TurnInterruptResponse")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class TurnStartedNotification:
    thread_id: str
    turn: Turn | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn", _turn(self.turn))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "turn": self.turn.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "turn": self.turn.to_camel_mapping()}


class TurnCompletedNotification(TurnStartedNotification):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_tokens", _i32(self.input_tokens, "input_tokens"))
        object.__setattr__(self, "cached_input_tokens", _i32(self.cached_input_tokens, "cached_input_tokens"))
        object.__setattr__(self, "output_tokens", _i32(self.output_tokens, "output_tokens"))

    def to_mapping(self) -> dict[str, int]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, int]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class TurnDiffUpdatedNotification:
    thread_id: str
    turn_id: str
    diff: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "diff", _ensure_str(self.diff, "diff"))

    def to_mapping(self) -> dict[str, str]:
        return {"thread_id": self.thread_id, "turn_id": self.turn_id, "diff": self.diff}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"threadId": self.thread_id, "turnId": self.turn_id, "diff": self.diff}


@dataclass(frozen=True)
class TurnPlanStep:
    step: str
    status: TurnPlanStepStatus | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "step", _ensure_str(self.step, "step"))
        object.__setattr__(self, "status", TurnPlanStepStatus.parse(self.status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnPlanStep":
        data = _mapping(value, "TurnPlanStep")
        return cls(step=_ensure_str(data["step"], "step"), status=TurnPlanStepStatus.parse(data["status"]))

    @classmethod
    def from_core(cls, value: PlanItemArg) -> "TurnPlanStep":
        if not isinstance(value, PlanItemArg):
            raise TypeError("value must be PlanItemArg")
        status = {
            StepStatus.PENDING: TurnPlanStepStatus.PENDING,
            StepStatus.IN_PROGRESS: TurnPlanStepStatus.IN_PROGRESS,
            StepStatus.COMPLETED: TurnPlanStepStatus.COMPLETED,
        }[value.status]
        return cls(step=value.step, status=status)

    def to_mapping(self) -> dict[str, str]:
        return {"step": self.step, "status": self.status.value}


@dataclass(frozen=True)
class TurnPlanUpdatedNotification:
    thread_id: str
    turn_id: str
    explanation: str | None
    plan: tuple[TurnPlanStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "explanation", _optional_str(self.explanation, "explanation"))
        object.__setattr__(self, "plan", tuple(_turn_plan_step(item) for item in self.plan))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "turn_id": self.turn_id, "explanation": self.explanation, "plan": [item.to_mapping() for item in self.plan]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "turnId": self.turn_id, "explanation": self.explanation, "plan": [item.to_mapping() for item in self.plan]}


def _normalize_turn_start_like(value: TurnStartParams) -> None:
    object.__setattr__(value, "thread_id", _ensure_str(value.thread_id, "thread_id"))
    object.__setattr__(value, "input", tuple(_user_input(item) for item in value.input))
    object.__setattr__(value, "responsesapi_client_metadata", _str_map(value.responsesapi_client_metadata))
    object.__setattr__(value, "additional_context", _additional_context_map(value.additional_context))
    if value.environments is not None:
        object.__setattr__(value, "environments", tuple(_turn_environment(item) for item in value.environments))
    object.__setattr__(value, "cwd", _optional_path_str(value.cwd, "cwd"))
    object.__setattr__(value, "runtime_workspace_roots", _path_tuple(value.runtime_workspace_roots, "runtime_workspace_roots"))
    object.__setattr__(value, "permissions", _optional_str(value.permissions, "permissions"))
    object.__setattr__(value, "model", _optional_str(value.model, "model"))


def _turn_start_like_mapping(value: TurnStartParams, *, camel: bool) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for field_ in fields(value):
        key = field_.name
        item = getattr(value, key)
        if key == "service_tier" and item is UNSET:
            continue
        if item is None:
            result[_snake_to_camel(key) if camel else key] = None
        else:
            result[_snake_to_camel(key) if camel else key] = _serialize_camel(item) if camel else _serialize(item)
    return result


def _normalize_user_input_fields(type_: str, fields_: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    data = copy.deepcopy(dict(_mapping(fields_, "fields")))
    if type_ == "text":
        data["text"] = _ensure_str(data["text"], "text")
        raw_elements = _pick(data, "text_elements", "textElements", default=[])
        data.pop("text_elements", None)
        data["textElements"] = [_text_element(item).to_camel_mapping() for item in raw_elements]
    elif type_ == "image":
        data["url"] = _ensure_str(data["url"], "url")
    elif type_ == "localImage":
        data["path"] = _path_str(data["path"], "path")
    elif type_ == "skill":
        data["name"] = _ensure_str(data["name"], "name")
        data["path"] = _path_str(data["path"], "path")
    elif type_ == "mention":
        data["name"] = _ensure_str(data["name"], "name")
        data["path"] = _ensure_str(data["path"], "path")
    else:
        raise ValueError(f"unknown UserInput type: {type_}")
    return data


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _path_str(value: Path | str, field_name: str) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"{field_name} must be a path string")


def _optional_path_str(value: Path | str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _path_str(value, field_name)


def _usize(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _i32(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < -(2**31) or value > 2**31 - 1:
        raise TypeError(f"{field_name} must be a signed 32-bit integer")
    return value


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _str_map(value: JsonValue) -> dict[str, str] | None:
    if value is None:
        return None
    data = _mapping(value, "string map")
    result: dict[str, str] = {}
    for key, item in data.items():
        result[_ensure_str(key, "map key")] = _ensure_str(item, "map value")
    return result


def _additional_context_map(value: JsonValue) -> dict[str, AdditionalContextEntry] | None:
    if value is None:
        return None
    data = _mapping(value, "additional_context")
    return {str(key): _additional_context_entry(item) for key, item in data.items()}


def _path_tuple(value: JsonValue, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of path strings")
    return tuple(_path_str(item, field_name) for item in value)


def _byte_range(value: ByteRange | Mapping[str, JsonValue]) -> ByteRange:
    if isinstance(value, ByteRange):
        return value
    return ByteRange.from_mapping(value)


def _text_element(value: TextElement | Mapping[str, JsonValue]) -> TextElement:
    if isinstance(value, TextElement):
        return value
    return TextElement.from_mapping(value)


def _user_input(value: UserInput | Mapping[str, JsonValue]) -> UserInput:
    if isinstance(value, UserInput):
        return value
    return UserInput.from_mapping(value)


def _turn(value: Turn | Mapping[str, JsonValue]) -> Turn:
    if isinstance(value, Turn):
        return value
    return Turn.from_mapping(value)


def _turn_environment(value: TurnEnvironmentParams | Mapping[str, JsonValue]) -> TurnEnvironmentParams:
    if isinstance(value, TurnEnvironmentParams):
        return value
    return TurnEnvironmentParams.from_mapping(value)


def _additional_context_entry(value: AdditionalContextEntry | Mapping[str, JsonValue]) -> AdditionalContextEntry:
    if isinstance(value, AdditionalContextEntry):
        return value
    return AdditionalContextEntry.from_mapping(value)


def _turn_plan_step(value: TurnPlanStep | Mapping[str, JsonValue]) -> TurnPlanStep:
    if isinstance(value, TurnPlanStep):
        return value
    return TurnPlanStep.from_mapping(value)


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _serialize_camel(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, list):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_camel(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _serialize_mapping(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {str(key): _serialize_camel(item) for key, item in value.items() if item is not None}


def _to_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return {field_.name: _serialize(getattr(value, field_.name)) for field_ in fields(value)}


def _to_camel_mapping(value: JsonValue) -> dict[str, JsonValue]:
    return {_snake_to_camel(field_.name): _serialize_camel(getattr(value, field_.name)) for field_ in fields(value)}


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "AdditionalContextEntry",
    "AdditionalContextKind",
    "ByteRange",
    "TextElement",
    "TurnCompletedNotification",
    "TurnDiffUpdatedNotification",
    "TurnEnvironmentParams",
    "TurnInterruptParams",
    "TurnInterruptResponse",
    "TurnPlanStep",
    "TurnPlanStepStatus",
    "TurnPlanUpdatedNotification",
    "TurnStartParams",
    "TurnStartResponse",
    "TurnStartedNotification",
    "TurnStatus",
    "TurnSteerParams",
    "TurnSteerResponse",
    "UNSET",
    "Usage",
    "UserInput",
]
