"""Semantic port of codex-rs/tui/src/test_support.rs.

Rust's module is test-only glue: it re-exports absolute-path test helpers and
converts app-server protocol enum values through serde JSON into legacy helper
shapes.  The Python port keeps those deterministic helper semantics without
claiming completion for the dependency crate that owns the original path type.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Callable, TypeVar

from pycodex.protocol import SessionSource

from ._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="test_support",
    source="codex/codex-rs/tui/src/test_support.rs",
)

T = TypeVar("T")


class SkillScope(str, Enum):
    USER = "user"
    REPO = "repo"
    SYSTEM = "system"
    ADMIN = "admin"


@dataclass(frozen=True)
class TestPathBuf:
    """Small semantic stand-in for codex_utils_absolute_path test paths."""

    path: str

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("test path must not be empty")

    def abs(self) -> "TestPathBuf":
        return self

    def display(self) -> str:
        return str(self)

    def as_posix(self) -> str:
        return str(self)

    def __fspath__(self) -> str:
        return str(self)

    def __str__(self) -> str:
        text = self.path.replace("\\", "/")
        if len(text) >= 2 and text[1] == ":":
            return text
        if text.startswith("/"):
            return str(PurePosixPath(text))
        return str(PurePosixPath("/", text))


class PathBufExt:
    """Compatibility wrapper mirroring the Rust test helper trait shape."""

    @staticmethod
    def abs(path: str | TestPathBuf) -> TestPathBuf:
        return path if isinstance(path, TestPathBuf) else test_path_buf(str(path))


def test_path_buf(path: str) -> TestPathBuf:
    return TestPathBuf(path)


def test_path_display(path: str) -> str:
    return test_path_buf(path).display()


def session_source_cli(target: Callable[[Any], T] | type[T] | None = None) -> T | SessionSource:
    return from_app_server_wire(SessionSource.cli(), target)


def skill_scope_user(target: Callable[[Any], T] | type[T] | None = None) -> T | SkillScope:
    return from_app_server_wire(SkillScope.USER, target)


def skill_scope_repo(target: Callable[[Any], T] | type[T] | None = None) -> T | SkillScope:
    return from_app_server_wire(SkillScope.REPO, target)


def from_app_server_wire(value: Any, target: Callable[[Any], T] | type[T] | None = None) -> Any:
    """Round-trip an app-server wire value into an optional target shape.

    Rust serializes to ``serde_json::Value`` and immediately deserializes into
    ``T``.  Python callers can either use the normalized wire value directly or
    pass a constructor/callable to receive the decoded value.
    """

    wire_value = _to_wire_value(value)
    if target is None:
        return wire_value
    try:
        return target(wire_value)
    except Exception as exc:  # pragma: no cover - parity boundary message
        raise ValueError(
            f"app-server wire value should map to legacy helper type: {exc}"
        ) from exc


def _to_wire_value(value: Any) -> Any:
    if isinstance(value, SessionSource):
        if value.type == "custom":
            return {"custom": value.custom}
        if value.type == "subagent":
            return {"subAgent": _to_wire_value(value.subagent_source)}
        if value.type == "mcp":
            return "appServer"
        return value.type
    if isinstance(value, SkillScope):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _to_wire_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_wire_value(item) for item in value]
    return value


__all__ = [
    "PathBufExt",
    "RUST_MODULE",
    "SkillScope",
    "TestPathBuf",
    "from_app_server_wire",
    "session_source_cli",
    "skill_scope_repo",
    "skill_scope_user",
    "test_path_buf",
    "test_path_display",
]
