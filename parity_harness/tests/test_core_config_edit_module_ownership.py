"""Ownership checks for ``core::config::edit::document_helpers``."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _defined_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class CoreConfigEditModuleOwnershipTests(unittest.TestCase):
    def test_document_helpers_is_a_child_of_the_edit_package(self) -> None:
        edit_package = REPO_ROOT / "pycodex/core/config/edit"
        parent = edit_package / "__init__.py"
        child = edit_package / "document_helpers.py"

        self.assertTrue(parent.is_file())
        self.assertTrue(child.is_file())
        self.assertTrue(
            {
                "ensure_table_for_write",
                "ensure_table_for_read",
                "serialize_mcp_server",
                "serialize_mcp_server_inline",
                "merge_inline_table",
                "new_implicit_table",
                "parse_tool_suggest_disabled_tool",
                "parse_tool_suggest_disabled_tool_table",
                "tool_suggest_disabled_tools_value",
            }.issubset(_defined_functions(child))
        )

    def test_edit_parent_does_not_define_document_helper_items(self) -> None:
        parent = REPO_ROOT / "pycodex/core/config/edit/__init__.py"
        foreign_items = {
            "_serialize_mcp_server",
            "_serialize_mcp_server_tools",
            "_iter_tool_suggest_disabled_tools",
        }

        self.assertEqual(_defined_functions(parent).intersection(foreign_items), set())


if __name__ == "__main__":
    unittest.main()
