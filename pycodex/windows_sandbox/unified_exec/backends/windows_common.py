"""Common parent-side runner process driver.

Rust owner: ``codex-windows-sandbox::unified_exec::backends::windows_common``.
"""

from __future__ import annotations

import io
import os
import subprocess
import threading

from ...elevated.ipc_framed import (
    ErrorPayload,
    ExitPayload,
    FramedMessage,
    IPC_PROTOCOL_VERSION,
    Message,
    OutputPayload,
    OutputStream,
    ResizePayload,
    StdinPayload,
    decode_bytes,
    encode_bytes,
    read_frame,
    write_frame,
)
from ...elevated.runner_client import RunnerTransport, RunnerTransportError


def normalize_windows_tty_input(
    data: bytes,
    previous_was_cr: bool,
) -> tuple[bytes, bool]:
    normalized = bytearray()
    for byte in data:
        if byte == 0x0A:
            if not previous_was_cr:
                normalized.append(0x0D)
            normalized.append(byte)
            previous_was_cr = False
        else:
            normalized.append(byte)
            previous_was_cr = byte == 0x0D
    return bytes(normalized), previous_was_cr


class _RunnerStdin:
    def __init__(self, owner: "RunnerBackedPopen") -> None:
        self._owner = owner
        self.closed = False
        self._previous_was_cr = False

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self.closed:
            raise BrokenPipeError("runner stdin is closed")
        value = bytes(data)
        payload = value
        if self._owner._tty:
            payload, self._previous_was_cr = normalize_windows_tty_input(
                value,
                self._previous_was_cr,
            )
        self._owner._send(
            FramedMessage(
                IPC_PROTOCOL_VERSION,
                Message.stdin(StdinPayload(encode_bytes(payload))),
            )
        )
        return len(value)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._owner._send(
                FramedMessage(IPC_PROTOCOL_VERSION, Message.close_stdin()),
                ignore_errors=True,
            )


class RunnerBackedPopen:
    """Popen-compatible driver backed by the elevated command runner."""

    def __init__(
        self,
        transport: RunnerTransport,
        stdin_open: bool,
        merge_stderr: bool,
        tty: bool,
    ) -> None:
        self._transport = transport
        self._writer_transport, self._reader_transport = transport.into_files()
        self._send_lock = threading.Lock()
        self._done = threading.Event()
        self._tty = tty
        self.returncode: int | None = None
        self.timed_out = False
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
        self._reader = start_runner_stdout_reader(self)

    def _read_loop(self) -> None:
        try:
            while True:
                frame = read_frame(self._reader_transport)
                if frame is None:
                    raise EOFError("runner pipe closed before exit")
                message = frame.message
                if message.type == "output":
                    payload = message.payload
                    if not isinstance(payload, OutputPayload):
                        raise ValueError("runner output payload has wrong type")
                    destination = (
                        self._error_output
                        if payload.stream is OutputStream.STDERR
                        else self._output
                    )
                    if destination is not None:
                        destination.write(decode_bytes(payload.data_b64))
                        destination.flush()
                elif message.type == "exit":
                    payload = message.payload
                    if not isinstance(payload, ExitPayload):
                        raise ValueError("runner exit payload has wrong type")
                    self.returncode = payload.exit_code
                    self.timed_out = payload.timed_out
                    return
                elif message.type == "error":
                    payload = message.payload
                    if not isinstance(payload, ErrorPayload):
                        raise ValueError("runner error payload has wrong type")
                    self.returncode = 1
                    destination = self._error_output or self._output
                    destination.write(
                        f"runner error: {payload.message}\n".encode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                    return
        except (EOFError, OSError, ValueError) as exc:
            if self.returncode is None:
                self.returncode = 1
                destination = self._error_output or self._output
                try:
                    destination.write(
                        f"runner error: {exc}\n".encode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                except OSError:
                    pass
        finally:
            for stream in (self._output, self._error_output):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            self._done.set()

    def _send(
        self,
        message: FramedMessage,
        *,
        ignore_errors: bool = False,
    ) -> None:
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
        self._send(
            FramedMessage(IPC_PROTOCOL_VERSION, Message.terminate()),
            ignore_errors=True,
        )
        if not self._done.wait(2):
            self._transport.close()
            self.returncode = 1
            self._done.set()

    kill = terminate

    def resize(self, cols: int, rows: int) -> None:
        if not self._tty:
            raise RunnerTransportError("cannot resize a non-TTY sandbox process")
        if cols <= 0 or rows <= 0 or cols > 32767 or rows > 32767:
            raise ValueError("ConPTY size must be within 1..32767")
        self._send(
            FramedMessage(
                IPC_PROTOCOL_VERSION,
                Message.resize(ResizePayload(rows=rows, cols=cols)),
            )
        )

    def close(self) -> None:
        if self.returncode is None:
            self.terminate()
        if self.stdin is not None and not self.stdin.closed:
            self.stdin.close()
        self._transport.close()
        for stream in (self.stdout, self.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass
        if self._reader.is_alive() and self._reader is not threading.current_thread():
            self._reader.join(1)

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


def finish_driver_spawn(
    process: RunnerBackedPopen,
    stdin_open: bool,
) -> RunnerBackedPopen:
    if not stdin_open and process.stdin is not None:
        process.stdin.close()
    return process


def start_runner_pipe_writer(
    stream: io.RawIOBase,
) -> callable:
    lock = threading.Lock()

    def send(message: FramedMessage) -> None:
        with lock:
            write_frame(stream, message)

    return send


def start_runner_stdin_writer(process: RunnerBackedPopen) -> _RunnerStdin | None:
    return process.stdin


def start_runner_stdout_reader(
    process: RunnerBackedPopen,
) -> threading.Thread:
    thread = threading.Thread(
        target=process._read_loop,
        name="pycodex-sandbox-runner-reader",
        daemon=True,
    )
    thread.start()
    return thread


def make_runner_resizer(process: RunnerBackedPopen):
    return process.resize


__all__ = [
    "RunnerBackedPopen",
    "finish_driver_spawn",
    "make_runner_resizer",
    "normalize_windows_tty_input",
    "start_runner_pipe_writer",
    "start_runner_stdin_writer",
    "start_runner_stdout_reader",
]
