"""Parity tests for low-level helpers in Rust ``codex-tui::status::tests``.

Rust source: ``codex/codex-rs/tui/src/status/tests.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pycodex.tui.line_truncation import Line, Span
from pycodex.tui.status import tests as status_tests


@dataclass
class PermissionsRecorder:
    workspace_roots: list[str] | None = None

    def set_workspace_roots(self, roots: list[str]) -> None:
        self.workspace_roots = list(roots)


@dataclass
class ConfigStub:
    permissions: PermissionsRecorder
    cwd: str | None = None
    workspace_roots: list[str] | None = None


def test_status_tests_render_lines_concatenates_spans() -> None:
    lines = [
        Line.from_spans([Span("Model: "), Span("gpt-5")]),
        "plain",
    ]

    assert status_tests.render_lines(lines) == ["Model: gpt-5", "plain"]


def test_status_tests_sanitize_directory_preserves_card_width() -> None:
    line = "│ Directory: /tmp/workspace     │"

    assert status_tests.sanitize_directory([line]) == ["│ Directory: [[workspace]]      │"]


def test_status_tests_reset_at_from_returns_utc_timestamp() -> None:
    captured_at = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    assert status_tests.reset_at_from(captured_at, 600) == 1704165245


def test_status_tests_workspace_profile_and_cwd_helpers_are_semantic() -> None:
    profile = status_tests.app_server_workspace_write_profile(network_enabled=True)
    assert profile["network"] == "enabled"
    assert profile["file_system"]["entries"][1] == {
        "path": "project_roots",
        "subpath": None,
        "access": "write",
    }

    config = ConfigStub(permissions=PermissionsRecorder())
    status_tests.set_workspace_cwd(config, "/workspace/tests")
    assert config.cwd == "/workspace/tests"
    assert config.workspace_roots == ["/workspace/tests"]
    assert config.permissions.workspace_roots == ["/workspace/tests"]
    assert status_tests.test_status_account_display() is None
