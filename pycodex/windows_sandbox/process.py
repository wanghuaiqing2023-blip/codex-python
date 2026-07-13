"""Restricted-token process creation for the native Windows sandbox.

Rust owner: ``codex-windows-sandbox::process`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
import io
from enum import Enum
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .desktop import LaunchDesktop
from .token import WinHandle


class WindowsSandboxProcessError(OSError):
    pass


@dataclass(frozen=True)
class ProcessCaptureResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    cancelled: bool = False


class StdinMode(str, Enum):
    CLOSED = "closed"
    OPEN = "open"


class StderrMode(str, Enum):
    MERGE_STDOUT = "merge_stdout"
    SEPARATE = "separate"


@dataclass
class PipeSpawnHandles:
    process_handle: object
    thread_handle: object
    stdin_write: object | None
    stdout_read: object
    stderr_read: object | None
    desktop: LaunchDesktop


class ConptyInstance:
    """Own a native pseudo console and the remaining host pipe handles."""

    def __init__(self, pseudoconsole: object, input_write: object, output_read: object, desktop: LaunchDesktop) -> None:
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
            raise WindowsSandboxProcessError("pseudo console is closed")
        if cols <= 0 or rows <= 0 or cols > 32767 or rows > 32767:
            raise ValueError("ConPTY size must be within 1..32767")
        result = _kernel32.ResizePseudoConsole(self._pseudoconsole, COORD(cols, rows))
        if result < 0:
            raise WindowsSandboxProcessError(result, f"ResizePseudoConsole failed: 0x{result & 0xffffffff:08x}")

    def close(self) -> None:
        for name in ("_input_write", "_output_read"):
            handle = getattr(self, name)
            if handle is not None:
                _close_handle(handle)
                setattr(self, name, None)
        if self.raw_handle:
            _kernel32.ClosePseudoConsole(self._pseudoconsole)
            self._pseudoconsole = None
        self._desktop.close()

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


class _ConptyInputWriter:
    """Normalize bare LF input the same way as Rust's Windows TTY driver."""

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


class NativeProcessPopen:
    """Popen-compatible owner for a restricted Win32 process and its job."""

    def __init__(
        self,
        process_handle: object,
        job_handle: object,
        stdin: object | None,
        stdout: io.BufferedReader,
        stderr: io.BufferedReader | None = None,
        resource_owner: object | None = None,
    ) -> None:
        self._process_handle = process_handle
        self._job_handle = job_handle
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None
        self._closed_handles = False
        self._resource_owner = resource_owner

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        result = _kernel32.WaitForSingleObject(self._process_handle, 0)
        if result == WAIT_TIMEOUT:
            return None
        if result == WAIT_FAILED:
            _raise_last_error("WaitForSingleObject failed")
        if result != WAIT_OBJECT_0:
            raise WindowsSandboxProcessError(f"unexpected process wait status 0x{result:08x}")
        code = DWORD()
        if not _kernel32.GetExitCodeProcess(self._process_handle, ctypes.byref(code)):
            _raise_last_error("GetExitCodeProcess failed")
        self.returncode = int(code.value)
        # A ConPTY output pipe does not reach EOF until its pseudo console is
        # closed. Rust drops the pseudo-console owner when the child exits;
        # mirror that lifecycle before callers drain stdout after wait().
        self.close_output_source()
        self._close_kernel_handles()
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            result = self.poll()
            if result is not None:
                return result
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("restricted Windows process", timeout)
            time.sleep(0.01)

    def terminate(self) -> None:
        if self.poll() is not None:
            return
        _terminate_job(self._job_handle)
        self.wait()

    kill = terminate

    def resize(self, cols: int, rows: int) -> None:
        resize = getattr(self._resource_owner, "resize", None)
        if not callable(resize):
            raise WindowsSandboxProcessError("cannot resize a non-TTY sandbox process")
        resize(cols, rows)

    def close_output_source(self) -> None:
        """Drop ConPTY after process exit so output readers observe EOF."""

        owner, self._resource_owner = self._resource_owner, None
        close = getattr(owner, "close", None)
        if callable(close):
            close()

    def close(self) -> None:
        if self.poll() is None:
            self.terminate()
        for stream in (self.stdin, self.stdout, self.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        self.close_output_source()
        self._close_kernel_handles()

    def _close_kernel_handles(self) -> None:
        if self._closed_handles:
            return
        self._closed_handles = True
        _close_handle(self._process_handle)
        _close_handle(self._job_handle)

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


if os.name == "nt":
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL
    SIZE_T = ctypes.c_size_t
    LPVOID = ctypes.c_void_p

    STARTF_USESTDHANDLES = 0x00000100
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_SUSPENDED = 0x00000004
    PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
    PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
    HANDLE_FLAG_INHERIT = 0x00000001
    WAIT_OBJECT_0 = 0x00000000
    WAIT_TIMEOUT = 0x00000102
    WAIT_FAILED = 0xFFFFFFFF
    INFINITE = 0xFFFFFFFF
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", DWORD),
            ("lpSecurityDescriptor", LPVOID),
            ("bInheritHandle", BOOL),
        ]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", DWORD),
            ("dwY", DWORD),
            ("dwXSize", DWORD),
            ("dwYSize", DWORD),
            ("dwXCountChars", DWORD),
            ("dwYCountChars", DWORD),
            ("dwFillAttribute", DWORD),
            ("dwFlags", DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", HANDLE),
            ("hStdOutput", HANDLE),
            ("hStdError", HANDLE),
        ]

    class STARTUPINFOEXW(ctypes.Structure):
        _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", LPVOID)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", HANDLE),
            ("hThread", HANDLE),
            ("dwProcessId", DWORD),
            ("dwThreadId", DWORD),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", DWORD),
            ("MinimumWorkingSetSize", SIZE_T),
            ("MaximumWorkingSetSize", SIZE_T),
            ("ActiveProcessLimit", DWORD),
            ("Affinity", SIZE_T),
            ("PriorityClass", DWORD),
            ("SchedulingClass", DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", SIZE_T),
            ("JobMemoryLimit", SIZE_T),
            ("PeakProcessMemoryUsed", SIZE_T),
            ("PeakJobMemoryUsed", SIZE_T),
        ]

    _kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(HANDLE),
        ctypes.POINTER(HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES),
        DWORD,
    ]
    _kernel32.CreatePipe.restype = BOOL
    _kernel32.SetHandleInformation.argtypes = [HANDLE, DWORD, DWORD]
    _kernel32.SetHandleInformation.restype = BOOL
    _kernel32.InitializeProcThreadAttributeList.argtypes = [LPVOID, DWORD, DWORD, ctypes.POINTER(SIZE_T)]
    _kernel32.InitializeProcThreadAttributeList.restype = BOOL
    _kernel32.UpdateProcThreadAttribute.argtypes = [
        LPVOID,
        DWORD,
        SIZE_T,
        LPVOID,
        SIZE_T,
        LPVOID,
        ctypes.POINTER(SIZE_T),
    ]
    _kernel32.UpdateProcThreadAttribute.restype = BOOL
    _kernel32.DeleteProcThreadAttributeList.argtypes = [LPVOID]
    _kernel32.ReadFile.argtypes = [HANDLE, LPVOID, DWORD, ctypes.POINTER(DWORD), LPVOID]
    _kernel32.ReadFile.restype = BOOL
    _kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    _kernel32.WaitForSingleObject.restype = DWORD
    _kernel32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    _kernel32.GetExitCodeProcess.restype = BOOL
    _kernel32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = BOOL
    _kernel32.CloseHandle.argtypes = [HANDLE]
    _kernel32.CloseHandle.restype = BOOL
    _kernel32.CreateJobObjectW.argtypes = [LPVOID, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = HANDLE
    _kernel32.SetInformationJobObject.argtypes = [HANDLE, ctypes.c_int, LPVOID, DWORD]
    _kernel32.SetInformationJobObject.restype = BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
    _kernel32.AssignProcessToJobObject.restype = BOOL
    _kernel32.TerminateJobObject.argtypes = [HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = BOOL
    _kernel32.ResumeThread.argtypes = [HANDLE]
    _kernel32.ResumeThread.restype = DWORD
    _kernel32.CreatePseudoConsole.argtypes = [COORD, HANDLE, HANDLE, DWORD, ctypes.POINTER(HANDLE)]
    _kernel32.CreatePseudoConsole.restype = ctypes.c_long
    _kernel32.ResizePseudoConsole.argtypes = [HANDLE, COORD]
    _kernel32.ResizePseudoConsole.restype = ctypes.c_long
    _kernel32.ClosePseudoConsole.argtypes = [HANDLE]
    _kernel32.ClosePseudoConsole.restype = None

    _advapi32.CreateProcessAsUserW.argtypes = [
        HANDLE,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        LPVOID,
        LPVOID,
        BOOL,
        DWORD,
        LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    _advapi32.CreateProcessAsUserW.restype = BOOL


def make_env_block(env: Mapping[str, str]) -> ctypes.Array[ctypes.c_wchar]:
    items = sorted(((str(key), str(value)) for key, value in env.items()), key=lambda item: (item[0].upper(), item[0]))
    text = "\0".join(f"{key}={value}" for key, value in items) + "\0\0"
    return ctypes.create_unicode_buffer(text, len(text))


def create_process_as_user_capture(
    token: WinHandle | int,
    command: Sequence[str],
    cwd: str | Path,
    env: Mapping[str, str],
    timeout_ms: int | None = None,
    *,
    use_private_desktop: bool = False,
    is_cancelled: Callable[[], bool] | None = None,
) -> ProcessCaptureResult:
    _require_windows()
    if not command or not all(isinstance(arg, str) for arg in command):
        raise ValueError("command must contain at least one string argument")
    if timeout_ms is not None and (isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms < 0):
        raise ValueError("timeout_ms must be a non-negative integer or None")
    if is_cancelled is not None and not callable(is_cancelled):
        raise TypeError("is_cancelled must be callable or None")
    desktop = LaunchDesktop.prepare(use_private_desktop)
    stdin_read, stdin_write = _create_pipe()
    stdout_read, stdout_write = _create_pipe()
    stderr_read, stderr_write = _create_pipe()
    process_info = PROCESS_INFORMATION()
    job_handle = HANDLE()
    attribute_buffer: ctypes.Array[ctypes.c_char] | None = None
    attribute_value: object | None = None
    attribute_list: LPVOID | None = None
    desktop_buffer = ctypes.create_unicode_buffer(desktop.startup_name)
    try:
        child_handles = (stdin_read, stdout_write, stderr_write)
        for handle in child_handles:
            _set_inheritable(handle)
        attribute_buffer, attribute_list, attribute_value = _handle_attribute_list(child_handles)

        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.lpDesktop = ctypes.cast(desktop_buffer, wintypes.LPWSTR)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin_read
        startup.StartupInfo.hStdOutput = stdout_write
        startup.StartupInfo.hStdError = stderr_write
        startup.lpAttributeList = attribute_list

        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
        environment = make_env_block(env)
        flags = CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED
        if not _advapi32.CreateProcessAsUserW(
            _as_handle(token),
            None,
            command_line,
            None,
            None,
            True,
            flags,
            environment,
            str(Path(cwd)),
            ctypes.byref(startup.StartupInfo),
            ctypes.byref(process_info),
        ):
            error = ctypes.get_last_error()
            raise WindowsSandboxProcessError(
                error,
                f"CreateProcessAsUserW failed: {error}",
            )
        job_handle = _create_kill_on_close_job()
        if not _kernel32.AssignProcessToJobObject(job_handle, process_info.hProcess):
            error = ctypes.get_last_error()
            _kernel32.TerminateProcess(process_info.hProcess, 1)
            raise WindowsSandboxProcessError(error, f"AssignProcessToJobObject failed: {error}")
        if _kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            _kernel32.TerminateJobObject(job_handle, 1)
            raise WindowsSandboxProcessError(error, f"ResumeThread failed: {error}")
    except BaseException:
        for handle in (stdin_read, stdin_write, stdout_read, stdout_write, stderr_read, stderr_write):
            _close_handle(handle)
        desktop.close()
        _close_handle(job_handle)
        _close_handle(process_info.hThread)
        _close_handle(process_info.hProcess)
        raise
    finally:
        if attribute_list:
            _kernel32.DeleteProcThreadAttributeList(attribute_list)
        attribute_buffer = None
        attribute_value = None

    _close_handle(stdin_read)
    _close_handle(stdin_write)
    _close_handle(stdout_write)
    _close_handle(stderr_write)

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_thread = threading.Thread(target=_read_handle, args=(stdout_read, stdout_chunks), daemon=True)
    stderr_thread = threading.Thread(target=_read_handle, args=(stderr_read, stderr_chunks), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    timed_out = False
    cancelled = False
    try:
        started = time.monotonic()
        while True:
            if is_cancelled is not None and is_cancelled():
                cancelled = True
                _terminate_job(job_handle)
                _kernel32.WaitForSingleObject(process_info.hProcess, INFINITE)
                break
            if timeout_ms is None:
                wait_slice = 50 if is_cancelled is not None else INFINITE
            else:
                remaining = timeout_ms - int((time.monotonic() - started) * 1000)
                if remaining <= 0:
                    timed_out = True
                    _terminate_job(job_handle)
                    _kernel32.WaitForSingleObject(process_info.hProcess, INFINITE)
                    break
                wait_slice = min(remaining, 50) if is_cancelled is not None else remaining
            wait_result = _kernel32.WaitForSingleObject(process_info.hProcess, wait_slice)
            if wait_result == WAIT_OBJECT_0:
                break
            if wait_result == WAIT_FAILED:
                _raise_last_error("WaitForSingleObject failed")
            if wait_result != WAIT_TIMEOUT:
                raise WindowsSandboxProcessError(
                    f"WaitForSingleObject returned unexpected status 0x{wait_result:08x}"
                )

        exit_code = DWORD(1)
        if not _kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(exit_code)):
            _raise_last_error("GetExitCodeProcess failed")
    finally:
        _close_handle(process_info.hThread)
        _close_handle(process_info.hProcess)
        _close_handle(job_handle)
        stdout_thread.join()
        stderr_thread.join()
        desktop.close()

    return ProcessCaptureResult(
        exit_code=192 if timed_out else 1 if cancelled else int(exit_code.value),
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
        timed_out=timed_out,
        cancelled=cancelled,
    )


def create_process_as_user_popen(
    token: WinHandle | int,
    command: Sequence[str],
    cwd: str | Path,
    env: Mapping[str, str],
    *,
    stdin_open: bool,
    tty: bool = False,
    merge_stderr: bool = True,
    use_private_desktop: bool = False,
) -> NativeProcessPopen:
    """Spawn a restricted process suitable for unified-exec streaming."""

    _require_windows()
    if not command or not all(isinstance(arg, str) for arg in command):
        raise ValueError("command must contain at least one string argument")
    if tty:
        return create_process_as_user_conpty_popen(
            token,
            command,
            cwd,
            env,
            stdin_open=stdin_open,
            use_private_desktop=use_private_desktop,
        )
    desktop = LaunchDesktop.prepare(use_private_desktop)
    stdin_read, stdin_write = _create_pipe()
    stdout_read, stdout_write = _create_pipe()
    stderr_read, stderr_write = (HANDLE(), HANDLE()) if merge_stderr else _create_pipe()
    process_info = PROCESS_INFORMATION()
    job_handle = HANDLE()
    attribute_list: LPVOID | None = None
    attribute_buffer: ctypes.Array[ctypes.c_char] | None = None
    attribute_value: object | None = None
    desktop_buffer = ctypes.create_unicode_buffer(desktop.startup_name)
    try:
        child_handles = (stdin_read, stdout_write) if merge_stderr else (stdin_read, stdout_write, stderr_write)
        for handle in child_handles:
            _set_inheritable(handle)
        attribute_buffer, attribute_list, attribute_value = _handle_attribute_list(child_handles)
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.lpDesktop = ctypes.cast(desktop_buffer, wintypes.LPWSTR)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin_read
        startup.StartupInfo.hStdOutput = stdout_write
        startup.StartupInfo.hStdError = stdout_write if merge_stderr else stderr_write
        startup.lpAttributeList = attribute_list
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
        environment = make_env_block(env)
        flags = CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED
        if not _advapi32.CreateProcessAsUserW(
            _as_handle(token),
            None,
            command_line,
            None,
            None,
            True,
            flags,
            environment,
            str(Path(cwd)),
            ctypes.byref(startup.StartupInfo),
            ctypes.byref(process_info),
        ):
            error = ctypes.get_last_error()
            raise WindowsSandboxProcessError(error, f"CreateProcessAsUserW failed: {error}")
        job_handle = _create_kill_on_close_job()
        if not _kernel32.AssignProcessToJobObject(job_handle, process_info.hProcess):
            error = ctypes.get_last_error()
            _kernel32.TerminateProcess(process_info.hProcess, 1)
            raise WindowsSandboxProcessError(error, f"AssignProcessToJobObject failed: {error}")
        if _kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            _kernel32.TerminateJobObject(job_handle, 1)
            raise WindowsSandboxProcessError(error, f"ResumeThread failed: {error}")
        _close_handle(process_info.hThread)
        process_info.hThread = HANDLE()
        _close_handle(stdin_read)
        stdin_read = HANDLE()
        _close_handle(stdout_write)
        stdout_write = HANDLE()
        if not merge_stderr:
            _close_handle(stderr_write)
            stderr_write = HANDLE()
        if not stdin_open:
            _close_handle(stdin_write)
            stdin_write = HANDLE()
        stdin_file = _handle_file(stdin_write, "wb") if stdin_open else None
        stdin_write = HANDLE()
        stdout_file = _handle_file(stdout_read, "rb")
        stdout_read = HANDLE()
        stderr_file = _handle_file(stderr_read, "rb") if not merge_stderr else None
        stderr_read = HANDLE()
        result = NativeProcessPopen(
            process_info.hProcess,
            job_handle,
            stdin_file,
            stdout_file,
            stderr_file,
            desktop,
        )
        process_info.hProcess = HANDLE()
        job_handle = HANDLE()
        desktop = None
        return result
    except BaseException:
        if getattr(process_info.hProcess, "value", process_info.hProcess):
            _kernel32.TerminateProcess(process_info.hProcess, 1)
        raise
    finally:
        if attribute_list:
            _kernel32.DeleteProcThreadAttributeList(attribute_list)
        attribute_buffer = None
        attribute_value = None
        for handle in (stdin_read, stdin_write, stdout_read, stdout_write, stderr_read, stderr_write, process_info.hThread, process_info.hProcess, job_handle):
            _close_handle(handle)
        if desktop is not None:
            desktop.close()


def create_process_as_user_conpty_popen(
    token: WinHandle | int,
    command: Sequence[str],
    cwd: str | Path,
    env: Mapping[str, str],
    *,
    stdin_open: bool,
    use_private_desktop: bool = False,
    cols: int = 80,
    rows: int = 24,
) -> NativeProcessPopen:
    """Spawn a restricted process attached to a real Windows ConPTY."""

    _require_windows()
    if not command or not all(isinstance(arg, str) for arg in command):
        raise ValueError("command must contain at least one string argument")
    if cols <= 0 or rows <= 0 or cols > 32767 or rows > 32767:
        raise ValueError("ConPTY size must be within 1..32767")
    desktop = LaunchDesktop.prepare(use_private_desktop)
    input_read, input_write = _create_pipe()
    output_read, output_write = _create_pipe()
    pseudoconsole = HANDLE()
    process_info = PROCESS_INFORMATION()
    job_handle = HANDLE()
    attribute_list: LPVOID | None = None
    attribute_buffer: ctypes.Array[ctypes.c_char] | None = None
    attribute_value: object | None = None
    desktop_buffer = ctypes.create_unicode_buffer(desktop.startup_name)
    conpty: ConptyInstance | None = None
    try:
        result = _kernel32.CreatePseudoConsole(
            COORD(cols, rows), input_read, output_write, 0, ctypes.byref(pseudoconsole)
        )
        if result < 0:
            raise WindowsSandboxProcessError(result, f"CreatePseudoConsole failed: 0x{result & 0xffffffff:08x}")
        _close_handle(input_read)
        input_read = HANDLE()
        _close_handle(output_write)
        output_write = HANDLE()
        conpty = ConptyInstance(pseudoconsole, input_write, output_read, desktop)
        pseudoconsole = HANDLE()
        input_write = HANDLE()
        output_read = HANDLE()
        desktop = None

        attribute_buffer, attribute_list, attribute_value = _pseudoconsole_attribute_list(conpty.raw_handle)
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.lpDesktop = ctypes.cast(desktop_buffer, wintypes.LPWSTR)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = HANDLE(INVALID_HANDLE_VALUE)
        startup.StartupInfo.hStdOutput = HANDLE(INVALID_HANDLE_VALUE)
        startup.StartupInfo.hStdError = HANDLE(INVALID_HANDLE_VALUE)
        startup.lpAttributeList = attribute_list
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
        environment = make_env_block(env)
        flags = CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED
        if not _advapi32.CreateProcessAsUserW(
            _as_handle(token), None, command_line, None, None, False, flags,
            environment, str(Path(cwd)), ctypes.byref(startup.StartupInfo), ctypes.byref(process_info),
        ):
            error = ctypes.get_last_error()
            raise WindowsSandboxProcessError(error, f"CreateProcessAsUserW failed: {error}")
        job_handle = _create_kill_on_close_job()
        if not _kernel32.AssignProcessToJobObject(job_handle, process_info.hProcess):
            error = ctypes.get_last_error()
            _kernel32.TerminateProcess(process_info.hProcess, 1)
            raise WindowsSandboxProcessError(error, f"AssignProcessToJobObject failed: {error}")
        if _kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            _kernel32.TerminateJobObject(job_handle, 1)
            raise WindowsSandboxProcessError(error, f"ResumeThread failed: {error}")
        _close_handle(process_info.hThread)
        process_info.hThread = HANDLE()
        input_handle = conpty.take_input_write()
        if not stdin_open:
            _close_handle(input_handle)
            input_handle = None
        output_handle = conpty.take_output_read()
        stdin_file = (
            _ConptyInputWriter(_handle_file(input_handle, "wb"))
            if input_handle is not None
            else None
        )
        stdout_file = _handle_file(output_handle, "rb")
        result_process = NativeProcessPopen(
            process_info.hProcess, job_handle, stdin_file, stdout_file, None, conpty
        )
        process_info.hProcess = HANDLE()
        job_handle = HANDLE()
        conpty = None
        return result_process
    except BaseException:
        if getattr(process_info.hProcess, "value", process_info.hProcess):
            _kernel32.TerminateProcess(process_info.hProcess, 1)
        raise
    finally:
        if attribute_list:
            _kernel32.DeleteProcThreadAttributeList(attribute_list)
        attribute_buffer = None
        attribute_value = None
        for handle in (input_read, input_write, output_read, output_write, pseudoconsole, process_info.hThread, process_info.hProcess, job_handle):
            _close_handle(handle)
        if conpty is not None:
            conpty.close()
        if desktop is not None:
            desktop.close()


def _handle_file(handle: object, mode: str) -> io.BufferedReader | io.BufferedWriter:
    import msvcrt

    value = getattr(handle, "value", handle)
    flags = os.O_BINARY | (os.O_RDONLY if mode == "rb" else os.O_WRONLY)
    descriptor = msvcrt.open_osfhandle(int(value), flags)
    return os.fdopen(descriptor, mode, buffering=0)


def _create_kill_on_close_job() -> HANDLE:
    handle = _kernel32.CreateJobObjectW(None, None)
    if not getattr(handle, "value", handle):
        _raise_last_error("CreateJobObjectW failed")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        handle,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        error = ctypes.get_last_error()
        _close_handle(handle)
        raise WindowsSandboxProcessError(error, f"SetInformationJobObject failed: {error}")
    return handle


def _terminate_job(handle: HANDLE) -> None:
    if not _kernel32.TerminateJobObject(handle, 1):
        _raise_last_error("TerminateJobObject failed")


def _create_pipe() -> tuple[HANDLE, HANDLE]:
    read_handle = HANDLE()
    write_handle = HANDLE()
    if not _kernel32.CreatePipe(ctypes.byref(read_handle), ctypes.byref(write_handle), None, 0):
        _raise_last_error("CreatePipe failed")
    return read_handle, write_handle


def _set_inheritable(handle: HANDLE) -> None:
    if not _kernel32.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT):
        _raise_last_error("SetHandleInformation failed for stdio handle")


def _handle_attribute_list(
    handles: Sequence[HANDLE],
) -> tuple[ctypes.Array[ctypes.c_char], LPVOID, object]:
    size = SIZE_T()
    _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    if not size.value:
        _raise_last_error("InitializeProcThreadAttributeList size query failed")
    buffer = ctypes.create_string_buffer(size.value)
    attribute_list = ctypes.cast(buffer, LPVOID)
    if not _kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(size)):
        _raise_last_error("InitializeProcThreadAttributeList failed")
    handle_array = (HANDLE * len(handles))(*handles)
    if not _kernel32.UpdateProcThreadAttribute(
        attribute_list,
        0,
        PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
        ctypes.cast(handle_array, LPVOID),
        ctypes.sizeof(handle_array),
        None,
        None,
    ):
        _kernel32.DeleteProcThreadAttributeList(attribute_list)
        _raise_last_error("UpdateProcThreadAttribute(handle list) failed")
    return buffer, attribute_list, handle_array


def _pseudoconsole_attribute_list(raw_handle: int | None) -> tuple[ctypes.Array[ctypes.c_char], LPVOID, object]:
    if raw_handle is None:
        raise WindowsSandboxProcessError("invalid pseudo console handle")
    size = SIZE_T()
    _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    if not size.value:
        _raise_last_error("InitializeProcThreadAttributeList size query failed")
    buffer = ctypes.create_string_buffer(size.value)
    attribute_list = ctypes.cast(buffer, LPVOID)
    if not _kernel32.InitializeProcThreadAttributeList(attribute_list, 1, 0, ctypes.byref(size)):
        _raise_last_error("InitializeProcThreadAttributeList failed")
    value = HANDLE(raw_handle)
    if not _kernel32.UpdateProcThreadAttribute(
        attribute_list,
        0,
        PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
        ctypes.cast(value, LPVOID),
        ctypes.sizeof(HANDLE),
        None,
        None,
    ):
        _kernel32.DeleteProcThreadAttributeList(attribute_list)
        _raise_last_error("UpdateProcThreadAttribute(pseudoconsole) failed")
    return buffer, attribute_list, value


def _read_handle(handle: HANDLE, chunks: list[bytes]) -> None:
    try:
        buffer = ctypes.create_string_buffer(8192)
        while True:
            read = DWORD()
            ok = _kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(read), None)
            if not ok or not read.value:
                break
            chunks.append(buffer.raw[: read.value])
    finally:
        _close_handle(handle)


def _as_handle(token: WinHandle | int) -> HANDLE:
    value = token.value if isinstance(token, WinHandle) else token
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise WindowsSandboxProcessError("invalid Windows token handle")
    return HANDLE(value)


def _close_handle(handle: object) -> None:
    value = getattr(handle, "value", handle)
    if value:
        _kernel32.CloseHandle(HANDLE(value))


def _raise_last_error(message: str) -> None:
    error = ctypes.get_last_error()
    raise WindowsSandboxProcessError(error, f"{message}: {error}")


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsSandboxProcessError("Windows sandbox process APIs are only available on Windows")


__all__ = [
    "ProcessCaptureResult",
    "ConptyInstance",
    "NativeProcessPopen",
    "PipeSpawnHandles",
    "StderrMode",
    "StdinMode",
    "WindowsSandboxProcessError",
    "create_process_as_user_capture",
    "create_process_as_user_popen",
    "create_process_as_user_conpty_popen",
    "make_env_block",
]
