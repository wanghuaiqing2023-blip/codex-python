from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "backend_client"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_backend_client_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "client.py": {
            "AddCreditsNudgeCreditType",
            "Client",
            "PathStyle",
            "RequestError",
        },
        "types.py": {
            "CodeTaskDetailsResponse",
            "ContentFragment",
            "Turn",
            "TurnAttemptsSiblingTurnsResponse",
            "TurnError",
            "TurnItem",
            "Worklog",
            "WorklogMessage",
        },
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_backend_client_crate_root_does_not_define_child_items() -> None:
    names = _defined_names(PACKAGE / "__init__.py")
    assert not names
