"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import binascii
import errno
import hashlib
from functools import total_ordering
import inspect
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import struct
import sys
import time
import tomllib
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request, method_not_found
from pycodex.app_server_protocol.jsonrpc_lite import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    PermissionProfile,
    RequestId,
    WindowsSandboxLevel,
)
from pycodex.sandboxing import (
    SandboxCommand,
    SandboxManager,
    SandboxTransformRequest,
    SandboxablePreference,
)
from pycodex.protocol.shell_environment import create_env as create_shell_env
from pycodex.utils.absolute_path import AbsolutePathBuf



from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecutorFileSystem,
    FileMetadata,
    FileSystemSandboxContext,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.file_system import FileSystemResult


MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS = 1024 * 1024


LOCAL_PROCESS_EXITED_PROCESS_RETENTION_SECONDS = 30.0


@dataclass
class RetainedOutputChunk:
    seq: int
    stream: "ExecOutputStream"
    chunk: bytes


@dataclass
class LocalRunningProcess:
    output: list[RetainedOutputChunk] = field(default_factory=list)
    next_seq: int = 1
    exit_code: int | None = None
    closed: bool = False
    retained_bytes: int = 0
    tty: bool = False
    pipe_stdin: bool = False
    writer_open: bool = True
    written_chunks: list[bytes] = field(default_factory=list)
    terminate_called: bool = False
    child_process: Any | None = None
    stdin_writer: Any | None = None
    task_handles: list[asyncio.Task[Any]] = field(default_factory=list)
    open_streams: int = 0
    output_event: asyncio.Event = field(default_factory=asyncio.Event)
    events: "ExecProcessEventLog | None" = None
    wake_queue: asyncio.Queue[int] = field(default_factory=asyncio.Queue)

    def record_output(self, stream: "ExecOutputStream", chunk: bytes) -> int:
        seq = self.next_seq
        self.next_seq += 1
        data = bytes(chunk)
        self.retained_bytes += len(data)
        self.output.append(RetainedOutputChunk(seq=seq, stream=stream, chunk=data))
        while self.retained_bytes > MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS and self.output:
            evicted = self.output.pop(0)
            self.retained_bytes = max(0, self.retained_bytes - len(evicted.chunk))
        self.output_event.set()
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(
                ExecProcessEvent.output(
                    ProcessOutputChunk(seq=seq, stream=stream, chunk=ByteChunk(data))
                )
            )
        return seq

    def record_exit(self, exit_code: int) -> int:
        seq = self.next_seq
        self.next_seq += 1
        self.exit_code = exit_code
        self.output_event.set()
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(ExecProcessEvent.exited(seq=seq, exit_code=exit_code))
        return seq

    def mark_closed(self, seq: int | None = None) -> None:
        self.closed = True
        self.output_event.set()
        if seq is None:
            seq = self.next_seq
            self.next_seq += 1
        _put_latest_nowait(self.wake_queue, seq)
        if self.events is not None:
            self.events.publish(ExecProcessEvent.closed(seq=seq))

    def accepts_stdin(self) -> bool:
        return self.tty or self.pipe_stdin

    async def write_stdin(self, chunk: bytes) -> None:
        if not self.writer_open:
            raise BrokenPipeError("failed to write to process stdin")
        if self.stdin_writer is not None:
            self.stdin_writer.write(bytes(chunk))
            drain = getattr(self.stdin_writer, "drain", None)
            if drain is not None:
                await _maybe_await(drain())
            return
        self.written_chunks.append(bytes(chunk))

    def terminate(self) -> None:
        self.terminate_called = True
        if self.child_process is not None:
            _terminate_process_tree(self.child_process)


class LocalProcessStarting:
    pass


def _put_latest_nowait(queue: asyncio.Queue[int], value: int) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    try:
        queue.put_nowait(value)
    except asyncio.QueueFull:
        pass


class LocalProcess:
    def __init__(self, notifications: RpcNotificationSender | None, spawn_process: Any | None = None) -> None:
        self.notifications = notifications
        self.shutdown_called = False
        self.processes: dict[ProcessId, LocalRunningProcess | LocalProcessStarting] = {}
        self.spawn_process = spawn_process

    @classmethod
    def new(cls, notifications: RpcNotificationSender | None) -> "LocalProcess":
        return cls(notifications)

    async def shutdown(self) -> None:
        self.shutdown_called = True
        running = [process for process in self.processes.values() if isinstance(process, LocalRunningProcess)]
        self.processes.clear()
        for process in running:
            process.terminate()
        for process in running:
            for task in process.task_handles:
                task.cancel()
            if process.task_handles:
                await asyncio.gather(*process.task_handles, return_exceptions=True)

    def set_notification_sender(self, notifications: RpcNotificationSender | None) -> None:
        self.notifications = notifications

    def insert_running_process_for_tests(
        self,
        process_id: ProcessId | str,
        process: LocalRunningProcess | None = None,
    ) -> LocalRunningProcess:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        process = process or LocalRunningProcess()
        self.processes[process_id] = process
        return process

    def insert_starting_process_for_tests(self, process_id: ProcessId | str) -> None:
        process_id = ProcessId.new(process_id) if isinstance(process_id, str) else process_id
        self.processes[process_id] = LocalProcessStarting()

    async def exec(self, params: ExecParams) -> ExecResponse | JSONRPCErrorError:
        return await self.start_process(params)

    async def start_process(self, params: ExecParams) -> ExecResponse | JSONRPCErrorError:
        process_id = params.process_id
        if not params.argv:
            return invalid_params("argv must not be empty")
        if process_id in self.processes:
            return invalid_request(f"process {process_id} already exists")
        self.processes[process_id] = LocalProcessStarting()
        try:
            if self.spawn_process is None:
                spawned = await _spawn_local_running_process(params, child_env(params), self)
            else:
                spawned = await _maybe_await(self.spawn_process(params, child_env(params)))
        except Exception as exc:
            if isinstance(self.processes.get(process_id), LocalProcessStarting):
                self.processes.pop(process_id, None)
            return internal_error(exc)
        if isinstance(spawned, LocalRunningProcess):
            process = spawned
        else:
            process = LocalRunningProcess(tty=params.tty, pipe_stdin=params.pipe_stdin)
        process.tty = params.tty
        process.pipe_stdin = params.pipe_stdin
        if process.events is None:
            process.events = ExecProcessEventLog.new(256, MAX_RETAINED_OUTPUT_BYTES_PER_PROCESS)
        self.processes[process_id] = process
        return ExecResponse(process_id=process_id)

    async def start(self, params: ExecParams) -> StartedExecProcess | ExecServerError:
        response = await self.start_process(params)
        if isinstance(response, JSONRPCErrorError):
            from pycodex.exec_server.client import ExecServerError
            return ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        process = self.processes.get(response.process_id)
        if not isinstance(process, LocalRunningProcess):
            from pycodex.exec_server.client import ExecServerError
            return ExecServerError.protocol(f"process id {response.process_id} is starting")
        return StartedExecProcess(process=LocalExecProcess(response.process_id, self, process))

    async def exec_read(self, params: ReadParams) -> ReadResponse:
        process = self.processes.get(params.process_id)
        if process is None:
            return invalid_request(f"unknown process id {params.process_id}")
        if isinstance(process, LocalProcessStarting):
            return invalid_request(f"process id {params.process_id} is starting")
        deadline = time.monotonic() + ((params.wait_ms or 0) / 1000)
        after_seq = params.after_seq if params.after_seq is not None else 0
        while True:
            response = _local_process_read_response(process, params)
            has_new_terminal_event = response.exited and after_seq < max(0, response.next_seq - 1)
            if response.chunks or response.closed or has_new_terminal_event or time.monotonic() >= deadline:
                return response
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return response
            process.output_event.clear()
            try:
                await asyncio.wait_for(process.output_event.wait(), timeout=remaining)
            except TimeoutError:
                return _local_process_read_response(process, params)

    async def exec_write(self, params: WriteParams) -> WriteResponse:
        process = self.processes.get(params.process_id)
        if process is None:
            return WriteResponse(status=WriteStatus.UNKNOWN_PROCESS)
        if isinstance(process, LocalProcessStarting):
            return WriteResponse(status=WriteStatus.STARTING)
        if not process.accepts_stdin():
            return WriteResponse(status=WriteStatus.STDIN_CLOSED)
        try:
            await process.write_stdin(params.chunk.into_inner())
        except BrokenPipeError as exc:
            return internal_error(exc)
        return WriteResponse(status=WriteStatus.ACCEPTED)

    async def terminate_process(self, params: TerminateParams) -> TerminateResponse:
        process = self.processes.get(params.process_id)
        if process is None or isinstance(process, LocalProcessStarting):
            return TerminateResponse(running=False)
        if process.exit_code is not None:
            return TerminateResponse(running=False)
        process.terminate()
        return TerminateResponse(running=True)


def _local_process_read_response(process: LocalRunningProcess, params: ReadParams) -> ReadResponse:
    after_seq = params.after_seq if params.after_seq is not None else 0
    max_bytes = params.max_bytes if params.max_bytes is not None else sys.maxsize
    chunks: list[ProcessOutputChunk] = []
    total_bytes = 0
    next_seq = process.next_seq
    for retained in (chunk for chunk in process.output if chunk.seq > after_seq):
        chunk_len = len(retained.chunk)
        if chunks and total_bytes + chunk_len > max_bytes:
            break
        total_bytes += chunk_len
        chunks.append(
            ProcessOutputChunk(
                seq=retained.seq,
                stream=retained.stream,
                chunk=ByteChunk(retained.chunk),
            )
        )
        next_seq = retained.seq + 1
        if total_bytes >= max_bytes:
            break
    return ReadResponse(
        chunks=chunks,
        next_seq=next_seq,
        exited=process.exit_code is not None,
        exit_code=process.exit_code,
        closed=process.closed,
        failure=None,
    )


async def _spawn_local_running_process(
    params: ExecParams,
    env: dict[str, str],
    backend: LocalProcess,
) -> LocalRunningProcess:
    if params.tty:
        return await _spawn_local_pty_process(params, env, backend)
    program, *args = params.argv
    command_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": params.cwd,
        "env": env,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "stdin": asyncio.subprocess.PIPE if params.pipe_stdin else asyncio.subprocess.DEVNULL,
    }
    if os.name == "posix":
        kwargs["process_group"] = 0
    if params.arg0 is not None:
        command_args = [params.arg0, *args]
        kwargs["executable"] = program
    child = await asyncio.create_subprocess_exec(*command_args, **kwargs)
    child_process = _LocalPipeChildProcess(child)
    process = LocalRunningProcess(
        tty=False,
        pipe_stdin=params.pipe_stdin,
        child_process=child_process,
        stdin_writer=child.stdin if params.pipe_stdin else None,
        open_streams=2,
    )
    process.task_handles.extend(
        [
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.STDOUT,
                    child.stdout,
                )
            ),
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.STDERR,
                    child.stderr,
                )
            ),
            asyncio.create_task(_local_process_watch_exit(backend, params.process_id, process, child_process)),
        ]
    )
    return process


class _EmptyAsyncReader:
    async def read(self, _size: int = -1) -> bytes:
        return b""


class _PtyStdinWriter:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def write(self, chunk: bytes) -> None:
        try:
            os.write(self._fd, bytes(chunk))
        except OSError as exc:
            raise BrokenPipeError("failed to write to process stdin") from exc

    async def drain(self) -> None:
        return None


class _LocalPipeChildProcess:
    def __init__(self, child: Any) -> None:
        self._child = child

    async def wait(self) -> int:
        result = await _maybe_await(self._child.wait())
        return int(result if result is not None else -1)

    def terminate(self) -> None:
        if _terminate_child_process_group(self._child, 15):
            return
        self._child.terminate()

    def kill(self) -> None:
        if _terminate_child_process_group(self._child, 9):
            return
        self._child.kill()


class _LocalPtyChildProcess:
    def __init__(self, child: Any) -> None:
        self._child = child

    async def wait(self) -> int:
        return await asyncio.to_thread(self._child.wait)

    def terminate(self) -> None:
        if _terminate_child_process_group(self._child, 15):
            return
        self._child.terminate()

    def kill(self) -> None:
        if _terminate_child_process_group(self._child, 9):
            return
        self._child.kill()


def _terminate_child_process_group(child: Any, signal_number: int) -> bool:
    if os.name != "posix":
        return False
    pid = getattr(child, "pid", None)
    if pid is None:
        return False
    try:
        os.killpg(int(pid), signal_number)
        return True
    except ProcessLookupError:
        return True
    except OSError:
        return False


async def _spawn_local_pty_process(
    params: ExecParams,
    env: dict[str, str],
    backend: LocalProcess,
) -> LocalRunningProcess:
    if os.name != "posix":
        raise RuntimeError("codex-exec-server LocalProcess PTY runtime is not ported")

    import fcntl
    import pty
    import struct
    import subprocess
    import termios

    program, *args = params.argv
    master_fd, slave_fd = pty.openpty()
    try:
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    except OSError:
        pass

    def configure_child() -> None:
        os.setsid()
        try:
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        except OSError:
            pass

    command_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": params.cwd,
        "env": env,
        "stdin": slave_fd,
        "stdout": slave_fd,
        "stderr": slave_fd,
        "close_fds": True,
        "preexec_fn": configure_child,
    }
    if params.arg0 is not None:
        command_args = [params.arg0, *args]
        kwargs["executable"] = program
    try:
        child = subprocess.Popen(command_args, **kwargs)
    finally:
        try:
            os.close(slave_fd)
        except OSError:
            pass

    child_process = _LocalPtyChildProcess(child)
    process = LocalRunningProcess(
        tty=True,
        pipe_stdin=params.pipe_stdin,
        child_process=child_process,
        stdin_writer=_PtyStdinWriter(master_fd),
        open_streams=2,
    )
    process.task_handles.extend(
        [
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.PTY,
                    _PtyMasterReader(master_fd),
                )
            ),
            asyncio.create_task(
                _local_process_stream_output(
                    backend,
                    params.process_id,
                    process,
                    ExecOutputStream.PTY,
                    _EmptyAsyncReader(),
                )
            ),
            asyncio.create_task(_local_process_watch_exit(backend, params.process_id, process, child_process)),
        ]
    )
    return process


class _PtyMasterReader:
    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._closed = False

    async def read(self, size: int = 4096) -> bytes:
        if self._closed:
            return b""
        try:
            return await asyncio.to_thread(os.read, self._fd, size)
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                self.close()
                return b""
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._fd)
        except OSError:
            pass


async def _local_process_stream_output(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
    stream: "ExecOutputStream",
    reader: Any,
) -> None:
    try:
        while reader is not None:
            chunk = await _maybe_await(reader.read(4096))
            if not chunk:
                break
            seq = process.record_output(stream, bytes(chunk))
            if backend.notifications is not None:
                await backend.notifications.notify(
                    EXEC_OUTPUT_DELTA_METHOD,
                    ExecOutputDeltaNotification(
                        process_id=process_id,
                        seq=seq,
                        stream=stream,
                        chunk=ByteChunk(bytes(chunk)),
                    ),
                )
    finally:
        close = getattr(reader, "close", None)
        if close is not None:
            close()
        process.open_streams = max(0, process.open_streams - 1)
        await _local_process_maybe_mark_closed(backend, process_id, process)


async def _local_process_watch_exit(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
    child: Any,
) -> None:
    wait_result = await _maybe_await(child.wait())
    exit_code = int(wait_result if wait_result is not None else -1)
    seq = process.record_exit(exit_code)
    if backend.notifications is not None:
        await backend.notifications.notify(
            EXEC_EXITED_METHOD,
            ExecExitedNotification(process_id=process_id, seq=seq, exit_code=exit_code),
        )
    await _local_process_maybe_mark_closed(backend, process_id, process)


async def _local_process_maybe_mark_closed(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
) -> None:
    if process.closed or process.open_streams != 0 or process.exit_code is None:
        return
    seq = process.next_seq
    process.next_seq += 1
    process.mark_closed(seq)
    if backend.notifications is not None:
        await backend.notifications.notify(
            EXEC_CLOSED_METHOD,
            ExecClosedNotification(process_id=process_id, seq=seq),
        )
    cleanup_task = asyncio.create_task(_local_process_cleanup_closed_after_retention(backend, process_id, process))
    process.task_handles.append(cleanup_task)


async def _local_process_cleanup_closed_after_retention(
    backend: LocalProcess,
    process_id: ProcessId,
    process: LocalRunningProcess,
) -> None:
    await asyncio.sleep(LOCAL_PROCESS_EXITED_PROCESS_RETENTION_SECONDS)
    if backend.processes.get(process_id) is process and process.closed:
        backend.processes.pop(process_id, None)


class LocalExecProcess:
    def __init__(self, process_id: ProcessId, backend: LocalProcess, process: LocalRunningProcess) -> None:
        self._process_id = process_id
        self._backend = backend
        self._process = process

    def process_id(self) -> ProcessId:
        return self._process_id

    def subscribe_wake(self) -> asyncio.Queue[int]:
        return self._process.wake_queue

    def subscribe_events(self) -> ExecProcessEventReceiver:
        if self._process.events is None:
            return ExecProcessEventReceiver.empty()
        return self._process.events.subscribe()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        response = await self._backend.exec_read(
            ReadParams(
                process_id=self._process_id,
                after_seq=after_seq,
                max_bytes=max_bytes,
                wait_ms=wait_ms,
            )
        )
        if isinstance(response, JSONRPCErrorError):
            from pycodex.exec_server.client import ExecServerError
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        return response

    async def write(self, chunk: bytes) -> WriteResponse:
        response = await self._backend.exec_write(
            WriteParams(process_id=self._process_id, chunk=ByteChunk(chunk))
        )
        if isinstance(response, JSONRPCErrorError):
            from pycodex.exec_server.client import ExecServerError
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")
        return response

    async def terminate(self) -> None:
        response = await self._backend.terminate_process(TerminateParams(process_id=self._process_id))
        if isinstance(response, JSONRPCErrorError):
            from pycodex.exec_server.client import ExecServerError
            raise ExecServerError(f"exec-server rejected request ({response.code}): {response.message}", "server")


PROCESS_EVENT_CHANNEL_CAPACITY = 256


from pycodex.exec_server.connection import _terminate_process_tree
from pycodex.exec_server.process import ExecProcessEvent, ExecProcessEventLog, ExecProcessEventReceiver, StartedExecProcess
from pycodex.exec_server.process_id import ProcessId
from pycodex.exec_server.protocol import ByteChunk, EXEC_CLOSED_METHOD, EXEC_EXITED_METHOD, EXEC_OUTPUT_DELTA_METHOD, ExecClosedNotification, ExecExitedNotification, ExecOutputDeltaNotification, ExecOutputStream, ExecParams, ExecResponse, ProcessOutputChunk, ReadParams, ReadResponse, TerminateParams, TerminateResponse, WriteParams, WriteResponse, WriteStatus, child_env
from pycodex.exec_server.rpc import RpcNotificationSender, _maybe_await
