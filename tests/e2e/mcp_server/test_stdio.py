from __future__ import annotations

import json
import os
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from pathlib import Path

import pytest

from tests.e2e.support.responses_fixture import (
    _SseFixtureServer,
    _completed_text_response,
)
from tests.support.mcp_test_support import McpProcess


def test_stdio_server_runs_json_rpc_protocol_to_eof() -> None:
    # Rust: codex-mcp-server/src/lib.rs::run_main.
    repo_root = Path(__file__).resolve().parents[3]
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "e2e", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}},
        {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}},
    ]
    payload = "\n".join(json.dumps(message) for message in messages) + "\n"

    completed = subprocess.run(
        [sys.executable, "-B", "-m", "pycodex", "mcp-server"],
        input=payload,
        text=True,
        capture_output=True,
        cwd=repo_root,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert responses[0]["result"]["serverInfo"]["name"] == "codex-mcp-server"
    assert [tool["name"] for tool in responses[1]["result"]["tools"]] == [
        "codex",
        "codex-reply",
    ]
    assert responses[2] == {"jsonrpc": "2.0", "id": 3, "result": {}}
    assert responses[3]["error"] == {
        "code": -32601,
        "message": "method not found: unknown/method",
        "data": {"method": "unknown/method"},
    }


def test_stdio_server_reports_invalid_json_and_continues() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    payload = "{broken\n" + json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    ) + "\n"

    completed = subprocess.run(
        [sys.executable, "-B", "-m", "pycodex", "mcp-server"],
        input=payload,
        text=True,
        capture_output=True,
        cwd=repo_root,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    assert "Failed to deserialize JSON-RPC message" in completed.stderr
    assert json.loads(completed.stdout) == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {},
    }


@pytest.mark.asyncio
async def test_mcp_test_support_process_initializes_real_stdio_server(
    tmp_path: Path,
) -> None:
    process = await McpProcess.new(tmp_path / "mcp-support-home")
    try:
        initialized = await process.initialize()
        ping_id = await process.send_request("ping", {})
        ping = await process.read_stream_until_response_message(ping_id)
    finally:
        await process.close()

    assert initialized["result"]["serverInfo"]["name"] == "codex-mcp-server"
    assert ping == {"jsonrpc": "2.0", "id": ping_id, "result": {}}


def test_stdio_server_runs_real_codex_thread_and_reply(
    tmp_path: Path,
) -> None:
    """Rust: codex_tool_runner keeps one ThreadManager-backed CodexThread."""

    repo_root = Path(__file__).resolve().parents[3]
    first_body = _completed_text_response("resp-1", "msg-1", "first answer")
    second_body = _completed_text_response("resp-2", "msg-2", "second answer")

    with _SseFixtureServer((first_body, second_body)) as server:
        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            "\n".join(
                (
                    'model = "mock-model"',
                    'model_provider = "pycodex_mock"',
                    'approval_policy = "never"',
                    'sandbox_mode = "read-only"',
                    "",
                    "[model_providers.pycodex_mock]",
                    'name = "MCP E2E provider"',
                    f'base_url = "{server.base_url}"',
                    'wire_api = "responses"',
                    "request_max_retries = 0",
                    "stream_max_retries = 0",
                    "supports_websockets = false",
                    "",
                )
            ),
            encoding="utf-8",
        )
        env = dict(os.environ)
        env.update(
            {
                "CODEX_HOME": str(codex_home),
                "OPENAI_API_KEY": "test-key",
                "PYTHONIOENCODING": "utf-8",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "pycodex", "mcp-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=repo_root,
            env=env,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        output: Queue[dict[str, object]] = Queue()

        def read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output.put(json.loads(line))

        reader = Thread(target=read_stdout, daemon=True)
        reader.start()
        try:
            _send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "clientInfo": {"name": "e2e", "version": "1"},
                    },
                },
            )
            assert _read_response(output, 1)["result"]["serverInfo"]["name"] == "codex-mcp-server"

            _send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "codex",
                        "arguments": {"prompt": "first prompt"},
                    },
                },
            )
            first = _read_response(output, 2)
            assert first["result"]["structuredContent"]["content"] == "first answer"
            thread_id = first["result"]["structuredContent"]["threadId"]

            _send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "codex-reply",
                        "arguments": {
                            "threadId": thread_id,
                            "prompt": "second prompt",
                        },
                    },
                },
            )
            second = _read_response(output, 3)
            assert second["result"]["structuredContent"] == {
                "threadId": thread_id,
                "content": "second answer",
            }
        finally:
            process.stdin.close()
            process.wait(timeout=30)
            reader.join(timeout=5)

        assert process.returncode == 0
        assert len(server.requests) == 2
        request_payloads = [json.loads(body) for body in server.request_bodies]
        assert "first prompt" in json.dumps(request_payloads[0])
        second_request = json.dumps(request_payloads[1])
        assert "first prompt" in second_request
        assert "first answer" in second_request
        assert "second prompt" in second_request


def _send(process: subprocess.Popen[str], message: dict[str, object]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _read_response(
    output: Queue[dict[str, object]],
    request_id: int,
    *,
    timeout: float = 30,
) -> dict[str, object]:
    while True:
        try:
            message = output.get(timeout=timeout)
        except Empty as exc:
            raise AssertionError(f"timed out waiting for MCP response {request_id}") from exc
        if message.get("id") == request_id:
            return message
