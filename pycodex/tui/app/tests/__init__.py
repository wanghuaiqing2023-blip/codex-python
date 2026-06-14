"""Test-only aggregation helpers for Rust ``codex-tui::app::tests``.

Rust source: ``codex/codex-rs/tui/src/app/tests.rs``.

This module is not production TUI behavior.  It mirrors the small pieces that
``app/tests.rs`` itself owns: child test-module declarations, app snapshot
binding, lightweight fixture-helper names, and explicit boundaries for the
heavyweight async ``App`` fixtures that belong to integration tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::tests",
    source="codex/codex-rs/tui/src/app/tests.rs",
)

DECLARED_TEST_MODULES: tuple[str, ...] = (
    "model_catalog",
    "session_summary",
    "startup",
)

APP_SNAPSHOT_DIR = "../snapshots"

LIGHTWEIGHT_HELPERS: tuple[str, ...] = (
    "test_absolute_path",
    "assert_app_snapshot",
    "lines_to_single_string",
    "test_turn",
    "turn_started_notification",
    "turn_completed_notification",
    "thread_closed_notification",
    "token_usage_notification",
    "agent_message_delta_notification",
    "exec_approval_request",
    "request_user_input_request",
    "test_session_telemetry",
)

HEAVYWEIGHT_APP_FIXTURES: tuple[str, ...] = (
    "make_test_app",
    "make_test_app_with_channels",
    "start_config_write_test_app_server",
)

TEST_STACK_SIZE_BYTES: int | None = None
WORKER_THREADS: int | None = None


@dataclass(frozen=True)
class AppSnapshotAssertion:
    """Semantic model for the Rust ``assert_app_snapshot!`` macro binding."""

    name: str
    value: str
    snapshot_path: str = APP_SNAPSHOT_DIR


@dataclass(frozen=True)
class NotifiedDrop:
    """Semantic stand-in for Rust's drop-notification test helper."""

    notified: bool = False

    def drop(self) -> "NotifiedDrop":
        return NotifiedDrop(notified=True)


# Preserve the scaffold's historical exported name while giving it behavior.
NotifyOnDrop = NotifiedDrop


def test_absolute_path(path: str | Path) -> Path:
    """Return an absolute path or raise, matching Rust's fixture helper intent."""

    value = Path(path)
    if not value.is_absolute():
        raise ValueError(f"absolute test path required: {path!r}")
    return value


def assert_app_snapshot(name: str, value: Any) -> AppSnapshotAssertion:
    """Create the semantic snapshot assertion used by app-level tests."""

    return AppSnapshotAssertion(name=str(name), value=str(value))


def lines_to_single_string(lines: Any) -> str:
    """Flatten Rust/ratatui-like line values into a newline-joined string."""

    rendered: list[str] = []
    for line in lines:
        if isinstance(line, str):
            rendered.append(line)
        elif isinstance(line, dict):
            rendered.append(str(line.get("text", "")))
        elif hasattr(line, "spans"):
            rendered.append("".join(str(getattr(span, "content", span)) for span in line.spans))
        else:
            rendered.append(str(getattr(line, "text", line)))
    return "\n".join(rendered)


def declared_test_modules() -> tuple[str, ...]:
    return DECLARED_TEST_MODULES


def helper_names() -> tuple[str, ...]:
    return LIGHTWEIGHT_HELPERS


def heavyweight_fixture_names() -> tuple[str, ...]:
    return HEAVYWEIGHT_APP_FIXTURES


def make_test_app(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::tests.make_test_app requires full async App/AppServer runtime")


def make_test_app_with_channels(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::tests.make_test_app_with_channels requires full async App/AppServer runtime")


async def start_config_write_test_app_server(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::tests.start_config_write_test_app_server requires app-server runtime")


__all__ = [
    "APP_SNAPSHOT_DIR",
    "AppSnapshotAssertion",
    "DECLARED_TEST_MODULES",
    "HEAVYWEIGHT_APP_FIXTURES",
    "LIGHTWEIGHT_HELPERS",
    "NotifyOnDrop",
    "NotifiedDrop",
    "RUST_MODULE",
    "TEST_STACK_SIZE_BYTES",
    "WORKER_THREADS",
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
