"""Executor-backed MCP stdio transport.

This mirrors ``codex-rmcp-client::executor_process_transport``: it translates
newline-delimited JSON-RPC bytes only. Process placement remains owned by
``stdio_server_launcher`` and MCP lifecycle remains owned by ``rmcp_client``.
"""

from __future__ import annotations

import itertools
import json
import logging
from typing import Any

from pycodex.exec_server.process import ExecProcess
from pycodex.exec_server.process_id import ProcessId
from pycodex.exec_server.protocol import ExecOutputStream, ProcessOutputChunk, WriteStatus

_LOG = logging.getLogger(__name__)
_PROCESS_COUNTER = itertools.count(1)


class ExecutorProcessTransport:
    def __init__(self, process: ExecProcess, program_name: str) -> None:
        self._process = process
        self._events = process.subscribe_events()
        self._program_name = str(program_name)
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._closed = False
        self._terminated = False
        self._last_seq = 0

    @staticmethod
    def next_process_id() -> ProcessId:
        return ProcessId.new(f"mcp-stdio-{next(_PROCESS_COUNTER)}")

    async def send(self, item: Any) -> None:
        payload = json.dumps(item, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        response = await self._process.write(payload + b"\n")
        if response.status is WriteStatus.ACCEPTED:
            return
        if response.status is WriteStatus.UNKNOWN_PROCESS:
            raise BrokenPipeError("unknown process")
        if response.status is WriteStatus.STDIN_CLOSED:
            raise BrokenPipeError("stdin closed")
        if response.status is WriteStatus.STARTING:
            raise BlockingIOError("process is starting")
        raise OSError(f"unexpected executor write status: {response.status}")

    async def receive(self) -> Any | None:
        while True:
            message = self._take_stdout_message(allow_partial=self._closed)
            if message is not None:
                return message
            if self._closed:
                self._flush_stderr()
                return None

            event = await self._events.recv()
            if event.kind == "output" and event.chunk is not None:
                self._push_process_output_if_new(event.chunk)
            elif event.kind == "exited":
                self._note_seq(event.seq_value)
            elif event.kind == "closed":
                self._note_seq(event.seq_value)
                self._closed = True
            elif event.kind == "failed":
                _LOG.warning(
                    "Remote MCP server process failed (%s): %s",
                    self._program_name,
                    event.message,
                )
                self._closed = True

    async def close(self) -> None:
        if not self._terminated:
            await self._process.terminate()
            self._terminated = True
        self._closed = True

    def _note_seq(self, seq: int | None) -> None:
        if seq is not None:
            self._last_seq = max(self._last_seq, int(seq))

    def _push_process_output_if_new(self, chunk: ProcessOutputChunk) -> None:
        if chunk.seq <= self._last_seq:
            return
        self._last_seq = chunk.seq
        data = chunk.chunk.into_inner()
        if chunk.stream in {ExecOutputStream.STDOUT, ExecOutputStream.PTY}:
            self._stdout.extend(data)
        else:
            self._push_stderr(data)

    def _take_stdout_message(self, *, allow_partial: bool) -> Any | None:
        while True:
            try:
                index = self._stdout.index(b"\n")
            except ValueError:
                if not allow_partial or not self._stdout:
                    return None
                line = bytes(self._stdout)
                self._stdout.clear()
            else:
                line = bytes(self._stdout[:index])
                del self._stdout[: index + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            try:
                return json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                _LOG.debug(
                    "Failed to parse remote MCP server message (%s): %s",
                    self._program_name,
                    exc,
                )

    def _push_stderr(self, data: bytes) -> None:
        self._stderr.extend(data)
        while b"\n" in self._stderr:
            index = self._stderr.index(b"\n")
            line = bytes(self._stderr[:index]).rstrip(b"\r")
            del self._stderr[: index + 1]
            _LOG.info(
                "MCP server stderr (%s): %s",
                self._program_name,
                line.decode("utf-8", errors="replace"),
            )

    def _flush_stderr(self) -> None:
        if not self._stderr:
            return
        line = bytes(self._stderr)
        self._stderr.clear()
        _LOG.info(
            "MCP server stderr (%s): %s",
            self._program_name,
            line.decode("utf-8", errors="replace"),
        )


__all__ = ["ExecutorProcessTransport"]
