"""Sandbox-account side of the elevated Windows command-runner transport."""

from __future__ import annotations

import base64
import os
import sys
import threading
from pathlib import Path

from pycodex.protocol import PermissionProfile

from .acl import allow_null_device
from .process import create_process_as_user_popen
from .resolved_permissions import token_mode_for_permission_profile, WindowsSandboxTokenMode
from .runner_transport import connect_runner_pipe, read_frame, write_frame
from .token import (
    LocalSid,
    create_readonly_token_with_caps_and_user_from,
    create_workspace_write_token_with_caps_and_user_from,
    get_current_token_for_restriction,
)


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
    reader = connect_runner_pipe(pipe_in_name, access="read")
    writer = connect_runner_pipe(pipe_out_name, access="write")
    _trace("runner:connected")
    send_lock = threading.Lock()

    def send(message: dict[str, object]) -> None:
        with send_lock:
            write_frame(writer, message)

    process = None
    sids: list[LocalSid] = []
    try:
        request = read_frame(reader)
        _trace("runner:request")
        if request.get("type") != "spawn":
            raise ValueError("expected spawn frame")
        command = tuple(str(part) for part in request.get("command", ()))
        if not command:
            raise ValueError("spawn command is empty")
        cwd = Path(str(request["cwd"]))
        env = request.get("env")
        if not isinstance(env, dict):
            raise ValueError("spawn env must be an object")
        environment = {str(key): str(value) for key, value in env.items()}
        profile = PermissionProfile.from_mapping(request["permission_profile"])
        profile_cwd = Path(str(request["permission_profile_cwd"]))
        mode = token_mode_for_permission_profile(profile, profile_cwd, environment)
        sids = [LocalSid(str(value)) for value in request.get("cap_sids", ())]
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
                    stdin_open=bool(request.get("stdin_open", False)),
                    tty=bool(request.get("tty", False)),
                    merge_stderr=bool(request.get("merge_stderr", True)),
                    use_private_desktop=bool(request.get("use_private_desktop", False)),
                )
        _trace("runner:spawned")
        send({"type": "ready"})
        _trace("runner:ready")

        def input_loop() -> None:
            while process is not None and process.poll() is None:
                try:
                    message = read_frame(reader)
                except (EOFError, OSError, ValueError):
                    process.terminate()
                    return
                kind = message.get("type")
                if kind == "stdin" and process.stdin is not None:
                    process.stdin.write(base64.b64decode(str(message.get("data", ""))))
                    process.stdin.flush()
                elif kind == "close_stdin" and process.stdin is not None:
                    process.stdin.close()
                elif kind == "resize":
                    resize = getattr(process, "resize", None)
                    if callable(resize):
                        resize(int(message.get("cols", 0)), int(message.get("rows", 0)))
                elif kind == "terminate":
                    process.terminate()
                    return

        input_thread = threading.Thread(target=input_loop, daemon=True)
        input_thread.start()
        assert process.stdout is not None
        def output_loop(stream, stream_name: str) -> None:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                send({"type": "output", "stream": stream_name, "data": base64.b64encode(chunk).decode("ascii")})

        output_threads = [threading.Thread(target=output_loop, args=(process.stdout, "stdout"), daemon=True)]
        if process.stderr is not None:
            output_threads.append(threading.Thread(target=output_loop, args=(process.stderr, "stderr"), daemon=True))
        for output_thread in output_threads:
            output_thread.start()
        _trace("runner:wait")
        exit_code = process.wait()
        _trace(f"runner:wait-done:{exit_code}")
        close_output_source = getattr(process, "close_output_source", None)
        if callable(close_output_source):
            close_output_source()
        for output_thread in output_threads:
            output_thread.join()
        _trace("runner:output-joined:true")
        send({"type": "exit", "exit_code": exit_code})
        _trace("runner:exit-sent")
        process.close()
        process = None
        return 0
    except BaseException as exc:
        _trace(f"runner:error:{type(exc).__name__}:{exc}")
        try:
            send({"type": "error", "message": str(exc)})
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


if __name__ == "__main__":
    raise SystemExit(main())
