"""ConPTY system from codex-utils-pty/src/win/conpty.rs."""

from __future__ import annotations

import asyncio
import ctypes
import os
from collections.abc import Mapping, Sequence
from ctypes import wintypes

from ..process import ProcessHandle, SpawnedProcess, TerminalSize
from .psuedocon import COORD, PsuedoCon

ERROR_BROKEN_PIPE = 109
ERROR_HANDLE_EOF = 38
ERROR_NO_DATA = 232


def _kernel32() -> ctypes.WinDLL:
    if os.name != "nt":
        raise OSError("ConPTY is only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _create_pipe() -> tuple[int, int]:
    read = wintypes.HANDLE()
    write = wintypes.HANDLE()
    if not _kernel32().CreatePipe(ctypes.byref(read), ctypes.byref(write), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(read.value), int(write.value)


class RawConPty:
    def __init__(self, con: PsuedoCon, input_write: int, output_read: int) -> None:
        self.con = con
        self.input_write = int(input_write)
        self.output_read = int(output_read)
        self._closed_input = False
        self._closed_output = False

    @classmethod
    def new(cls, cols: int, rows: int) -> "RawConPty":
        input_read, input_write = _create_pipe()
        output_read, output_write = _create_pipe()
        try:
            con = PsuedoCon.new(COORD(int(cols), int(rows)), input_read, output_write)
        except Exception:
            kernel32 = _kernel32()
            for handle in (input_read, input_write, output_read, output_write):
                kernel32.CloseHandle(wintypes.HANDLE(handle))
            raise
        return cls(con, input_write, output_read)

    def pseudoconsole_handle(self) -> int:
        return self.con.raw_handle()

    def into_handles(self) -> tuple[PsuedoCon, int, int]:
        con, input_write, output_read = self.con, self.input_write, self.output_read
        self._closed_input = True
        self._closed_output = True
        return con, input_write, output_read

    def write(self, data: bytes) -> None:
        if self._closed_input:
            return
        buffer = ctypes.create_string_buffer(data)
        written = wintypes.DWORD()
        if not _kernel32().WriteFile(
            wintypes.HANDLE(self.input_write),
            buffer,
            len(data),
            ctypes.byref(written),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def read(self, size: int = 8192) -> bytes:
        if self._closed_output:
            return b""
        buffer = ctypes.create_string_buffer(size)
        read = wintypes.DWORD()
        if not _kernel32().ReadFile(
            wintypes.HANDLE(self.output_read),
            buffer,
            size,
            ctypes.byref(read),
            None,
        ):
            error = ctypes.get_last_error()
            if error in {ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF, ERROR_NO_DATA}:
                return b""
            raise ctypes.WinError(error)
        return buffer.raw[: int(read.value)]

    def resize(self, size: TerminalSize) -> None:
        self.con.resize(COORD(int(size.cols), int(size.rows)))

    def close_input(self) -> None:
        if not self._closed_input:
            _kernel32().CloseHandle(wintypes.HANDLE(self.input_write))
            self._closed_input = True

    def close_output(self) -> None:
        if not self._closed_output:
            _kernel32().CloseHandle(wintypes.HANDLE(self.output_read))
            self._closed_output = True

    def close(self) -> None:
        self.close_input()
        self.close_output()
        self.con.close()


class ConPtySystem:
    async def spawn_process(
        self,
        program: str,
        args: Sequence[str],
        cwd: str | os.PathLike[str],
        env: Mapping[str, str],
        size: TerminalSize,
    ) -> SpawnedProcess:
        raw = RawConPty.new(size.cols, size.rows)
        try:
            child = raw.con.spawn_command(program, args, cwd, env)
        except Exception:
            raw.close()
            raise

        stdout_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=128)
        stderr_rx: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)

        async def read_output() -> None:
            try:
                while True:
                    chunk = await asyncio.to_thread(raw.read)
                    if not chunk:
                        break
                    await stdout_rx.put(chunk)
            finally:
                raw.close_output()

        reader_task = asyncio.create_task(read_output())
        exit_future = asyncio.create_task(asyncio.to_thread(child.wait))

        async def write_stdin(chunk: bytes) -> None:
            await asyncio.to_thread(raw.write, chunk)

        def close_stdin() -> None:
            raw.close_input()

        async def close_after_exit() -> None:
            try:
                await exit_future
            finally:
                # Closing the pseudo console releases its terminal-side pipe
                # handles and lets the blocking ReadFile observe EOF.
                raw.con.close()
                raw.close_input()
                try:
                    await asyncio.wait_for(reader_task, timeout=2.0)
                except TimeoutError:
                    reader_task.cancel()
                child.close()
                raw.close_output()

        cleanup_task = asyncio.create_task(close_after_exit())
        handle = ProcessHandle(
            child,
            stdin_writer=write_stdin,
            close_stdin=close_stdin,
            terminator=child.kill,
            resizer=raw.resize,
            exit_future=exit_future,
            helper_tasks=(reader_task, cleanup_task),
        )
        return SpawnedProcess(handle, stdout_rx, stderr_rx, exit_future)


__all__ = ["ConPtySystem", "RawConPty"]
