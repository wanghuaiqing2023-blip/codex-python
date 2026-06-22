from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

from pycodex.exec_server import (
    EXEC_METHOD,
    EXEC_READ_METHOD,
    EXEC_TERMINATE_METHOD,
    INITIALIZED_METHOD,
    INITIALIZE_METHOD,
    ConnectionProcessor,
    ExecServerRuntimePaths,
    SessionRegistry,
)


def _runtime_paths(tmp_path: Path) -> ExecServerRuntimePaths:
    return ExecServerRuntimePaths.new(tmp_path / "codex", None)


def _send_request(reader: asyncio.StreamReader, request_id: int, method: str, params: dict[str, object]) -> None:
    message = {"id": request_id, "method": method, "params": params}
    reader.feed_data(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")


def _send_notification(reader: asyncio.StreamReader, method: str, params: object | None = None) -> None:
    message = {"method": method, "params": params}
    reader.feed_data(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")


async def _read_response(writer: "MemoryWriter", expected_id: int) -> dict[str, object]:
    while True:
        lines = writer.json_lines()
        for line in lines:
            if line.get("id") == expected_id:
                return line
        await asyncio.wait_for(writer.updated.wait(), timeout=1)
        writer.updated.clear()


def test_transport_disconnect_detaches_session_during_in_flight_read(tmp_path: Path) -> None:
    # Rust crate/module/test:
    # codex-exec-server/src/server/processor.rs
    # transport_disconnect_detaches_session_during_in_flight_read.
    # Contract: a transport disconnect races in-flight request handling, causes
    # the first connection to detach, and allows a second connection to resume
    # the same session without waiting for the old long-poll read to finish.
    async def run() -> str:
        registry = SessionRegistry.new()
        processor = ConnectionProcessor(_runtime_paths(tmp_path), session_registry=registry)

        first_reader = asyncio.StreamReader()
        first_writer = MemoryWriter()
        first_task = asyncio.create_task(processor.run_stdio(first_reader, first_writer))

        _send_request(
            first_reader,
            1,
            INITIALIZE_METHOD,
            {"clientName": "exec-server-test"},
        )
        initialize_response = await _read_response(first_writer, 1)
        session_id = initialize_response["result"]["sessionId"]  # type: ignore[index]
        assert isinstance(session_id, str)
        _send_notification(first_reader, INITIALIZED_METHOD)

        process_id = "proc-long-poll"
        _send_request(
            first_reader,
            2,
            EXEC_METHOD,
            {
                "processId": process_id,
                "argv": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(1); print('late')",
                ],
                "cwd": str(tmp_path),
                "envPolicy": None,
                "env": os.environ.copy(),
                "tty": False,
                "pipeStdin": False,
                "arg0": None,
            },
        )
        await _read_response(first_writer, 2)

        _send_request(
            first_reader,
            3,
            EXEC_READ_METHOD,
            {
                "processId": process_id,
                "afterSeq": None,
                "maxBytes": None,
                "waitMs": 5_000,
            },
        )
        await asyncio.sleep(0.05)
        first_reader.feed_eof()
        await asyncio.wait_for(first_task, timeout=1)

        second_reader = asyncio.StreamReader()
        second_writer = MemoryWriter()
        second_task = asyncio.create_task(processor.run_stdio(second_reader, second_writer))
        _send_request(
            second_reader,
            1,
            INITIALIZE_METHOD,
            {
                "clientName": "exec-server-test",
                "resumeSessionId": session_id,
            },
        )
        second_initialize_response = await _read_response(second_writer, 1)
        assert second_initialize_response["result"]["sessionId"] == session_id  # type: ignore[index]

        _send_notification(second_reader, INITIALIZED_METHOD)
        _send_request(second_reader, 2, EXEC_TERMINATE_METHOD, {"processId": process_id})
        await _read_response(second_writer, 2)
        _send_request(
            second_reader,
            3,
            EXEC_READ_METHOD,
            {
                "processId": process_id,
                "afterSeq": None,
                "maxBytes": None,
                "waitMs": 1_000,
            },
        )
        await _read_response(second_writer, 3)
        await asyncio.sleep(0)
        second_reader.feed_eof()
        await asyncio.wait_for(second_task, timeout=1)
        return session_id

    assert asyncio.run(run())


class MemoryWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.updated = asyncio.Event()

    def write(self, data: bytes) -> None:
        self.data.extend(data)
        self.updated.set()

    async def drain(self) -> None:
        return None

    def json_lines(self) -> list[dict[str, object]]:
        lines = []
        for line in bytes(self.data).splitlines():
            lines.append(json.loads(line.decode("utf-8")))
        return lines
