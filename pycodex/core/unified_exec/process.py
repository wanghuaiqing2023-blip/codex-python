"""Subprocess lifecycle owned by ``core::unified_exec::process``."""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

from . import TRAILING_OUTPUT_GRACE_MS
from . import generate_chunk_id
from .errors import UnifiedExecError
from .head_tail_buffer import HeadTailBuffer


class UnifiedExecProcess:
    """Small subprocess-backed process used by the Python Core manager."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        process_id: int,
        hook_command: str,
        tty: bool,
        truncation_policy: Any,
    ) -> None:
        self.process = process
        self.process_id = process_id
        self.hook_command = hook_command
        self.tty = tty
        self.truncation_policy = truncation_policy
        self._buffer = HeadTailBuffer()
        self._condition = threading.Condition()
        self._output_closed = False
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        stream = self.process.stdout
        if stream is None:
            with self._condition:
                self._output_closed = True
                self._condition.notify_all()
            return
        try:
            while True:
                chunk = stream.read(1)
                if not chunk:
                    break
                with self._condition:
                    self._buffer.push_chunk(chunk)
                    self._condition.notify_all()
        finally:
            with self._condition:
                self._output_closed = True
                self._condition.notify_all()

    def has_exited(self) -> bool:
        return self.process.poll() is not None

    def exit_code(self) -> int | None:
        return self.process.poll()

    def terminate(self) -> None:
        if not self.has_exited():
            self.process.terminate()

    def close(self) -> None:
        if not self.has_exited():
            return
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

    def write(self, chars: str) -> None:
        if not self.tty:
            raise UnifiedExecError.stdin_closed()
        stdin = self.process.stdin
        if stdin is None or stdin.closed:
            raise UnifiedExecError.stdin_closed()
        if chars == "\x04":
            stdin.close()
            return
        try:
            stdin.write(chars.encode("utf-8"))
            stdin.flush()
        except BrokenPipeError as err:
            raise UnifiedExecError.stdin_closed() from err
        except OSError as err:
            raise UnifiedExecError.write_to_stdin() from err

    def snapshot(
        self,
        *,
        yield_time_ms: int,
        max_output_tokens: int | None,
        event_call_id: str,
    ) -> Any:
        start = time.monotonic()
        deadline = start + (yield_time_ms / 1000.0)
        post_exit_deadline: float | None = None
        exit_signal_received = self.has_exited()
        collected: list[bytes] = []
        with self._condition:
            while True:
                chunks = self._buffer.drain_chunks()
                if chunks:
                    collected.extend(chunks)
                    exit_signal_received = self.has_exited()
                    if self.tty and not exit_signal_received:
                        break
                    if time.monotonic() >= deadline:
                        break
                    continue

                exit_signal_received = exit_signal_received or self.has_exited()
                if exit_signal_received and self._output_closed:
                    break

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                if exit_signal_received:
                    now = time.monotonic()
                    if post_exit_deadline is None:
                        post_exit_deadline = now + min(
                            remaining,
                            TRAILING_OUTPUT_GRACE_MS / 1000.0,
                        )
                    wait_time = post_exit_deadline - now
                    if wait_time <= 0:
                        break
                    self._condition.wait(wait_time)
                    continue

                self._condition.wait(remaining)

            raw_output = b"".join(collected)
        wall_time_seconds = time.monotonic() - start
        exited = self.has_exited()
        exit_code = self.exit_code() if exited else None
        output_process_id = None if exited else self.process_id

        from pycodex.core.tools.context import ExecCommandToolOutput
        from pycodex.protocol.exec_output import bytes_to_string_smart
        from pycodex.utils.string import approx_token_count

        text = bytes_to_string_smart(raw_output)
        return ExecCommandToolOutput(
            event_call_id=event_call_id,
            chunk_id=generate_chunk_id(),
            wall_time_seconds=wall_time_seconds,
            raw_output=raw_output,
            truncation_policy=self.truncation_policy,
            max_output_tokens=max_output_tokens,
            process_id=output_process_id,
            exit_code=exit_code,
            original_token_count=approx_token_count(text),
            hook_command=self.hook_command,
        )


__all__ = ["UnifiedExecProcess"]
