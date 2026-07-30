"""Async MCP server process fixture derived from ``mcp_process.rs``."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping


class McpProcess:
    def __init__(
        self,
        process: asyncio.subprocess.Process,
        stderr_task: asyncio.Task[None],
    ) -> None:
        self._next_request_id = 0
        self._process = process
        self._stderr_task = stderr_task

    @classmethod
    async def new(cls, codex_home: str | Path) -> "McpProcess":
        return await cls.new_with_env(codex_home, {})

    @classmethod
    async def new_with_env(
        cls,
        codex_home: str | Path,
        env_overrides: Mapping[str, str | None],
    ) -> "McpProcess":
        home = Path(codex_home).resolve()
        home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update(
            {
                "CODEX_HOME": str(home),
                "PYTHONIOENCODING": "utf-8",
                "RUST_LOG": "debug",
            }
        )
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        repo_root = Path(__file__).resolve().parents[3]
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-m",
            "pycodex",
            "mcp-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_root,
            env=env,
        )

        async def drain_stderr() -> None:
            assert process.stderr is not None
            while await process.stderr.readline():
                pass

        return cls(process, asyncio.create_task(drain_stderr()))

    async def initialize(self) -> dict[str, Any]:
        request_id = await self.send_request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "elicitation": {
                        "form": {},
                    }
                },
                "clientInfo": {
                    "name": "elicitation test",
                    "title": "Elicitation Test",
                    "version": "0.0.0",
                },
            },
        )
        response = await self.read_stream_until_response_message(request_id)
        result = response.get("result", {})
        if result.get("serverInfo", {}).get("name") != "codex-mcp-server":
            raise AssertionError(f"unexpected initialize response: {response!r}")
        await self.send_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        return response

    async def send_codex_tool_call(self, params: Mapping[str, Any]) -> int:
        return await self.send_request(
            "tools/call",
            {"name": "codex", "arguments": dict(params)},
        )

    async def send_request(self, method: str, params: Any = None) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        await self.send_jsonrpc_message(message)
        return request_id

    async def send_response(self, request_id: int | str, result: Any) -> None:
        await self.send_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    async def send_jsonrpc_message(self, message: Mapping[str, Any]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("MCP process stdin is unavailable")
        payload = json.dumps(message, separators=(",", ":")) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

    async def read_jsonrpc_message(self, timeout: float = 30.0) -> dict[str, Any]:
        if self._process.stdout is None:
            raise RuntimeError("MCP process stdout is unavailable")
        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
        if not line:
            raise EOFError("MCP process stdout closed")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise ValueError(f"expected JSON-RPC object, got {type(message).__name__}")
        return message

    async def read_stream_until_request_message(self) -> dict[str, Any]:
        while True:
            message = await self.read_jsonrpc_message()
            if "method" in message and "id" in message:
                return message
            if "error" in message or "result" in message:
                raise RuntimeError(f"unexpected JSON-RPC response: {message!r}")

    async def read_stream_until_response_message(
        self,
        request_id: int | str,
    ) -> dict[str, Any]:
        while True:
            message = await self.read_jsonrpc_message()
            if message.get("id") == request_id and ("result" in message or "error" in message):
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message
            if "method" in message and "id" in message:
                raise RuntimeError(f"unexpected JSON-RPC request: {message!r}")

    async def read_stream_until_legacy_task_complete_notification(self) -> dict[str, Any]:
        while True:
            message = await self.read_jsonrpc_message()
            if (
                message.get("method") == "codex/event"
                and message.get("params", {}).get("msg", {}).get("type") == "task_complete"
            ):
                return message
            if "id" in message:
                raise RuntimeError(f"unexpected addressed JSON-RPC message: {message!r}")

    async def close(self) -> None:
        if self._process.stdin is not None and not self._process.stdin.is_closing():
            self._process.stdin.close()
            try:
                await self._process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()
        await self._stderr_task

    async def __aenter__(self) -> "McpProcess":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()


__all__ = ["McpProcess"]
