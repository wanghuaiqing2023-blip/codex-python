"""Python port of the public ``codex-utils-pty`` crate interface.

Rust reference:
- ``codex/codex-rs/utils/pty/src/lib.rs``
- ``codex/codex-rs/utils/pty/src/process.rs``
- ``codex/codex-rs/utils/pty/src/pipe.rs``
- ``codex/codex-rs/utils/pty/src/pty.rs``
- ``codex/codex-rs/utils/pty/src/process_group.rs``
"""

from __future__ import annotations

import asyncio
import ctypes
import errno
import os
import signal
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_BYTES_CAP = 1024 * 1024
_SIGKILL = getattr(signal, "SIGKILL", 9)
_SIGTERM = getattr(signal, "SIGTERM", 15)


@dataclass(frozen=True)
class TerminalSize:
    rows: int = 24
    cols: int = 80

    def __post_init__(self) -> None:
        for name, value in (("rows", self.rows), ("cols", self.cols)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0 or value > 0xFFFF:
                raise ValueError(f"{name} must fit in u16")


class _WriterSender:
    def __init__(self, write: Callable[[bytes], Awaitable[None]]) -> None:
        self._write = write

    async def send(self, chunk: bytes | bytearray | memoryview) -> None:
        await self._write(bytes(chunk))


class ProcessHandle:
    """Handle for driving an interactive process.

    This mirrors the Rust handle's user-visible contract: expose a stdin sender,
    exit state/code, resize, close stdin, and terminate helpers.
    """

    def __init__(
        self,
        process: asyncio.subprocess.Process | subprocess.Popen[bytes] | None,
        *,
        stdin_writer: Callable[[bytes], Awaitable[None]] | None = None,
        close_stdin: Callable[[], None] | None = None,
        terminator: Callable[[], None] | None = None,
        resizer: Callable[[TerminalSize], None] | None = None,
        exit_future: asyncio.Future[int] | None = None,
        helper_tasks: Sequence[asyncio.Task[Any]] = (),
    ) -> None:
        self._process = process
        self._stdin_writer = stdin_writer
        self._close_stdin = close_stdin
        self._terminator = terminator
        self._resizer = resizer
        self._exit_future = exit_future
        self._helper_tasks = list(helper_tasks)
        self._stdin_closed = False

    def writer_sender(self) -> _WriterSender:
        async def send(chunk: bytes) -> None:
            if not self._stdin_closed and self._stdin_writer is not None:
                await self._stdin_writer(chunk)

        return _WriterSender(send)

    def has_exited(self) -> bool:
        if self._exit_future is not None:
            return self._exit_future.done()
        return self._process is not None and self._process.returncode is not None

    def exit_code(self) -> int | None:
        if self._exit_future is not None and self._exit_future.done():
            try:
                return self._exit_future.result()
            except Exception:
                return -1
        if self._process is None:
            return None
        return self._process.returncode

    def resize(self, size: TerminalSize) -> None:
        if self._resizer is None:
            raise RuntimeError("process is not attached to a PTY")
        self._resizer(size)

    def close_stdin(self) -> None:
        self._stdin_closed = True
        if self._close_stdin is not None:
            self._close_stdin()

    def request_terminate(self) -> None:
        if self._terminator is not None:
            self._terminator()
            return
        if self._process is not None and self._process.returncode is None:
            self._process.kill()

    def terminate(self) -> None:
        self.request_terminate()
        for task in self._helper_tasks:
            task.cancel()


class _PtyChildTerminator:
    def __init__(
        self,
        killer: Callable[[], None],
        process_group_id: int | None = None,
    ) -> None:
        self._killer = killer
        self._process_group_id = process_group_id

    def kill(self) -> None:
        if os.name != "nt" and self._process_group_id is not None:
            process_group_error: OSError | None = None
            try:
                process_group.kill_process_group(self._process_group_id)
            except OSError as exc:
                process_group_error = exc

            try:
                self._killer()
                return
            except OSError as exc:
                if process_group._is_not_found_error(exc):
                    if process_group_error is not None:
                        raise process_group_error
                    return
                if process_group_error is not None:
                    raise exc
                return

        self._killer()


@dataclass
class SpawnedProcess:
    session: ProcessHandle
    stdout_rx: asyncio.Queue[bytes]
    stderr_rx: asyncio.Queue[bytes]
    exit_rx: asyncio.Future[int]


@dataclass
class ProcessDriver:
    writer_tx: Any
    stdout_rx: Any
    stderr_rx: Any | None
    exit_rx: Awaitable[int] | asyncio.Future[int]
    terminator: Callable[[], None] | None = None
    writer_handle: asyncio.Task[Any] | None = None
    resizer: Callable[[TerminalSize], None] | None = None


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

    process = await asyncio.create_subprocess_exec(
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
    stdout_task = asyncio.create_task(_read_stream(process.stdout, stdout_rx))
    stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_rx))
    exit_future = asyncio.create_task(_wait_process(process))

    async def write_stdin(chunk: bytes) -> None:
        if process.stdin is None or process.stdin.is_closing():
            return
        process.stdin.write(chunk)
        await process.stdin.drain()

    def close_stdin() -> None:
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()

    def terminate_process() -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, _SIGKILL)
            except ProcessLookupError:
                pass

    handle = ProcessHandle(
        process,
        stdin_writer=write_stdin if stdin_enabled else None,
        close_stdin=close_stdin,
        terminator=terminate_process,
        exit_future=exit_future,
        helper_tasks=(stdout_task, stderr_task),
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


async def spawn_pipe_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=True)


async def spawn_pipe_process_no_stdin(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
) -> SpawnedProcess:
    return await _spawn_process(program, args, cwd, env, arg0, stdin_enabled=False)


async def spawn_pipe_process_no_stdin_with_inherited_fds(
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


async def _spawn_pty_process_portable(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    del size
    command_name = arg0 if arg0 is not None else program
    return await _spawn_process(
        command_name,
        args,
        cwd,
        env,
        None,
        stdin_enabled=True,
        missing_program_message="missing program for PTY spawn",
    )


def _set_cloexec(fd: int) -> None:
    import fcntl

    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def _open_unix_pty(size: TerminalSize) -> tuple[int, int]:
    try:
        master_fd, slave_fd = os.openpty()
    except OSError as exc:
        raise OSError(exc.errno, f"failed to openpty: {exc}") from exc
    try:
        _set_cloexec(master_fd)
        _set_cloexec(slave_fd)
        _resize_raw_pty(master_fd, size)
    except Exception:
        os.close(master_fd)
        os.close(slave_fd)
        raise
    return master_fd, slave_fd


def _close_inherited_fds_except(preserved_fds: Sequence[int]) -> None:
    import fcntl

    preserved = {int(fd) for fd in preserved_fds}
    try:
        names = os.listdir("/dev/fd")
    except OSError:
        return

    to_close: list[int] = []
    for name in names:
        try:
            fd = int(name)
        except ValueError:
            continue
        if fd <= 2 or fd in preserved:
            continue
        try:
            flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        except OSError:
            continue
        if flags & fcntl.FD_CLOEXEC:
            continue
        to_close.append(fd)

    for fd in to_close:
        try:
            os.close(fd)
        except OSError:
            pass


def _reset_child_signal_state() -> None:
    for signum in (
        getattr(signal, "SIGCHLD", None),
        getattr(signal, "SIGHUP", None),
        getattr(signal, "SIGINT", None),
        getattr(signal, "SIGQUIT", None),
        getattr(signal, "SIGTERM", None),
        getattr(signal, "SIGALRM", None),
    ):
        if signum is not None:
            signal.signal(signum, signal.SIG_DFL)
    if hasattr(signal, "pthread_sigmask"):
        signal.pthread_sigmask(signal.SIG_SETMASK, [])


def _make_pty_preexec(preserved_fds: Sequence[int]) -> Callable[[], None]:
    preserved = tuple(int(fd) for fd in preserved_fds)

    def preexec() -> None:
        _reset_child_signal_state()
        os.setsid()
        import fcntl
        import termios

        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        _close_inherited_fds_except(preserved)

    return preexec


def _resize_raw_pty(raw_fd: int, size: TerminalSize) -> None:
    import fcntl
    import struct
    import termios

    winsize = struct.pack("HHHH", size.rows, size.cols, 0, 0)
    fcntl.ioctl(raw_fd, termios.TIOCSWINSZ, winsize)


async def _read_pty_fd(master_fd: int, queue: asyncio.Queue[bytes]) -> None:
    while True:
        try:
            chunk = await asyncio.to_thread(os.read, master_fd, 8192)
        except InterruptedError:
            continue
        except BlockingIOError:
            await asyncio.sleep(0.005)
            continue
        except OSError:
            break
        if not chunk:
            break
        await queue.put(chunk)


async def _spawn_pty_process_preserving_fds(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
    inherited_fds: Sequence[int] = (),
) -> SpawnedProcess:
    master_fd, slave_fd = _open_unix_pty(size)
    stdin_file = os.fdopen(os.dup(slave_fd), "rb", buffering=0)
    stdout_file = os.fdopen(os.dup(slave_fd), "wb", buffering=0)
    stderr_file = os.fdopen(os.dup(slave_fd), "wb", buffering=0)
    slave_keepalive = os.fdopen(slave_fd, "rb", buffering=0)

    argv = [program, *map(str, args)]
    if arg0 is not None:
        argv[0] = arg0

    pass_fds = tuple({int(fd) for fd in inherited_fds})
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            executable=program,
            cwd=Path(cwd),
            env=_normalize_env(env),
            stdin=stdin_file,
            stdout=stdout_file,
            stderr=stderr_file,
            pass_fds=pass_fds,
            preexec_fn=_make_pty_preexec(pass_fds),
        )
    except Exception:
        for handle in (stdin_file, stdout_file, stderr_file, slave_keepalive):
            handle.close()
        os.close(master_fd)
        raise
    finally:
        stdin_file.close()
        stdout_file.close()
        stderr_file.close()
        slave_keepalive.close()

    stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
    stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    reader_task = asyncio.create_task(_read_pty_fd(master_fd, stdout_rx))
    exit_future = asyncio.create_task(_wait_process(process))

    async def write_stdin(chunk: bytes) -> None:
        try:
            await asyncio.to_thread(os.write, master_fd, chunk)
        except OSError:
            return

    def close_stdin() -> None:
        return

    def terminate_process_group() -> None:
        process_group.kill_process_group(process.pid)

    def resize(size: TerminalSize) -> None:
        _resize_raw_pty(master_fd, size)

    async def close_master_after_exit() -> None:
        try:
            await exit_future
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass

    asyncio.create_task(close_master_after_exit())
    handle = ProcessHandle(
        process,
        stdin_writer=write_stdin,
        close_stdin=close_stdin,
        terminator=terminate_process_group,
        resizer=resize,
        exit_future=exit_future,
        helper_tasks=(reader_task,),
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


async def spawn_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    return await spawn_process_with_inherited_fds(
        program,
        args,
        cwd,
        env,
        arg0,
        size,
        inherited_fds=(),
    )


async def spawn_pty_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    return await spawn_process(program, args, cwd, env, arg0, size)


async def spawn_process_with_inherited_fds(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
    inherited_fds: Sequence[int] = (),
) -> SpawnedProcess:
    if not program:
        raise ValueError("missing program for PTY spawn")
    if inherited_fds and os.name == "posix":
        return await _spawn_pty_process_preserving_fds(program, args, cwd, env, arg0, size, inherited_fds)
    return await _spawn_pty_process_portable(program, args, cwd, env, arg0, size)


ExecCommandSession = ProcessHandle
SpawnedPty = SpawnedProcess


def conpty_supported() -> bool:
    return os.name != "nt" or sys.getwindowsversion().major >= 10


async def _forward_queue(src: Any, dst: asyncio.Queue[bytes]) -> None:
    while True:
        if hasattr(src, "get"):
            item = await src.get()
        elif hasattr(src, "recv"):
            item = await src.recv()
        else:
            raise TypeError("output receiver must provide get() or recv()")
        if item is None:
            break
        await dst.put(bytes(item))


def combine_output_receivers(stdout_rx: Any, stderr_rx: Any) -> asyncio.Queue[bytes]:
    combined: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    asyncio.create_task(_forward_queue(stdout_rx, combined))
    asyncio.create_task(_forward_queue(stderr_rx, combined))
    return combined


def spawn_from_driver(driver: ProcessDriver) -> SpawnedProcess:
    stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    tasks = [
        asyncio.create_task(_forward_queue(driver.stdout_rx, stdout_rx)),
    ]
    if driver.stderr_rx is not None:
        tasks.append(asyncio.create_task(_forward_queue(driver.stderr_rx, stderr_rx)))
    if driver.writer_handle is not None:
        tasks.append(driver.writer_handle)

    exit_future = asyncio.ensure_future(driver.exit_rx)

    async def write_stdin(chunk: bytes) -> None:
        writer = driver.writer_tx
        if hasattr(writer, "put"):
            await writer.put(chunk)
        elif hasattr(writer, "send"):
            result = writer.send(chunk)
            if hasattr(result, "__await__"):
                await result
        else:
            raise TypeError("driver writer must provide put() or send()")

    handle = ProcessHandle(
        None,
        stdin_writer=write_stdin,
        terminator=driver.terminator,
        resizer=driver.resizer,
        exit_future=exit_future,
        helper_tasks=tasks,
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


class process_group:
    @staticmethod
    def _is_not_found_error(exc: OSError) -> bool:
        return isinstance(exc, ProcessLookupError) or exc.errno in {errno.ESRCH, errno.ENOENT}

    @staticmethod
    def set_parent_death_signal(parent_pid: int) -> None:
        if not sys.platform.startswith("linux"):
            return
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        PR_SET_PDEATHSIG = 1
        if prctl(PR_SET_PDEATHSIG, _SIGTERM, 0, 0, 0) == -1:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        if os.getppid() != int(parent_pid):
            os.kill(os.getpid(), _SIGTERM)

    @staticmethod
    def detach_from_tty() -> None:
        if os.name != "nt":
            try:
                os.setsid()
            except OSError as exc:
                if exc.errno == errno.EPERM:
                    process_group.set_process_group()
                else:
                    raise

    @staticmethod
    def set_process_group() -> None:
        if os.name != "nt":
            os.setpgid(0, 0)

    @staticmethod
    def kill_process_group_by_pid(pid: int) -> None:
        if os.name != "nt":
            try:
                pgid = os.getpgid(pid)
            except OSError as exc:
                if process_group._is_not_found_error(exc):
                    return
                raise
            try:
                os.killpg(pgid, _SIGKILL)
            except OSError as exc:
                if process_group._is_not_found_error(exc):
                    return
                raise

    @staticmethod
    def _killpg(process_group_id: int, sig: int) -> None:
        try:
            os.killpg(process_group_id, sig)
        except OSError as exc:
            if process_group._is_not_found_error(exc):
                return
            raise

    @staticmethod
    def terminate_process_group(process_group_id: int) -> bool:
        if os.name == "nt":
            return False
        try:
            os.killpg(process_group_id, _SIGTERM)
            return True
        except OSError as exc:
            if process_group._is_not_found_error(exc):
                return False
            raise

    @staticmethod
    def kill_process_group(process_group_id: int) -> None:
        if os.name != "nt":
            process_group._killpg(process_group_id, _SIGKILL)

    @staticmethod
    def kill_child_process_group(child: Any) -> None:
        pid = getattr(child, "pid", None)
        if pid is not None:
            process_group.kill_process_group_by_pid(pid)


__all__ = [
    "DEFAULT_OUTPUT_BYTES_CAP",
    "ExecCommandSession",
    "ProcessDriver",
    "ProcessHandle",
    "SpawnedProcess",
    "SpawnedPty",
    "TerminalSize",
    "combine_output_receivers",
    "conpty_supported",
    "process_group",
    "spawn_from_driver",
    "spawn_pipe_process",
    "spawn_pipe_process_no_stdin",
    "spawn_pipe_process_no_stdin_with_inherited_fds",
    "spawn_process",
    "spawn_process_with_inherited_fds",
    "spawn_pty_process",
]
