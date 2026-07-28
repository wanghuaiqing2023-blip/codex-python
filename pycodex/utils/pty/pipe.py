"""Pipe-backed spawning from codex-utils-pty/src/pipe.rs."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import process_group
from .process import ProcessHandle, SpawnedProcess

_SIGKILL = getattr(__import__("signal"), "SIGKILL", 9)


async def _read_stream(stream: asyncio.StreamReader | None, queue: asyncio.Queue[bytes]) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        await queue.put(chunk)


async def _wait_process(process: asyncio.subprocess.Process) -> int:
    try:
        return await process.wait()
    except Exception:
        return -1


def _normalize_env(env: Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in env.items()}


def _pipe_preexec(parent_pid: int | None = None) -> None:
    process_group.detach_from_tty()
    if parent_pid is not None and sys.platform.startswith("linux"):
        process_group.set_parent_death_signal(parent_pid)


async def _spawn_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None,
    *,
    stdin_enabled: bool,
    inherited_fds: Sequence[int] = (),
    missing_program_message: str = "missing program for pipe spawn",
) -> SpawnedProcess:
    if not program:
        raise ValueError(missing_program_message)

    creationflags = 0
    preexec_fn = None
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        parent_pid = os.getpid() if sys.platform.startswith("linux") else None
        preexec_fn = lambda: _pipe_preexec(parent_pid)

    argv = [program, *map(str, args)]
    executable = program
    if os.name != "nt" and arg0 is not None:
        argv[0] = arg0

    create_kwargs: dict[str, Any] = {}
    if os.name != "nt":
        create_kwargs["pass_fds"] = tuple(int(fd) for fd in inherited_fds)

    child = await asyncio.create_subprocess_exec(
        *argv,
        executable=executable,
        cwd=Path(cwd),
        env=_normalize_env(env),
        stdin=asyncio.subprocess.PIPE if stdin_enabled else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=creationflags,
        preexec_fn=preexec_fn,
        **create_kwargs,
    )

    stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
    stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
    stdout_task = asyncio.create_task(_read_stream(child.stdout, stdout_rx))
    stderr_task = asyncio.create_task(_read_stream(child.stderr, stderr_rx))
    exit_future = asyncio.create_task(_wait_process(child))

    async def write_stdin(chunk: bytes) -> None:
        if child.stdin is None or child.stdin.is_closing():
            return
        child.stdin.write(chunk)
        await child.stdin.drain()

    def close_stdin() -> None:
        if child.stdin is not None and not child.stdin.is_closing():
            child.stdin.close()

    def terminate_process() -> None:
        if child.returncode is not None:
            return
        if os.name == "nt":
            child.kill()
        else:
            try:
                os.killpg(child.pid, _SIGKILL)
            except ProcessLookupError:
                pass

    handle = ProcessHandle(
        child,
        stdin_writer=write_stdin if stdin_enabled else None,
        close_stdin=close_stdin,
        terminator=terminate_process,
        exit_future=exit_future,
        helper_tasks=(stdout_task, stderr_task),
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


async def spawn_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=True)


async def spawn_process_no_stdin(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=False)


async def spawn_process_no_stdin_with_inherited_fds(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    inherited_fds: Sequence[int] = (),
) -> SpawnedProcess:
    return await _spawn_process(
        program,
        args,
        cwd,
        env,
        arg0,
        stdin_enabled=False,
        inherited_fds=inherited_fds,
    )


__all__ = [
    "spawn_process",
    "spawn_process_no_stdin",
    "spawn_process_no_stdin_with_inherited_fds",
]
