"""ConPTY creation and restricted-token process spawning.

Rust owner: ``codex-windows-sandbox::conpty``.
"""

from __future__ import annotations

import ctypes
import io
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from ..desktop import LaunchDesktop
from ..proc_thread_attr import ProcThreadAttributeList
from .. import process as _process
from ..token import WinHandle


if os.name == "nt":
    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


    _process._kernel32.CreatePseudoConsole.argtypes = [
        COORD,
        _process.HANDLE,
        _process.HANDLE,
        _process.DWORD,
        ctypes.POINTER(_process.HANDLE),
    ]
    _process._kernel32.CreatePseudoConsole.restype = ctypes.c_long
    _process._kernel32.ResizePseudoConsole.argtypes = [_process.HANDLE, COORD]
    _process._kernel32.ResizePseudoConsole.restype = ctypes.c_long
    _process._kernel32.ClosePseudoConsole.argtypes = [_process.HANDLE]
    _process._kernel32.ClosePseudoConsole.restype = None


class ConptyInstance:
    """Own a pseudo console and its backing host pipe handles."""

    def __init__(
        self,
        pseudoconsole: object,
        input_write: object,
        output_read: object,
        desktop: LaunchDesktop | None = None,
    ) -> None:
        self._pseudoconsole = pseudoconsole
        self._input_write = input_write
        self._output_read = output_read
        self._desktop = desktop

    @property
    def raw_handle(self) -> int | None:
        value = getattr(self._pseudoconsole, "value", self._pseudoconsole)
        return int(value) if value else None

    def take_input_write(self) -> object:
        handle, self._input_write = self._input_write, None
        return handle

    def take_output_read(self) -> object:
        handle, self._output_read = self._output_read, None
        return handle

    def resize(self, cols: int, rows: int) -> None:
        if not self.raw_handle:
            raise _process.WindowsSandboxProcessError("pseudo console is closed")
        _validate_size(cols, rows)
        result = _process._kernel32.ResizePseudoConsole(
            self._pseudoconsole,
            COORD(cols, rows),
        )
        if result < 0:
            raise _process.WindowsSandboxProcessError(
                result,
                f"ResizePseudoConsole failed: 0x{result & 0xffffffff:08x}",
            )

    def close(self) -> None:
        for name in ("_input_write", "_output_read"):
            handle = getattr(self, name)
            if handle is not None:
                _process._close_handle(handle)
                setattr(self, name, None)
        if self.raw_handle:
            _process._kernel32.ClosePseudoConsole(self._pseudoconsole)
            self._pseudoconsole = None
        if self._desktop is not None:
            self._desktop.close()
            self._desktop = None

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


class _ConptyInputWriter:
    def __init__(self, stream: io.BufferedWriter) -> None:
        self._stream = stream
        self._previous_was_cr = False

    @property
    def closed(self) -> bool:
        return self._stream.closed

    def write(self, data: bytes | bytearray | memoryview) -> int:
        source = bytes(data)
        normalized = bytearray()
        for byte in source:
            if byte == 0x0A and not self._previous_was_cr:
                normalized.append(0x0D)
            normalized.append(byte)
            self._previous_was_cr = byte == 0x0D
        self._stream.write(normalized)
        return len(source)

    def flush(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()


def _validate_size(cols: int, rows: int) -> None:
    if cols <= 0 or rows <= 0 or cols > 32767 or rows > 32767:
        raise ValueError("ConPTY size must be within 1..32767")


def create_conpty(cols: int, rows: int) -> ConptyInstance:
    """Create a ConPTY with backing pipes."""

    _process._require_windows()
    _validate_size(cols, rows)
    input_read, input_write = _process._create_pipe()
    output_read, output_write = _process._create_pipe()
    pseudoconsole = _process.HANDLE()
    try:
        result = _process._kernel32.CreatePseudoConsole(
            COORD(cols, rows),
            input_read,
            output_write,
            0,
            ctypes.byref(pseudoconsole),
        )
        if result < 0:
            raise _process.WindowsSandboxProcessError(
                result,
                f"CreatePseudoConsole failed: 0x{result & 0xffffffff:08x}",
            )
        _process._close_handle(input_read)
        input_read = _process.HANDLE()
        _process._close_handle(output_write)
        output_write = _process.HANDLE()
        instance = ConptyInstance(pseudoconsole, input_write, output_read)
        pseudoconsole = _process.HANDLE()
        input_write = _process.HANDLE()
        output_read = _process.HANDLE()
        return instance
    finally:
        for handle in (
            input_read,
            input_write,
            output_read,
            output_write,
            pseudoconsole,
        ):
            _process._close_handle(handle)


def spawn_conpty_process_as_user(
    token: WinHandle | int,
    argv: Sequence[str],
    cwd: str | Path,
    env_map: Mapping[str, str],
    *,
    stdin_open: bool = True,
    use_private_desktop: bool = False,
    logs_base_dir: str | Path | None = None,
    cols: int = 80,
    rows: int = 24,
) -> _process.NativeProcessPopen:
    """Spawn a restricted process attached to a Windows ConPTY."""

    del logs_base_dir
    _process._require_windows()
    if not argv or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("command must contain at least one string argument")
    _validate_size(cols, rows)
    desktop = LaunchDesktop.prepare(use_private_desktop)
    conpty = create_conpty(cols, rows)
    conpty._desktop = desktop
    desktop = None
    process_info = _process.PROCESS_INFORMATION()
    job_handle = _process.HANDLE()
    attrs: ProcThreadAttributeList | None = None
    desktop_buffer = ctypes.create_unicode_buffer(conpty._desktop.startup_name)
    try:
        attrs = ProcThreadAttributeList(1)
        raw_handle = conpty.raw_handle
        if raw_handle is None:
            raise _process.WindowsSandboxProcessError(
                "invalid pseudo console handle"
            )
        attrs.set_pseudoconsole(raw_handle)
        startup = _process.STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(_process.STARTUPINFOEXW)
        startup.StartupInfo.lpDesktop = ctypes.cast(
            desktop_buffer,
            _process.wintypes.LPWSTR,
        )
        startup.StartupInfo.dwFlags = _process.STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = _process.HANDLE(
            _process.INVALID_HANDLE_VALUE
        )
        startup.StartupInfo.hStdOutput = _process.HANDLE(
            _process.INVALID_HANDLE_VALUE
        )
        startup.StartupInfo.hStdError = _process.HANDLE(
            _process.INVALID_HANDLE_VALUE
        )
        startup.lpAttributeList = attrs.as_mut_ptr()
        command_line = ctypes.create_unicode_buffer(
            subprocess.list2cmdline(list(argv))
        )
        environment = _process.make_env_block(env_map)
        flags = (
            _process.CREATE_UNICODE_ENVIRONMENT
            | _process.EXTENDED_STARTUPINFO_PRESENT
            | _process.CREATE_SUSPENDED
        )
        if not _process._advapi32.CreateProcessAsUserW(
            _process._as_handle(token),
            None,
            command_line,
            None,
            None,
            False,
            flags,
            environment,
            str(Path(cwd)),
            ctypes.byref(startup.StartupInfo),
            ctypes.byref(process_info),
        ):
            error = ctypes.get_last_error()
            raise _process.WindowsSandboxProcessError(
                error,
                f"CreateProcessAsUserW failed: {error}",
            )
        job_handle = _process._create_kill_on_close_job()
        if not _process._kernel32.AssignProcessToJobObject(
            job_handle,
            process_info.hProcess,
        ):
            error = ctypes.get_last_error()
            _process._kernel32.TerminateProcess(process_info.hProcess, 1)
            raise _process.WindowsSandboxProcessError(
                error,
                f"AssignProcessToJobObject failed: {error}",
            )
        if _process._kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            _process._kernel32.TerminateJobObject(job_handle, 1)
            raise _process.WindowsSandboxProcessError(
                error,
                f"ResumeThread failed: {error}",
            )
        _process._close_handle(process_info.hThread)
        process_info.hThread = _process.HANDLE()
        input_handle = conpty.take_input_write()
        if not stdin_open:
            _process._close_handle(input_handle)
            input_handle = None
        output_handle = conpty.take_output_read()
        stdin_file = (
            _ConptyInputWriter(_process._handle_file(input_handle, "wb"))
            if input_handle is not None
            else None
        )
        stdout_file = _process._handle_file(output_handle, "rb")
        result = _process.NativeProcessPopen(
            process_info.hProcess,
            job_handle,
            int(process_info.dwProcessId),
            stdin_file,
            stdout_file,
            None,
            conpty,
        )
        process_info.hProcess = _process.HANDLE()
        job_handle = _process.HANDLE()
        conpty = None
        return result
    except BaseException:
        if getattr(process_info.hProcess, "value", process_info.hProcess):
            _process._kernel32.TerminateProcess(process_info.hProcess, 1)
        raise
    finally:
        if attrs is not None:
            attrs.close()
        for handle in (
            process_info.hThread,
            process_info.hProcess,
            job_handle,
        ):
            _process._close_handle(handle)
        if conpty is not None:
            conpty.close()
        if desktop is not None:
            desktop.close()


__all__ = [
    "ConptyInstance",
    "create_conpty",
    "spawn_conpty_process_as_user",
]
