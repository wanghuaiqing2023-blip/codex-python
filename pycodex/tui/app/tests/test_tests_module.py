from pathlib import Path

import pytest

from pycodex.tui.app.tests import (
    APP_SNAPSHOT_DIR,
    AppSnapshotAssertion,
    AppTestFixturePlan,
    NotifiedDrop,
    assert_app_snapshot,
    declared_test_modules,
    heavyweight_fixture_names,
    helper_names,
    lines_to_single_string,
    make_test_app,
    make_test_app_with_channels,
    start_config_write_test_app_server,
    test_absolute_path as build_test_absolute_path,
)


def test_declared_test_modules_match_rust_mod_declarations() -> None:
    assert declared_test_modules() == ("model_catalog", "session_summary", "startup")


def test_snapshot_assertion_models_rust_macro_binding() -> None:
    assert assert_app_snapshot("bypass_hook", "rendered") == AppSnapshotAssertion(
        name="bypass_hook",
        value="rendered",
        snapshot_path=APP_SNAPSHOT_DIR,
    )
    assert APP_SNAPSHOT_DIR == "../snapshots"


def test_absolute_path_accepts_only_absolute_paths(tmp_path: Path) -> None:
    assert build_test_absolute_path(tmp_path) == tmp_path
    with pytest.raises(ValueError):
        build_test_absolute_path("relative/path")


def test_lines_to_single_string_flattens_simple_line_shapes() -> None:
    class Span:
        def __init__(self, content: str) -> None:
            self.content = content

    class Line:
        spans = [Span("he"), Span("llo")]

    assert lines_to_single_string(["one", {"text": "two"}, Line()]) == "one\ntwo\nhello"


def test_helper_and_heavyweight_fixture_boundaries_are_declared() -> None:
    assert "test_absolute_path" in helper_names()
    assert "lines_to_single_string" in helper_names()
    assert heavyweight_fixture_names() == (
        "make_test_app",
        "make_test_app_with_channels",
        "start_config_write_test_app_server",
    )
    assert make_test_app() == AppTestFixturePlan(name="make_test_app")


def test_heavyweight_fixture_helpers_return_semantic_plans() -> None:
    assert make_test_app_with_channels() == AppTestFixturePlan(
        name="make_test_app_with_channels",
        channels=True,
    )
    assert start_config_write_test_app_server() == AppTestFixturePlan(
        name="start_config_write_test_app_server",
        app_server=True,
    )


def test_notify_on_drop_semantic_helper_marks_drop() -> None:
    assert NotifiedDrop().drop().notified is True
