from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pycodex.protocol import ElicitationAction
from pycodex.rmcp_client import (
    ElicitationResponse,
    ListToolsWithConnectorIdResult,
    RmcpClient,
    ToolWithConnectorId,
)


class _Transport:
    def __init__(self) -> None:
        self.initialized_with: Any = None
        self.closed = False
        self.tool_calls: list[tuple[str, Any, Any]] = []

    async def initialize(self, params: Any) -> dict[str, Any]:
        self.initialized_with = params
        return {"serverInfo": {"name": "in-process"}}

    async def list_tools(self, _params: Any = None) -> dict[str, Any]:
        return {
            "nextCursor": "next",
            "tools": [
                {
                    "name": "search",
                    "_meta": {
                        "connector_id": "connector-1",
                        "connector_display_name": "Calendar",
                        "connectorDescription": "Search calendars",
                    },
                }
            ],
        }

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.tool_calls.append((name, arguments, meta))
        return {"content": [{"type": "text", "text": "ok"}]}

    async def shutdown(self) -> None:
        self.closed = True


class _Factory:
    def __init__(self, transport: _Transport) -> None:
        self.transport = transport
        self.opens = 0

    async def open(self) -> _Transport:
        self.opens += 1
        return self.transport


def test_rmcp_client_items_use_rust_module_owner() -> None:
    assert RmcpClient.__module__ == "pycodex.rmcp_client.rmcp_client"
    assert ElicitationResponse.__module__ == "pycodex.rmcp_client.rmcp_client"
    assert ToolWithConnectorId.__module__ == "pycodex.rmcp_client.rmcp_client"
    assert ListToolsWithConnectorIdResult.__module__ == "pycodex.rmcp_client.rmcp_client"


def test_in_process_client_runs_initialize_tool_and_shutdown_chain() -> None:
    async def scenario() -> None:
        transport = _Transport()
        factory = _Factory(transport)
        client = await RmcpClient.new_in_process_client(factory)

        initialized = await client.initialize(
            {"clientInfo": {"name": "test"}},
            timeout=1,
            send_elicitation=lambda *_args: None,
        )
        assert initialized == {"serverInfo": {"name": "in-process"}}
        assert transport.initialized_with == {"clientInfo": {"name": "test"}}
        assert factory.opens == 1

        listed = await client.list_tools_with_connector_ids(timeout=1)
        assert listed == ListToolsWithConnectorIdResult(
            next_cursor="next",
            tools=(
                ToolWithConnectorId(
                    tool={"name": "search", "_meta": listed.tools[0].tool["_meta"]},
                    connector_id="connector-1",
                    connector_name="Calendar",
                    connector_description="Search calendars",
                ),
            ),
        )

        result = await client.call_tool(
            "search",
            {"query": "today"},
            {"trace": "one"},
            timeout=1,
        )
        assert result == {"content": [{"type": "text", "text": "ok"}]}
        assert transport.tool_calls == [
            ("search", {"query": "today"}, {"trace": "one"})
        ]

        await client.shutdown()
        assert transport.closed
        with pytest.raises(RuntimeError, match="MCP client is shut down"):
            await client.list_tools(timeout=1)

    asyncio.run(scenario())


def test_call_tool_rejects_non_object_arguments_and_meta() -> None:
    async def scenario() -> None:
        client = await RmcpClient.new_in_process_client(_Factory(_Transport()))
        await client.initialize({}, timeout=1, send_elicitation=lambda *_args: None)
        with pytest.raises(ValueError, match="arguments must be a JSON object"):
            await client.call_tool("search", ["bad"], None)
        with pytest.raises(ValueError, match="_meta must be a JSON object"):
            await client.call_tool("search", None, ["bad"])

    asyncio.run(scenario())


def test_elicitation_response_uses_protocol_action() -> None:
    response = ElicitationResponse(
        action=ElicitationAction.ACCEPT,
        content={"approved": True},
        meta={"trace": "one"},
    )
    assert response.action is ElicitationAction.ACCEPT

