from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Mapping


DEFAULT_CLIENT_NAME = "codex-app-server-tests"
DISABLE_PLUGIN_STARTUP_TASKS_ARG = "--disable-plugin-startup-tasks-for-tests"


class McpProcess:
    def __init__(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        self.process = process
        self.next_request_id = 1
        self.pending_messages: list[dict[str, object]] = []

    @classmethod
    async def new(cls, codex_home: Path) -> "McpProcess":
        return await cls.new_with_env_and_args(
            codex_home,
            {},
            (DISABLE_PLUGIN_STARTUP_TASKS_ARG,),
        )

    @classmethod
    async def new_without_managed_config(cls, codex_home: Path) -> "McpProcess":
        return await cls.new_with_env(
            codex_home,
            {"CODEX_APP_SERVER_DISABLE_MANAGED_CONFIG": "1"},
        )

    @classmethod
    async def new_with_env(
        cls,
        codex_home: Path,
        env_overrides: Mapping[str, str | None],
    ) -> "McpProcess":
        return await cls.new_with_env_and_args(
            codex_home,
            env_overrides,
            (DISABLE_PLUGIN_STARTUP_TASKS_ARG,),
        )

    @classmethod
    async def new_with_args(
        cls,
        codex_home: Path,
        args: tuple[str, ...] | list[str],
    ) -> "McpProcess":
        return await cls.new_with_env_and_args(
            codex_home,
            {},
            (DISABLE_PLUGIN_STARTUP_TASKS_ARG, *args),
        )

    @classmethod
    async def new_with_env_and_args(
        cls,
        codex_home: Path,
        env_overrides: Mapping[str, str | None],
        args: tuple[str, ...] | list[str],
    ) -> "McpProcess":
        codex_home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-m",
            "pycodex",
            "app-server",
            *args,
            cwd=Path(__file__).resolve().parents[3],
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return cls(process)

    async def initialize(
        self,
        *,
        client_name: str = DEFAULT_CLIENT_NAME,
    ) -> dict[str, object]:
        return await self.send_request(
            "initialize",
            {
                "clientInfo": {
                    "name": client_name,
                    "title": "Codex app-server tests",
                    "version": "0.0.0",
                },
                "capabilities": {},
            },
        )

    async def send_raw_request(
        self,
        method: str,
        params: object,
    ) -> int:
        request_id = self.next_request_id
        self.next_request_id += 1
        await self._write({"id": request_id, "method": method, "params": params})
        return request_id

    async def send_request(
        self,
        method: str,
        params: object,
    ) -> dict[str, object]:
        request_id = await self.send_raw_request(method, params)
        return await self.read_stream_until_response_message(request_id)

    async def send_response(self, request_id: object, result: object) -> None:
        await self._write({"id": request_id, "result": result})

    async def send_error(self, request_id: object, error: object) -> None:
        await self._write({"id": request_id, "error": error})

    async def send_notification(self, method: str, params: object) -> None:
        await self._write({"method": method, "params": params})

    async def read_stream_until_response_message(
        self,
        request_id: object,
    ) -> dict[str, object]:
        while True:
            message = await self.read_stream_message()
            if message.get("id") == request_id and (
                "result" in message or "error" in message
            ):
                return message
            self.pending_messages.append(message)

    async def read_stream_message(self) -> dict[str, object]:
        if self.pending_messages:
            return self.pending_messages.pop(0)
        if self.process.stdout is None:
            raise RuntimeError("app-server stdout is unavailable")
        line = await asyncio.wait_for(self.process.stdout.readline(), timeout=15)
        if not line:
            stderr = b""
            if self.process.stderr is not None:
                stderr = await self.process.stderr.read()
            raise RuntimeError(
                "app-server exited before sending a message: "
                + stderr.decode(errors="replace")
            )
        message = json.loads(line)
        if not isinstance(message, dict):
            raise RuntimeError("app-server emitted a non-object JSON-RPC message")
        return message

    async def close(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.is_closing():
            self.process.stdin.close()
            await self.process.stdin.wait_closed()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=2)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()

    async def _write(self, message: Mapping[str, object]) -> None:
        if self.process.stdin is None:
            raise RuntimeError("app-server stdin is unavailable")
        self.process.stdin.write(
            (json.dumps(message, separators=(",", ":")) + "\n").encode()
        )
        await self.process.stdin.drain()
