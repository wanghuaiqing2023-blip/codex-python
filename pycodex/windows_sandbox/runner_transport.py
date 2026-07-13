"""Elevated sandbox command-runner transport for Windows.

This is the Python adapter for the fixed Rust modules
``elevated::runner_client``, ``runner_pipe``, and ``ipc_framed``.  The parent
never tries to spawn a process directly from a foreign logon token.  It starts
this project's runner under the sandbox account with ``CreateProcessWithLogonW``
and exchanges framed messages over a SID-restricted named pipe.
"""

from __future__ import annotations

import base64
import ctypes
import io
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any, Mapping, Sequence

from .identity import SandboxCreds
from .local_accounts import resolve_account_sid_string
from .process import WindowsSandboxProcessError, make_env_block


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    PIPE_ACCESS_DUPLEX = 0x00000003
    PIPE_ACCESS_INBOUND = 0x00000001
    PIPE_ACCESS_OUTBOUND = 0x00000002
    PIPE_TYPE_BYTE = 0x00000000
    PIPE_READMODE_BYTE = 0x00000000
    PIPE_WAIT = 0x00000000
    ERROR_PIPE_CONNECTED = 535
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    LOGON_WITH_PROFILE = 0x00000001
    CREATE_NO_WINDOW = 0x08000000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 0x102

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("nLength", DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", BOOL)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR), ("dwX", DWORD), ("dwY", DWORD),
            ("dwXSize", DWORD), ("dwYSize", DWORD), ("dwXCountChars", DWORD),
            ("dwYCountChars", DWORD), ("dwFillAttribute", DWORD), ("dwFlags", DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)), ("hStdInput", HANDLE),
            ("hStdOutput", HANDLE), ("hStdError", HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", DWORD), ("dwThreadId", DWORD)]

    _kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES)]
    _kernel32.CreateNamedPipeW.restype = HANDLE
    _kernel32.ConnectNamedPipe.argtypes = [HANDLE, ctypes.c_void_p]
    _kernel32.ConnectNamedPipe.restype = BOOL
    _kernel32.DisconnectNamedPipe.argtypes = [HANDLE]
    _kernel32.DisconnectNamedPipe.restype = BOOL
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, DWORD, DWORD, ctypes.c_void_p, DWORD, DWORD, HANDLE]
    _kernel32.CreateFileW.restype = HANDLE
    _kernel32.CloseHandle.argtypes = [HANDLE]
    _kernel32.CloseHandle.restype = BOOL
    _kernel32.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
    _kernel32.ReadFile.restype = BOOL
    _kernel32.WriteFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
    _kernel32.WriteFile.restype = BOOL
    _kernel32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    _kernel32.WaitForSingleObject.restype = DWORD
    _kernel32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    _kernel32.GetExitCodeProcess.restype = BOOL
    _kernel32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(DWORD)]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = BOOL
    _advapi32.CreateProcessWithLogonW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD,
        wintypes.LPCWSTR, wintypes.LPWSTR, DWORD, ctypes.c_void_p,
        wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    _advapi32.CreateProcessWithLogonW.restype = BOOL


class RunnerTransportError(WindowsSandboxProcessError):
    pass


class _PipeHandleClosedError(RunnerTransportError):
    """A failed connect already consumed the server handle."""


class _PipeStream:
    """Lock-free synchronous duplex named-pipe stream."""

    def __init__(self, handle: object) -> None:
        self._handle = handle
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            return b""
        size = 65536 if size is None or size < 0 else size
        if size == 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        read = DWORD()
        if not _kernel32.ReadFile(self._handle, buffer, size, ctypes.byref(read), None):
            error = ctypes.get_last_error()
            if error in {109, 232, 233}:
                return b""
            raise OSError(error, f"ReadFile runner pipe failed: {error}")
        return buffer.raw[: read.value]

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self.closed:
            raise BrokenPipeError("runner pipe is closed")
        source = bytes(data)
        offset = 0
        while offset < len(source):
            chunk = source[offset:]
            written = DWORD()
            buffer = ctypes.create_string_buffer(chunk, len(chunk))
            if not _kernel32.WriteFile(self._handle, buffer, len(chunk), ctypes.byref(written), None):
                error = ctypes.get_last_error()
                raise OSError(error, f"WriteFile runner pipe failed: {error}")
            if not written.value:
                raise BrokenPipeError("runner pipe wrote zero bytes")
            offset += written.value
        return len(source)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            value = getattr(self._handle, "value", self._handle)
            if value:
                _kernel32.CloseHandle(HANDLE(value))
            self._handle = HANDLE()


class _RunnerStdin:
    def __init__(self, owner: "RunnerBackedPopen") -> None:
        self._owner = owner
        self.closed = False

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self.closed:
            raise BrokenPipeError("runner stdin is closed")
        value = bytes(data)
        self._owner._send({"type": "stdin", "data": base64.b64encode(value).decode("ascii")})
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._owner._send({"type": "close_stdin"}, ignore_errors=True)


class RunnerBackedPopen:
    """Popen-compatible parent side of the elevated command runner."""

    def __init__(
        self,
        process_handle: object,
        reader: io.RawIOBase,
        writer: io.RawIOBase,
        stdin_open: bool,
        merge_stderr: bool,
        tty: bool,
    ) -> None:
        self._process_handle = process_handle
        self._reader_transport = reader
        self._writer_transport = writer
        self._send_lock = threading.Lock()
        self._done = threading.Event()
        self._tty = tty
        self.returncode: int | None = None
        read_fd, write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb", buffering=0)
        self._output = os.fdopen(write_fd, "wb", buffering=0)
        if merge_stderr:
            self.stderr = None
            self._error_output = None
        else:
            error_read_fd, error_write_fd = os.pipe()
            self.stderr = os.fdopen(error_read_fd, "rb", buffering=0)
            self._error_output = os.fdopen(error_write_fd, "wb", buffering=0)
        self.stdin = _RunnerStdin(self) if stdin_open else None
        self._reader = threading.Thread(target=self._read_loop, name="pycodex-sandbox-runner-reader", daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while True:
                message = read_frame(self._reader_transport)
                kind = message.get("type")
                if kind == "output":
                    destination = self._error_output if message.get("stream") == "stderr" else self._output
                    if destination is not None:
                        destination.write(base64.b64decode(str(message.get("data", ""))))
                        destination.flush()
                elif kind == "exit":
                    self.returncode = int(message.get("exit_code", 1))
                    return
                elif kind == "error":
                    self.returncode = 1
                    self._output.write(str(message.get("message", "runner error")).encode("utf-8", errors="replace"))
                    return
        except (EOFError, OSError, ValueError) as exc:
            if self.returncode is None:
                self.returncode = 1
                try:
                    self._output.write(f"sandbox runner transport failed: {exc}".encode("utf-8", errors="replace"))
                except OSError:
                    pass
        finally:
            try:
                self._output.close()
            except OSError:
                pass
            if self._error_output is not None:
                try:
                    self._error_output.close()
                except OSError:
                    pass
            self._done.set()

    def _send(self, message: Mapping[str, Any], *, ignore_errors: bool = False) -> None:
        try:
            with self._send_lock:
                write_frame(self._writer_transport, message)
        except (OSError, ValueError):
            if not ignore_errors:
                raise BrokenPipeError("sandbox runner transport is closed")

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if not self._done.wait(timeout):
            raise subprocess.TimeoutExpired("elevated sandbox runner", timeout)
        return 1 if self.returncode is None else self.returncode

    def terminate(self) -> None:
        if self.returncode is not None:
            return
        self._send({"type": "terminate"}, ignore_errors=True)
        if not self._done.wait(2):
            _kernel32.TerminateProcess(self._process_handle, 1)
            self.returncode = 1
            self._done.set()

    kill = terminate

    def resize(self, cols: int, rows: int) -> None:
        if not self._tty:
            raise RunnerTransportError("cannot resize a non-TTY sandbox process")
        if cols <= 0 or rows <= 0 or cols > 32767 or rows > 32767:
            raise ValueError("ConPTY size must be within 1..32767")
        self._send({"type": "resize", "cols": cols, "rows": rows})

    def close(self) -> None:
        if self.returncode is None:
            self.terminate()
        if self.stdin is not None and not self.stdin.closed:
            self.stdin.close()
        for stream in (self.stdout, self.stderr, self._reader_transport, self._writer_transport):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass
        if self._reader.is_alive() and self._reader is not threading.current_thread():
            self._reader.join(1)
        value = getattr(self._process_handle, "value", self._process_handle)
        if value:
            _kernel32.CloseHandle(HANDLE(value))
            self._process_handle = HANDLE()

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


def spawn_runner_popen(
    credentials: SandboxCreds,
    command: Sequence[str],
    cwd: str | Path,
    env: Mapping[str, str],
    *,
    permission_profile: Any,
    permission_profile_cwd: str | Path,
    codex_home: str | Path,
    cap_sids: Sequence[str],
    stdin_open: bool,
    tty: bool,
    merge_stderr: bool = True,
    use_private_desktop: bool,
) -> RunnerBackedPopen:
    if os.name != "nt":
        raise RunnerTransportError("elevated sandbox runner is only available on Windows")
    user_sid = resolve_account_sid_string(credentials.username)
    nonce = uuid.uuid4()
    pipe_in_name = rf"\\.\pipe\pycodex-sandbox-{nonce}-in"
    pipe_out_name = rf"\\.\pipe\pycodex-sandbox-{nonce}-out"
    pipe_in = HANDLE()
    pipe_out = HANDLE()
    descriptor_in = ctypes.c_void_p()
    descriptor_out = ctypes.c_void_p()
    reader = None
    writer = None
    process_info = PROCESS_INFORMATION()
    try:
        pipe_in, descriptor_in = _create_server_pipe(pipe_in_name, user_sid, PIPE_ACCESS_OUTBOUND)
        pipe_out, descriptor_out = _create_server_pipe(pipe_out_name, user_sid, PIPE_ACCESS_INBOUND)
        process_info = _launch_runner(credentials, pipe_in_name, pipe_out_name, cwd)
        try:
            _connect_pipe(pipe_in, process_info.hProcess)
        except _PipeHandleClosedError:
            pipe_in = HANDLE()
            raise
        try:
            _connect_pipe(pipe_out, process_info.hProcess)
        except _PipeHandleClosedError:
            pipe_out = HANDLE()
            raise
        writer = _handle_file(pipe_in)
        reader = _handle_file(pipe_out)
        pipe_in = HANDLE()
        pipe_out = HANDLE()
        request = {
            "type": "spawn",
            "command": [str(part) for part in command],
            "cwd": str(Path(cwd)),
            "env": {str(key): str(value) for key, value in env.items()},
            "permission_profile": permission_profile.to_mapping(),
            "permission_profile_cwd": str(Path(permission_profile_cwd)),
            "codex_home": str(Path(codex_home)),
            "cap_sids": list(cap_sids),
            "stdin_open": stdin_open,
            "tty": tty,
            "merge_stderr": merge_stderr,
            "use_private_desktop": use_private_desktop,
        }
        write_frame(writer, request)
        ready = read_frame(reader)
        if ready.get("type") != "ready":
            raise RunnerTransportError(str(ready.get("message", "runner did not become ready")))
        _kernel32.CloseHandle(process_info.hThread)
        process_info.hThread = HANDLE()
        result = RunnerBackedPopen(process_info.hProcess, reader, writer, stdin_open, merge_stderr, tty)
        reader = None
        writer = None
        process_info.hProcess = HANDLE()
        return result
    except BaseException:
        if getattr(process_info.hProcess, "value", process_info.hProcess):
            _kernel32.TerminateProcess(process_info.hProcess, 1)
        raise
    finally:
        for stream in (reader, writer):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for handle in (pipe_in, pipe_out, process_info.hThread, process_info.hProcess):
            value = getattr(handle, "value", handle)
            if value:
                _kernel32.CloseHandle(HANDLE(value))
        for descriptor in (descriptor_in, descriptor_out):
            if descriptor.value:
                _kernel32.LocalFree(descriptor)


def connect_runner_pipe(pipe_name: str, *, access: str = "duplex") -> io.RawIOBase:
    desired = {"read": GENERIC_READ, "write": GENERIC_WRITE, "duplex": GENERIC_READ | GENERIC_WRITE}.get(access)
    if desired is None:
        raise ValueError("runner pipe access must be read, write, or duplex")
    handle = _kernel32.CreateFileW(pipe_name, desired, 0, None, OPEN_EXISTING, 0, None)
    value = getattr(handle, "value", handle)
    if not value or value == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        raise RunnerTransportError(error, f"CreateFileW runner pipe failed: {error}")
    return _handle_file(handle)


def write_frame(stream: io.RawIOBase, message: Mapping[str, Any]) -> None:
    payload = json.dumps(dict(message), separators=(",", ":")).encode("utf-8")
    if len(payload) > 64 * 1024 * 1024:
        raise ValueError("runner frame is too large")
    stream.write(len(payload).to_bytes(4, "little") + payload)
    stream.flush()


def read_frame(stream: io.RawIOBase) -> dict[str, Any]:
    size = int.from_bytes(_read_exact(stream, 4), "little")
    if size < 2 or size > 64 * 1024 * 1024:
        raise ValueError(f"invalid runner frame size: {size}")
    value = json.loads(_read_exact(stream, size).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runner frame must contain an object")
    return value


def _read_exact(stream: io.RawIOBase, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("runner pipe closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _create_server_pipe(pipe_name: str, user_sid: str, access_mode: int) -> tuple[object, ctypes.c_void_p]:
    descriptor = ctypes.c_void_p()
    sddl = f"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;{user_sid})"
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    ):
        error = ctypes.get_last_error()
        raise RunnerTransportError(error, f"build runner pipe security descriptor failed: {error}")
    attrs = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
    handle = _kernel32.CreateNamedPipeW(
        pipe_name,
        access_mode,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
        1,
        65536,
        65536,
        15000,
        ctypes.byref(attrs),
    )
    value = getattr(handle, "value", handle)
    if not value or value == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        _kernel32.LocalFree(descriptor)
        raise RunnerTransportError(error, f"CreateNamedPipeW failed: {error}")
    return handle, descriptor


def _connect_pipe(pipe: object, process_handle: object) -> None:
    result: list[BaseException | None] = []

    def connect() -> None:
        if _kernel32.ConnectNamedPipe(pipe, None):
            result.append(None)
            return
        error = ctypes.get_last_error()
        result.append(None if error == ERROR_PIPE_CONNECTED else RunnerTransportError(error, f"ConnectNamedPipe failed: {error}"))

    thread = threading.Thread(target=connect, daemon=True)
    thread.start()
    thread.join(15)
    if thread.is_alive():
        _kernel32.TerminateProcess(process_handle, 1)
        _kernel32.CloseHandle(pipe)
        thread.join(1)
        raise _PipeHandleClosedError("timed out connecting sandbox runner pipe")
    if result and result[0] is not None:
        raise result[0]


def _launch_runner(credentials: SandboxCreds, pipe_in_name: str, pipe_out_name: str, cwd: str | Path) -> object:
    runner_python = _runner_python_executable()
    argv = [
        str(runner_python),
        "-m",
        "pycodex.windows_sandbox.command_runner",
        f"--pipe-in={pipe_in_name}",
        f"--pipe-out={pipe_out_name}",
    ]
    command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    environment = dict(os.environ)
    repo_root = str(Path(__file__).resolve().parents[2])
    environment["PYTHONPATH"] = repo_root + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    env_block = make_env_block(environment)
    startup = STARTUPINFOW()
    startup.cb = ctypes.sizeof(startup)
    process = PROCESS_INFORMATION()
    if not _advapi32.CreateProcessWithLogonW(
        credentials.username,
        ".",
        credentials.password,
        LOGON_WITH_PROFILE,
        str(runner_python),
        command_line,
        CREATE_NO_WINDOW | CREATE_UNICODE_ENVIRONMENT,
        env_block,
        str(Path(cwd)),
        ctypes.byref(startup),
        ctypes.byref(process),
    ):
        error = ctypes.get_last_error()
        raise RunnerTransportError(error, f"CreateProcessWithLogonW failed: {error}")
    return process


def _runner_python_executable() -> Path:
    configured = os.environ.get("PYCODEX_SANDBOX_RUNNER_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RunnerTransportError("no readable Python runtime is available for the sandbox command runner")


def _handle_file(handle: object) -> _PipeStream:
    return _PipeStream(handle)


__all__ = [
    "RunnerBackedPopen",
    "RunnerTransportError",
    "connect_runner_pipe",
    "read_frame",
    "spawn_runner_popen",
    "write_frame",
]
