from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pycodex.codex_mcp import McpConnectionManager, McpRuntimeContext
from pycodex.config.mcp_types import McpServerConfig
from pycodex.exec_server.environment import EnvironmentManager


def test_stdio_client_runs_full_mcp_protocol() -> None:
    # Rust: codex-mcp/src/connection_manager.rs and rmcp_client.rs.
    repo_root = Path(__file__).resolve().parents[3]

    async def exercise() -> None:
        config = McpServerConfig.from_mapping(
            {
                "command": sys.executable,
                "args": [
                    "-B",
                    "-m",
                    "pycodex.rmcp_client.bin.test_stdio_server",
                ],
                "cwd": str(repo_root),
                "env": {"MCP_TEST_VALUE": "from-e2e"},
                "required": True,
            }
        )
        context = McpRuntimeContext(
            EnvironmentManager.default_for_tests(),
            repo_root,
        )
        manager = McpConnectionManager(
            {"fixture": config},
            runtime_context=context,
        )
        try:
            tools = await manager.list_all_tools()
            assert {tool.callable_name for tool in tools} >= {
                "echo",
                "cwd",
                "sandbox_meta",
            }

            result = await manager.call_tool(
                "fixture",
                "echo",
                {"message": "hello"},
            )
            assert result["structuredContent"] == {
                "echo": "ECHOING: hello",
                "env": "from-e2e",
            }

            resources = await manager.list_all_resources()
            assert resources["fixture"][0]["uri"] == "memo://codex/example-note"
            resource = await manager.read_resource(
                "fixture",
                "memo://codex/example-note",
            )
            assert resource["contents"][0]["text"].startswith(
                "This is a sample MCP resource"
            )
        finally:
            await manager.close()

    asyncio.run(exercise())
