"""Function tool error boundary ported from ``core/src/function_tool.rs``.

The Rust core module re-exports ``codex_tools::FunctionCallError``.  The actual
enum has two variants: model-visible recoverable errors and fatal internal
errors.  Keeping this as a shared Python type lets tool routers, agent
resolution, apply-patch, and stream-event handling agree on the same boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FunctionCallErrorKind(str, Enum):
    RESPOND_TO_MODEL = "respond_to_model"
    FATAL = "fatal"


@dataclass(frozen=True)
class FunctionCallError(Exception):
    kind: FunctionCallErrorKind
    message: str

    @classmethod
    def respond_to_model(cls, message: str) -> "FunctionCallError":
        return cls(FunctionCallErrorKind.RESPOND_TO_MODEL, _ensure_str(message, "message"))

    @classmethod
    def fatal(cls, message: str) -> "FunctionCallError":
        return cls(FunctionCallErrorKind.FATAL, _ensure_str(message, "message"))

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FunctionCallErrorKind):
            if not isinstance(self.kind, str):
                raise TypeError("kind must be a FunctionCallErrorKind or string")
            try:
                object.__setattr__(self, "kind", FunctionCallErrorKind(self.kind))
            except ValueError as exc:
                raise ValueError(f"unknown FunctionCallError kind: {self.kind}") from exc
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "args", (str(self),))

    @property
    def is_model_response(self) -> bool:
        return self.kind is FunctionCallErrorKind.RESPOND_TO_MODEL

    @property
    def is_fatal(self) -> bool:
        return self.kind is FunctionCallErrorKind.FATAL

    def __str__(self) -> str:
        if self.kind is FunctionCallErrorKind.FATAL:
            return f"Fatal error: {self.message}"
        return self.message


def _ensure_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


__all__ = [
    "FunctionCallError",
    "FunctionCallErrorKind",
]
