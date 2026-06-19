"""Feedback protocol types ported from ``protocol/v2/feedback.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class FeedbackUploadParams:
    classification: str
    reason: str | None = None
    thread_id: str | None = None
    include_logs: bool = False
    extra_log_files: tuple[Path, ...] | None = None
    tags: dict[str, str] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification", _ensure_str(self.classification, "classification"))
        object.__setattr__(self, "reason", _optional_str(self.reason, "reason"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "include_logs", _ensure_bool(self.include_logs, "include_logs"))
        object.__setattr__(
            self,
            "extra_log_files",
            _optional_path_tuple(self.extra_log_files, "extra_log_files"),
        )
        object.__setattr__(self, "tags", _optional_string_map(self.tags, "tags"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FeedbackUploadParams":
        if not isinstance(value, Mapping):
            raise TypeError("FeedbackUploadParams mapping must be a mapping")
        return cls(
            classification=_ensure_str(value["classification"], "classification"),
            reason=_optional_str(_pick(value, "reason"), "reason"),
            thread_id=_optional_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            include_logs=_ensure_bool(
                _pick(value, "include_logs", "includeLogs", default=False),
                "include_logs",
            ),
            extra_log_files=_optional_path_tuple(
                _pick(value, "extra_log_files", "extraLogFiles"),
                "extra_log_files",
            ),
            tags=_optional_string_map(_pick(value, "tags"), "tags"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "classification": self.classification,
            "reason": self.reason,
            "thread_id": self.thread_id,
            "extra_log_files": _paths_to_strings(self.extra_log_files),
            "tags": None if self.tags is None else dict(self.tags),
        }
        if self.include_logs:
            result["include_logs"] = self.include_logs
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "classification": self.classification,
            "reason": self.reason,
            "threadId": self.thread_id,
            "extraLogFiles": _paths_to_strings(self.extra_log_files),
            "tags": None if self.tags is None else dict(self.tags),
        }
        if self.include_logs:
            result["includeLogs"] = self.include_logs
        return result


@dataclass(frozen=True)
class FeedbackUploadResponse:
    thread_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "FeedbackUploadResponse":
        if not isinstance(value, Mapping):
            raise TypeError("FeedbackUploadResponse mapping must be a mapping")
        return cls(thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id}


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


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_path_tuple(value: JsonValue, field_name: str) -> tuple[Path, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of paths")
    paths: list[Path] = []
    for item in value:
        if isinstance(item, Path):
            paths.append(item)
        elif isinstance(item, str):
            paths.append(Path(item))
        else:
            raise TypeError(f"{field_name} item must be a path string or Path")
    return tuple(paths)


def _paths_to_strings(value: tuple[Path, ...] | None) -> list[str] | None:
    if value is None:
        return None
    return [str(path) for path in value]


def _optional_string_map(value: JsonValue, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return {
        _ensure_str(key, f"{field_name} key"): _ensure_str(item, f"{field_name} value")
        for key, item in value.items()
    }


__all__ = [
    "FeedbackUploadParams",
    "FeedbackUploadResponse",
]
