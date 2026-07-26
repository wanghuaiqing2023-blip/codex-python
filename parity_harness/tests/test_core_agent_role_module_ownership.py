"""Rust-derived ownership checks for ``core::agent::role`` inline modules."""

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


class CoreAgentRoleModuleOwnershipTests(unittest.TestCase):
    def test_inline_modules_use_one_continuous_role_package(self) -> None:
        role_package = REPO_ROOT / "pycodex/core/agent/role"
        expected = {
            "__init__.py": {"apply_role_to_config", "resolve_role_config"},
            "built_in.py": {"configs", "config_file_contents"},
            "reload.py": {"build_next_config"},
            "spawn_tool_spec.py": {"build", "build_from_configs", "format_role"},
        }

        self.assertTrue(role_package.is_dir())
        for filename, functions in expected.items():
            with self.subTest(filename=filename):
                owner = role_package / filename
                self.assertTrue(owner.is_file(), f"missing Python owner {owner}")
                self.assertTrue(functions.issubset(_defined_functions(owner)))

    def test_config_agent_roles_does_not_own_agent_role_items(self) -> None:
        config_owner = REPO_ROOT / "pycodex/core/config/agent_roles.py"
        foreign_items = {
            "built_in_agent_role_configs",
            "built_in_agent_role_config_file_contents",
            "resolve_role_config",
            "build_spawn_agent_tool_description",
            "format_role_for_spawn_tool",
            "locked_settings_note_for_role",
        }

        self.assertEqual(_defined_functions(config_owner).intersection(foreign_items), set())


if __name__ == "__main__":
    unittest.main()
