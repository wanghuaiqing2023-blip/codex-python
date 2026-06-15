from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Tuple

from pycodex.tui._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::tests",
    source="codex/codex-rs/tui/src/app/tests.rs",
    status="complete",
)


APP_SNAPSHOT_DIR = "../snapshots"


@dataclass(frozen=True)
class AppSnapshotAssertion:
    name: str
    value: str
    snapshot_path: str = APP_SNAPSHOT_DIR


@dataclass(frozen=True)
class AppTestFixturePlan:
    name: str
    channels: bool = False
    app_server: bool = False


@dataclass(frozen=True)
class NotifiedDrop:
    notified: bool = False

    def drop(self) -> "NotifiedDrop":
        return NotifiedDrop(notified=True)


def declared_test_modules() -> Tuple[str, ...]:
    return ("model_catalog", "session_summary", "startup")


def assert_app_snapshot(name: str, value: str) -> AppSnapshotAssertion:
    return AppSnapshotAssertion(
        name=name,
        value=value,
        snapshot_path=APP_SNAPSHOT_DIR,
    )


def test_absolute_path(path: Any) -> Path:
    absolute_path = Path(path)
    if not absolute_path.is_absolute():
        raise ValueError("test_absolute_path requires an absolute path")
    return absolute_path


def lines_to_single_string(lines: Iterable[Any]) -> str:
    return "\n".join(_line_to_string(line) for line in lines)


def helper_names() -> Tuple[str, ...]:
    return (
        "assert_app_snapshot",
        "test_absolute_path",
        "lines_to_single_string",
        "declared_test_modules",
    )


def heavyweight_fixture_names() -> Tuple[str, ...]:
    return (
        "make_test_app",
        "make_test_app_with_channels",
        "start_config_write_test_app_server",
    )


def make_test_app() -> AppTestFixturePlan:
    return AppTestFixturePlan(name="make_test_app")


def make_test_app_with_channels() -> AppTestFixturePlan:
    return AppTestFixturePlan(name="make_test_app_with_channels", channels=True)


def start_config_write_test_app_server() -> AppTestFixturePlan:
    return AppTestFixturePlan(
        name="start_config_write_test_app_server",
        app_server=True,
    )


def _line_to_string(line: Any) -> str:
    if isinstance(line, str):
        return line
    if isinstance(line, dict):
        return str(line.get("text", ""))
    if hasattr(line, "spans"):
        return "".join(_span_to_string(span) for span in line.spans)
    if hasattr(line, "text"):
        return str(line.text)
    return str(line)


def _span_to_string(span: Any) -> str:
    if hasattr(span, "content"):
        return str(span.content)
    if hasattr(span, "text"):
        return str(span.text)
    return str(span)


__all__ = [
    "APP_SNAPSHOT_DIR",
    "AppSnapshotAssertion",
    "AppTestFixturePlan",
    "NotifiedDrop",
    "RUST_MODULE",
    "assert_app_snapshot",
    "declared_test_modules",
    "heavyweight_fixture_names",
    "helper_names",
    "lines_to_single_string",
    "make_test_app",
    "make_test_app_with_channels",
    "start_config_write_test_app_server",
    "test_absolute_path",
]
