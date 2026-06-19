"""Plan tool argument models.

Ported from ``codex/codex-rs/protocol/src/plan_tool.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


JsonValue = Any


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _deny_unknown_fields(value: dict[str, JsonValue], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"{label} has unknown field(s): {joined}")


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass(frozen=True)
class PlanItemArg:
    step: str
    status: StepStatus

    def __post_init__(self) -> None:
        if not isinstance(self.step, str):
            raise TypeError("step must be a string")
        object.__setattr__(self, "status", StepStatus(self.status))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "PlanItemArg":
        data = _mapping(value, "plan item")
        _deny_unknown_fields(data, {"step", "status"}, "plan item")
        return cls(step=_required_str(data, "step"), status=StepStatus(_required_str(data, "status")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"step": self.step, "status": self.status.value}


@dataclass(frozen=True)
class UpdatePlanArgs:
    plan: tuple[PlanItemArg, ...]
    explanation: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.plan, str) or not isinstance(self.plan, (list, tuple)):
            raise TypeError("plan must be a list or tuple")
        if not isinstance(self.plan, tuple):
            object.__setattr__(self, "plan", tuple(self.plan))
        if not all(isinstance(item, PlanItemArg) for item in self.plan):
            raise TypeError("plan entries must be PlanItemArg")
        if self.explanation is not None and not isinstance(self.explanation, str):
            raise TypeError("explanation must be a string or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "UpdatePlanArgs":
        data = _mapping(value, "update plan args")
        _deny_unknown_fields(data, {"explanation", "plan"}, "update plan args")
        if "plan" not in data:
            raise KeyError("plan")
        raw_plan = data.get("plan")
        if not isinstance(raw_plan, list):
            raise TypeError("plan must be a list")
        return cls(
            plan=tuple(PlanItemArg.from_mapping(item) for item in raw_plan),
            explanation=_optional_str(data, "explanation"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"plan": [item.to_mapping() for item in self.plan]}
        if self.explanation is not None:
            data["explanation"] = self.explanation
        return data
