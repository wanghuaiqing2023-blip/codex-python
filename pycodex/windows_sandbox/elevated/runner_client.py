"""Parent-side elevated runner startup and handshake.

Rust owner: ``codex-windows-sandbox::elevated::runner_client``.
"""

from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

from ..identity import SandboxCreds
from ..process import WindowsSandboxProcessError, make_env_block
from .ipc_framed import (
    ErrorPayload,
    FramedMessage,
    IPC_PROTOCOL_VERSION,
    Message,
    SpawnRequest,
    read_frame,
    write_frame,
)
from .runner_pipe import (
    PIPE_ACCESS_INBOUND,
    PIPE_ACCESS_OUTBOUND,
    close_handle,
    connect_pipe,
    create_named_pipe,
    find_runner_exe,
    pipe_pair,
    pipe_stream,
)


RUNNER_SPAWN_READY_TIMEOUT = 15.0
RUNNER_PIPE_CONNECT_TIMEOUT = 15.0
_RUNNER_SPAWN_READY_POLL_INTERVAL = 0.05


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD

    class _StartupInfo(ctypes.Structure):
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

    class _ProcessInformation(ctypes.Structure):
        _fields_ = [
            ("hProcess", HANDLE),
            ("hThread", HANDLE),
            ("dwProcessId", DWORD),
            ("dwThreadId", DWORD),
        ]

    _kernel32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.PeekNamedPipe.argtypes = [
        HANDLE,
        ctypes.c_void_p,
        DWORD,
        ctypes.POINTER(DWORD),
        ctypes.POINTER(DWORD),
        ctypes.POINTER(DWORD),
    ]
    _kernel32.PeekNamedPipe.restype = wintypes.BOOL
    _advapi32.CreateProcessWithLogonW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        DWORD,
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(_StartupInfo),
        ctypes.POINTER(_ProcessInformation),
    ]
    _advapi32.CreateProcessWithLogonW.restype = wintypes.BOOL
else:
    HANDLE = ctypes.c_void_p
    DWORD = ctypes.c_uint32


class RunnerTransportError(WindowsSandboxProcessError):
    pass


class RunnerTransport:
    def __init__(self, pipe_write: object, pipe_read: object) -> None:
        self.pipe_write = pipe_write
        self.pipe_read = pipe_read

    def send_spawn_request(self, request: SpawnRequest) -> None:
        write_frame(
            self.pipe_write,
            FramedMessage(
                IPC_PROTOCOL_VERSION,
                Message.spawn_request(request),
            ),
        )

    def read_spawn_ready(self) -> None:
        _wait_for_complete_frame(self.pipe_read, RUNNER_SPAWN_READY_TIMEOUT)
        frame = read_frame(self.pipe_read)
        if frame is None:
            raise RunnerTransportError("runner pipe closed before spawn_ready")
        if frame.message.type == "spawn_ready":
            return
        if isinstance(frame.message.payload, ErrorPayload):
            raise RunnerTransportError(
                f"runner error: {frame.message.payload.message}"
            )
        raise RunnerTransportError(
            f"expected spawn_ready from runner, got {frame.message.type}"
        )

    def into_files(self) -> tuple[object, object]:
        return self.pipe_write, self.pipe_read

    def close(self) -> None:
        for stream in (self.pipe_write, self.pipe_read):
            try:
                stream.close()
            except OSError:
                pass


def spawn_runner_transport(
    codex_home: str | Path,
    cwd: str | Path,
    sandbox_creds: SandboxCreds,
    log_dir: str | Path | None,
    spawn_request: SpawnRequest,
) -> RunnerTransport:
    if os.name != "nt":
        raise RunnerTransportError(
            "elevated sandbox runner is only available on Windows"
        )
    pipe_in_name, pipe_out_name = pipe_pair()
    pipe_in = HANDLE()
    pipe_out = HANDLE()
    process = _ProcessInformation()
    writer = None
    reader = None
    try:
        pipe_in = create_named_pipe(
            pipe_in_name,
            PIPE_ACCESS_OUTBOUND,
            sandbox_creds.username,
        )
        pipe_out = create_named_pipe(
            pipe_out_name,
            PIPE_ACCESS_INBOUND,
            sandbox_creds.username,
        )
        process = _launch_runner(
            codex_home,
            cwd,
            sandbox_creds,
            log_dir,
            pipe_in_name,
            pipe_out_name,
        )
        _connect_pipe_with_timeout(
            pipe_in,
            int(process.dwProcessId),
            "pipe-in",
        )
        _connect_pipe_with_timeout(
            pipe_out,
            int(process.dwProcessId),
            "pipe-out",
        )
        writer = pipe_stream(pipe_in)
        reader = pipe_stream(pipe_out)
        pipe_in = HANDLE()
        pipe_out = HANDLE()
        transport = RunnerTransport(writer, reader)
        writer = None
        reader = None
        try:
            transport.send_spawn_request(spawn_request)
            transport.read_spawn_ready()
        except BaseException:
            transport.close()
            raise
        return transport
    except BaseException:
        process_handle = getattr(process, "hProcess", HANDLE())
        if getattr(process_handle, "value", process_handle):
            _kernel32.TerminateProcess(process_handle, 1)
        raise
    finally:
        for stream in (writer, reader):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        close_handle(pipe_in)
        close_handle(pipe_out)
        close_handle(getattr(process, "hThread", HANDLE()))
        close_handle(getattr(process, "hProcess", HANDLE()))


def _connect_pipe_with_timeout(
    handle: object,
    expected_runner_pid: int,
    pipe_label: str,
) -> None:
    results: queue.Queue[BaseException | None] = queue.Queue(maxsize=1)

    def connect() -> None:
        try:
            connect_pipe(handle, expected_runner_pid)
        except BaseException as exc:
            results.put(exc)
        else:
            results.put(None)

    thread = threading.Thread(
        target=connect,
        name=f"codex-runner-connect-{pipe_label}",
        daemon=True,
    )
    thread.start()
    try:
        result = results.get(timeout=RUNNER_PIPE_CONNECT_TIMEOUT)
    except queue.Empty as exc:
        close_handle(handle)
        raise RunnerTransportError(
            f"timed out after {int(RUNNER_PIPE_CONNECT_TIMEOUT * 1000)}ms "
            f"connecting runner {pipe_label}"
        ) from exc
    if result is not None:
        raise result


def _launch_runner(
    codex_home: str | Path,
    cwd: str | Path,
    credentials: SandboxCreds,
    log_dir: str | Path | None,
    pipe_in_name: str,
    pipe_out_name: str,
) -> _ProcessInformation:
    runner_exe = find_runner_exe(codex_home, log_dir)
    argv = [
        str(runner_exe),
        "-m",
        "pycodex.windows_sandbox.bin.command_runner",
        f"--pipe-in={pipe_in_name}",
        f"--pipe-out={pipe_out_name}",
    ]
    command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    environment = dict(os.environ)
    repo_root = str(Path(__file__).resolve().parents[3])
    environment["PYTHONPATH"] = repo_root + (
        os.pathsep + environment["PYTHONPATH"]
        if environment.get("PYTHONPATH")
        else ""
    )
    env_block = make_env_block(environment)
    startup = _StartupInfo()
    startup.cb = ctypes.sizeof(startup)
    process = _ProcessInformation()
    if not _advapi32.CreateProcessWithLogonW(
        credentials.username,
        ".",
        credentials.password,
        0x00000001,
        str(runner_exe),
        command_line,
        0x08000000 | 0x00000400,
        env_block,
        str(Path(cwd)),
        ctypes.byref(startup),
        ctypes.byref(process),
    ):
        error = ctypes.get_last_error()
        raise RunnerTransportError(
            error,
            f"CreateProcessWithLogonW failed: {error}",
        )
    return process


def _wait_for_complete_frame(stream: object, timeout: float) -> None:
    handle = getattr(stream, "handle", None)
    if handle is None or os.name != "nt":
        return
    deadline = time.monotonic() + timeout
    length_buffer = (ctypes.c_ubyte * 4)()
    while True:
        bytes_read = DWORD()
        total_available = DWORD()
        if not _kernel32.PeekNamedPipe(
            handle,
            length_buffer,
            4,
            ctypes.byref(bytes_read),
            ctypes.byref(total_available),
            None,
        ):
            error = ctypes.get_last_error()
            raise RunnerTransportError(
                error,
                f"PeekNamedPipe failed while waiting for spawn_ready: {error}",
            )
        if bytes_read.value == 4:
            frame_len = int.from_bytes(bytes(length_buffer), "little")
            if total_available.value >= frame_len + 4:
                return
        if time.monotonic() >= deadline:
            raise RunnerTransportError(
                f"timed out after {int(timeout * 1000)}ms waiting for "
                "runner spawn_ready"
            )
        time.sleep(_RUNNER_SPAWN_READY_POLL_INTERVAL)


__all__ = [
    "RunnerTransport",
    "RunnerTransportError",
    "spawn_runner_transport",
]
