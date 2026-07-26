"""Rust-derived ownership checks for ``core::tasks::user_shell``."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _defined_items(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


class CoreTasksUserShellModuleOwnershipTests(unittest.TestCase):
    def test_user_shell_items_have_their_rust_aligned_owner(self) -> None:
        owner = REPO_ROOT / "pycodex/core/tasks/user_shell.py"

        self.assertTrue(owner.is_file(), f"missing Python owner {owner}")
        self.assertTrue(
            {
                "UserShellCommandMode",
                "UserShellCommandTask",
                "execute_user_shell_command",
                "persist_user_shell_output",
            }.issubset(_defined_items(owner))
        )

    def test_session_handlers_does_not_define_user_shell_task_items(self) -> None:
        handlers = REPO_ROOT / "pycodex/core/session/handlers.py"

        self.assertEqual(
            _defined_items(handlers).intersection(
                {
                    "UserShellCommandMode",
                    "UserShellCommandTask",
                    "execute_user_shell_command",
                    "persist_user_shell_output",
                }
            ),
            set(),
        )


if __name__ == "__main__":
    unittest.main()
