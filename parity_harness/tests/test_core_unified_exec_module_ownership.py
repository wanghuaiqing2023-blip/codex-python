"""Rust-derived ownership checks for Core unified-exec modules."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _classes(relative_path: str) -> set[str]:
    path = REPO_ROOT / relative_path
    if not path.is_file():
        return set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


class CoreUnifiedExecModuleOwnershipTests(unittest.TestCase):
    def test_errors_module_owns_unified_exec_error(self) -> None:
        self.assertIn("UnifiedExecError", _classes("pycodex/core/unified_exec/errors.py"))
        self.assertNotIn(
            "UnifiedExecError",
            _classes("pycodex/core/unified_exec/__init__.py"),
        )

    def test_process_module_owns_unified_exec_process(self) -> None:
        self.assertIn(
            "UnifiedExecProcess",
            _classes("pycodex/core/unified_exec/process.py"),
        )
        self.assertNotIn(
            "_ManagedUnifiedExecSession",
            _classes("pycodex/core/unified_exec/process_manager.py"),
        )


if __name__ == "__main__":
    unittest.main()
