"""PTY-backed spawning from codex-utils-pty/src/pty.rs."""

from __future__ import annotations

import asyncio
import errno
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from . import process_group
from .pipe import _normalize_env, _spawn_process, _wait_process
from .process import ProcessHandle, SpawnedProcess, TerminalSize


class _PtyChildTerminator:
    def __init__(self, killer: Callable[[], None], process_group_id: int | None = None) -> None:
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


def conpty_supported() -> bool:
    if os.name != "nt":
        return True
    from .win import conpty_supported as windows_conpty_supported

    return windows_conpty_supported()


def _set_cloexec(fd: int) -> None:
    import fcntl

    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)


def _resize_raw_pty(raw_fd: int, size: TerminalSize) -> None:
    import fcntl
    import struct
    import termios

    winsize = struct.pack("HHHH", size.rows, size.cols, 0, 0)
    fcntl.ioctl(raw_fd, termios.TIOCSWINSZ, winsize)


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
        if not flags & fcntl.FD_CLOEXEC:
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
        child = await asyncio.create_subprocess_exec(
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
    exit_future = asyncio.create_task(_wait_process(child))

    async def write_stdin(chunk: bytes) -> None:
        try:
            await asyncio.to_thread(os.write, master_fd, chunk)
        except OSError:
            return

    def terminate_process_group() -> None:
        process_group.kill_process_group(child.pid)

    async def close_master_after_exit() -> None:
        try:
            await exit_future
        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass

    cleanup_task = asyncio.create_task(close_master_after_exit())
    handle = ProcessHandle(
        child,
        stdin_writer=write_stdin,
        close_stdin=lambda: None,
        terminator=terminate_process_group,
        resizer=lambda new_size: _resize_raw_pty(master_fd, new_size),
        exit_future=exit_future,
        helper_tasks=(reader_task, cleanup_task),
    )
    return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


async def _spawn_pty_process_portable(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    command_name = arg0 if arg0 is not None else program
    if os.name == "nt":
        from .win import ConPtySystem

        return await ConPtySystem().spawn_process(command_name, args, cwd, env, size)
    if os.name == "posix":
        return await _spawn_pty_process_preserving_fds(command_name, args, cwd, env, None, size, ())
    return await _spawn_process(
        command_name,
        args,
        cwd,
        env,
        None,
        stdin_enabled=True,
        missing_program_message="missing program for PTY spawn",
    )


async def spawn_process(
    program: str,
    args: Sequence[str],
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    arg0: str | None = None,
    size: TerminalSize = TerminalSize(),
) -> SpawnedProcess:
    return await spawn_process_with_inherited_fds(program, args, cwd, env, arg0, size, ())


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


__all__ = ["conpty_supported", "spawn_process", "spawn_process_with_inherited_fds"]
