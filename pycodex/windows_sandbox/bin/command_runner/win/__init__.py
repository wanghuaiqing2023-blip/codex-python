"""Sandbox-account side of the elevated Windows command-runner transport."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes
from pathlib import Path

from ....acl import allow_null_device
from ....elevated.ipc_framed import (
    ErrorPayload,
    ExitPayload,
    FramedMessage,
    IPC_PROTOCOL_VERSION,
    Message,
    OutputPayload,
    OutputStream,
    ResizePayload,
    SpawnReady,
    SpawnRequest,
    StdinPayload,
    decode_bytes,
    encode_bytes,
    read_frame,
    write_frame,
)
from ....logging import log_note
from ....hide_users import hide_current_user_profile_dir
from ....process import create_process_as_user_popen
from ....resolved_permissions import token_mode_for_permission_profile, WindowsSandboxTokenMode
from ....elevated.runner_pipe import pipe_stream
from ....token import (
    LocalSid,
    create_readonly_token_with_caps_and_user_from,
    create_workspace_write_token_with_caps_and_user_from,
    get_current_token_for_restriction,
)
from .cwd_junction import create_cwd_junction


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.OpenMutexW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    _kernel32.OpenMutexW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


READ_ACL_MUTEX_NAME = r"Local\CodexSandboxReadAcl"


def _open_pipe(pipe_name: str, access: str):
    desired = {
        "read": 0x80000000,
        "write": 0x40000000,
    }.get(access)
    if desired is None:
        raise ValueError("runner pipe access must be read or write")
    handle = _kernel32.CreateFileW(pipe_name, desired, 0, None, 3, 0, None)
    value = getattr(handle, "value", handle)
    if not value or value == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        raise OSError(error, f"CreateFileW failed for pipe {pipe_name}: {error}")
    return pipe_stream(handle)


def read_acl_mutex_exists() -> bool:
    handle = _kernel32.OpenMutexW(0x001F0001, False, READ_ACL_MUTEX_NAME)
    value = getattr(handle, "value", handle)
    if value:
        _kernel32.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error == 2:
        return False
    raise OSError(error, f"OpenMutexW failed: {error}")


def effective_cwd(
    requested_cwd: str | Path,
    log_dir: str | Path | None,
) -> Path:
    requested = Path(requested_cwd)
    try:
        use_junction = read_acl_mutex_exists()
    except OSError as exc:
        log_note(
            "junction: failed to probe ACL mutex state: "
            f"{exc}; defaulting to junction cwd",
            Path(log_dir) if log_dir is not None else None,
        )
        use_junction = True
    if not use_junction:
        return requested
    junction = create_cwd_junction(
        requested,
        Path(log_dir) if log_dir is not None else None,
    )
    return requested if junction is None else junction


def _trace(message: str) -> None:
    path = os.environ.get("PYCODEX_SANDBOX_RUNNER_TRACE")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(message + "\n")
    except OSError:
        pass


def run(pipe_in_name: str, pipe_out_name: str) -> int:
    _trace("runner:start")
    reader = _open_pipe(pipe_in_name, access="read")
    writer = _open_pipe(pipe_out_name, access="write")
    _trace("runner:connected")
    send_lock = threading.Lock()

    def send(message: FramedMessage) -> None:
        with send_lock:
            write_frame(writer, message)

    process = None
    sids: list[LocalSid] = []
    try:
        frame = read_frame(reader)
        _trace("runner:request")
        if frame is None:
            raise ValueError("runner: pipe closed before spawn_request")
        if frame.version != IPC_PROTOCOL_VERSION:
            raise ValueError(f"runner: unsupported protocol version {frame.version}")
        if frame.message.type != "spawn_request" or not isinstance(
            frame.message.payload,
            SpawnRequest,
        ):
            raise ValueError(f"runner: expected spawn_request, got {frame.message.type}")
        request = frame.message.payload
        hide_current_user_profile_dir(request.codex_home)
        command = request.command
        if not command:
            raise ValueError("spawn command is empty")
        cwd = effective_cwd(request.cwd, request.codex_home)
        environment = dict(request.env)
        profile = request.permission_profile
        profile_cwd = request.permission_profile_cwd
        mode = token_mode_for_permission_profile(profile, profile_cwd, environment)
        sids = [LocalSid(value) for value in request.cap_sids]
        if not sids:
            raise ValueError("spawn requires capability SIDs")
        for sid in sids:
            allow_null_device(sid)
        with get_current_token_for_restriction() as base:
            if mode is WindowsSandboxTokenMode.WRITABLE_ROOTS_CAPABILITY:
                restricted = create_workspace_write_token_with_caps_and_user_from(base, sids)
            else:
                restricted = create_readonly_token_with_caps_and_user_from(base, sids)
            with restricted:
                process = create_process_as_user_popen(
                    restricted,
                    command,
                    cwd,
                    environment,
                    stdin_open=request.stdin_open,
                    tty=request.tty,
                    merge_stderr=False,
                    use_private_desktop=request.use_private_desktop,
                )
        _trace("runner:spawned")
        send(
            FramedMessage(
                IPC_PROTOCOL_VERSION,
                Message.spawn_ready(SpawnReady(process.pid)),
            )
        )
        _trace("runner:ready")

        def input_loop() -> None:
            while process is not None and process.poll() is None:
                try:
                    frame = read_frame(reader)
                except (EOFError, OSError, ValueError):
                    process.terminate()
                    return
                if frame is None:
                    return
                message = frame.message
                kind = message.type
                if (
                    kind == "stdin"
                    and isinstance(message.payload, StdinPayload)
                    and process.stdin is not None
                ):
                    process.stdin.write(decode_bytes(message.payload.data_b64))
                    process.stdin.flush()
                elif kind == "close_stdin" and process.stdin is not None:
                    process.stdin.close()
                elif kind == "resize" and isinstance(message.payload, ResizePayload):
                    resize = getattr(process, "resize", None)
                    if callable(resize):
                        resize(message.payload.cols, message.payload.rows)
                elif kind == "terminate":
                    process.terminate()
                    return

        input_thread = threading.Thread(target=input_loop, daemon=True)
        input_thread.start()
        assert process.stdout is not None
        def output_loop(stream, stream_name: OutputStream) -> None:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                send(
                    FramedMessage(
                        IPC_PROTOCOL_VERSION,
                        Message.output(OutputPayload(encode_bytes(chunk), stream_name)),
                    )
                )

        output_threads = [
            threading.Thread(
                target=output_loop,
                args=(process.stdout, OutputStream.STDOUT),
                daemon=True,
            )
        ]
        if process.stderr is not None:
            output_threads.append(
                threading.Thread(
                    target=output_loop,
                    args=(process.stderr, OutputStream.STDERR),
                    daemon=True,
                )
            )
        for output_thread in output_threads:
            output_thread.start()
        _trace("runner:wait")
        timed_out = False
        try:
            timeout = None if request.timeout_ms is None else request.timeout_ms / 1000
            exit_code = process.wait(timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            exit_code = 192
        _trace(f"runner:wait-done:{exit_code}")
        close_output_source = getattr(process, "close_output_source", None)
        if callable(close_output_source):
            close_output_source()
        for output_thread in output_threads:
            output_thread.join()
        _trace("runner:output-joined:true")
        send(
            FramedMessage(
                IPC_PROTOCOL_VERSION,
                Message.exit(ExitPayload(exit_code, timed_out)),
            )
        )
        _trace("runner:exit-sent")
        process.close()
        process = None
        return 0
    except BaseException as exc:
        _trace(f"runner:error:{type(exc).__name__}:{exc}")
        try:
            send(
                FramedMessage(
                    IPC_PROTOCOL_VERSION,
                    Message.error(ErrorPayload(str(exc), "spawn_failed")),
                )
            )
        except BaseException:
            pass
        if process is not None:
            try:
                process.terminate()
            except BaseException:
                pass
        return 1
    finally:
        for sid in sids:
            sid.close()
        reader.close()
        writer.close()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        return 2
    values = {arg.split("=", 1)[0]: arg.split("=", 1)[1] for arg in args if "=" in arg}
    if "--pipe-in" not in values or "--pipe-out" not in values:
        return 2
    return run(values["--pipe-in"], values["--pipe-out"])


__all__ = [
    "effective_cwd",
    "main",
    "read_acl_mutex_exists",
    "run",
]
