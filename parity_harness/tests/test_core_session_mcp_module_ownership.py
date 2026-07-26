"""Rust-derived ownership checks for ``core::session::mcp``."""

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


class CoreSessionMcpModuleOwnershipTests(unittest.TestCase):
    def test_session_mcp_owns_the_rust_production_items(self) -> None:
        owner = REPO_ROOT / "pycodex/core/session/mcp.py"
        expected = {
            "GuardianElicitationReview",
            "GuardianMcpElicitationReviewer",
            "McpServerElicitationOutcome",
            "PluginInstallElicitationTelemetryMetadata",
            "mcp_elicitation_reviewer",
            "request_mcp_server_elicitation",
            "resolve_elicitation",
            "list_resources",
            "list_resource_templates",
            "read_resource",
            "call_tool",
            "refresh_mcp_servers_inner",
            "refresh_mcp_servers_if_requested",
            "refresh_mcp_servers_now",
            "cancel_mcp_startup",
            "review_guardian_mcp_elicitation",
            "guardian_elicitation_review_request",
            "plugin_install_elicitation_telemetry_metadata",
            "mcp_elicitation_response_from_guardian_decision_parts",
        }

        self.assertTrue(owner.is_file(), f"missing Python owner {owner}")
        self.assertTrue(expected.issubset(_defined_items(owner)))


if __name__ == "__main__":
    unittest.main()
