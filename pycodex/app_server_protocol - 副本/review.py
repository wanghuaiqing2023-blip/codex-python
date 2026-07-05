"""Review protocol types ported from ``protocol/v2/review.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

JsonValue = Any


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


class ReviewDelivery(_StringEnum):
    INLINE = "inline"
    DETACHED = "detached"


@dataclass(frozen=True)
class ReviewTarget:
    type: str
    branch: str | None = None
    sha: str | None = None
    title: str | None = None
    instructions: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_str(self.type, "type"))
        object.__setattr__(self, "branch", _optional_str(self.branch, "branch"))
        object.__setattr__(self, "sha", _optional_str(self.sha, "sha"))
        object.__setattr__(self, "title", _optional_str(self.title, "title"))
        object.__setattr__(self, "instructions", _optional_str(self.instructions, "instructions"))
        if self.type == "uncommittedChanges":
            _reject_fields(self, "branch", "sha", "title", "instructions")
        elif self.type == "baseBranch":
            _require_field(self.branch, "branch")
            _reject_fields(self, "sha", "title", "instructions")
        elif self.type == "commit":
            _require_field(self.sha, "sha")
            _reject_fields(self, "branch", "instructions")
        elif self.type == "custom":
            _require_field(self.instructions, "instructions")
            _reject_fields(self, "branch", "sha", "title")
        else:
            raise ValueError(f"unknown review target type: {self.type}")

    @classmethod
    def uncommitted_changes(cls) -> "ReviewTarget":
        return cls("uncommittedChanges")

    @classmethod
    def base_branch(cls, branch: str) -> "ReviewTarget":
        return cls("baseBranch", branch=branch)

    @classmethod
    def commit(cls, sha: str, title: str | None = None) -> "ReviewTarget":
        return cls("commit", sha=sha, title=title)

    @classmethod
    def custom(cls, instructions: str) -> "ReviewTarget":
        return cls("custom", instructions=instructions)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ReviewTarget":
        _ensure_mapping(value, "ReviewTarget")
        target_type = _ensure_str(value["type"], "type")
        if target_type == "uncommittedChanges":
            return cls.uncommitted_changes()
        if target_type == "baseBranch":
            return cls.base_branch(_ensure_str(value["branch"], "branch"))
        if target_type == "commit":
            return cls.commit(_ensure_str(value["sha"], "sha"), _optional_str(value.get("title"), "title"))
        if target_type == "custom":
            return cls.custom(_ensure_str(value["instructions"], "instructions"))
        raise ValueError(f"unknown review target type: {target_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "baseBranch":
            result["branch"] = self.branch
        elif self.type == "commit":
            result["sha"] = self.sha
            result["title"] = self.title
        elif self.type == "custom":
            result["instructions"] = self.instructions
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ReviewStartParams:
    thread_id: str
    target: ReviewTarget | Mapping[str, JsonValue]
    delivery: ReviewDelivery | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "target", _target(self.target))
        object.__setattr__(self, "delivery", None if self.delivery is None else ReviewDelivery.parse(self.delivery))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ReviewStartParams":
        _ensure_mapping(value, "ReviewStartParams")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            target=_target(value["target"]),
            delivery=None if _pick(value, "delivery") is None else ReviewDelivery.parse(value["delivery"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "thread_id": self.thread_id,
            "target": self.target.to_mapping(),
            "delivery": None if self.delivery is None else self.delivery.value,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "threadId": self.thread_id,
            "target": self.target.to_camel_mapping(),
            "delivery": None if self.delivery is None else self.delivery.value,
        }


@dataclass(frozen=True)
class ReviewStartResponse:
    turn: JsonValue
    review_thread_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "turn", _turn_value(self.turn, "turn"))
        object.__setattr__(self, "review_thread_id", _ensure_str(self.review_thread_id, "review_thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ReviewStartResponse":
        _ensure_mapping(value, "ReviewStartResponse")
        return cls(
            turn=_turn_value(value["turn"], "turn"),
            review_thread_id=_ensure_str(_pick(value, "review_thread_id", "reviewThreadId"), "review_thread_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"turn": _serialize_turn(self.turn, camel=False), "review_thread_id": self.review_thread_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"turn": _serialize_turn(self.turn, camel=True), "reviewThreadId": self.review_thread_id}


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _require_field(value: JsonValue, field_name: str) -> None:
    if value is None:
        raise ValueError(f"{field_name} is required for this review target")


def _reject_fields(target: ReviewTarget, *field_names: str) -> None:
    for field_name in field_names:
        if getattr(target, field_name) is not None:
            raise ValueError(f"{field_name} is not valid for {target.type} review target")


def _target(value: JsonValue) -> ReviewTarget:
    if isinstance(value, ReviewTarget):
        return value
    if isinstance(value, Mapping):
        return ReviewTarget.from_mapping(value)
    raise TypeError("target must be ReviewTarget or mapping")


def _turn_value(value: JsonValue, field_name: str) -> JsonValue:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_mapping") or hasattr(value, "to_camel_mapping"):
        return value
    raise TypeError(f"{field_name} must be a Turn-compatible mapping")


def _serialize_turn(value: JsonValue, *, camel: bool) -> JsonValue:
    if camel and hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return dict(value)
    return value


__all__ = [
    "ReviewDelivery",
    "ReviewStartParams",
    "ReviewStartResponse",
    "ReviewTarget",
]
