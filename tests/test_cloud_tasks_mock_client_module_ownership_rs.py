"""Module ownership for ``codex-cloud-tasks-mock-client``."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _definitions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_lib_rs_is_a_pure_mock_client_reexport() -> None:
    path = ROOT / "pycodex" / "cloud_tasks_mock_client" / "__init__.py"

    assert _definitions(path) == set()


def test_mock_rs_owns_mock_client_and_helpers() -> None:
    path = ROOT / "pycodex" / "cloud_tasks_mock_client" / "mock.py"

    assert path.is_file()
    assert _definitions(path) == {
        "MockClient",
        "mock_diff_for",
        "count_from_unified",
    }
