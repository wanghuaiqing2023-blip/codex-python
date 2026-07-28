from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from pycodex.config.mcp_types import McpServerEnvVar
from pycodex.exec_server.process import ExecBackend, ExecProcess, StartedExecProcess
from pycodex.exec_server.protocol import (
    ExecParams,
    ReadResponse,
    WriteResponse,
    WriteStatus,
)
from pycodex.rmcp_client.rmcp_client import RmcpClient
from pycodex.rmcp_client.stdio_server_launcher import (
    ExecutorStdioServerLauncher,
    LocalStdioServerLauncher,
    StdioServerCommand,
)


_MCP_SERVER = r"""
import json
import os
import sys

for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        continue
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fixture", "version": "1"},
        }
    elif method == "tools/list":
        result = {
            "tools": [{
                "name": "echo",
                "description": "echo a value",
                "inputSchema": {"type": "object"},
                "_meta": {"connector_id": "fixture"},
            }]
        }
    elif method == "tools/call":
        value = message.get("params", {}).get("arguments", {}).get("value")
        result = {
            "content": [{"type": "text", "text": str(value)}],
            "environment": os.environ.get("PYCODEX_RMCP_FIXTURE"),
        }
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
    sys.stdout.flush()
"""

_ELICITATION_SERVER = r"""
import json
import sys

initialize = json.loads(sys.stdin.readline())
sys.stdout.write(json.dumps({
    "jsonrpc": "2.0",
    "id": "server-elicitation",
    "method": "elicitation/create",
    "params": {
        "message": "Persist this choice?",
        "_meta": {
            "progressToken": "internal",
            "persist": "session",
        },
    },
}) + "\n")
sys.stdout.flush()
elicitation = json.loads(sys.stdin.readline())
sys.stdout.write(json.dumps({
    "jsonrpc": "2.0",
    "id": initialize["id"],
    "result": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "serverInfo": {"name": "elicitation-fixture", "version": "1"},
        "elicitationResult": elicitation["result"],
    },
}) + "\n")
sys.stdout.flush()
"""


@pytest.mark.asyncio
async def test_local_launcher_resolves_program_and_exchanges_json_rpc(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Rust: codex-rmcp-client/src/stdio_server_launcher.rs::LocalStdioServerLauncher.
    import pycodex.rmcp_client.stdio_server_launcher as launcher_module

    real_resolve = launcher_module.program_resolver.resolve
    calls: list[tuple[str, Path]] = []

    def recording_resolve(
        program: str,
        environment: dict[str, str],
        cwd: str | os.PathLike[str],
    ) -> str:
        calls.append((program, Path(cwd)))
        return real_resolve(program, environment, cwd)

    monkeypatch.setattr(
        launcher_module.program_resolver,
        "resolve",
        recording_resolve,
    )
    launcher = LocalStdioServerLauncher(tmp_path)
    transport = await launcher.launch(
        StdioServerCommand(
            program=sys.executable,
            args=("-u", "-c", _MCP_SERVER),
            env={"PYCODEX_RMCP_FIXTURE": "local"},
            env_vars=(),
            cwd=None,
        )
    )
    await transport.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"arguments": {"value": "hello"}},
        }
    )
    response = await transport.receive()
    await transport.close()

    assert calls == [(sys.executable, tmp_path)]
    assert response["result"]["content"][0]["text"] == "hello"
    assert response["result"]["environment"] == "local"
    assert transport.process_handle().terminated


@pytest.mark.asyncio
async def test_rmcp_client_stdio_real_initialize_list_and_call(tmp_path: Path) -> None:
    # Rust: RmcpClient::new_stdio_client -> launcher -> serve_client.
    client = await RmcpClient.new_stdio_client(
        program=sys.executable,
        args=("-u", "-c", _MCP_SERVER),
        env={"PYCODEX_RMCP_FIXTURE": "client"},
        env_vars=(),
        cwd=tmp_path,
        launcher=LocalStdioServerLauncher(tmp_path),
    )

    initialized = await client.initialize(
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pycodex-test", "version": "1"},
        },
        timeout=5,
    )
    tools = await client.list_tools_with_connector_ids(timeout=5)
    called = await client.call_tool(
        "echo",
        {"value": "round-trip"},
        None,
        timeout=5,
    )
    await client.shutdown()

    assert initialized["serverInfo"]["name"] == "fixture"
    assert [item.tool["name"] for item in tools.tools] == ["echo"]
    assert tools.tools[0].connector_id == "fixture"
    assert called["content"][0]["text"] == "round-trip"
    assert called["environment"] == "client"


@pytest.mark.asyncio
async def test_rmcp_client_stdio_handles_server_elicitation_during_initialize(
    tmp_path: Path,
) -> None:
    # Rust: connect_pending_transport + ElicitationClientService.
    from pycodex.protocol import ElicitationAction
    from pycodex.rmcp_client.rmcp_client import ElicitationResponse

    observed: list[tuple[Any, Any]] = []

    async def send_elicitation(
        request_id: Any,
        request: Any,
    ) -> ElicitationResponse:
        observed.append((request_id, request))
        return ElicitationResponse(
            ElicitationAction.ACCEPT,
            {"confirmed": True},
            {"persist": "always"},
        )

    client = await RmcpClient.new_stdio_client(
        program=sys.executable,
        args=("-u", "-c", _ELICITATION_SERVER),
        env=None,
        env_vars=(),
        cwd=tmp_path,
        launcher=LocalStdioServerLauncher(tmp_path),
    )
    initialized = await client.initialize(
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {"elicitation": {}},
            "clientInfo": {"name": "pycodex-test", "version": "1"},
        },
        timeout=5,
        send_elicitation=send_elicitation,
    )
    await client.shutdown()

    assert observed == [
        (
            "server-elicitation",
            {
                "message": "Persist this choice?",
                "_meta": {"persist": "session"},
            },
        )
    ]
    assert initialized["elicitationResult"] == {
        "action": "accept",
        "content": {"confirmed": True},
        "_meta": {"persist": "always"},
    }


class _RemoteProcess(ExecProcess):
    def subscribe_events(self):
        from pycodex.exec_server.process import ExecProcessEventReceiver

        return ExecProcessEventReceiver.empty()

    async def write(self, chunk: bytes) -> WriteResponse:
        return WriteResponse(WriteStatus.ACCEPTED)

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        return ReadResponse([], 1, False, None, False)

    async def terminate(self) -> None:
        return None


class _RemoteBackend(ExecBackend):
    def __init__(self) -> None:
        self.params: ExecParams | None = None
        self.process = _RemoteProcess()

    async def start(self, params: ExecParams) -> StartedExecProcess:
        self.params = params
        return StartedExecProcess(self.process)


@pytest.mark.asyncio
async def test_executor_launcher_uses_executor_process_contract(tmp_path: Path) -> None:
    # Rust: ExecutorStdioServerLauncher::launch_server.
    backend = _RemoteBackend()
    launcher = ExecutorStdioServerLauncher(backend)
    transport = await launcher.launch(
        StdioServerCommand(
            program="remote-mcp",
            args=("--stdio",),
            env={"EXPLICIT": "yes"},
            env_vars=(McpServerEnvVar.from_value({"name": "REMOTE_TOKEN", "source": "remote"}),),
            cwd=tmp_path,
        )
    )

    assert backend.params is not None
    assert backend.params.argv == ["remote-mcp", "--stdio"]
    assert backend.params.cwd == str(tmp_path)
    assert backend.params.env == {"EXPLICIT": "yes"}
    assert backend.params.tty is False
    assert backend.params.pipe_stdin is True
    assert backend.params.env_policy is not None
    assert "REMOTE_TOKEN" in backend.params.env_policy.include_only
    await transport.close()


@pytest.mark.asyncio
async def test_executor_launcher_requires_explicit_cwd() -> None:
    launcher = ExecutorStdioServerLauncher(_RemoteBackend())
    with pytest.raises(ValueError, match="requires an explicit cwd"):
        await launcher.launch(
            StdioServerCommand(
                program="remote-mcp",
                args=(),
                env=None,
                env_vars=(),
                cwd=None,
            )
        )
