"""MCP stdio process launchers.

This package mirrors ``codex-rmcp-client::stdio_server_launcher`` and its
inline ``private`` module.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.config.mcp_types import McpServerEnvVar
from pycodex.exec_server.process import ExecBackend, ExecProcess
from pycodex.exec_server.protocol import ExecEnvPolicy, ExecParams
from pycodex.protocol.config_types import ShellEnvironmentPolicyInherit

from .. import program_resolver
from ..executor_process_transport import ExecutorProcessTransport
from ..utils import (
    DEFAULT_ENV_VARS,
    create_env_for_mcp_server,
    create_env_overlay_for_remote_mcp_server,
    remote_mcp_env_var_names,
)
from .private import Sealed

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class StdioServerCommand:
    program: str | os.PathLike[str]
    args: Sequence[str | os.PathLike[str]]
    env: Mapping[str, str] | None
    env_vars: Sequence[McpServerEnvVar]
    cwd: str | os.PathLike[str] | None


class StdioServerProcessHandle:
    def __init__(
        self,
        program_name: str,
        *,
        local: asyncio.subprocess.Process | None = None,
        executor: ExecProcess | None = None,
    ) -> None:
        self.program_name = str(program_name)
        self._local = local
        self._executor = executor
        self.terminated = False
        self._lock = asyncio.Lock()

    async def terminate(self) -> None:
        async with self._lock:
            if self.terminated:
                return
            if self._executor is not None:
                await self._executor.terminate()
            elif self._local is not None:
                if self._local.returncode is None:
                    if sys.platform == "win32" and self._local.pid is not None:
                        taskkill = await asyncio.create_subprocess_exec(
                            "taskkill",
                            "/PID",
                            str(self._local.pid),
                            "/T",
                            "/F",
                            stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await taskkill.wait()
                    else:
                        self._local.terminate()
                    try:
                        await asyncio.wait_for(self._local.wait(), 2)
                    except TimeoutError:
                        self._local.kill()
                        await self._local.wait()
            self.terminated = True


class StdioServerTransport:
    def __init__(
        self,
        *,
        process: StdioServerProcessHandle,
        local: asyncio.subprocess.Process | None = None,
        executor: ExecutorProcessTransport | None = None,
        stderr_task: asyncio.Task[None] | None = None,
    ) -> None:
        self._process = process
        self._local = local
        self._executor = executor
        self._stderr_task = stderr_task

    def process_handle(self) -> StdioServerProcessHandle:
        return self._process

    async def send(self, item: Any) -> None:
        if self._executor is not None:
            await self._executor.send(item)
            return
        if self._local is None or self._local.stdin is None:
            raise BrokenPipeError("stdin closed")
        import json

        payload = json.dumps(item, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self._local.stdin.write(payload + b"\n")
        await self._local.stdin.drain()

    async def receive(self) -> Any | None:
        if self._executor is not None:
            return await self._executor.receive()
        if self._local is None or self._local.stdout is None:
            return None
        import json

        while True:
            line = await self._local.stdout.readline()
            if not line:
                return None
            try:
                return json.loads(line.rstrip(b"\r\n"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                _LOG.debug(
                    "Failed to parse MCP server message (%s): %s",
                    self._process.program_name,
                    exc,
                )

    async def close(self) -> None:
        if self._local is not None and self._local.stdin is not None:
            self._local.stdin.close()
            try:
                await self._local.stdin.wait_closed()
            except (BrokenPipeError, ConnectionError):
                pass
        await self._process.terminate()
        if self._executor is not None:
            await self._executor.close()
        if self._stderr_task is not None:
            try:
                await asyncio.wait_for(self._stderr_task, 1)
            except TimeoutError:
                self._stderr_task.cancel()
                await asyncio.gather(self._stderr_task, return_exceptions=True)
        if self._local is not None and self._local.stdout is not None:
            await self._local.stdout.read()


class StdioServerLauncher(Sealed):
    async def launch(self, command: StdioServerCommand) -> StdioServerTransport:
        raise NotImplementedError


class LocalStdioServerLauncher(StdioServerLauncher):
    def __init__(self, fallback_cwd: str | os.PathLike[str]) -> None:
        self.fallback_cwd = Path(fallback_cwd)

    async def launch(self, command: StdioServerCommand) -> StdioServerTransport:
        environment = create_env_for_mcp_server(command.env, command.env_vars)
        cwd = Path(command.cwd) if command.cwd is not None else self.fallback_cwd
        program_name = os.fspath(command.program)
        resolved_program = program_resolver.resolve(program_name, environment, cwd)
        process = await asyncio.create_subprocess_exec(
            resolved_program,
            *(os.fspath(arg) for arg in command.args),
            cwd=str(cwd),
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=sys.platform != "win32",
        )
        handle = StdioServerProcessHandle(program_name, local=process)
        stderr_task = asyncio.create_task(
            self._log_stderr(process, program_name),
            name=f"mcp-stderr-{process.pid}",
        )
        return StdioServerTransport(
            process=handle,
            local=process,
            stderr_task=stderr_task,
        )

    @staticmethod
    async def _log_stderr(
        process: asyncio.subprocess.Process,
        program_name: str,
    ) -> None:
        if process.stderr is None:
            return
        while line := await process.stderr.readline():
            _LOG.info(
                "MCP server stderr (%s): %s",
                program_name,
                line.rstrip(b"\r\n").decode("utf-8", errors="replace"),
            )


class ExecutorStdioServerLauncher(StdioServerLauncher):
    def __init__(self, exec_backend: ExecBackend) -> None:
        self.exec_backend = exec_backend

    async def launch(self, command: StdioServerCommand) -> StdioServerTransport:
        if command.cwd is None:
            raise ValueError("executor stdio server requires an explicit cwd")
        environment = create_env_overlay_for_remote_mcp_server(
            command.env,
            command.env_vars,
        )
        remote_names = remote_mcp_env_var_names(command.env_vars)
        params = ExecParams(
            process_id=ExecutorProcessTransport.next_process_id(),
            argv=[
                os.fspath(command.program),
                *(os.fspath(arg) for arg in command.args),
            ],
            cwd=os.fspath(command.cwd),
            env=environment,
            tty=False,
            env_policy=self._remote_env_policy(remote_names),
            pipe_stdin=True,
            arg0=None,
        )
        started = await self.exec_backend.start(params)
        process = started.process
        program_name = os.fspath(command.program)
        handle = StdioServerProcessHandle(program_name, executor=process)
        return StdioServerTransport(
            process=handle,
            executor=ExecutorProcessTransport(process, program_name),
        )

    @staticmethod
    def _remote_env_policy(remote_names: Sequence[str]) -> ExecEnvPolicy:
        include_only = (
            [*DEFAULT_ENV_VARS, *remote_names]
            if remote_names
            else []
        )
        return ExecEnvPolicy(
            inherit=(
                ShellEnvironmentPolicyInherit.ALL
                if remote_names
                else ShellEnvironmentPolicyInherit.CORE
            ),
            ignore_default_excludes=True,
            exclude=[],
            set={},
            include_only=list(include_only),
        )


__all__ = [
    "ExecutorStdioServerLauncher",
    "LocalStdioServerLauncher",
    "StdioServerCommand",
    "StdioServerLauncher",
    "StdioServerProcessHandle",
    "StdioServerTransport",
]
