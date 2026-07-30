from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

import pytest

from tests.support.mcp_test_support import McpProcess, to_response
from tests.support.mcp_test_support.mock_model_server import (
    create_mock_responses_server,
)
from tests.support.mcp_test_support.responses import (
    create_apply_patch_sse_response,
    create_final_assistant_message_sse_response,
    create_shell_command_sse_response,
)


def test_response_helpers_match_mcp_test_support_rust_shapes(tmp_path: Path) -> None:
    # Rust: mcp-server/tests/common/responses.rs
    shell = create_shell_command_sse_response(
        ["python", "-V"],
        workdir=tmp_path,
        timeout_ms=5000,
        call_id="shell-1",
    )
    patch = create_apply_patch_sse_response("*** Begin Patch\n*** End Patch", "patch-1")
    final = create_final_assistant_message_sse_response("finished")

    assert '"call_id":"shell-1"' in shell
    assert '\\"workdir\\":' in shell
    assert "apply_patch &lt;&lt;" not in patch
    assert "apply_patch <<'EOF'" in patch
    assert '"text":"finished"' in final


@pytest.mark.asyncio
async def test_mock_model_server_serves_ordered_real_http_responses() -> None:
    # Rust: mcp-server/tests/common/mock_model_server.rs
    server = await create_mock_responses_server(["first", "second"])
    try:
        async def post() -> str:
            request = urllib.request.Request(
                server.base_url + "/responses",
                data=b"{}",
                method="POST",
            )
            return await asyncio.to_thread(
                lambda: urllib.request.urlopen(request, timeout=5).read().decode()
            )

        assert await post() == "first"
        assert await post() == "second"
        assert len(await server.requests()) == 2
    finally:
        await server.shutdown()


@pytest.mark.asyncio
async def test_mcp_process_performs_real_initialize_handshake(tmp_path: Path) -> None:
    # Rust: mcp-server/tests/common/mcp_process.rs
    process = await McpProcess.new(tmp_path / "codex-home")
    try:
        response = await process.initialize()
    finally:
        await process.close()

    result = to_response(response)
    assert result["serverInfo"]["name"] == "codex-mcp-server"
    assert [tool for tool in result["capabilities"]] == ["tools"]
