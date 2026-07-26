"""Rust-derived ownership checks for split Core tool handlers."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]

RUST_HANDLER_OWNERS = {
    "pycodex/core/tools/code_mode/execute_handler.py": "CodeModeExecuteHandler",
    "pycodex/core/tools/handlers/agent_jobs/report_agent_job_result.py": "ReportAgentJobResultHandler",
    "pycodex/core/tools/handlers/goal/create_goal.py": "CreateGoalHandler",
    "pycodex/core/tools/handlers/goal/get_goal.py": "GetGoalHandler",
    "pycodex/core/tools/handlers/goal/update_goal.py": "UpdateGoalHandler",
    "pycodex/core/tools/handlers/mcp_resource/list_mcp_resource_templates.py": "ListMcpResourceTemplatesHandler",
    "pycodex/core/tools/handlers/mcp_resource/list_mcp_resources.py": "ListMcpResourcesHandler",
    "pycodex/core/tools/handlers/mcp_resource/read_mcp_resource.py": "ReadMcpResourceHandler",
    "pycodex/core/tools/handlers/multi_agents/close_agent.py": "Handler",
    "pycodex/core/tools/handlers/multi_agents/send_input.py": "Handler",
    "pycodex/core/tools/handlers/multi_agents/spawn.py": "Handler",
    "pycodex/core/tools/handlers/multi_agents/wait.py": "Handler",
    "pycodex/core/tools/handlers/unified_exec/exec_command.py": "ExecCommandHandler",
}


def _defined_classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


class CoreToolHandlerModuleOwnershipTests(unittest.TestCase):
    def test_handlers_are_defined_by_their_rust_coordinate_module(self) -> None:
        for relative_path, type_name in RUST_HANDLER_OWNERS.items():
            with self.subTest(path=relative_path):
                owner = REPO_ROOT / relative_path
                self.assertTrue(owner.is_file(), f"missing Python owner {relative_path}")
                self.assertIn(type_name, _defined_classes(owner))

    def test_goal_parent_only_reexports_child_handlers(self) -> None:
        parent = REPO_ROOT / "pycodex/core/tools/handlers/goal/__init__.py"
        child_types = {
            type_name
            for path, type_name in RUST_HANDLER_OWNERS.items()
            if "/goal/" in path
        }
        self.assertEqual(_defined_classes(parent).intersection(child_types), set())

    def test_other_handler_parents_only_reexport_child_handlers(self) -> None:
        parents = {
            "pycodex/core/tools/code_mode/__init__.py": {"CodeModeExecuteHandler"},
            "pycodex/core/tools/handlers/agent_jobs/__init__.py": {
                "ReportAgentJobResultHandler"
            },
            "pycodex/core/tools/handlers/mcp_resource/__init__.py": {
                "ListMcpResourceTemplatesHandler",
                "ListMcpResourcesHandler",
                "ReadMcpResourceHandler",
            },
            "pycodex/core/tools/handlers/multi_agents/__init__.py": {
                "V1CloseAgentHandler",
                "SendInputHandler",
                "V1SpawnAgentHandler",
                "V1WaitAgentHandler",
            },
            "pycodex/core/tools/handlers/unified_exec/__init__.py": {
                "ExecCommandHandler",
                "ExecCommandHandlerOptions",
            },
        }
        for relative_path, child_types in parents.items():
            with self.subTest(path=relative_path):
                self.assertEqual(
                    _defined_classes(REPO_ROOT / relative_path).intersection(child_types),
                    set(),
                )


if __name__ == "__main__":
    unittest.main()
