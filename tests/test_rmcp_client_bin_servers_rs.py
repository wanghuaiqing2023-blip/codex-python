from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from pycodex.rmcp_client.rmcp_client import RmcpClient
from pycodex.rmcp_client.stdio_server_launcher import LocalStdioServerLauncher
from pycodex.rmcp_client.bin.test_stdio_server import (
    SMALL_PNG_BASE64,
    TestToolServer as StdioTestToolServer,
    parse_data_url,
    wait_on_sync_barrier,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


async def _stdio_client(
    module: str,
    tmp_path: Path,
    env: dict[str, str] | None = None,
) -> RmcpClient:
    process_env = {
        "PYTHONPATH": os.pathsep.join(
            part
            for part in (str(_REPO_ROOT), os.environ.get("PYTHONPATH", ""))
            if part
        ),
        **(env or {}),
    }
    return await RmcpClient.new_stdio_client(
        program=sys.executable,
        args=("-u", "-m", module),
        env=process_env,
        env_vars=(),
        cwd=tmp_path,
        launcher=LocalStdioServerLauncher(tmp_path),
    )


async def _initialize(client: RmcpClient) -> dict[str, Any]:
    return await client.initialize(
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pycodex-test", "version": "1"},
        },
        timeout=5,
    )


@pytest.mark.asyncio
async def test_rmcp_test_server_process_round_trip(tmp_path: Path) -> None:
    # Rust: codex-rmcp-client/src/bin/rmcp_test_server.rs.
    client = await _stdio_client(
        "pycodex.rmcp_client.bin.rmcp_test_server",
        tmp_path,
        {"MCP_TEST_VALUE": "from-env"},
    )
    try:
        initialized = await _initialize(client)
        tools = await client.list_tools(timeout=5)
        result = await client.call_tool(
            "echo",
            {"message": "hello"},
            None,
            timeout=5,
        )
    finally:
        await client.shutdown()

    assert initialized["capabilities"]["tools"]["listChanged"] is True
    assert [tool["name"] for tool in tools["tools"]] == ["echo"]
    assert result["structuredContent"] == {
        "echo": "hello",
        "env": "from-env",
    }


@pytest.mark.asyncio
async def test_stdio_server_process_exposes_rust_fixture_surface(
    tmp_path: Path,
) -> None:
    # Rust: codex-rmcp-client/src/bin/test_stdio_server.rs.
    pid_file = tmp_path / "mcp.pid"
    client = await _stdio_client(
        "pycodex.rmcp_client.bin.test_stdio_server",
        tmp_path,
        {
            "MCP_TEST_VALUE": "stdio-env",
            "MCP_TEST_PID_FILE": str(pid_file),
        },
    )
    try:
        initialized = await _initialize(client)
        tools = await client.list_tools(timeout=5)
        resources = await client.list_resources(timeout=5)
        templates = await client.list_resource_templates(timeout=5)
        resource = await client.read_resource(
            {"uri": "memo://codex/example-note"},
            timeout=5,
        )
        echo = await client.call_tool(
            "echo-tool",
            {"message": "round-trip"},
            None,
            timeout=5,
        )
        sandbox = await client.call_tool(
            "sandbox_meta",
            {},
            {"codex/sandbox-state-meta": {"sandboxCwd": str(tmp_path)}},
            timeout=5,
        )
        image = await client.call_tool(
            "image_scenario",
            {"scenario": "text_then_image", "caption": "tiny"},
            None,
            timeout=5,
        )
    finally:
        await client.shutdown()

    assert initialized["capabilities"]["resources"] == {}
    assert [tool["name"] for tool in tools["tools"]] == [
        "echo",
        "echo-tool",
        "cwd",
        "sync",
        "sync_readonly",
        "image",
        "image_scenario",
        "sandbox_meta",
    ]
    assert resources["resources"][0]["uri"] == "memo://codex/example-note"
    assert templates["resourceTemplates"][0]["uriTemplate"] == "memo://codex/{slug}"
    assert "sample MCP resource" in resource["contents"][0]["text"]
    assert echo["structuredContent"] == {
        "echo": "ECHOING: round-trip",
        "env": "stdio-env",
    }
    assert sandbox["structuredContent"] == {
        "codex/sandbox-state-meta": {"sandboxCwd": str(tmp_path)}
    }
    assert [item["type"] for item in image["content"]] == ["text", "image"]
    assert pid_file.read_text(encoding="utf-8").isdigit()


def _json_request(
    url: str,
    method: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            **({"Content-Type": "application/json"} if body is not None else {}),
            **(headers or {}),
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        value = json.loads(data) if data else None
        return (
            response.status,
            {key.lower(): value for key, value in response.headers.items()},
            value,
        )


def _wait_for_bound_addr(path: Path) -> str:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8").strip()
        time.sleep(0.02)
    raise AssertionError("streamable HTTP fixture did not publish its bound address")


def test_stdio_server_image_scenarios_and_data_url_match_rust() -> None:
    # Rust: test_stdio_server.rs::parse_data_url/ImageScenario.
    server = StdioTestToolServer()
    assert parse_data_url("data:image/png;base64,AAAA") == (
        "image/png",
        "AAAA",
    )
    assert parse_data_url("https://example.test/image.png") is None
    expected_types = {
        "image_only": ["image"],
        "image_only_original_detail": ["image"],
        "text_then_image": ["text", "image"],
        "invalid_base64_then_image": ["image", "image"],
        "invalid_image_bytes_then_image": ["image", "image"],
        "multiple_valid_images": ["image", "image"],
        "image_then_text": ["image", "text"],
        "text_only": ["text"],
    }
    for scenario, content_types in expected_types.items():
        result = server.image_scenario_result(
            {
                "scenario": scenario,
                "data_url": f"data:image/png;base64,{SMALL_PNG_BASE64}",
            }
        )
        assert [item["type"] for item in result["content"]] == content_types
    original = server.image_scenario_result(
        {"scenario": "image_only_original_detail"}
    )
    assert original["content"][0]["_meta"] == {
        "codex/imageDetail": "original"
    }


def test_stdio_server_sync_barrier_validation_and_release() -> None:
    # Rust: test_stdio_server.rs::wait_on_sync_barrier.
    with pytest.raises(ValueError, match="participants must be greater than zero"):
        wait_on_sync_barrier({"id": "invalid", "participants": 0})
    with pytest.raises(ValueError, match="timeout must be greater than zero"):
        wait_on_sync_barrier(
            {"id": "invalid", "participants": 1, "timeout_ms": 0}
        )

    errors: list[BaseException] = []

    def wait() -> None:
        try:
            wait_on_sync_barrier(
                {"id": "pair", "participants": 2, "timeout_ms": 1_000}
            )
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=wait)
    second = threading.Thread(target=wait)
    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []


def test_streamable_http_server_process_session_auth_and_failure(
    tmp_path: Path,
) -> None:
    # Rust: codex-rmcp-client/src/bin/test_streamable_http_server.rs.
    bound_file = tmp_path / "bound.txt"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                part
                for part in (str(_REPO_ROOT), env.get("PYTHONPATH", ""))
                if part
            ),
            "MCP_STREAMABLE_HTTP_BIND_ADDR": "127.0.0.1:0",
            "MCP_STREAMABLE_HTTP_BOUND_ADDR_FILE": str(bound_file),
            "MCP_EXPECT_BEARER": "fixture-token",
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "pycodex.rmcp_client.bin.test_streamable_http_server",
        ],
        cwd=tmp_path,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        address = _wait_for_bound_addr(bound_file)
        base_url = f"http://{address}"
        status, _, metadata = _json_request(
            f"{base_url}/.well-known/oauth-authorization-server/mcp",
            "GET",
        )
        assert status == 200
        assert metadata["token_endpoint"] == f"{base_url}/oauth/token"

        status, _, _ = _json_request(
            f"{base_url}/mcp",
            "POST",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert status == 401

        auth = {"Authorization": "Bearer fixture-token"}
        status, headers, initialized = _json_request(
            f"{base_url}/mcp",
            "POST",
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
            auth,
        )
        assert status == 200
        assert initialized["result"]["capabilities"]["tools"]["listChanged"] is True
        assert initialized["result"]["capabilities"]["resources"] == {}
        session_id = headers["mcp-session-id"]
        session_headers = {**auth, "mcp-session-id": session_id}

        status, _, _ = _json_request(
            f"{base_url}/test/control/session-post-failure",
            "POST",
            {
                "status": 429,
                "remaining": 1,
                "www_authenticate_headers": [
                    'Bearer error="insufficient_scope", scope="files:read"'
                ],
            },
            auth,
        )
        assert status == 204

        status, headers, _ = _json_request(
            f"{base_url}/mcp",
            "POST",
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            session_headers,
        )
        assert status == 429
        assert "insufficient_scope" in headers["www-authenticate"]

        status, _, tools = _json_request(
            f"{base_url}/mcp",
            "POST",
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
            session_headers,
        )
        assert status == 200
        assert [tool["name"] for tool in tools["result"]["tools"]] == ["echo"]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
