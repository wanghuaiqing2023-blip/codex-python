from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "pycodex" / "ext" / "web_search"


def _defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_web_search_extension_rust_modules_have_unique_python_owners() -> None:
    expected = {
        "extension.py": {
            "WebSearchExtension",
            "WebSearchExtensionConfig",
            "install",
            "search_settings",
        },
        "history.py": {"recent_input"},
        "output.py": {"EncryptedSearchOutput"},
        "schema.py": {"commands_schema"},
        "tool.py": {"WebSearchTool", "parse_commands"},
    }
    for relative, names in expected.items():
        path = PACKAGE / relative
        assert path.is_file(), f"missing Python owner for Rust module: {relative}"
        assert names <= _defined_names(path)


def test_web_search_extension_crate_root_only_reexports_install() -> None:
    assert not _defined_names(PACKAGE / "__init__.py")
