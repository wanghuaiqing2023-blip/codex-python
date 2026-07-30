"""Task response types and fetch operation owned by ``get_task.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .chatgpt_client import chatgpt_get_request

JsonValue = Any


@dataclass(frozen=True)
class OutputDiff:
    diff: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "OutputDiff":
        return cls(diff=str(value["diff"]))


@dataclass(frozen=True)
class OutputItem:
    type: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "OutputItem":
        if value.get("type") == "pr":
            return PrOutputItem(
                output_diff=OutputDiff.from_mapping(_mapping(value, "output_diff"))
            )
        return OtherOutputItem()


@dataclass(frozen=True)
class PrOutputItem(OutputItem):
    output_diff: OutputDiff

    def __init__(self, output_diff: OutputDiff) -> None:
        object.__setattr__(self, "type", "pr")
        object.__setattr__(self, "output_diff", output_diff)


@dataclass(frozen=True)
class OtherOutputItem(OutputItem):
    def __init__(self) -> None:
        object.__setattr__(self, "type", "other")


@dataclass(frozen=True)
class AssistantTurn:
    output_items: tuple[OutputItem, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AssistantTurn":
        raw_items = value.get("output_items", ())
        if not isinstance(raw_items, (list, tuple)):
            raise TypeError("output_items must be an array")
        return cls(
            tuple(OutputItem.from_mapping(_ensure_mapping(item)) for item in raw_items)
        )


@dataclass(frozen=True)
class GetTaskResponse:
    current_diff_task_turn: AssistantTurn | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GetTaskResponse":
        raw_turn = value.get("current_diff_task_turn")
        return cls(
            None
            if raw_turn is None
            else AssistantTurn.from_mapping(_ensure_mapping(raw_turn))
        )


async def get_task(config: Any, task_id: str) -> GetTaskResponse:
    payload = await chatgpt_get_request(config, f"/wham/tasks/{task_id}")
    return GetTaskResponse.from_mapping(_ensure_mapping(payload))


def _mapping(value: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    return _ensure_mapping(value[key])


def _ensure_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError("task response value must be an object")
    return value


__all__ = [
    "AssistantTurn",
    "GetTaskResponse",
    "OtherOutputItem",
    "OutputDiff",
    "OutputItem",
    "PrOutputItem",
    "get_task",
]
